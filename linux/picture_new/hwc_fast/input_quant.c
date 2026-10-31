#include "input_quant.h"
#include "xq_int8_layer.h"
#include <float.h>
#include <string.h>
_Static_assert(sizeof(float)==4 && FLT_RADIX==2 && FLT_MANT_DIG==24,"binary32 required");
static unsigned bucket(uint32_t key)
{return ((key^(key>>15))*UINT32_C(0x9e3779b9))>>23;}
int xqih_input_table_init(xqih_input_table *t,int exponent)
{
    if(!t || exponent< -120 || exponent>120)return 0;
    float colors[256];int8_t codes[256];
    for(unsigned i=0;i<256;i++)colors[i]=(float)i/255.f;
    if(!xqi_quantize(colors,256,exponent,codes))return 0;
    memset(t->keys,0xff,sizeof(t->keys));t->exponent=exponent;
    for(unsigned i=0;i<256;i++){
        uint32_t key;memcpy(&key,colors+i,4);unsigned at=bucket(key);
        while(t->keys[at]!=UINT32_MAX)at=(at+1)&511;
        t->keys[at]=key;t->values[at]=codes[i];
    }
    return 1;
}
int xqih_input_quantize(const xqih_input_table *t,const float *in,size_t count,int8_t *out)
{
    if(!t || !in || !out)return 0;
    for(size_t i=0;i<count;i++){
        uint32_t key;memcpy(&key,in+i,4);unsigned at=bucket(key);
        while(t->keys[at]!=UINT32_MAX && t->keys[at]!=key)at=(at+1)&511;
        if(t->keys[at]==key && key!=UINT32_MAX)out[i]=t->values[at];
        else if(!xqi_quantize(in+i,1,t->exponent,out+i))return 0;
    }
    return 1;
}
