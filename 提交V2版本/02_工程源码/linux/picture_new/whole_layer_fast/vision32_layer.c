/* Preserve the pinned Picture_new arithmetic; optimize compatible whole
 * convolutions, with hardware matrix tiling for every remaining shape. */
#define xqi_layer xqi_tiled_layer
#include "upstream/adapter/runtime/xq_int8_layer.c"
#undef xqi_layer
extern int xqv_run(const xqm_transport *,struct pango_vision32_job *);
static unsigned align4(unsigned n){return (n+3)&~3u;}
static int layout(struct pango_vision32_job *j,unsigned bytes,unsigned sizes[5])
{
    unsigned k=j->cin*j->kernel*j->kernel,groups=(j->cout+7)/8;
    j->weights=align4(j->height*j->width*align4(j->cin));
    j->params=j->weights+groups*k*8;
    j->output=align4(j->params+groups*8*12);
    return pango_vision32_sizes(j,bytes,sizes);
}
static __attribute__((noinline)) int xqi_whole_layer(const xqm_transport *io,const xqi_shape *s,const int8_t *input,
    const int8_t *weight,const int32_t *bias,const int64_t *shifts,
    const int8_t *lut,size_t lut_bytes,int32_t *acc,int16_t *pre,int16_t *out,xqm_stats *stats)
{
    struct pango_vision32_job j={0};
    unsigned oh,ow,k,ci4,groups,sizes[5],spatial;
    if(!io || !s || s->cpu_reference || s->linear || !s->batch || s->batch>300 ||
       !s->width || !s->height || !s->cin || !s->cout || s->cin>512 || s->cout>256 ||
       s->width>640 || s->height>640 || s->kh!=s->kw ||
       (s->kh!=1 && s->kh!=3 && s->kh!=6) || s->stride_h!=s->stride_w ||
       (s->stride_h!=1 && s->stride_h!=2) || s->pad_h!=s->pad_w || s->pad_h>=s->kh ||
       s->dilation_h!=1 || s->dilation_w!=1 || s->width+2*s->pad_w<s->kw ||
       s->height+2*s->pad_h<s->kh || s->cin*s->kh*s->kw>1152)
        return xqi_tiled_layer(io,s,input,weight,bias,shifts,lut,lut_bytes,acc,pre,out,stats);
    if(!io->shadow || io->bytes!=0x100000 || !input || !weight || !bias || !shifts || !out || (lut_bytes && (lut_bytes!=65536 || !lut)))return 0;
    for(unsigned c=0;c<s->cout;c++)if(shifts[c]<0 || shifts[c]>62)return 0;
    oh=(s->height+2*s->pad_h-s->kh)/s->stride_h+1;
    ow=(s->width+2*s->pad_w-s->kw)/s->stride_w+1;
    k=s->cin*s->kh*s->kw;ci4=align4(s->cin);groups=(s->cout+7)/8;spatial=oh*ow;
    j.abi_version=PANGO_VISION32_ABI;j.width=s->width;j.height=s->height;
    j.cin=s->cin;j.cout=s->cout;j.kernel=s->kh;j.stride=s->stride_h;j.padding=s->pad_h;
    j.input=0;j.weights=align4(s->height*s->width*ci4);
    j.params=j.weights+groups*k*8;j.output=align4(j.params+groups*8*12);
    j.lut=0;j.flags=2;j.timeout_cycles=49500000;j.timeout_us=1000000;
    if(!pango_vision32_sizes(&j,(uint32_t)io->bytes,sizes))
        return xqi_tiled_layer(io,s,input,weight,bias,shifts,lut,lut_bytes,acc,pre,out,stats);
    if(stats)memset(stats,0,sizeof(*stats));
    memset(io->shadow+j.weights,0,sizes[1]);memset(io->shadow+j.params,0,sizes[3]);
    for(unsigned co=0;co<s->cout;co++)for(unsigned ky=0;ky<s->kh;ky++)
        for(unsigned kx=0;kx<s->kw;kx++)for(unsigned ci=0;ci<s->cin;ci++){
            size_t to=j.weights+(((co/8*s->kh+ky)*s->kw+kx)*s->cin+ci)*8+co%8;
            io->shadow[to]=(uint8_t)weight[((size_t)co*s->cin+ci)*s->kh*s->kw+ky*s->kw+kx];
        }
    for(unsigned b=0;b<s->batch;b++){
        memset(io->shadow,0,sizes[0]);
        for(unsigned p=0;p<s->height*s->width;p++)for(unsigned c=0;c<s->cin;c++)
            io->shadow[p*ci4+c]=(uint8_t)input[((size_t)b*s->cin+c)*s->height*s->width+p];
        if(!xqv_run(io,&j))return 0;
        if(stats){stats->jobs++;stats->cycles+=j.cycles;}
        for(unsigned p=0;p<spatial;p++)for(unsigned c=0;c<s->cout;c++){
            int32_t raw;int64_t value;int16_t pv;
            size_t index=((size_t)b*s->cout+c)*spatial+p;
            memcpy(&raw,io->shadow+j.output+4*(p*s->cout+c),4);value=(int64_t)raw+bias[c];
            if(value<INT32_MIN || value>INT32_MAX)return 0;
            pv=pre_value((int32_t)value,(unsigned)shifts[c]);
            if(acc)acc[index]=(int32_t)value;
            if(pre)pre[index]=pv;
            out[index]=lut_bytes?lut[(int)pv+32768]:pv;
        }
    }
    return 1;
}

int xqi_layer(const xqm_transport *io,const xqi_shape *s,const int8_t *input,
    const int8_t *weight,const int32_t *bias,const int64_t *shifts,
    const int8_t *lut,size_t lut_bytes,int32_t *acc,int16_t *pre,int16_t *out,xqm_stats *stats)
{
    struct pango_vision32_job j={0};
    unsigned oh,ow,ci4,sizes[5],spatial,tw,th;
    int rectangles=0;
    if(!io || !s || s->cpu_reference || s->linear || !s->batch || s->batch>300 ||
       !s->width || !s->height || !s->cin || !s->cout || s->cin>512 || s->cout>256 ||
       s->width>640 || s->height>640 || s->kh!=s->kw ||
       (s->kh!=1 && s->kh!=3 && s->kh!=6) || s->stride_h!=s->stride_w ||
       (s->stride_h!=1 && s->stride_h!=2) || s->pad_h!=s->pad_w || s->pad_h>=s->kh ||
       s->dilation_h!=1 || s->dilation_w!=1 || s->width+2*s->pad_w<s->kw ||
       s->height+2*s->pad_h<s->kh || s->cin*s->kh*s->kw>1152)
        return xqi_tiled_layer(io,s,input,weight,bias,shifts,lut,lut_bytes,acc,pre,out,stats);
    if(!io->shadow || io->bytes!=0x100000 || !input || !weight || !bias || !shifts || !out || (lut_bytes && (lut_bytes!=65536 || !lut)))return 0;
    for(unsigned c=0;c<s->cout;c++)if(shifts[c]<0 || shifts[c]>62)return 0;
    oh=(s->height+2*s->pad_h-s->kh)/s->stride_h+1;
    ow=(s->width+2*s->pad_w-s->kw)/s->stride_w+1;
    ci4=align4(s->cin);spatial=oh*ow;tw=ow;th=oh;
    j.abi_version=PANGO_VISION32_ABI;j.width=s->width;j.height=s->height;
    j.cin=s->cin;j.cout=s->cout;j.kernel=s->kh;j.stride=s->stride_h;j.padding=s->pad_h;
    j.input=0;
    j.lut=0;j.flags=2;j.timeout_cycles=49500000;j.timeout_us=1000000;
    if(layout(&j,(unsigned)io->bytes,sizes))
        return xqi_whole_layer(io,s,input,weight,bias,shifts,lut,lut_bytes,acc,pre,out,stats);
    {
        unsigned max_side=(640-s->kh)/s->stride_h+1;
        unsigned low=0,high=oh<max_side?oh:max_side;
        rectangles=1;tw=ow<max_side?ow:max_side;j.padding=0;
        j.width=(tw-1)*s->stride_w+s->kw;
        /* Largest height that fits; all sizes increase monotonically. */
        while(low<high){
            unsigned mid=low+(high-low+1)/2;
            j.height=(mid-1)*s->stride_h+s->kh;
            if(layout(&j,(unsigned)io->bytes,sizes))low=mid;else high=mid-1;
        }
        if(!low)return xqi_tiled_layer(io,s,input,weight,bias,shifts,lut,lut_bytes,acc,pre,out,stats);
        th=low;j.height=(th-1)*s->stride_h+s->kh;
        if(!layout(&j,(unsigned)io->bytes,sizes))return 0;
    }
    if(stats)memset(stats,0,sizeof(*stats));
    memset(io->shadow+j.weights,0,sizes[1]);memset(io->shadow+j.params,0,sizes[3]);
    for(unsigned co=0;co<s->cout;co++)for(unsigned ky=0;ky<s->kh;ky++)
        for(unsigned kx=0;kx<s->kw;kx++)for(unsigned ci=0;ci<s->cin;ci++){
            size_t to=j.weights+(((co/8*s->kh+ky)*s->kw+kx)*s->cin+ci)*8+co%8;
            io->shadow[to]=(uint8_t)weight[((size_t)co*s->cin+ci)*s->kh*s->kw+ky*s->kw+kx];
        }
    for(unsigned b=0;b<s->batch;b++)for(unsigned ty=0;ty<oh;ty+=th)for(unsigned tx=0;tx<ow;tx+=tw){
        unsigned ny=oh-ty<th?oh-ty:th,nx=ow-tx<tw?ow-tx:tw;
        if(rectangles){j.width=(nx-1)*s->stride_w+s->kw;j.height=(ny-1)*s->stride_h+s->kh;}
        memset(io->shadow,0,j.height*j.width*ci4);
        for(unsigned y=0;y<j.height;y++)for(unsigned x=0;x<j.width;x++){
            int iy=rectangles?(int)(ty*s->stride_h+y)-(int)s->pad_h:(int)y;
            int ix=rectangles?(int)(tx*s->stride_w+x)-(int)s->pad_w:(int)x;
            if(iy<0 || ix<0 || iy>=(int)s->height || ix>=(int)s->width)continue;
            for(unsigned c=0;c<s->cin;c++)
                io->shadow[(y*j.width+x)*ci4+c]=(uint8_t)input[((size_t)b*s->cin+c)*s->height*s->width+(unsigned)iy*s->width+(unsigned)ix];
        }
        if(!xqv_run(io,&j))return 0;
        if(stats){stats->jobs++;stats->cycles+=j.cycles;}
        for(unsigned y=0;y<ny;y++)for(unsigned x=0;x<nx;x++)for(unsigned c=0;c<s->cout;c++){
            int32_t raw;int64_t value;int16_t pv;
            size_t index=((size_t)b*s->cout+c)*spatial+(ty+y)*ow+tx+x;
            memcpy(&raw,io->shadow+j.output+4*((y*nx+x)*s->cout+c),4);value=(int64_t)raw+bias[c];
            if(value<INT32_MIN || value>INT32_MAX)return 0;
            pv=pre_value((int32_t)value,(unsigned)shifts[c]);
            if(acc)acc[index]=(int32_t)value;
            if(pre)pre[index]=pv;
            out[index]=lut_bytes?lut[(int)pv+32768]:pv;
        }
    }
    return 1;
}
