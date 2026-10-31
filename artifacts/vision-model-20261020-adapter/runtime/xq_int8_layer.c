#include "xq_int8_layer.h"
#ifdef XQ_NATIVE_DIRECT_PACK
#include "xq_resident_matrix.h"
#endif
#include <limits.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include <float.h>
_Static_assert(sizeof(float)==4 && FLT_RADIX==2 && FLT_MANT_DIG==24,"IEEE binary32 required");

int xqi_quantize(const float *source,size_t count,int exponent,int8_t *out)
{
    size_t i;
    if(!source || !out || exponent < -120 || exponent > 120)return 0;
    for(i=0;i<count;i++) {
        uint32_t bits,mantissa,q;unsigned field,negative;int shift;
        memcpy(&bits,source+i,4);field=(bits>>23)&255;negative=bits>>31;
        if(field==255)return 0;
        if(!field){out[i]=0;continue;} /* subnormal/2^-120 is below 1/2 */
        mantissa=(bits&0x7fffffu)|0x800000u;shift=150+exponent-(int)field;
        if(shift<=16)q=128;
        else if(shift>24)q=0;
        else {
            uint32_t mask=(1u<<shift)-1u,half=1u<<(shift-1),remainder=mantissa&mask;
            q=mantissa>>shift;if(remainder>half || (remainder==half && (q&1)))++q;
        }
        if(q>(negative?128u:127u))q=negative?128u:127u;
        out[i]=(int8_t)(negative?-(int)q:(int)q);
    }
    return 1;
}
int xqi_dequantize(const int16_t *source,size_t count,int exponent,float *out)
{
    if(!source || !out || exponent< -120 || exponent>120)return 0;
    for(size_t i=0;i<count;i++) {
        int32_t value=source[i];uint32_t mag=(uint32_t)(value<0?-value:value),bits=0;
        if(mag) {
            unsigned top=0,v=mag;
            if(v>=256){v>>=8;top+=8;}
            if(v>=16){v>>=4;top+=4;}
            if(v>=4){v>>=2;top+=2;}
            if(v>=2)++top;
            int field=127+(int)top+exponent;
            bits=field>=255?0x7f800000u:((uint32_t)field<<23)|((mag<<(23-top))&0x7fffffu);
            if(value<0)bits|=0x80000000u;
        }
        memcpy(out+i,&bits,4);
    }
    return 1;
}
static int16_t pre_value(int32_t value,unsigned shift)
{
    int64_t v=value;
    uint64_t mag=(uint64_t)(v<0?-v:v),q,r,half;
    if(shift) {
        q=mag>>shift;r=mag- (q<<shift);half=UINT64_C(1)<<(shift-1);
        if(r>half || (r==half && (q&1)))++q;
    } else q=mag;
    v=v<0?-(int64_t)q:(int64_t)q;
    if(v>32767)v=32767;
    if(v< -32768)v= -32768;
    return (int16_t)v;
}
static int cpu_matrix(const int8_t *a,const int8_t *b,const int32_t *bias,
                      unsigned m,unsigned k,unsigned n,int32_t *out)
{
    unsigned i,j,t;
    for(i=0;i<m;i++)for(j=0;j<n;j++) {
        int64_t sum=bias[j];
        for(t=0;t<k;t++)sum+=(int32_t)a[(size_t)i*k+t]*b[(size_t)j*k+t];
        if(sum<INT32_MIN || sum>INT32_MAX)return 0;
        out[(size_t)i*n+j]=(int32_t)sum;
    }
    return 1;
}
int xqi_layer(const xqm_transport *io,const xqi_shape *s,const int8_t *input,
              const int8_t *weight,const int32_t *bias,const int64_t *shifts,
              const int8_t *lut,size_t lut_bytes,int32_t *acc,int16_t *pre,
              int16_t *out,xqm_stats *stats)
{
    unsigned oh,ow,k,m,row,j,i,c,ky,kx;
    size_t total;
    int8_t *cols=NULL;
    int32_t *values=NULL;
    int okay=0,direct=0;
    if(stats)memset(stats,0,sizeof(*stats));
    if(!s || !input || !weight || !bias || !shifts || !out ||
       (!io && !s->cpu_reference) || (io && s->cpu_reference) || s->cpu_reference>1 ||
       !s->batch || s->batch>300 || !s->cin || s->cin>(s->linear?65535u:1024u) || !s->cout || s->cout>1024 ||
       !s->height || !s->width || s->height>640 || s->width>640 ||
       !s->kh || !s->kw || s->kh>6 || s->kw>6 || !s->stride_h || !s->stride_w ||
       s->stride_h>8 || s->stride_w>8 || s->pad_h>8 || s->pad_w>8 ||
       !s->dilation_h || !s->dilation_w || s->dilation_h>8 || s->dilation_w>8 ||
       s->height+2*s->pad_h<s->dilation_h*(s->kh-1)+1 ||
       s->width+2*s->pad_w<s->dilation_w*(s->kw-1)+1 ||
       (lut_bytes!=0 && lut_bytes!=65536) || (lut_bytes && !lut) || s->linear>1)return 0;
    if(s->linear && (s->kh!=1 || s->kw!=1 || s->height!=1 || s->width!=1 ||
                     s->stride_h!=1 || s->stride_w!=1 || s->pad_h || s->pad_w))return 0;
    oh=(s->height+2*s->pad_h-s->dilation_h*(s->kh-1)-1)/s->stride_h+1;
    ow=(s->width+2*s->pad_w-s->dilation_w*(s->kw-1)-1)/s->stride_w+1;
    k=s->cin*s->kh*s->kw;m=s->batch*oh*ow;total=(size_t)m*s->cout;
    if(k>65535)return 0;
    if(total>640u*640u*256u || (size_t)s->batch*s->cin*s->height*s->width>640u*640u*256u)return 0;
    for(j=0;j<s->cout;j++)if(shifts[j]<0 || shifts[j]>62)return 0;
#ifdef XQ_NATIVE_DIRECT_PACK
    direct=io && s->kh==1 && s->kw==1 && s->stride_h==1 && s->stride_w==1 && !s->pad_h && !s->pad_w;
#endif
    if(!direct)cols=malloc((size_t)16*k);
    values=malloc((size_t)16*s->cout*sizeof(*values));
    if((!direct && !cols) || !values)goto done;
    for(row=0;row<m;row+=16) {
        unsigned mt=m-row<16?m-row:16;
        xqm_stats st={0,0};
        if(io && io->cancelled && io->cancelled(io->context))goto done;
        for(i=0;!direct && i<mt;i++) {
            unsigned pos=row+i,batch=pos/(oh*ow),y=(pos/ow)%oh,x=pos%ow;
            size_t n=0;
            int sy=(int)(y*s->stride_h)-(int)s->pad_h;
            int sx=(int)(x*s->stride_w)-(int)s->pad_w;
            int8_t *destination=cols+(size_t)i*k;
            if(s->linear) {
                memcpy(destination,input+(size_t)batch*s->cin,k);
                continue;
            }
            /* Interior patches have no padding branches. Copy each contiguous
             * kernel row from ordinary RAM; no aperture/MMIO access here. */
            if(sy>=0 && sx>=0 && s->dilation_w==1 &&
               (unsigned)sy+(s->kh-1)*s->dilation_h<s->height &&
               (unsigned)sx+s->kw<=s->width) {
                const int8_t *plane=input+(size_t)batch*s->cin*s->height*s->width+
                                    (unsigned)sy*s->width+(unsigned)sx;
                if(s->kh==1 && s->kw==1) {
                    for(c=0;c<s->cin;c++) {
                        destination[c]=*plane;plane+=(size_t)s->height*s->width;
                    }
                    continue;
                }
                for(c=0;c<s->cin;c++) {
                    for(ky=0;ky<s->kh;ky++) {
                        const int8_t *source=plane+(size_t)ky*s->dilation_h*s->width;
                        if(s->kw==3 || s->kw==6) {
                            destination[n]=source[0];destination[n+1]=source[1];destination[n+2]=source[2];
                            if(s->kw==6) {
                                destination[n+3]=source[3];destination[n+4]=source[4];destination[n+5]=source[5];
                            }
                        } else memcpy(destination+n,source,s->kw);
                        n+=s->kw;
                    }
                    plane+=(size_t)s->height*s->width;
                }
                continue;
            }
            for(c=0;c<s->cin;c++)for(ky=0;ky<s->kh;ky++)for(kx=0;kx<s->kw;kx++) {
                int iy=(int)(y*s->stride_h+ky*s->dilation_h)-(int)s->pad_h;
                int ix=(int)(x*s->stride_w+kx*s->dilation_w)-(int)s->pad_w;
                destination[n++]=iy<0 || ix<0 || iy>=(int)s->height || ix>=(int)s->width?0:
                    input[((size_t)batch*s->cin+c)*s->height*s->width+(unsigned)iy*s->width+(unsigned)ix];
            }
        }
        if(io) {
#ifdef XQ_NATIVE_DIRECT_PACK
            if(direct) {
                if(!xqn_resident_pointwise(io,input,(size_t)s->batch*s->cin*s->height*s->width,
                    weight,(size_t)s->cout*k,bias,s->cout,mt,k,s->cout,oh*ow,row,values,(size_t)mt*s->cout,&st))goto done;
            } else
#endif
            if(!xqm_matrix(io,cols,(size_t)mt*k,weight,(size_t)s->cout*k,bias,s->cout,
                           mt,k,s->cout,values,(size_t)mt*s->cout,&st))goto done;
        } else if(!cpu_matrix(cols,weight,bias,mt,k,s->cout,values))goto done;
        if(stats){stats->jobs+=st.jobs;stats->cycles+=st.cycles;}
        for(i=0;i<mt;i++)for(j=0;j<s->cout;j++) {
            unsigned pos=row+i,batch=pos/(oh*ow),spatial=pos%(oh*ow);
            size_t index=((size_t)batch*s->cout+j)*oh*ow+spatial;
            int32_t v=values[(size_t)i*s->cout+j];
            int16_t p=pre_value(v,(unsigned)shifts[j]);
            if(acc)acc[index]=v;
            if(pre)pre[index]=p;
            out[index]=lut_bytes?lut[(int)p+32768]:p;
        }
    }
    okay=1;
done:
    free(cols);free(values);return okay;
}
