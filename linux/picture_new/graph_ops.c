#include "graph_ops.h"
#include <limits.h>
#include <string.h>
#define XQG_OP_MAX_ELEMENTS (16u*1024u*1024u)
static int valid(const xqg_s16_view *v)
{
    if(!v || !v->data || !v->batch || v->batch>300 || !v->channels || v->channels>65535 ||
       !v->height || v->height>640 || !v->width || v->width>640 || v->exponent< -120 || v->exponent>120)return 0;
    size_t n=v->batch;
    if(n>XQG_OP_MAX_ELEMENTS/v->channels)return 0;
    n*=v->channels;if(n>XQG_OP_MAX_ELEMENTS/v->height)return 0;
    n*=v->height;if(n>XQG_OP_MAX_ELEMENTS/v->width)return 0;
    return n*v->width==v->count;
}
static int16_t sat(int32_t v) { return v>32767?32767:v< -32768?-32768:(int16_t)v; }
static int32_t right_even(int32_t v,unsigned shift)
{
    if(!shift)return v;
    if(shift>=32)return 0;
    uint32_t m=v<0?0u-(uint32_t)v:(uint32_t)v;
    uint32_t q=m>>shift,r=m&((1u<<shift)-1u),half=1u<<(shift-1);
    if(r>half || (r==half && (q&1u)))q++;
    return v<0?-(int32_t)q:(int32_t)q;
}
static int32_t divide_even(int32_t v,unsigned denominator)
{
    uint32_t m=v<0?0u-(uint32_t)v:(uint32_t)v,q=m/denominator,r=m%denominator;
    if(r*2>denominator || (r*2==denominator && (q&1u)))q++;
    return v<0?-(int32_t)q:(int32_t)q;
}
int xqg_op_run(unsigned type,const xqg_s16_view *inputs,unsigned input_count,
               int16_t *out,size_t capacity,const xqg_s16_lut *lut,xqg_s16_view *result)
{
    if(!result)return 0;
    memset(result,0,sizeof(*result));
    if(!inputs || !input_count || input_count>4 || !out || type<3 || type>11)return 0;
    for(unsigned i=0;i<input_count;i++)if(!valid(&inputs[i]))return 0;
    const xqg_s16_view *a=inputs;
    xqg_s16_view o=*a;o.data=out;
    if(type!=7 && input_count!=(type==8?2u:1u))return 0;
    if(type==5 || type==6){
        if(a->height>320 || a->width>320 || a->count>XQG_OP_MAX_ELEMENTS/4)return 0;
        o.height*=2;o.width*=2;o.count*=4;
    } else if(type==7){
        o.channels=0;
        for(unsigned i=0;i<input_count;i++){
            const xqg_s16_view *v=inputs+i;
            if(v->batch!=a->batch || v->height!=a->height || v->width!=a->width || o.channels>65535-v->channels)return 0;
            o.channels+=v->channels;if(v->exponent>o.exponent)o.exponent=v->exponent;
        }
        size_t plane=(size_t)a->batch*a->height*a->width;
        if(plane>XQG_OP_MAX_ELEMENTS/o.channels)return 0;
        o.count=plane*o.channels;
    } else if(type==8){
        const xqg_s16_view *b=inputs+1;
        if(b->batch!=a->batch || b->channels!=a->channels || b->height!=a->height || b->width!=a->width)return 0;
        if(b->exponent>o.exponent)o.exponent=b->exponent;
    } else if(type==9){
        /* <=65536 S16 values guarantee I32 accumulation, including -32768.
         * The delivered PieceCNN GAP uses <=16 pixels per channel. */
        if((size_t)a->height*a->width>65536)return 0;
        o.height=o.width=1;o.count=(size_t)a->batch*a->channels;
    } else if(type==3){
        if(!lut || !lut->data || lut->count!=65536 || lut->input_exponent!=a->exponent || lut->output_exponent!=-15)return 0;
        o.exponent=-15;
    }
    if(capacity<o.count)return 0;
    if(type==8){
        unsigned da=(unsigned)(o.exponent-a->exponent),db=(unsigned)(o.exponent-inputs[1].exponent);
        for(size_t i=0;i<o.count;i++)out[i]=sat(right_even(a->data[i],da)+right_even(inputs[1].data[i],db));
    } else if(type==7){
        unsigned at=0;size_t pixels=(size_t)a->height*a->width;
        for(unsigned i=0;i<input_count;i++){
            const xqg_s16_view *v=inputs+i;
            size_t n=(size_t)v->channels*pixels;unsigned shift=(unsigned)(o.exponent-v->exponent);
            for(unsigned b=0;b<a->batch;b++){
                int16_t *to=out+((size_t)b*o.channels+at)*pixels;const int16_t *from=v->data+(size_t)b*n;
                if(!shift)memcpy(to,from,n*2);
                else for(size_t j=0;j<n;j++)to[j]=(int16_t)right_even(from[j],shift);
            }
            at+=v->channels;
        }
    } else if(type==5 || type==6){
        for(unsigned b=0;b<a->batch;b++)for(unsigned c=0;c<a->channels;c++){
            const int16_t *from=a->data+((size_t)b*a->channels+c)*a->height*a->width;
            int16_t *to=out+((size_t)b*o.channels+c)*o.height*o.width;
            for(unsigned y=0;y<o.height;y++)for(unsigned x=0;x<o.width;x++){
                if(type==5)to[(size_t)y*o.width+x]=from[(size_t)(y/2)*a->width+x/2];
                else {
                    /* align_corners=false: max(0,(2*y-1)/4), entirely integer.
                     * Numerators sum to 16, per the authoritative Oct25
                     * adjudication; the initial spec's extra /4 is invalid. */
                    unsigned sy=y?2*y-1:0,sx=x?2*x-1:0,y0=sy/4,x0=sx/4,fy=sy%4,fx=sx%4;
                    unsigned y1=y0+1<a->height?y0+1:y0,x1=x0+1<a->width?x0+1:x0;
                    int32_t sum=(int32_t)((4-fy)*(4-fx))*from[(size_t)y0*a->width+x0]+
                        (int32_t)((4-fy)*fx)*from[(size_t)y0*a->width+x1]+
                        (int32_t)(fy*(4-fx))*from[(size_t)y1*a->width+x0]+
                        (int32_t)(fy*fx)*from[(size_t)y1*a->width+x1];
                    to[(size_t)y*o.width+x]=sat(right_even(sum,4));
                }
            }
        }
    } else if(type==4){
        for(unsigned b=0;b<a->batch;b++)for(unsigned c=0;c<a->channels;c++){
            size_t base=((size_t)b*a->channels+c)*a->height*a->width;
            for(unsigned y=0;y<a->height;y++)for(unsigned x=0;x<a->width;x++){
                int16_t maximum=INT16_MIN;
                for(int dy=-2;dy<=2;dy++)for(int dx=-2;dx<=2;dx++){
                    int yy=(int)y+dy,xx=(int)x+dx;
                    if(yy>=0 && yy<(int)a->height && xx>=0 && xx<(int)a->width){
                        int16_t v=a->data[base+(size_t)yy*a->width+(unsigned)xx];if(v>maximum)maximum=v;
                    }
                }
                out[base+(size_t)y*a->width+x]=maximum;
            }
        }
    } else if(type==9){
        unsigned pixels=a->height*a->width;
        for(size_t bc=0;bc<(size_t)a->batch*a->channels;bc++){
            int32_t sum=0;for(unsigned i=0;i<pixels;i++)sum+=a->data[bc*pixels+i];
            out[bc]=sat(divide_even(sum,pixels));
        }
    } else if(type==3){
        for(size_t i=0;i<a->count;i++)out[i]=lut->data[(int32_t)a->data[i]+32768];
    } else if(type==10)memcpy(out,a->data,a->count*2);
    else if(type==11)for(size_t i=0;i<a->count;i++)out[i]=a->data[i]>0?a->data[i]:0;
    *result=o;return 1;
}
