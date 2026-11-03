#define _POSIX_C_SOURCE 200809L
#include "input_quant.h"
#include "xq_int8_layer.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static uint64_t compared;
static void check(const xqih_input_table *t,const float *values,size_t count)
{
    int8_t *a=malloc(count),*b=malloc(count);assert(a && b);memset(a,0xa5,count);memset(b,0xa5,count);
    int x=xqi_quantize(values,count,t->exponent,a),y=xqih_input_quantize(t,values,count,b);
    assert(x==y && !memcmp(a,b,count));compared+=count;free(a);free(b);
}
static uint64_t now(void)
{struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC,&t));return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;}
int main(void)
{
    float colors[256],neighbors[768];xqih_input_table table;
    for(unsigned i=0;i<256;i++){
        colors[i]=(float)i/255.f;
        neighbors[3*i]=colors[i];neighbors[3*i+1]=nextafterf(colors[i],-INFINITY);neighbors[3*i+2]=nextafterf(colors[i],INFINITY);
    }
    for(int e=-120;e<=120;e++){
        assert(xqih_input_table_init(&table,e));check(&table,colors,256);check(&table,neighbors,768);
    }
    assert(xqih_input_table_init(&table,-7));
    uint32_t rng=UINT32_C(0x26591ab7);
    for(unsigned i=0;i<32768;i++){
        rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;float value;memcpy(&value,&rng,4);check(&table,&value,1);
    }
    const uint32_t exceptions[]={0,UINT32_C(0x80000000),UINT32_C(0x7f800000),UINT32_C(0xff800000),UINT32_C(0x7fc00000),UINT32_MAX};
    for(unsigned at=0;at<sizeof(exceptions)/sizeof(exceptions[0]);at++){
        float values[8];for(unsigned i=0;i<8;i++)values[i]=colors[17*i];
        memcpy(values+3,exceptions+at,4);check(&table,values,8);
    }
    assert(!xqih_input_table_init(NULL,0) && !xqih_input_table_init(&table,-121) && !xqih_input_table_init(&table,121));
    assert(!xqih_input_quantize(NULL,colors,1,(int8_t *)neighbors));
    const size_t n=3u*640u*640u;float *input=malloc(n*4);int8_t *a=malloc(n),*b=malloc(n);assert(input && a && b);
    for(size_t i=0;i<n;i++)input[i]=colors[(i*71+13)%256];
    uint64_t start=now();assert(xqi_quantize(input,n,-7,a));uint64_t middle=now();
    assert(xqih_input_quantize(&table,input,n,b));uint64_t end=now();assert(!memcmp(a,b,n));compared+=n;
    printf("HWC_RGB_QUANT_TIMING_NOT_BOARD reference_ns=%llu lookup_ns=%llu\n",(unsigned long long)(middle-start),(unsigned long long)(end-middle));
    free(input);free(a);free(b);
    printf("HWC_RGB_QUANT_ALL241_EXPONENTS_COLORS_NEIGHBORS_RANDOM_EXCEPTION_PREFIX_PASS_NOT_BOARD compared=%llu\n",(unsigned long long)compared);return 0;
}
