#include "xqvoice_mac.h"
#include <stddef.h>
#if defined(__linux__) && defined(XQVOICE_WITH_MAC)
#include "pango_mac_uapi.h"
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>

static int fd=-1;static uint8_t *shadow;static size_t shadow_size;
static unsigned timeout_us;
static unsigned long long jobs,cycles;
static unsigned resident_available,resident_prepared,prepared_K,prepared_cout;
static const uint8_t *prepared_weights;
static unsigned long long resident_jobs;
static unsigned async_available,async_pending;
static struct pango_mac_async_job pending;
int xqvoice_mac_open(void) {
    struct pango_mac_info info;
    if(fd>=0)return -1;
    fd=open("/dev/pango-mac0",O_RDWR|O_CLOEXEC);
    if(fd<0)return -2;
    memset(&info,0,sizeof(info));
    if(ioctl(fd,PANGO_MAC_IOC_GET_INFO,&info)<0 || info.abi_version!=PANGO_MAC_ABI_VERSION ||
       info.device_id!=PANGO_MAC_ID || info.device_version!=PANGO_MAC_VERSION ||
       (info.features&(PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED))!=
           (PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED) ||
       info.scratch_bytes<65536u || info.scratch_bytes>1048576u || info.max_pixels<16u || info.max_channels<200u || !info.max_timeout_us) {
        xqvoice_mac_close();return -3;
    }
    shadow_size=info.scratch_bytes;timeout_us=info.max_timeout_us<100000u?info.max_timeout_us:100000u;
    shadow=(uint8_t*)mmap(NULL,shadow_size,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    if(shadow==MAP_FAILED){shadow=NULL;xqvoice_mac_close();return -4;}
    {
        const char *setting=getenv("XQVOICE_MAC_RESIDENT");
        if(setting && strcmp(setting,"0") && strcmp(setting,"1")){xqvoice_mac_close();return -5;}
        resident_available=(info.features&PANGO_MAC_FEATURE_RESIDENT_MODEL)!=0;
        if(setting && !strcmp(setting,"1") && !resident_available){xqvoice_mac_close();return -6;}
        if(setting && !strcmp(setting,"0"))resident_available=0;
    }
    {
        const char *setting=getenv("XQVOICE_MAC_PIPELINE");
        if(setting && strcmp(setting,"0") && strcmp(setting,"1")){xqvoice_mac_close();return -7;}
        async_available=(info.features&PANGO_MAC_FEATURE_ASYNC_DENSE)!=0;
        if(setting && !strcmp(setting,"1") && !async_available){xqvoice_mac_close();return -8;}
        /* Experimental until real-board paired timing establishes a win. */
        if(!setting || !strcmp(setting,"0"))async_available=0;
    }
    jobs=0;cycles=0;resident_jobs=0;resident_prepared=0;prepared_weights=NULL;async_pending=0;return 0;
}
void xqvoice_mac_close(void) {
    /* close aborts any outstanding ticket in the driver. */
    async_available=async_pending=0;
    resident_prepared=resident_available=0;prepared_weights=NULL;
    if(shadow){munmap(shadow,shadow_size);shadow=NULL;}
    if(fd>=0){close(fd);fd=-1;}
}
static void copy_words(uint8_t *dst,const uint8_t *src,size_t bytes) {
    size_t i;
#ifdef XQVOICE_TEST_COPY
    extern void xqvoice_test_copy(const uint8_t *,size_t);
    xqvoice_test_copy(dst,bytes);
#endif
    for(i=0;i<bytes;i+=4) {
        uint32_t w=(uint32_t)src[i]|((uint32_t)src[i+1]<<8)|((uint32_t)src[i+2]<<16)|((uint32_t)src[i+3]<<24);
        *(volatile uint32_t*)(void*)(dst+i)=w;
    }
}
int xqvoice_mac_prepare_layer(const uint8_t *weights,unsigned K,unsigned cout,unsigned job_count) {
    struct pango_mac_model model;unsigned rows;
    resident_prepared=0;prepared_weights=NULL;
    if(fd<0 || !shadow || async_pending || !weights || K<4u || K>256u || K%4u || cout<1u || cout>32u || !job_count)return -1;
    rows=(K/4u)*((cout+31u)/32u);if(rows>64u)return -1;
    /* A single job has no reuse to amortize registration/allocation. */
    if(!resident_available || job_count<2u)return 0;
    copy_words(shadow+8192u,weights,rows*128u);
    memset(&model,0,sizeof(model));model.abi_version=PANGO_MAC_MODEL_ABI_VERSION;
    model.offset=8192u;model.bytes=rows*128u;
    if(ioctl(fd,PANGO_MAC_IOC_REGISTER_MODEL,&model)<0)return -2;
    prepared_weights=weights;prepared_K=K;prepared_cout=cout;resident_prepared=1;return 0;
}
int xqvoice_mac_dense(const uint8_t *input,const uint8_t *weights,unsigned pixels,unsigned K,unsigned cout,int32_t *accum) {
    struct pango_mac_job job;unsigned i,tiles=(K+3u)/4u,rows=tiles*((cout+31u)/32u);
    unsigned use_resident;
    if(fd<0 || !shadow || async_pending || !input || !weights || !accum || pixels<1u || pixels>16u || K<4u || K>256u || K%4u || cout<1u || cout>32u || rows>64u)return -1;
    use_resident=resident_prepared && prepared_weights==weights && prepared_K==K && prepared_cout==cout;
    if(input!=shadow)copy_words(shadow,input,pixels*tiles*8u);
    if(!use_resident){resident_prepared=0;prepared_weights=NULL;copy_words(shadow+8192u,weights,rows*128u);}
    memset(&job,0,sizeof(job));job.abi_version=PANGO_MAC_ABI_VERSION;
    job.pixels=(uint16_t)pixels;job.cin=(uint16_t)K;job.cout=(uint16_t)cout;
    job.compute_mode=1;job.zero_bias=1;job.output_format=3;
    job.input_offset=0;job.weight_offset=8192u;job.output_offset=24576u;job.timeout_us=timeout_us;
    __sync_synchronize();
    if(ioctl(fd,use_resident?PANGO_MAC_IOC_RUN_RESIDENT:PANGO_MAC_IOC_RUN,&job)<0 || job.error_code)return -2;
    __sync_synchronize();
    for(i=0;i<pixels*cout;i++) {
        uint32_t u=*(volatile uint32_t*)(void*)(shadow+24576u+i*4u);
        accum[i]=u<=INT32_MAX?(int32_t)u:(int32_t)((int64_t)u-INT64_C(4294967296));
    }
    jobs++;cycles+=job.cycles;if(use_resident)resident_jobs++;return 0;
}
unsigned long long xqvoice_mac_resident_jobs(void){return resident_jobs;}
unsigned long long xqvoice_mac_jobs(void){return jobs;}
unsigned long long xqvoice_mac_cycles(void){return cycles;}
uint8_t *xqvoice_mac_input_buffer(unsigned pixels,unsigned K) {
    if(fd<0 || !shadow || !pixels || pixels>16u || K<4u || K>256u || K%4u)return NULL;
    return shadow;
}
int xqvoice_mac_async_enabled(void){return async_available!=0;}
int xqvoice_mac_start(const uint8_t *weights,unsigned pixels,unsigned K,unsigned cout) {
    unsigned use_resident,rows;
    if(!async_available || async_pending || !weights || !xqvoice_mac_input_buffer(pixels,K) || !cout || cout>32u)return -1;
    rows=(K/4u)*((cout+31u)/32u);if(rows>64u)return -1;
    use_resident=resident_prepared && prepared_weights==weights && prepared_K==K && prepared_cout==cout;
    if(!use_resident){resident_prepared=0;prepared_weights=NULL;copy_words(shadow+8192u,weights,rows*128u);}
    memset(&pending,0,sizeof(pending));pending.job.abi_version=PANGO_MAC_ABI_VERSION;
    pending.job.pixels=(uint16_t)pixels;pending.job.cin=(uint16_t)K;pending.job.cout=(uint16_t)cout;
    pending.job.compute_mode=1;pending.job.zero_bias=1;pending.job.output_format=3;
    pending.job.input_offset=0;pending.job.weight_offset=8192u;pending.job.output_offset=24576u;pending.job.timeout_us=timeout_us;
    if(use_resident)pending.flags=PANGO_MAC_ASYNC_RESIDENT;
    __sync_synchronize();
    if(ioctl(fd,PANGO_MAC_IOC_DENSE_START,&pending)<0 || !pending.ticket)return -2;
    async_pending=1;return 0;
}
int xqvoice_mac_finish(void) {
    if(!async_pending)return -1;
    if(ioctl(fd,PANGO_MAC_IOC_DENSE_FINISH,&pending)<0 || pending.job.error_code){async_pending=0;return -2;}
    __sync_synchronize();async_pending=0;jobs++;cycles+=pending.job.cycles;
    if(pending.flags&PANGO_MAC_ASYNC_RESIDENT)resident_jobs++;
    return 0;
}
const uint8_t *xqvoice_mac_output_buffer(void){return fd>=0 && !async_pending?shadow+24576u:NULL;}
#else
int xqvoice_mac_open(void){return -99;}
void xqvoice_mac_close(void){}
int xqvoice_mac_prepare_layer(const uint8_t *w,unsigned K,unsigned c,unsigned n){(void)w;(void)K;(void)c;(void)n;return -99;}
unsigned long long xqvoice_mac_resident_jobs(void){return 0;}
int xqvoice_mac_dense(const uint8_t *i,const uint8_t *w,unsigned p,unsigned k,unsigned c,int32_t *a){(void)i;(void)w;(void)p;(void)k;(void)c;(void)a;return -99;}
unsigned long long xqvoice_mac_jobs(void){return 0;}
unsigned long long xqvoice_mac_cycles(void){return 0;}
uint8_t *xqvoice_mac_input_buffer(unsigned p,unsigned k){(void)p;(void)k;return NULL;}
int xqvoice_mac_async_enabled(void){return 0;}
int xqvoice_mac_start(const uint8_t *w,unsigned p,unsigned k,unsigned c){(void)w;(void)p;(void)k;(void)c;return -99;}
int xqvoice_mac_finish(void){return -99;}
const uint8_t *xqvoice_mac_output_buffer(void){return NULL;}
#endif
