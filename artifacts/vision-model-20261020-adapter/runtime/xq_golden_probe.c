#define _POSIX_C_SOURCE 200809L
#include "xq_native_graph.h"
#include "crc32_fast.h"
#include "xq_sha256.h"
#include "pango_mac_uapi.h"
#include <errno.h>
#include <stdarg.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t stopped;
static unsigned records;
static uint64_t last_layer_ms;
typedef struct {
    uint64_t driver_us,jobs,cycles,registrations,registered_bytes,input_bytes,output_bytes,hash_us;
} profile;
static profile measured,previous;
static void stop(int s){(void)s;stopped=1;}
static int cancel(void *p){(void)p;return stopped!=0;}
static uint64_t now_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static uint64_t now_us(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000+t.tv_nsec/1000;}
int __real_ioctl(int,unsigned long,...);
int __wrap_ioctl(int fd,unsigned long request,...)
{
    va_list args;va_start(args,request);void *arg=va_arg(args,void *);va_end(args);
    uint64_t begin=now_us();int rc=__real_ioctl(fd,request,arg),saved=errno;
    measured.driver_us+=now_us()-begin;
    if(!rc && request==PANGO_MAC_IOC_REGISTER_MODEL) {
        const struct pango_mac_model *m=arg;measured.registrations++;measured.registered_bytes+=m->bytes;
    }
    if(!rc && (request==PANGO_MAC_IOC_RUN_RESIDENT || request==PANGO_MAC_IOC_RUN)) {
        const struct pango_mac_job *j=arg;measured.jobs++;measured.cycles+=j->cycles;
        measured.input_bytes+=(uint64_t)j->pixels*((j->cin+3u)/4u)*8u;
        measured.output_bytes+=(uint64_t)j->pixels*j->cout*4u;
    }
    errno=saved;return rc;
}
static void observe(void *context,unsigned layer,const int8_t *q,size_t qn,const int16_t *out,size_t on,const int32_t *acc,const int16_t *pre)
{
    FILE *f=context;
    char qhash[65],ahash[65],phash[65],ohash[65];
    uint64_t hash_begin=now_us();
    xq_sha256_hex(q,qn,qhash);xq_sha256_hex(acc,on*4,ahash);
    xq_sha256_hex(pre,on*2,phash);xq_sha256_hex(out,on*2,ohash);
    measured.hash_us+=now_us()-hash_begin;
    fprintf(f,"%u %zu %zu %08x %08x %08x %08x %s %s %s %s\n",layer,qn,on,
        crc32_fast(0xffffffffu,q,(uint32_t)qn)^0xffffffffu,
        crc32_fast(0xffffffffu,acc,(uint32_t)(on*4))^0xffffffffu,
        crc32_fast(0xffffffffu,pre,(uint32_t)(on*2))^0xffffffffu,
        crc32_fast(0xffffffffu,out,(uint32_t)(on*2))^0xffffffffu,qhash,ahash,phash,ohash);
    ++records;
    uint64_t finished=now_ms();
    printf("XQ_GOLDEN_LAYER layer=%u elapsed_ms=%llu driver_us=%llu jobs=%llu cycles=%llu hash_us=%llu\n",layer,
           (unsigned long long)(finished-last_layer_ms),
           (unsigned long long)(measured.driver_us-previous.driver_us),
           (unsigned long long)(measured.jobs-previous.jobs),
           (unsigned long long)(measured.cycles-previous.cycles),
           (unsigned long long)(measured.hash_us-previous.hash_us));
    previous=measured;
    fflush(stdout);last_layer_ms=finished;
}
int main(int argc,char **argv)
{
    xqm_linux mac;xqm_stats totals={0};FILE *checks=NULL;int driver,rc=2;uint64_t start=now_ms();
    const char *names[3]={"board","detector","classifier"};char path[600];
    memset(&mac,0,sizeof(mac));mac.fd=-1;
    if(argc!=5)return 2;
    driver=!strcmp(argv[4],"--driver");
    if(!driver && strcmp(argv[4],"--cpu-reference"))return 2;
    if(driver && !xqm_linux_open(&mac))return 2;
    signal(SIGINT,stop);signal(SIGTERM,stop);signal(SIGALRM,stop);alarm(7200);mac.io.cancelled=cancel;
    last_layer_ms=now_ms();
    checks=fopen(argv[3],"wx");if(!checks)goto done;
    fputs("XQ_NATIVE_CHECKS_V1\n",checks);
    for(unsigned model=0;model<3 && !stopped;model++) {
        FILE *file=NULL;xqn_model *network=NULL;int8_t *input=NULL;int16_t *wide=NULL;float *tensor=NULL;
        char magic[8];uint32_t header[8];int32_t exponent;xqm_stats stats;int okay=0;
        uint64_t model_start=now_ms();memset(&measured,0,sizeof(measured));memset(&previous,0,sizeof(previous));
        last_layer_ms=model_start;
        if(snprintf(path,sizeof(path),"%s/%s.input",argv[2],names[model])>=(int)sizeof(path) || !(file=fopen(path,"rb")))goto model_done;
        if(fread(magic,1,8,file)!=8 || memcmp(magic,"XQINP1\0\0",8) || fread(header,4,8,file)!=8 || fread(&exponent,4,1,file)!=1 ||
           header[0]!=1 || header[1]!=model || !header[2] || header[2]>256 || header[3]!=3 ||
           header[4]!=(model==0?192u:model==1?640u:32u) || header[5]!=header[4] ||
           header[6]!=(size_t)header[2]*header[3]*header[4]*header[5] || header[6]>2u*1024u*1024u ||
           (model<2 && header[2]!=1))goto model_done;
        input=malloc(header[6]);wide=malloc((size_t)header[6]*2);tensor=malloc((size_t)header[6]*4);
        if(!input || !wide || !tensor || fread(input,1,header[6],file)!=header[6] || fgetc(file)!=EOF || ferror(file) ||
           (crc32_fast(0xffffffffu,input,header[6])^0xffffffffu)!=header[7])goto model_done;
        for(unsigned i=0;i<header[6];i++)wide[i]=input[i];
        if(!xqi_dequantize(wide,header[6],exponent,tensor))goto model_done;
        if(snprintf(path,sizeof(path),"%s/%s.xqm",argv[1],names[model])>=(int)sizeof(path) || !(network=xqn_load(path)))goto model_done;
        if(driver && model!=1 && !xqn_pin_resident(network,&mac.io))goto model_done;
        xqn_observe(network,observe,checks);
        if(!xqn_run(network,driver?&mac.io:NULL,header[2],tensor,!driver,&stats))goto model_done;
        totals.jobs+=stats.jobs;totals.cycles+=stats.cycles;
        printf("XQ_GOLDEN_MODEL_DONE model=%s driver=%d jobs=%llu cycles=%llu records=%u\n",names[model],driver,
            (unsigned long long)stats.jobs,(unsigned long long)stats.cycles,records);fflush(stdout);okay=1;
        if(driver && (measured.jobs!=stats.jobs || measured.cycles!=stats.cycles ||
           measured.registrations!=(model==1?60u:1u))) {okay=0;goto model_done;}
        printf("XQ_GOLDEN_PROFILE model=%s wall_ms=%llu driver_us=%llu jobs=%llu cycles=%llu registrations=%llu registered_bytes=%llu input_bytes=%llu output_bytes=%llu hash_us=%llu\n",names[model],
            (unsigned long long)(now_ms()-model_start),(unsigned long long)measured.driver_us,
            (unsigned long long)measured.jobs,(unsigned long long)measured.cycles,
            (unsigned long long)measured.registrations,(unsigned long long)measured.registered_bytes,
            (unsigned long long)measured.input_bytes,(unsigned long long)measured.output_bytes,
            (unsigned long long)measured.hash_us);fflush(stdout);
model_done:
        if(file)fclose(file);
        xqn_free(network);free(input);free(wide);free(tensor);
        if(!okay)goto done;
        if(driver) {
            xqm_linux_close(&mac);
            if(model<2 && !xqm_linux_open(&mac))goto done;
            mac.io.cancelled=cancel;
        }
    }
    if(stopped || records!=80 || (driver && (!totals.jobs || !totals.cycles)))goto done;
    printf("XQ_GOLDEN_PROBE_DONE records=%u driver=%d jobs=%llu cycles=%llu elapsed_ms=%llu comparison=PENDING\n",records,driver,
        (unsigned long long)totals.jobs,(unsigned long long)totals.cycles,(unsigned long long)(now_ms()-start));rc=0;
done:
    if(checks && fclose(checks))rc=2;
    xqm_linux_close(&mac);return rc;
}
