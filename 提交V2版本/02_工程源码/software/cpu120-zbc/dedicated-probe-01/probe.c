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
static int basic_tests(void) {
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

static const int16_t initial_views[2048]={4,228,11,60,-52,-129,135,-67,13,-126,-137,172,61,2,196,-147,110,-56,15,-8,164,129,45,20,128,-124,-45,-28,-37,50,74,-73,29,22,21,-26,-135,-96,298,77,-53,186,-44,114,-10,-62,54,429,-248,294,-438,12,-30,264,-245,-22,-125,-188,-97,-9,-33,154,15,-71,-143,-85,57,7,27,2,124,-28,-59,-2,42,444,98,29,-109,110,114,82,-9,148,88,96,7,13,-111,-652,-250,97,-83,-141,376,177,-251,-571,-184,-97,96,125,-223,-50,77,38,-85,-5,-263,-15,163,-129,-46,192,-122,-7,32,-59,26,650,-121,-21,-3,-154,-61,20,84,17,2,227,-85,223,254,33,-7,-6,-790,-1333,-155,-613,66,-121,-149,-59,424,24,64,22,-119,-90,31,-169,-26,113,-12,-126,120,-13,-23,106,-59,-75,-5,-210,-49,-79,3,-19,114,-795,-206,171,-106,71,43,96,-104,19,-47,4,-42,-38,-28,231,-395,22,220,85,-149,-60,-84,201,89,-8,130,99,-18,-18,272,179,45,-32,85,11,-283,-6,-72,-198,76,-20,16,89,-68,-54,-12,-189,47,-638,-265,208,-162,-10,-25,83,59,26,51,152,63,-23,14,-410,-41,-127,-370,-72,-244,-411,106,-71,221,-107,255,-98,106,92,23,-19,-48,61,-20,118,130,-106,172,5,-220,126,-221,-67,-79,-53,-11,-42,-108,-110,-20,-100,-73,288,-11,100,316,-427,-342,-124,238,6,74,127,31,-173,197,-150,0,26,-62,-47,50,-81,11,-213,-68,-110,-92,108,-16,-102,263,-8,220,-83,-157,-139,-134,-218,197,-14,68,120,32,-1,-18,-25,-230,-72,-77,270,72,-73,-74,-123,-54,6,-5,53,-37,75,-98,-58,-93,-54,107,-13,-37,-22,79,-13,-34,-80,-45,78,-125,-98,-146,126,-439,-45,204,-131,-178,134,298,213,-55,-32,-48,-16,-47,59,-32,-18,-155,-38,1,-60,72,114,-47,33,-27,-52,-371,-56,138,-194,388,-98,-19,43,64,52,103,54,37,-2,35,134,-4,-28,-41,107,20,103,-137,198,127,162,183,76,155,-5,-32,-86,26,-514,-21,-97,39,56,71,-33,-191,-30,-238,-61,165,-58,-18,-24,-509,7,-50,-7,49,8,12,-164,-20,-125,-284,-1090,77,-49,-37,-20,-202,-75,-23,-50,1,-40,35,105,13,216,-16,-86,-19,-89,-69,24,-158,-383,-53,-237,-45,30,214,261,7,-4,-232,-38,144,-32,-74,300,-46,69,26,279,116,46,71,-98,41,49,-48,-14,-198,-11,195,9,-158,-560,-312,-284,100,-225,235,-314,132,5,-289,127,-160,21,-53,1,-121,83,50,44,174,260,-335,-14,-25,-42,165,-24,28,7,196,27,-139,-126,-108,-195,-109,158,-61,-60,185,251,16,52,-79,-85,74,83,-33,203,15,215,-104,-102,-89,-16,-11,14,52,88,149,30,46,-61,-171,-212,-152,180,-59,-109,133,3,395,65,11,37,-102,-312,-82,253,196,-22,-20,48,50,28,-81,89,-20,101,8,-178,-54,182,-61,42,61,-155,-14,159,64,356,39,28,87,143,-76,43,13,-3,27,54,-34,-140,66,-24,-182,-183,-546,-398,195,-54,-109,-125,-90,-29,-214,-374,-260,-364,-585,-171,4,-60,86,199,234,-209,-62,117,-150,-8,81,7,100,295,21,11,-81,49,-119,-218,152,-219,101,108,143,-32,-53,-3,-37,41,146,106,-1270,-1007,-1352,149,-23,108,83,272,-32,-125,-128,-132,168,-80,-49,18,172,-86,-27,5,6,141,158,9,297,194,301,329,43,79,15,77,24,-396,222,-26,-106,-2,158,20,-122,-20,-149,29,61,123,-52,-83,-621,-806,-14,-19,-59,119,-375,-68,-21,194,-202,65,68,4,25,9,307,383,-34,245,15,-128,-4,-54,146,51,-204,6,5,-14,-80,221,52,66,69,-184,169,-82,-112,-139,-11,201,73,-121,-242,-383,-109,-329,141,-159,-161,49,-167,-45,-12,-130,-112,188,-298,164,18,-84,60,11,-104,0,101,-28,-95,-34,-37,-13,71,-60,67,171,159,207,56,79,-86,49,-41,-46,92,-74,193,93,-153,-216,134,198,46,129,57,-94,-36,268,-109,81,209,-861,-78,-344,29,-79,107,-78,-55,128,205,33,87,-23,18,-20,21,60,-112,305,185,-116,-29,-124,-9,-77,-1,38,-67,3,222,46,21,-58,67,-78,77,53,71,-35,-167,113,140,-40,316,71,29,-6,-43,-33,110,30,-67,-261,-139,162,-43,-211,-201,-66,11,-4,49,-143,-93,-69,-93,-17,-139,-124,44,-78,-59,1,122,14,183,74,-158,-47,50,95,-126,-94,-19,17,174,120,-41,-239,-268,205,-31,78,136,-83,227,365,62,11,-27,-93,55,-97,214,1,-45,-30,0,-9,-167,-85,20,-23,-24,-154,-124,22,476,-130,65,-489,-97,482,-21,43,4,160,21,-81,-21,-56,0,42,-33,170,-215,59,229,2,-67,330,82,86,-33,201,-97,-895,-7,74,194,20,-2,-32,-3,-161,27,175,34,-110,481,47,150,-13,-75,-26,-17,-1,58,-294,-498,-491,81,-111,-160,76,-201,-188,-55,8,57,69,-180,153,60,32,20,-249,43,-39,-96,104,-96,-247,106,324,-44,-75,-224,-157,99,-316,289,67,43,-67,-141,-193,29,-43,-325,2,65,105,-23,86,-38,102,208,-44,-117,-133,49,109,-132,-3,-75,9,4,228,11,60,-52,-129,135,-67,13,-126,-137,172,61,2,196,-147,110,-56,15,-8,164,129,45,20,128,-124,-45,-28,-37,50,74,-73,29,22,21,-26,-135,-96,298,77,-53,186,-44,114,-10,-62,54,429,-248,294,-438,12,-30,264,-245,-22,-125,-188,-97,-9,-33,154,15,-71,-143,-85,57,7,27,2,124,-28,-59,-2,42,444,98,29,-109,110,114,82,-9,148,88,96,7,13,-111,-652,-250,97,-83,-141,376,177,-251,-571,-184,-97,96,125,-223,-50,77,38,-85,-5,-263,-15,163,-129,-46,192,-122,-7,32,-59,26,650,-121,-21,-3,-154,-61,20,84,17,2,227,-85,223,254,33,-7,-6,-790,-1333,-155,-613,66,-121,-149,-59,424,24,64,22,-119,-90,31,-169,-26,113,-12,-126,120,-13,-23,106,-59,-75,-5,-210,-49,-79,3,-19,114,-795,-206,171,-106,71,43,96,-104,19,-47,4,-42,-38,-28,231,-395,22,220,85,-149,-60,-84,201,89,-8,130,99,-18,-18,272,179,45,-32,85,11,-283,-6,-72,-198,76,-20,16,89,-68,-54,-12,-189,47,-638,-265,208,-162,-10,-25,83,59,26,51,152,63,-23,14,-410,-41,-127,-370,-72,-244,-411,106,-71,221,-107,255,-98,106,92,23,-19,-48,61,-20,118,130,-106,172,5,-220,126,-221,-67,-79,-53,-11,-42,-108,-110,-20,-100,-73,288,-11,100,316,-427,-342,-124,238,6,74,127,31,-173,197,-150,0,26,-62,-47,50,-81,11,-213,-68,-110,-92,108,-16,-102,263,-8,220,-83,-157,-139,-134,-218,197,-14,68,120,32,-1,-18,-25,-230,-72,-77,270,72,-73,-74,-123,-54,6,-5,53,-37,75,-98,-58,-93,-54,107,-13,-37,-22,79,-13,-34,-80,-45,78,-125,-98,-146,126,-439,-45,204,-131,-178,134,298,213,-55,-32,-48,-16,-47,59,-32,-18,-155,-38,1,-60,72,114,-47,33,-27,-52,-371,-56,138,-194,388,-98,-19,43,64,52,103,54,37,-2,35,134,-4,-28,-41,107,20,103,-137,198,127,162,183,76,155,-5,-32,-86,26,-514,-21,-97,39,56,71,-33,-191,-30,-238,-61,165,-58,-18,-24,-509,7,-50,-7,49,8,12,-164,-20,-125,-284,-1090,77,-49,-37,-20,-202,-75,-23,-50,1,-40,35,105,13,216,-16,-86,-19,-89,-69,24,-158,-383,-53,-237,-45,30,214,261,7,-4,-232,-38,144,-32,-74,300,-46,69,26,279,116,46,71,-98,41,49,-48,-14,-198,-11,195,9,-158,-560,-312,-284,100,-225,235,-314,132,5,-289,127,-160,21,-53,1,-121,83,50,44,174,260,-335,-14,-25,-42,165,-24,28,7,196,27,-139,-126,-108,-195,-109,158,-61,-60,185,251,16,52,-79,-85,74,83,-33,203,15,215,-104,-102,-89,-16,-11,14,52,88,149,30,46,-61,-171,-212,-152,180,-59,-109,133,3,395,65,11,37,-102,-312,-82,253,196,-22,-20,48,50,28,-81,89,-20,101,8,-178,-54,182,-61,42,61,-155,-14,159,64,356,39,28,87,143,-76,43,13,-3,27,54,-34,-140,66,-24,-182,-183,-546,-398,195,-54,-109,-125,-90,-29,-214,-374,-260,-364,-585,-171,4,-60,86,199,234,-209,-62,117,-150,-8,81,7,100,295,21,11,-81,49,-119,-218,152,-219,101,108,143,-32,-53,-3,-37,41,146,106,-1270,-1007,-1352,149,-23,108,83,272,-32,-125,-128,-132,168,-80,-49,18,172,-86,-27,5,6,141,158,9,297,194,301,329,43,79,15,77,24,-396,222,-26,-106,-2,158,20,-122,-20,-149,29,61,123,-52,-83,-621,-806,-14,-19,-59,119,-375,-68,-21,194,-202,65,68,4,25,9,307,383,-34,245,15,-128,-4,-54,146,51,-204,6,5,-14,-80,221,52,66,69,-184,169,-82,-112,-139,-11,201,73,-121,-242,-383,-109,-329,141,-159,-161,49,-167,-45,-12,-130,-112,188,-298,164,18,-84,60,11,-104,0,101,-28,-95,-34,-37,-13,71,-60,67,171,159,207,56,79,-86,49,-41,-46,92,-74,193,93,-153,-216,134,198,46,129,57,-94,-36,268,-109,81,209,-861,-78,-344,29,-79,107,-78,-55,128,205,33,87,-23,18,-20,21,60,-112,305,185,-116,-29,-124,-9,-77,-1,38,-67,3,222,46,21,-58,67,-78,77,53,71,-35,-167,113,140,-40,316,71,29,-6,-43,-33,110,30,-67,-261,-139,162,-43,-211,-201,-66,11,-4,49,-143,-93,-69,-93,-17,-139,-124,44,-78,-59,1,122,14,183,74,-158,-47,50,95,-126,-94,-19,17,174,120,-41,-239,-268,205,-31,78,136,-83,227,365,62,11,-27,-93,55,-97,214,1,-45,-30,0,-9,-167,-85,20,-23,-24,-154,-124,22,476,-130,65,-489,-97,482,-21,43,4,160,21,-81,-21,-56,0,42,-33,170,-215,59,229,2,-67,330,82,86,-33,201,-97,-895,-7,74,194,20,-2,-32,-3,-161,27,175,34,-110,481,47,150,-13,-75,-26,-17,-1,58,-294,-498,-491,81,-111,-160,76,-201,-188,-55,8,57,69,-180,153,60,32,20,-249,43,-39,-96,104,-96,-247,106,324,-44,-75,-224,-157,99,-316,289,67,43,-67,-141,-193,29,-43,-325,2,65,105,-23,86,-38,102,208,-44,-117,-133,49,109,-132,-3,-75,9};

static void load_file(const char *name,unsigned char *out,unsigned bytes) {
 FILE *f=fopen(name,"rb");check(f!=NULL,"fixture-open");
 check(fread(out,1,bytes,f)==bytes && fgetc(f)==EOF,"fixture-size");fclose(f);
}
static uint32_t get32(const unsigned char *p) {return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void upload_values(struct client *c,const int16_t *a,const int16_t *b) {
 unsigned v;for(v=0;v<2;v++) {
  struct pango_mac_nnue_upload u;memset(&u,0,sizeof(u));u.abi_version=PANGO_MAC_NNUE_ABI_VERSION;
  u.view=v;u.source_offset=0xf0000;memcpy(c->data+u.source_offset,v?b:a,2048);
  check(!ioctl(c->fd,PANGO_MAC_IOC_NNUE_UPLOAD,&u) && u.tag,"fixture-upload");c->tag[v]=u.tag;
 }
}
static unsigned test_score(struct client *c,unsigned bucket,int32_t expected,const char *label,unsigned index) {
 struct pango_mac_nnue_job j;struct pango_mac_nnue_cache_stats a=stats(c),b;
 memset(&j,0,sizeof(j));j.abi_version=PANGO_MAC_NNUE_ABI_VERSION;j.bucket=bucket;
 j.tag0=c->tag[0];j.tag1=c->tag[1];j.timeout_us=1000000;
 check(!ioctl(c->fd,PANGO_MAC_IOC_RUN_NNUE,&j) && j.jobs==6,"fixture-run");b=stats(c);
 printf("DEDICATED_OFFICIAL_CASE label=%s index=%u bucket=%u actual=%d expected=%d cycles=%u reads=%u hits=%u errors=%u\n",
 label,index,bucket,(int32_t)j.score,expected,j.cycles,b.read_words-a.read_words,b.hits-a.hits,b.errors-a.errors);
 return (int32_t)j.score!=expected;
}
int main(void) {
 static unsigned char golden[38176];struct client c;struct pango_mac_model m;
 int16_t a[1024],b[1024];unsigned i,v,k,mismatches=0;
 setvbuf(stdout,NULL,_IOLBF,0);basic_tests();c=open_client();
 load_file("/opt/pikafish/stageb-mac.bin",c.data,MODEL_BYTES);
 load_file("/opt/pikafish/stageb-position-golden.bin",golden,sizeof(golden));
 check(get32(golden)==0x32474650u && get32(golden+16)==32 && get32(golden+32)==1188,"golden-header");
 memset(&m,0,sizeof(m));m.abi_version=PANGO_MAC_MODEL_ABI_VERSION;m.bytes=MODEL_BYTES;
 check(!ioctl(c.fd,PANGO_MAC_IOC_REGISTER_MODEL,&m),"official-model");
 for(i=0;i<32;i++) {
  const unsigned char *r=golden+160+i*1188;
  for(v=0;v<2;v++)for(k=0;k<512;k++) {
   unsigned x=r[36+v*512+k];int16_t *out=v?b:a;check(x<128,"feature-range");
   out[k]=255;out[k+512]=(int16_t)((x*512+254)/255);
   check((255u*(unsigned)out[k+512])/512==x,"inverse-transform");
  }
  upload_values(&c,a,b);mismatches+=test_score(&c,get32(r),(int32_t)get32(r+16),"cold",i);
  mismatches+=test_score(&c,get32(r),(int32_t)get32(r+16),"warm",i);
 }
 upload_values(&c,initial_views,initial_views+1024);
 mismatches+=test_score(&c,11,2392,"initial-real",0);
 printf("DEDICATED_OFFICIAL_DIAGNOSTIC_DONE mismatches=%u cases=65\n",mismatches);
 munmap(c.data,BYTES);close(c.fd);return mismatches?1:0;
}
