#include "graph_tensor.h"
#include "xq_int8_layer.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int16_t reference_pre(int32_t value,unsigned shift)
{
    int64_t v=value;uint64_t m=(uint64_t)(v<0?-v:v);
    uint64_t divisor=UINT64_C(1)<<shift,q=m/divisor,r=m%divisor;
    if(shift && (r>divisor/2 || (r==divisor/2 && q%2)))q++;
    int64_t signed_q=v<0?-(int64_t)q:(int64_t)q;
    return signed_q>32767?32767:signed_q< -32768?-32768:(int16_t)signed_q;
}
int main(void)
{
    const size_t count=65536;
    int16_t *q=malloc(count*2);float *f=malloc(count*4);
    int8_t *old=malloc(count),*now=malloc(count);
    assert(q && f && old && now);
    for(size_t i=0;i<count;i++)q[i]=(int16_t)((int32_t)i-32768);
    uint64_t compared=0;
    /* Exhaust every S16 value and all useful rounding/saturation shifts. */
    xqg_tensor t={.q16=q,.count=count,.exponent=0};
    assert(xqi_dequantize(q,count,0,f));
    for(int exponent=-18;exponent<=18;exponent++){
        assert(xqi_quantize(f,count,exponent,old));
        assert(xqg_tensor_quantize(&t,exponent,now));
        assert(!memcmp(old,now,count));compared+=count;
    }
    const int16_t finite_edges[]={0,1,-1,127,-128,255,-255,256,-256,32767,-32768};
    for(int e=112;e<=120;e++)for(size_t i=0;i<sizeof(finite_edges)/sizeof(finite_edges[0]);i++){
        float value;int8_t ref,result;
        xqg_tensor edge={.q16=(int16_t *)&finite_edges[i],.count=1,.exponent=e};
        assert(xqi_dequantize(edge.q16,1,e,&value));
        int a=xqi_quantize(&value,1,120,&ref),b=xqg_tensor_quantize(&edge,120,&result);
        assert(a==b);if(a)assert(ref==result);
    }
    /* Cover supported exponent extremes and FP32 overflow rejection. */
    const int exponents[]={-120,-119,-112,-16,-1,0,1,16,110,112,113,119,120};
    for(size_t e=0;e<sizeof(exponents)/sizeof(exponents[0]);e++){
        t.exponent=exponents[e];assert(xqi_dequantize(q,count,t.exponent,f));
        for(size_t d=0;d<sizeof(exponents)/sizeof(exponents[0]);d++){
            int a=xqi_quantize(f,count,exponents[d],old);
            int b=xqg_tensor_quantize(&t,exponents[d],now);
            assert(a==b);if(a){assert(!memcmp(old,now,count));compared+=count;}
        }
    }
    /* Same tensor with both carriers keeps the exact q16 semantics. */
    t.exponent=-8;t.f32=NULL;
    const float *cache=xqg_tensor_float(&t);assert(cache && t.q16==q);
    assert(xqg_tensor_float(&t)==cache);
    assert(xqi_quantize(cache,count,-7,old) && xqg_tensor_quantize(&t,-7,now));
    assert(!memcmp(old,now,count));
    xqg_tensor_clear(&t);assert(!t.q16 && !t.f32 && !t.count);
    xqg_tensor_clear(&t);assert(!xqg_tensor_float(&t));
    assert(!xqg_tensor_quantize(&t,0,now) && !xqg_tensor_quantize(NULL,0,now));
    const int32_t edges[]={INT32_MIN,INT32_MIN+1,-1073741824,-65537,-65536,-65535,
        -32769,-32768,-32767,-129,-128,-127,-3,-2,-1,0,1,2,3,127,128,129,
        32767,32768,32769,65535,65536,65537,1073741824,INT32_MAX-1,INT32_MAX};
    uint32_t rng=0x21f79a43u;
    for(unsigned shift=0;shift<=62;shift++){
        for(size_t i=0;i<sizeof(edges)/sizeof(edges[0]);i++)
            assert(xqg_pre_value(edges[i],shift)==reference_pre(edges[i],shift));
        for(unsigned i=0;i<4096;i++){
            rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;
            int32_t v;memcpy(&v,&rng,4);
            assert(xqg_pre_value(v,shift)==reference_pre(v,shift));
        }
    }
    free(f);free(old);free(now);
    printf("GRAPH_TENSOR_EXHAUSTIVE_PASS compared=%llu pre_shifts=63 fanout_cache=1\n",(unsigned long long)compared);
    return 0;
}
