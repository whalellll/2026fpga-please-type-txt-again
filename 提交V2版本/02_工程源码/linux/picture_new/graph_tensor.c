#include "graph_tensor.h"
#include "graph_profile.h"
#include "xq_int8_layer.h"
#include <stdlib.h>
void xqg_tensor_clear(xqg_tensor *t)
{
    if(!t)return;
    free(t->q16);free(t->f32);
    t->q16=NULL;t->f32=NULL;t->count=0;t->exponent=0;
}
const float *xqg_tensor_float(xqg_tensor *t)
{
    if(!t || !t->count)return NULL;
    if(t->f32)return t->f32;
    if(!t->q16 || t->count>SIZE_MAX/sizeof(float))return NULL;
    t->f32=malloc(t->count*sizeof(float));if(!t->f32)return NULL;
    xqg_mark start=xqg_begin();
    int okay=xqi_dequantize(t->q16,t->count,t->exponent,t->f32);
    xqg_end(XQG_DEQUANTIZE,start,t->count);
    if(!okay){free(t->f32);t->f32=NULL;}
    return t->f32;
}
int xqg_tensor_quantize(const xqg_tensor *t,int exponent,int8_t *out)
{
    if(!t || !out || !t->count || exponent< -120 || exponent>120)return 0;
    if(!t->q16){
        if(!t->f32)return 0;
        xqg_mark start=xqg_begin();int okay=xqi_quantize(t->f32,t->count,exponent,out);
        xqg_end(XQG_QUANTIZE,start,t->count);return okay;
    }
    if(t->exponent< -120 || t->exponent>120)return 0;
    /* Preserve the old dequantize->quantize rejection of FP32 infinity.
     * Every nonzero S16 at the supported low exponents is a normal FP32.
     * Values have <=16 significant bits, so a finite dequantization is exact. */
    if(t->exponent>112){
        uint32_t finite_limit=1u<<(128-t->exponent);
        for(size_t i=0;i<t->count;i++){
            int32_t v=t->q16[i];uint32_t mag=(uint32_t)(v<0?-v:v);
            if(mag>=finite_limit)return 0;
        }
    }
    int shift=exponent-t->exponent;
    xqg_mark start=xqg_begin();
    for(size_t i=0;i<t->count;i++){
        int32_t v=t->q16[i];uint32_t mag=(uint32_t)(v<0?-v:v),q;
        if(shift<=0)q=shift<= -7?(mag?128u:0u):mag<<(unsigned)(-shift);
        else if(shift>=16)q=0;
        else {
            uint32_t half=1u<<(shift-1),rem=mag&((1u<<shift)-1u);
            q=mag>>shift;if(rem>half || (rem==half && (q&1u)))++q;
        }
        uint32_t limit=v<0?128u:127u;if(q>limit)q=limit;
        out[i]=(int8_t)(v<0?-(int32_t)q:(int32_t)q);
    }
    xqg_end(XQG_REQUANTIZE,start,t->count);return 1;
}
