#include "xq_int8_layer.h"
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static xqm_linux device;
static unsigned jobs;
static int fail_next;
int __wrap_ioctl(int fd,unsigned long cmd,...)
{
    va_list ap;va_start(ap,cmd);struct pango_vision32_job *j=va_arg(ap,void *);va_end(ap);
    assert(fd==71 && cmd==PANGO_MAC_IOC_RUN_VISION32);
    if(fail_next){errno=fail_next;fail_next=0;return -1;}
    unsigned sizes[5];assert(pango_vision32_sizes(j,device.io.bytes,sizes));
    assert(j->flags==2);
    unsigned ow=(j->width+2*j->padding-j->kernel)/j->stride+1;
    unsigned oh=(j->height+2*j->padding-j->kernel)/j->stride+1;
    unsigned ci4=(j->cin+3)&~3u,k=j->cin*j->kernel*j->kernel;
    const int8_t *x=(const int8_t *)device.io.shadow+j->input;
    const int8_t *w=(const int8_t *)device.io.shadow+j->weights;
    for(unsigned y=0;y<oh;y++)for(unsigned xx=0;xx<ow;xx++)for(unsigned o=0;o<j->cout;o++){
        int32_t dot=0;
        for(unsigned ky=0;ky<j->kernel;ky++)for(unsigned kx=0;kx<j->kernel;kx++)for(unsigned c=0;c<j->cin;c++){
            int iy=(int)(y*j->stride+ky)-(int)j->padding,ix=(int)(xx*j->stride+kx)-(int)j->padding;
            int value=(iy<0 || ix<0 || iy>=(int)j->height || ix>=(int)j->width)?0:x[(iy*j->width+ix)*ci4+c];
            unsigned wi=((o/8)*k+(ky*j->kernel+kx)*j->cin+c)*8+o%8;
            dot+=value*w[wi];
        }
        memcpy(device.io.shadow+j->output+4*((y*ow+xx)*j->cout+o),&dot,4);
    }
    jobs++;j->status=2;j->error=0;j->cycles=k*((j->cout+7)/8)*((ow*oh+3)/4);return 0;
}
static void layer(unsigned batch,unsigned ci,unsigned co,unsigned w,unsigned h,unsigned k,unsigned stride,unsigned pad,unsigned dilation,int linear)
{
    xqi_shape s={batch,ci,h,w,co,k,k,stride,stride,pad,pad,dilation,dilation,(unsigned)linear,1};
    unsigned oh=(h+2*pad-dilation*(k-1)-1)/stride+1;
    unsigned ow=(w+2*pad-dilation*(k-1)-1)/stride+1;
    size_t ni=(size_t)batch*ci*w*h,nw=(size_t)ci*co*k*k,no=(size_t)batch*co*oh*ow;
    int8_t *x=malloc(ni),*wt=malloc(nw),*lut=malloc(65536);
    int32_t *bias=malloc(co*4),*a=malloc(no*4),*b=malloc(no*4);
    int64_t *shifts=malloc(co*8);
    int16_t *p=malloc(no*2),*q=malloc(no*2),*r=malloc(no*2),*t=malloc(no*2);
    assert(x && wt && lut && bias && a && b && shifts && p && q && r && t);
    for(size_t i=0;i<ni;i++)x[i]=(int8_t)(i*19+13);
    for(size_t i=0;i<nw;i++)wt[i]=(int8_t)((i*11)%31-15);
    for(size_t i=0;i<65536;i++)lut[i]=(int8_t)(i*71+9);
    for(unsigned i=0;i<co;i++){bias[i]=(int32_t)i*4093-793;shifts[i]=i%18;}
    xqm_stats stats;
    assert(xqi_layer(NULL,&s,x,wt,bias,shifts,lut,65536,a,p,r,NULL));
    s.cpu_reference=0;
    assert(xqi_layer(&device.io,&s,x,wt,bias,shifts,lut,65536,b,q,t,&stats));
    assert(!memcmp(a,b,no*4) && !memcmp(p,q,no*2) && !memcmp(r,t,no*2) && stats.jobs);
    if(w==640 && h==37)assert(stats.jobs>1 && stats.jobs<16); /* halo tiles, not tiny matrix jobs */
    unsigned before=jobs;fail_next=ETIMEDOUT;
    assert(!xqi_layer(&device.io,&s,x,wt,bias,shifts,lut,65536,b,q,t,NULL));assert(jobs==before);
    printf("PICTURE_NEW_LAYER_INTERFACE_PASS batch=%u ci=%u co=%u width=%u height=%u kernel=%u dilation=%u jobs=%llu\n",batch,ci,co,w,h,k,dilation,(unsigned long long)stats.jobs);
    free(x);free(wt);free(lut);free(bias);free(shifts);free(a);free(b);free(p);free(q);free(r);free(t);
}
int main(void)
{
    _Static_assert(sizeof(struct pango_vision32_job)==112,"ABI size");
    memset(&device,0,sizeof(device));device.fd=71;device.io.shadow=calloc(1,0x100000);
    device.io.bytes=0x100000;device.io.context=&device;assert(device.io.shadow);
    layer(1,3,8,192,2,1,1,0,1,0); /* board192 pitch */
    layer(1,3,16,640,6,6,2,2,1,0); /* detector640 first shape */
    layer(1,3,16,640,37,3,1,1,1,0); /* >1MiB output, padding/halo and tail tiles */
    layer(3,3,7,32,32,3,2,1,1,0); /* classifier dynamic batch */
    layer(1,128,17,3,3,3,1,0,1,0); /* exact K1152 */
    layer(3,1153,257,1,1,1,1,0,1,1); /* K/OC boundary + linear */
    layer(1,4,9,5,5,3,1,2,2,0); /* dilated hardware tiling */
    struct pango_vision32_job j={0};unsigned sizes[5];
    j.abi_version=1;j.width=j.height=j.cin=j.cout=j.kernel=j.stride=1;j.flags=2;
    j.weights=0x1000;j.params=0x2000;j.output=0x3000;j.timeout_cycles=16;
    assert(pango_vision32_sizes(&j,0x100000,sizes));
    for(unsigned i=1;i<32;i++){j.width=640+(1u<<i);assert(!pango_vision32_sizes(&j,0x100000,sizes));}
    j.width=1;j.output=0;assert(!pango_vision32_sizes(&j,0x100000,sizes));
    j.output=0xffffc;j.cout=2;assert(!pango_vision32_sizes(&j,0x100000,sizes));
    j.output=0x3000;j.reserved[3]=1;assert(!pango_vision32_sizes(&j,0x100000,sizes));
    free(device.io.shadow);puts("PICTURE_NEW_VISION32_INTERFACE_AND_NO_FALLBACK_PASS");return 0;
}
