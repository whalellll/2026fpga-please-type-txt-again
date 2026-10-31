#include "xq_conv_dispatch.h"
#include <assert.h>
#include <stdarg.h>
#include <stdlib.h>
#include <stdio.h>
static xqm_linux ctx;static unsigned calls,fail;
int __wrap_ioctl(int fd,unsigned long request,...)
{
    assert(fd==42 && request==PANGO_MAC_IOC_RUN_CONV);++calls;if(fail)return -1;
    va_list ap;va_start(ap,request);struct pango_mac_conv_job *j=va_arg(ap,void *);va_end(ap);
    assert(j->abi_version==3 && j->flags==2 && !j->channel_tile);
    unsigned oh=(j->height+2*j->padding-j->kernel)/j->stride+1,ow=(j->width+2*j->padding-j->kernel)/j->stride+1;
    for(unsigned y=0;y<oh;y++)for(unsigned x=0;x<ow;x++)for(unsigned c=0;c<j->output_channels;c++) {
        int32_t v;memcpy(&v,ctx.io.shadow+j->reserved[0]+c*4,4);
        for(unsigned ky=0;ky<j->kernel;ky++)for(unsigned kx=0;kx<j->kernel;kx++)for(unsigned ic=0;ic<j->channels;ic++) {
            int sy=(int)(y*j->stride+ky)-j->padding,sx=(int)(x*j->stride+kx)-j->padding;
            unsigned scalar=(ky*j->kernel+kx)*j->channels+ic;
            if(sy>=0 && sx>=0 && sy<j->height && sx<j->width)
                v+=(int8_t)ctx.io.shadow[(sy*j->width+sx)*4+ic]*(int8_t)ctx.io.shadow[j->weight_offset+scalar/4*128+c*4+scalar%4];
        }
        assert(v>=-128 && v<=127);ctx.io.shadow[j->output_offset+(y*ow+x)*j->output_channels+c]=(uint8_t)v;
    }
    j->status=2;j->cycles=123;return 0;
}
int main(void)
{
    ctx.fd=42;ctx.io.context=&ctx;ctx.io.shadow=calloc(1,0x100000);ctx.io.bytes=0x100000;ctx.conv_enabled=1;ctx.features=PANGO_MAC_FEATURE_CONV_COMPUTE;
    xqi_shape s={1,3,7,9,2,3,3,2,2,1,1,1,1,0,0};
    int8_t input[3*7*9],w[54]={0};int32_t bias[2]={0},acc[40];int64_t shift[2]={0};int16_t pre[40],out[40];xqm_stats stats;
    w[0]=1;w[27+13]=1;for(unsigned i=0;i<sizeof(input);i++)input[i]=(int8_t)(i*31);
    assert(xqn_conv_eligible(&s,w,bias,shift));
    assert(xqn_try_conv(&ctx.io,&s,input,w,bias,shift,NULL,0,acc,pre,out,&stats)==1 && calls==1);
    for(unsigned c=0;c<2;c++)for(unsigned y=0;y<4;y++)for(unsigned x=0;x<5;x++) {
        int ky=c?1:0,kx=c?1:0,ic=c?1:0,sy=(int)y*2+ky-1,sx=(int)x*2+kx-1;
        int expected=sy<0 || sx<0 || sy>=7 || sx>=9?0:input[(ic*7+sy)*9+sx];unsigned at=(c*4+y)*5+x;
        assert(out[at]==expected && pre[at]==expected && acc[at]==expected);
    }
    shift[0]=1;assert(!xqn_conv_eligible(&s,w,bias,shift));shift[0]=0;
    w[0]=2;assert(!xqn_conv_eligible(&s,w,bias,shift));w[0]=1;
    s.width=640;assert(!xqn_conv_eligible(&s,w,bias,shift));s.width=9;
    ctx.features=0;assert(!xqn_try_conv(&ctx.io,&s,input,w,bias,shift,NULL,0,acc,pre,out,&stats));ctx.features=PANGO_MAC_FEATURE_CONV_COMPUTE;
    fail=1;assert(xqn_try_conv(&ctx.io,&s,input,w,bias,shift,NULL,0,acc,pre,out,&stats)==-1);
    free(ctx.io.shadow);puts("CONV_DISPATCH_PASS exact_subset padding_stride_tail capability_gate no_error_fallback");return 0;
}
