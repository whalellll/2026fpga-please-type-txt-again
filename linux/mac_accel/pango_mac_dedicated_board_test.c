#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include "pango_mac_uapi.h"
#define BYTES 1048576u
#define MODEL_BYTES 0x91000u
struct client { int fd; unsigned char *data; uint32_t tag[2]; };
static void check(int ok,const char *why) {
    if(!ok){fprintf(stderr,"DEDICATED_BOARD_FAIL reason=%s errno=%d\n",why,errno);exit(1);}
}
static struct client open_client(void) {
    struct client c;struct pango_mac_info info;
    memset(&c,0,sizeof(c));c.fd=open("/dev/pango-mac0",O_RDWR|O_CLOEXEC);
    check(c.fd>=0,"open");check(!ioctl(c.fd,PANGO_MAC_IOC_GET_INFO,&info),"info");
    check(info.device_id==PANGO_MAC_PIKAFISH_ID && info.device_version==PANGO_MAC_PIKAFISH_VERSION,"dedicated-id");
    check((info.features&PANGO_MAC_FEATURE_PIKAFISH_DEDICATED) && !(info.features&PANGO_MAC_FEATURE_DENSE),"capabilities");
    c.data=mmap(NULL,BYTES,PROT_READ|PROT_WRITE,MAP_SHARED,c.fd,0);
    check(c.data!=MAP_FAILED,"mmap");return c;
}
static void model(struct client *c,int32_t bias) {
    struct pango_mac_model m;unsigned bucket;
    memset(c->data,0,BYTES);
    for(bucket=0;bucket<16;bucket++)memcpy(c->data+0x1000+bucket*0x9000+0x8a80,&bias,4);
    memset(&m,0,sizeof(m));m.abi_version=PANGO_MAC_MODEL_ABI_VERSION;m.bytes=MODEL_BYTES;
    check(!ioctl(c->fd,PANGO_MAC_IOC_REGISTER_MODEL,&m),"register-model");
}
static void upload(struct client *c) {
    unsigned v;for(v=0;v<2;v++) {
        struct pango_mac_nnue_upload u;
        memset(&u,0,sizeof(u));u.abi_version=PANGO_MAC_NNUE_ABI_VERSION;u.view=v;u.source_offset=0xf0000;
        check(!ioctl(c->fd,PANGO_MAC_IOC_NNUE_UPLOAD,&u) && u.tag,"upload");c->tag[v]=u.tag;
    }
}
static struct pango_mac_nnue_cache_stats stats(struct client *c) {
    struct pango_mac_nnue_cache_stats s;memset(&s,0,sizeof(s));
    check(!ioctl(c->fd,PANGO_MAC_IOC_NNUE_CACHE_STATS,&s) && s.abi_version==1,"stats");return s;
}
static void run(struct client *c,int expected,unsigned reads,unsigned hits,const char *name) {
    struct pango_mac_nnue_job j;struct pango_mac_nnue_cache_stats a=stats(c),b;
    memset(&j,0,sizeof(j));j.abi_version=PANGO_MAC_NNUE_ABI_VERSION;
    j.tag0=c->tag[0];j.tag1=c->tag[1];j.timeout_us=1000000;
    check(!ioctl(c->fd,PANGO_MAC_IOC_RUN_NNUE,&j),"run");
    check((int32_t)j.score==expected && j.jobs==6 && j.cycles,"integer-result");b=stats(c);
    check(b.runs-a.runs==1 && b.read_words-a.read_words==reads && b.hits-a.hits==hits && b.errors==a.errors,"cache-counts");
    printf("DEDICATED_CACHE_CASE_PASS name=%s score=%d cycles=%u read_words=%u hit=%u restores=%u\n",name,(int32_t)j.score,j.cycles,reads,hits,b.model_restores-a.model_restores);
}
int main(void) {
    struct client a=open_client(),b=open_client();struct pango_mac_nnue_job j;struct pango_mac_job dense;
    model(&a,128);upload(&a);run(&a,75,8801,0,"cold-A");run(&a,75,0,1,"warm-A");
    model(&b,-256);upload(&b);run(&b,-150,8801,0,"switch-B-same-address");
    memset(&j,0,sizeof(j));j.abi_version=PANGO_MAC_NNUE_ABI_VERSION;j.tag0=a.tag[0];j.tag1=a.tag[1];j.timeout_us=1000000;
    errno=0;check(ioctl(a.fd,PANGO_MAC_IOC_RUN_NNUE,&j)<0 && errno==ESTALE,"stale-other-context");
    upload(&a);run(&a,75,8801,0,"restore-A");
    model(&a,384);upload(&a);run(&a,225,8801,0,"replace-A-same-address");run(&a,225,0,1,"warm-replaced-A");
    memset(&dense,0,sizeof(dense));dense.abi_version=PANGO_MAC_ABI_VERSION;dense.pixels=1;dense.cin=4;dense.cout=1;
    errno=0;check(ioctl(a.fd,PANGO_MAC_IOC_RUN,&dense)<0 && errno==EOPNOTSUPP,"removed-dense-rejected");
    munmap(a.data,BYTES);munmap(b.data,BYTES);close(a.fd);close(b.fd);
    puts("DEDICATED_MODEL_CONTEXT_CACHE_AND_REJECTION_BOARD_PASS");return 0;
}
