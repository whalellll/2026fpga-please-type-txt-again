/* On-board regression for immutable snapshots and restoration between files. */
#define _POSIX_C_SOURCE 200809L
#include "pango_mac_uapi.h"
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define SCRATCH_BYTES 0x100000u
#define MODEL_OFFSET 0x1000u
#define MODEL_BYTES 8192u
#define INPUT_OFFSET 0xf0000u
#define OUTPUT_OFFSET 0xf1000u
struct client { int fd; unsigned char *shadow; int expected; int failed; };
static void fail(const char *message)
{ perror(message); exit(1); }
static struct pango_mac_job job(void)
{
    struct pango_mac_job result={0};
    result.abi_version=PANGO_MAC_ABI_VERSION;
    result.pixels=1;result.cin=256;result.cout=32;
    result.compute_mode=2;result.output_format=3;result.zero_bias=1;
    result.input_offset=INPUT_OFFSET;result.weight_offset=MODEL_OFFSET;
    result.output_offset=OUTPUT_OFFSET;result.timeout_us=100000;
    return result;
}
static int run(struct client *client,unsigned long command,int expected)
{
    struct pango_mac_job request=job(); unsigned lane;
    if(ioctl(client->fd,command,&request)) return -1;
    for(lane=0;lane<32;lane++) {
        int value;memcpy(&value,client->shadow+OUTPUT_OFFSET+lane*4,4);
        if(value!=expected) { errno=EILSEQ;return -1; }
    }
    return 0;
}
static struct client open_client(unsigned char weight)
{
    struct client result={.fd=-1,.expected=256*weight};
    struct pango_mac_info info;
    struct pango_mac_model model={.abi_version=PANGO_MAC_MODEL_ABI_VERSION,
        .offset=MODEL_OFFSET,.bytes=MODEL_BYTES};unsigned feature;
    result.fd=open("/dev/pango-mac0",O_RDWR);
    if(result.fd<0)fail("open-mac");
    if(ioctl(result.fd,PANGO_MAC_IOC_GET_INFO,&info) ||
       !(info.features&PANGO_MAC_FEATURE_RESIDENT_MODEL))fail("resident-feature");
    result.shadow=mmap(NULL,SCRATCH_BYTES,PROT_READ|PROT_WRITE,MAP_SHARED,result.fd,0);
    if(result.shadow==MAP_FAILED)fail("mmap-shadow");
    memset(result.shadow+MODEL_OFFSET,weight,MODEL_BYTES);
    for(feature=0;feature<256;feature++) {
        result.shadow[INPUT_OFFSET+feature*2]=1;
        result.shadow[INPUT_OFFSET+feature*2+1]=0;
    }
    if(ioctl(result.fd,PANGO_MAC_IOC_REGISTER_MODEL,&model))fail("register-model");
    return result;
}
static long long now_ns(void)
{ struct timespec value;clock_gettime(CLOCK_MONOTONIC,&value);return (long long)value.tv_sec*1000000000+value.tv_nsec; }
static void measure(struct client *client,unsigned long command,const char *name)
{
    unsigned sample;long long total=0;
    if(run(client,command,client->expected))fail("warmup");
    for(sample=0;sample<100;sample++) {
        long long start=now_ns();
        if(run(client,command,client->expected))fail("measure-result");
        total+=now_ns()-start;
    }
    printf("MAC_RESIDENT_LATENCY backend=%s samples=100 mean_us=%lld source_weight_bytes=%u\n",
        name,total/100000,command==PANGO_MAC_IOC_RUN_RESIDENT?0:MODEL_BYTES);
}
static void *worker(void *argument)
{
    struct client *client=argument;unsigned sample;
    for(sample=0;sample<200;sample++)
        if(run(client,PANGO_MAC_IOC_RUN_RESIDENT,client->expected)) {client->failed=1;break;}
    return NULL;
}
int main(void)
{
    struct client a=open_client(1),b=open_client(3);
    struct pango_mac_job invalid=job();pthread_t threads[2];
    memset(a.shadow+MODEL_OFFSET,99,MODEL_BYTES);
    if(run(&a,PANGO_MAC_IOC_RUN_RESIDENT,256))fail("immutable-snapshot");
    memset(b.shadow+MODEL_OFFSET,7,MODEL_BYTES);
    if(run(&b,PANGO_MAC_IOC_RUN,1792) || run(&a,PANGO_MAC_IOC_RUN_RESIDENT,256) ||
       run(&b,PANGO_MAC_IOC_RUN_RESIDENT,768))fail("cross-file-restore");
    memset(a.shadow+OUTPUT_OFFSET,0xa5,128);
    invalid.weight_offset=MODEL_OFFSET+MODEL_BYTES-4;
    errno=0;
    if(ioctl(a.fd,PANGO_MAC_IOC_RUN_RESIDENT,&invalid)!=-1 || errno!=EINVAL)
        fail("resident-range-rejection");
    for(unsigned byte=0;byte<128;byte++)
        if(a.shadow[OUTPUT_OFFSET+byte]!=0xa5)fail("rejected-job-output");
    memset(a.shadow+MODEL_OFFSET,1,MODEL_BYTES);
    measure(&a,PANGO_MAC_IOC_RUN,"legacy");
    measure(&a,PANGO_MAC_IOC_RUN_RESIDENT,"resident");
    if(pthread_create(&threads[0],NULL,worker,&a) || pthread_create(&threads[1],NULL,worker,&b))fail("threads");
    pthread_join(threads[0],NULL);pthread_join(threads[1],NULL);
    if(a.failed || b.failed)fail("concurrent-files");
    munmap(a.shadow,SCRATCH_BYTES);munmap(b.shadow,SCRATCH_BYTES);close(a.fd);close(b.fd);
    puts("MAC_RESIDENT_BOARD_PASS files=2 concurrent_jobs=400 immutable=pass restore=pass");
    return 0;
}
