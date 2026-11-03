#define _POSIX_C_SOURCE 200809L
#include "xq_native_graph.h"
#include "crc32_fast.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

void *__real_malloc(size_t);
void *__real_calloc(size_t,size_t);
static unsigned fail_allocation,cancel_after_jobs;
static int cancel_now;
unsigned xqih_test_job_count(void);
void xqih_test_fail_after(unsigned);
void *__wrap_malloc(size_t n)
{if(fail_allocation && !--fail_allocation)return NULL;return __real_malloc(n);}
void *__wrap_calloc(size_t n,size_t size)
{if(fail_allocation && !--fail_allocation)return NULL;return __real_calloc(n,size);}
static int cancelled(void *unused)
{(void)unused;return cancel_now || (cancel_after_jobs && xqih_test_job_count()>=cancel_after_jobs);}
static void invalid(xqn_model *m)
{for(unsigned i=0;i<3;i++)assert(xqn_output(m,i,NULL)==NULL);}
static void observer(void *unused,unsigned i,const int8_t *a,size_t n,
                     const int16_t *b,size_t k,const int32_t *c,const int16_t *d)
{(void)unused;(void)i;(void)a;(void)n;(void)b;(void)k;(void)c;(void)d;abort();}
int main(int argc,char **argv)
{
    assert(argc==4);
    xqn_model *m=xqn_load(argv[1]);
    if(!m){puts("HWC_PRODUCT_MODEL_REJECTED_BEFORE_DEVICE");return 2;}
    float *input=malloc(3u*640u*640u*4);assert(input);
    FILE *f=fopen(argv[2],"rb");assert(f);
    assert(fread(input,4,3u*640u*640u,f)==3u*640u*640u && fgetc(f)==EOF && !ferror(f));assert(!fclose(f));
    xqm_linux device;assert(xqm_linux_open(&device));device.io.cancelled=cancelled;
    xqm_stats st;assert(xqn_run(m,&device.io,1,input,0,&st));assert(st.jobs==166);
    uint32_t crc=0xffffffffu;f=fopen(argv[3],"wb");assert(f);
    for(unsigned i=0;i<3;i++){
        unsigned dims[4];const float *values=xqn_output(m,i,dims);assert(values);
        size_t n=(size_t)dims[0]*dims[1]*dims[2]*dims[3];
        assert(fwrite(dims,4,4,f)==4 && fwrite(values,4,n,f)==n);crc=crc32_fast(crc,values,n*4);
    }
    assert(!fclose(f));printf("HWC_PRODUCT_OUTPUT jobs=%llu crc=%08x\n",(unsigned long long)st.jobs,crc^0xffffffffu);
    unsigned before=xqih_test_job_count(),features=device.features;
    device.features&=~PANGO_MAC_FEATURE_VISION32_EXACT;
    assert(!xqn_run(m,&device.io,1,input,0,&st));invalid(m);assert(xqih_test_job_count()==before);
    device.features=features;
    assert(!xqn_run(m,NULL,1,input,1,&st));invalid(m);assert(xqih_test_job_count()==before);
    xqn_observe(m,observer,NULL);assert(!xqn_run(m,&device.io,1,input,0,&st));invalid(m);
    xqn_observe(m,NULL,NULL);assert(xqih_test_job_count()==before);
    cancel_now=1;assert(!xqn_run(m,&device.io,1,input,0,&st));invalid(m);cancel_now=0;
    for(unsigned fail=1;fail<=2;fail++){
        fail_allocation=fail;assert(!xqn_run(m,&device.io,1,input,0,&st));invalid(m);assert(!fail_allocation);
    }
    assert(xqih_test_job_count()==before);
    cancel_after_jobs=before+1;assert(!xqn_run(m,&device.io,1,input,0,&st));invalid(m);
    assert(xqih_test_job_count()==before+1);cancel_after_jobs=0;
    before=xqih_test_job_count();xqih_test_fail_after(before+1);
    assert(!xqn_run(m,&device.io,1,input,0,&st));invalid(m);assert(xqih_test_job_count()==before+1);
    xqih_test_fail_after(0);
    xqn_free(m);free(input);xqm_linux_close(&device);
    puts("HWC_PRODUCT_BOUNDARY_NO_CPU_FALLBACK_NO_RAW2_OBSERVER_OOM_CANCEL_IOCTL_INVALIDATE_PASS");
    return 0;
}
