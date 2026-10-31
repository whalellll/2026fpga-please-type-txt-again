#define _POSIX_C_SOURCE 200809L
#define XQ_HWC_TILE_EXPORT 1
#ifndef XQIH_EXPORT_NO_PROBE
static unsigned fast_calls,fallback_calls;
#define XQIH_EXPORT_NOTE(fast) ((fast)?++fast_calls:++fallback_calls)
#endif
#include "../adapter.c"
#include <assert.h>

static unsigned checks,guarded_exponents;
#ifndef XQIH_EXPORT_NO_PROBE
static unsigned monitor_malloc,malloc_calls;
void *__real_malloc(size_t);
void *__wrap_malloc(size_t size)
{if(monitor_malloc){++malloc_calls;return NULL;}return __real_malloc(size);}
#endif

static void compare(xi8_model *model,unsigned index,size_t capacity,int destination,int dimensions,int fast)
{
    size_t count=xi8_output_elements(model,index),bytes=count*4+64;
    if(bytes<64)bytes=64;
    uint8_t *expected=malloc(bytes),*actual=malloc(bytes);
    unsigned dims_a[4]={0xdeadbeef,0xdeadbeef,0xdeadbeef,0xdeadbeef},dims_b[4];
    assert(expected && actual);memset(expected,0xa5,bytes);memset(actual,0xa5,bytes);memcpy(dims_b,dims_a,sizeof(dims_a));
#ifndef XQIH_EXPORT_NO_PROBE
    unsigned before_fast=fast_calls,before_fallback=fallback_calls;
    monitor_malloc=1;malloc_calls=0;
#else
    (void)fast;
#endif
    int a=xi8_export_f32(model,index,destination?expected:NULL,capacity,dimensions?dims_a:NULL);
    int b=xqih_export_f32_tiled(model,index,destination?actual:NULL,capacity,dimensions?dims_b:NULL);
#ifndef XQIH_EXPORT_NO_PROBE
    monitor_malloc=0;
#endif
    assert(a==b && !memcmp(expected,actual,bytes) && !memcmp(dims_a,dims_b,sizeof(dims_a)));
#ifndef XQIH_EXPORT_NO_PROBE
    assert(!malloc_calls);
    assert(fast_calls-before_fast==(unsigned)fast && fallback_calls-before_fallback==(unsigned)!fast);
#endif
    free(expected);free(actual);++checks;
}

static int16_t value(unsigned i)
{
    unsigned bits=(i*40503u+173u)&65535u;
    return (int16_t)(bits<32768u?(int)bits:(int)bits-65536);
}

#ifdef XQIH_EXPORT_NO_PROBE
static void benchmark(xi8_model *model)
{
    uint32_t *expected[3],*actual[3];size_t bytes[3];
    for(unsigned head=0;head<3;head++) {
        bytes[head]=xi8_output_elements(model,head)*4;
        expected[head]=malloc(bytes[head]);actual[head]=malloc(bytes[head]);
        assert(expected[head] && actual[head]);
        unsigned a[4],b[4];
        assert(xi8_export_f32(model,head,expected[head],bytes[head],a));
        assert(xqih_export_f32_tiled(model,head,actual[head],bytes[head],b));
        assert(!memcmp(expected[head],actual[head],bytes[head]) && !memcmp(a,b,sizeof(a)));
    }
    for(unsigned variant=0;variant<2;variant++)for(unsigned repeat=0;repeat<3;repeat++) {
        struct timespec a,b;int okay=1;
        assert(!clock_gettime(CLOCK_MONOTONIC,&a));
        for(unsigned head=0;head<3;head++)
            okay&=variant?xqih_export_f32_tiled(model,head,actual[head],bytes[head],NULL):
                           xi8_export_f32(model,head,expected[head],bytes[head],NULL);
        assert(!clock_gettime(CLOCK_MONOTONIC,&b));assert(okay);
        /* Consume each timed result after stopping the clock; the stores
         * cannot become dead work just because the buffers are freed later. */
        for(unsigned head=0;head<3;head++)assert(!memcmp(expected[head],actual[head],bytes[head]));
        printf("HWC_EXPORT_NO_PROBE_NS heads=3 variant=%u value=%llu\n",variant,
            (unsigned long long)(b.tv_sec-a.tv_sec)*1000000000u+b.tv_nsec-a.tv_nsec);
    }
    for(unsigned head=0;head<3;head++){free(expected[head]);free(actual[head]);}
}
#endif

int main(int argc,char **argv)
{
    xi8_model model={0};
    const unsigned sides[3]={80,40,20};
    for(unsigned head=0;head<3;head++) {
        size_t count=(size_t)57*sides[head]*sides[head];
        int16_t *data=malloc(count*sizeof(*data));assert(data);
        for(size_t i=0;i<count;i++)data[i]=value((unsigned)i);
        model.outputs[head]=(xi8_tensor){.data=data,.c=57,.h=sides[head],.w=sides[head],.pitch=57,.bits=16,.exponent=-6};
    }
    if(argc==2 && !strcmp(argv[1],"--bench")) {
#ifdef XQIH_EXPORT_NO_PROBE
        benchmark(&model);
        for(unsigned head=0;head<3;head++)free(model.outputs[head].data);
        return 0;
#else
        assert(!"probe build cannot measure production timing");
#endif
    }
    assert(argc==1);
    /* Full S16 domain appears in each 80x80 head. All frozen heads are compared
     * with the unchanged exporter including dimensions and untouched guards. */
    const int exponents[]={-126,-100,-6,0,100,112};
    for(unsigned e=0;e<sizeof(exponents)/sizeof(exponents[0]);e++)for(unsigned head=0;head<3;head++) {
        model.outputs[head].exponent=exponents[e];
        compare(&model,head,xi8_output_elements(&model,head)*4,1,1,1);
    }
    const int16_t edge_values[]={0,1,-1,2,-2,32767,-32768};
    xi8_tensor *t=&model.outputs[2];
    for(size_t p=0;p<(size_t)57*20*20;p++)((int16_t *)t->data)[p]=edge_values[p%7];
    for(int e=-126;e<=112;e++) {
        t->exponent=e;compare(&model,2,57u*20u*20u*4u,1,e&1,1);++guarded_exponents;
    }
    t->exponent=-6;
    compare(&model,2,57u*20u*20u*4u-1,1,1,0);
    compare(&model,2,57u*20u*20u*4u+128,1,0,1);
    compare(&model,2,57u*20u*20u*4u,0,1,0);
    compare(NULL,0,0,1,1,0);compare(&model,3,0,1,1,0);
    xi8_tensor saved=*t;
    t->data=NULL;compare(&model,2,0,1,1,0);*t=saved;
    t->h=0;compare(&model,2,0,1,1,0);*t=saved;
    t->c=0;compare(&model,2,0,1,1,0);*t=saved;
    t->bits=8;compare(&model,2,57u*20u*20u*4u,1,1,0);*t=saved;
    t->bits=32;compare(&model,2,57u*20u*20u*4u,1,1,0);*t=saved;
    /* Invalid-for-fast-path shape and pitch still use the original exporter. */
    t->pitch=0;compare(&model,2,57u*20u*20u*4u,1,1,0);*t=saved;
    t->pitch=56;compare(&model,2,57u*20u*20u*4u,1,1,0);*t=saved;
    t->c=56;compare(&model,2,56u*20u*20u*4u,1,1,0);*t=saved;
    t->w=19;compare(&model,2,57u*20u*19u*4u,1,1,0);*t=saved;
    /* A failure after some original c-major output writes must retain every
     * byte of that prefix and every untouched byte/dimension after it. */
    memset(t->data,0,57u*20u*20u*2u);
    ((int16_t *)t->data)[3*57]=1;t->exponent=-127;
    compare(&model,2,57u*20u*20u*4u,1,1,0);
    ((int16_t *)t->data)[3*57]=INT16_MIN;t->exponent=113;
    compare(&model,2,57u*20u*20u*4u,1,1,0);
    t->exponent=-6;
    uint32_t *output=malloc(57u*20u*20u*4u);assert(output);
    assert(xqih_export_tile_eligible(t,output,57u*20u*20u));
    assert(!xqih_export_tile_eligible(t,t->data,57u*20u*20u));
    assert(!xqih_export_tile_eligible(t,(uint8_t *)t->data+4,57u*20u*20u));
    assert(!xqih_export_tile_eligible(t,(uint8_t *)output+2,57u*20u*20u));
    assert(!xqih_export_tile_eligible(t,(void *)(UINTPTR_MAX-15),57u*20u*20u));
    xi8_tensor near=*t;near.data=(void *)(UINTPTR_MAX-3);
    assert(!xqih_export_tile_eligible(&near,output,57u*20u*20u));
    free(output);
    for(unsigned head=0;head<3;head++)free(model.outputs[head].data);
    printf("HWC_TILE_EXPORT_FULL_HEADS_S16_EXPONENTS_FAILURE_PREFIX_NO_ALLOC_PASS_NOT_BOARD cases=%u guarded_exponents=%u tile_array_bytes=512\n",checks,guarded_exponents);
    return 0;
}
