#include "graph_bilinear_s16.h"
#include <float.h>
#include <string.h>
_Static_assert(sizeof(float)==4 && FLT_RADIX==2 && FLT_MANT_DIG==24 && FLT_MAX_EXP==128,
               "Frozen graph requires IEEE754 binary32");

int xqg_bilinear_s16_eligible(const xqg_tensor *t,unsigned batch,unsigned channels,unsigned h,unsigned w)
{
    /* Above112 an S16 dequantization can overflow; below-120 the original
     * model contract does not apply. Keep those on the frozen float path.
     * The dimension cap also guarantees exact quarter-pixel FP32 coordinates. */
    if(!t || !t->q16 || !batch || !channels || !h || !w || h>4096 || w>4096 ||
       t->exponent< -120 || t->exponent>112 || (size_t)batch>SIZE_MAX/channels)return 0;
    size_t count=(size_t)batch*channels;
    if(count>SIZE_MAX/h)return 0;
    count*=h;if(count>SIZE_MAX/w)return 0;count*=w;
    return t->count==count && count<=SIZE_MAX/16;
}
static void store_exact(float *out,int32_t numerator,int exponent)
{
    /* Each axis has coefficients in {0,1,3,4}/4. All products and sums of
     * S16 parents have <=20 significant bits, so EVERY intermediate of the
     * frozen FP32 expression is exact. numerator*2^(exponent-4) is normal,
     * finite binary32 in the eligible range, including both signed extrema.
     * Pack that exact value without RV32 soft-float conversion/ldexp calls. */
    uint32_t bits=0;
    if(numerator){
        uint32_t mag=(uint32_t)(numerator<0?-numerator:numerator),v=mag;
        unsigned msb=0;
        if(v>=65536){v>>=16;msb+=16;}
        if(v>=256){v>>=8;msb+=8;}
        if(v>=16){v>>=4;msb+=4;}
        if(v>=4){v>>=2;msb+=2;}
        if(v>=2)msb++;
        bits=(numerator<0?UINT32_C(0x80000000):0) |
            ((uint32_t)((int)msb+exponent-4+127)<<23) |
            ((mag<<(23-msb))&UINT32_C(0x007fffff));
    }
    memcpy(out,&bits,4);
}
int xqg_bilinear_s16(const xqg_tensor *t,unsigned batch,unsigned channels,unsigned h,unsigned w,float *output)
{
    if(!output || !xqg_bilinear_s16_eligible(t,batch,channels,h,w))return 0;
    unsigned oh=h*2,ow=w*2;
    for(size_t p=0;p<(size_t)batch*channels;p++){
        const int16_t *base=t->q16+p*h*w;
        float *dst=output+p*oh*ow;
        for(unsigned y=0;y<oh;y++){
            unsigned y0=y?(y-1)/2:0,y1=y0+1<h?y0+1:y0,wy=y?(y&1?1:3):0;
            const int16_t *a=base+(size_t)y0*w,*b=base+(size_t)y1*w;
            for(unsigned x=0;x<ow;x++){
                unsigned x0=x?(x-1)/2:0,x1=x0+1<w?x0+1:x0,wx=x?(x&1?1:3):0;
                int32_t top=(int32_t)(4-wx)*a[x0]+(int32_t)wx*a[x1];
                int32_t bottom=(int32_t)(4-wx)*b[x0]+(int32_t)wx*b[x1];
                store_exact(dst+(size_t)y*ow+x,(int32_t)(4-wy)*top+(int32_t)wy*bottom,t->exponent);
            }
        }
    }
    return 1;
}
