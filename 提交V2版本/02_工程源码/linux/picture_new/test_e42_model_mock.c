/* Test-only serialized physical aperture plus eight private fd shadows.
 * Scalar dots/rounding are independent from graph/epilogue implementations.
 * Never linked into deployment; counters/times are not FPGA measurements. */
#define _POSIX_C_SOURCE 200809L
#include "xq_mac.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
static struct {int used;unsigned char *shadow;} contexts[8];
static unsigned char *physical;
static int owner=-1;
static unsigned key[11],attempts,jobs,raw_jobs,exact_jobs,fail_at;
unsigned xqtest_jobs(void){return jobs;}
unsigned xqtest_attempts(void){return attempts;}
unsigned xqtest_raw_jobs(void){return raw_jobs;}
unsigned xqtest_exact_jobs(void){return exact_jobs;}
void xqtest_fail_at(unsigned n){fail_at=n;}
extern int __real_open(const char *,int,...),__real_close(int);
extern void *__real_mmap(void *,size_t,int,int,int,off_t);
extern int __real_munmap(void *,size_t);
int __wrap_open(const char *path,int flags,...)
{
    if(!strcmp(path,"/dev/pango-mac0")){
        for(unsigned i=0;i<8;i++)if(!contexts[i].used){contexts[i].used=1;return 1000+(int)i;}
        errno=EMFILE;return -1;
    }
    if(flags&O_CREAT){va_list ap;va_start(ap,flags);int mode=va_arg(ap,int);va_end(ap);return __real_open(path,flags,mode);}
    return __real_open(path,flags);
}
int __wrap_close(int fd)
{
    if(fd<1000 || fd>=1008)return __real_close(fd);
    unsigned slot=(unsigned)(fd-1000);assert(contexts[slot].used && !contexts[slot].shadow);
    if(owner==(int)slot)owner=-1;
    contexts[slot].used=0;return 0;
}
void *__wrap_mmap(void *a,size_t n,int prot,int flags,int fd,off_t off)
{
    if(fd<1000 || fd>=1008)return __real_mmap(a,n,prot,flags,fd,off);
    unsigned slot=(unsigned)(fd-1000);assert(contexts[slot].used && !contexts[slot].shadow && !a && n==0x100000 && !off);
    if(!physical){physical=calloc(1,n);assert(physical);}
    contexts[slot].shadow=calloc(1,n);assert(contexts[slot].shadow);return contexts[slot].shadow;
}
int __wrap_munmap(void *a,size_t n)
{
    for(unsigned i=0;i<8;i++)if(contexts[i].shadow==a && a){assert(n==0x100000);free(a);contexts[i].shadow=NULL;return 0;}
    return __real_munmap(a,n);
}
int __wrap_ioctl(int fd,unsigned long cmd,...)
{
    assert(fd>=1000 && fd<1008);unsigned slot=(unsigned)(fd-1000);assert(contexts[slot].used);
    va_list ap;va_start(ap,cmd);void *arg=va_arg(ap,void *);va_end(ap);
    if(cmd==PANGO_MAC_IOC_GET_INFO){
        struct pango_mac_info *i=arg;memset(i,0,sizeof(*i));i->abi_version=1;
        i->device_id=PANGO_MAC_PIKAFISH_ID;i->device_version=PANGO_MAC_PIKAFISH_VERSION;
        i->scratch_bytes=0x100000;i->max_timeout_us=1000000;
        i->features=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|
                    PANGO_MAC_FEATURE_VISION32|PANGO_MAC_FEATURE_VISION32_EXACT|PANGO_MAC_FEATURE_VISION32_REUSE;
        return 0;
    }
    assert(cmd==PANGO_MAC_IOC_RUN_VISION32 && contexts[slot].shadow && physical);
    struct pango_vision32_job *j=arg;unsigned sizes[5],offsets[5]={j->input,j->weights,j->output,j->params,j->lut};
    assert(pango_vision32_sizes(j,0x100000,sizes) && (j->flags==2 || j->flags==4 || j->flags==5));
    ++attempts;
    if(fail_at && attempts>=fail_at){owner=-1;j->status=6;j->error=1;errno=EIO;return -1;}
    unsigned next[11]={j->model_generation,j->weights,sizes[1],j->params,sizes[3],j->lut,sizes[4],j->flags,j->cin,j->cout,j->kernel};
    int reusable=j->reserved[0]==PANGO_VISION32_REUSE_PARAMS;
    int hit=reusable && owner==(int)slot && !memcmp(key,next,sizeof(key));
    unsigned char *shadow=contexts[slot].shadow;owner=-1;
    for(unsigned i=0;i<5;i++)if(i!=2 && sizes[i]){
        if(hit && i!=0)assert(!memcmp(physical+offsets[i],shadow+offsets[i],sizes[i]));
        else memcpy(physical+offsets[i],shadow+offsets[i],sizes[i]);
    }
    unsigned ow=(j->width+2*j->padding-j->kernel)/j->stride+1,oh=(j->height+2*j->padding-j->kernel)/j->stride+1;
    unsigned ci4=(j->cin+3)&~3u,k=j->cin*j->kernel*j->kernel;
    const int8_t *input=(const int8_t *)physical+j->input,*weights=(const int8_t *)physical+j->weights;
    for(unsigned y=0;y<oh;y++)for(unsigned x=0;x<ow;x++)for(unsigned o=0;o<j->cout;o++){
        int64_t dot=0;
        for(unsigned ky=0;ky<j->kernel;ky++)for(unsigned kx=0;kx<j->kernel;kx++){
            int yy=(int)(y*j->stride+ky)-(int)j->padding,xx=(int)(x*j->stride+kx)-(int)j->padding;
            if(yy<0 || xx<0 || yy>=(int)j->height || xx>=(int)j->width)continue;
            unsigned wi=((o/8)*k+(ky*j->kernel+kx)*j->cin)*8+o%8;
            for(unsigned c=0;c<j->cin;c++)dot+=(int32_t)input[((unsigned)yy*j->width+(unsigned)xx)*ci4+c]*weights[wi+c*8];
        }
        assert(dot>=INT32_MIN && dot<=INT32_MAX);size_t at=((size_t)y*ow+x)*j->cout+o;
        if(j->flags==2){int32_t v=(int32_t)dot;memcpy(physical+j->output+at*4,&v,4);}
        else{
            int32_t bias;uint32_t scale,shift;
            memcpy(&bias,physical+j->params+o*12,4);memcpy(&scale,physical+j->params+o*12+4,4);memcpy(&shift,physical+j->params+o*12+8,4);
            assert(scale==1 && shift<=62);int64_t v=dot+bias;
            if(v<INT32_MIN || v>INT32_MAX){j->status=6;j->error=1;errno=EIO;return -1;}
            uint64_t mag=v<0?(uint64_t)-v:(uint64_t)v,q=mag>>shift;
            if(shift){uint64_t rem=mag-(q<<shift),half=UINT64_C(1)<<(shift-1);q+=rem>half || (rem==half && (q&1));}
            v=v<0?-(int64_t)q:(int64_t)q;
            int16_t out=v>32767?32767:v< -32768?-32768:(int16_t)v;
            if(j->flags==5)out=((const int8_t *)physical+j->lut)[(int)out+32768];
            memcpy(physical+j->output+at*2,&out,2);
        }
    }
    memcpy(shadow+j->output,physical+j->output,sizes[2]);
    if(reusable){owner=(int)slot;memcpy(key,next,sizeof(key));j->frame_id=(unsigned)hit;}
    j->status=2;j->error=0;j->cycles=0;++jobs;
    if(j->flags==2)++raw_jobs;else ++exact_jobs;
    return 0;
}
