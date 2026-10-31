#ifndef XQ_CONV_DISPATCH_H
#define XQ_CONV_DISPATCH_H
#include "xq_int8_layer.h"
#include <string.h>
#include <sys/ioctl.h>
/* ABI3 returns saturated S8, with ties-away rounding. Our general graph needs
 * ties-even S16+LUT. Only this provably exact, shift-zero, S8-bounded subset is
 * eligible; do not silently use ABI3 as an INT32 partial-sum interface. */
static int xqn_conv_eligible(const xqi_shape *s,const int8_t *w,const int32_t *bias,const int64_t *shift)
{
    if(!s || !w || !bias || !shift || s->batch!=1 || s->linear || !s->cin || s->cin>4 || !s->cout || s->cout>16 ||
       !s->height || s->height>320 || !s->width || s->width>320 || s->kh!=s->kw ||
       (s->kh!=1 && s->kh!=3 && s->kh!=6) || s->stride_h!=s->stride_w ||
       (s->stride_h!=1 && s->stride_h!=2) || s->pad_h!=s->pad_w || s->pad_h>=s->kh ||
       s->dilation_h!=1 || s->dilation_w!=1 || (s->cin*s->kh*s->kw+3)/4>32 ||
       s->height+2*s->pad_h<s->kh || s->width+2*s->pad_w<s->kw)return 0;
    unsigned k=s->cin*s->kh*s->kw;
    for(unsigned c=0;c<s->cout;c++) {
        int64_t lo=bias[c],hi=bias[c];if(shift[c])return 0;
        for(unsigned q=0;q<k;q++) {int v=w[c*k+q];lo+=v>=0?v*-128:v*127;hi+=v>=0?v*127:v*-128;}
        if(lo< -128 || hi>127)return 0;
    }
    return 1;
}
static int xqn_try_conv(const xqm_transport *io,const xqi_shape *s,const int8_t *input,const int8_t *w,
                        const int32_t *bias,const int64_t *shift,const int8_t *lut,size_t lut_bytes,
                        int32_t *acc,int16_t *pre,int16_t *out,xqm_stats *stats)
{
    if(!io || !io->context)return 0;
    xqm_linux *ctx=io->context;
    if(io!=&ctx->io || !ctx->conv_enabled || !(ctx->features&PANGO_MAC_FEATURE_CONV_COMPUTE) ||
       !xqn_conv_eligible(s,w,bias,shift))return 0;
    if(ctx->fd<0 || !input || !out || !io->shadow || io->bytes!=0x100000 ||
       (lut_bytes!=0 && lut_bytes!=65536) || (lut_bytes && !lut))return -1;
    unsigned oh=(s->height+2*s->pad_h-s->kh)/s->stride_h+1,ow=(s->width+2*s->pad_w-s->kw)/s->stride_w+1;
    unsigned pixels=s->height*s->width,k=s->cin*s->kh*s->kw,lines=(k+3)/4;
    unsigned wt=pixels*4,output=wt+lines*128,bo=(output+oh*ow*s->cout+3)&~3u,so=bo+64;
    if(so+16>io->bytes || (io->cancelled && io->cancelled(io->context)))return -1;
    /* Preprocess directly into private shadow; DMA may only read the 1MiB
     * aperture. Physical MMIO/bank access always stays inside the driver. */
    memset(io->shadow,0,wt+lines*128);
    for(unsigned p=0;p<pixels;p++)for(unsigned c=0;c<s->cin;c++)io->shadow[p*4+c]=(uint8_t)input[c*pixels+p];
    for(unsigned c=0;c<s->cout;c++)for(unsigned y=0;y<s->kh;y++)for(unsigned x=0;x<s->kw;x++)for(unsigned ic=0;ic<s->cin;ic++) {
        unsigned scalar=(y*s->kw+x)*s->cin+ic;
        io->shadow[wt+scalar/4*128+c*4+scalar%4]=(uint8_t)w[((c*s->cin+ic)*s->kh+y)*s->kw+x];
    }
    memset(io->shadow+bo,0,80);memcpy(io->shadow+bo,bias,s->cout*4);
    struct pango_mac_conv_job j={0};j.abi_version=3;j.flags=2;j.width=(uint16_t)s->width;j.height=(uint16_t)s->height;
    j.channels=(uint16_t)s->cin;j.output_channels=(uint16_t)s->cout;j.kernel=(uint8_t)s->kh;j.stride=(uint8_t)s->stride_h;
    j.padding=(uint8_t)s->pad_h;j.weight_lines=(uint16_t)lines;j.weight_offset=wt;j.output_offset=output;j.reserved[0]=bo;j.reserved[1]=so;j.timeout_us=1000000;
    if(ioctl(ctx->fd,PANGO_MAC_IOC_RUN_CONV,&j) || !(j.status&2) || (j.status&4) || j.error_code)return -1;
    for(unsigned c=0;c<s->cout;c++)for(unsigned p=0;p<oh*ow;p++) {
        unsigned at=c*oh*ow+p;int16_t v=(int8_t)io->shadow[output+p*s->cout+c];
        if(acc)acc[at]=v;
        if(pre)pre[at]=v;
        out[at]=lut_bytes?lut[v+32768]:v;
    }
    if(stats){stats->jobs=1;stats->cycles=j.cycles;}
    return 1;
}
#endif
