/* Host-only full-graph device oracle: scalar NHWC/OIHW dot, no timing claim. */
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
static unsigned char *shadow;
static unsigned total_jobs;
static unsigned test_fail_after;
unsigned xqih_test_job_count(void){return total_jobs;}
void xqih_test_fail_after(unsigned count){test_fail_after=count;}
static unsigned exact_jobs,raw_jobs;
static unsigned long long exact_output_bytes;
#include "vision_exact_capture.h"
extern int __real_open(const char *,int,...);
extern int __real_close(int);
extern void *__real_mmap(void *,size_t,int,int,int,off_t);
extern int __real_munmap(void *,size_t);
int __wrap_open(const char *path,int flags,...){
 if(!strcmp(path,"/dev/pango-mac0"))return 771;
 if(flags&O_CREAT){va_list ap;va_start(ap,flags);int mode=va_arg(ap,int);va_end(ap);return __real_open(path,flags,mode);}
 return __real_open(path,flags);
}
int __wrap_close(int fd){return fd==771?0:__real_close(fd);}
void *__wrap_mmap(void *a,size_t bytes,int prot,int flags,int fd,off_t off){
 if(fd!=771)return __real_mmap(a,bytes,prot,flags,fd,off);
 assert(!a && !off && bytes==0x100000 && !shadow);shadow=calloc(1,bytes);assert(shadow);return shadow;
}
int __wrap_munmap(void *a,size_t bytes){
 if(a!=shadow)return __real_munmap(a,bytes);
 assert(bytes==0x100000);free(shadow);shadow=NULL;
 fprintf(stderr,"PICTURE_GRAPH_MOCK_JOBS=%u exact=%u raw=%u output_bytes=%llu\n",total_jobs,exact_jobs,raw_jobs,exact_output_bytes);return 0;
}
int __wrap_ioctl(int fd,unsigned long cmd,...){
 va_list ap;va_start(ap,cmd);void *arg=va_arg(ap,void *);va_end(ap);assert(fd==771);
 if(cmd==PANGO_MAC_IOC_GET_INFO){
  struct pango_mac_info *i=arg;memset(i,0,sizeof(*i));i->abi_version=1;
  i->device_id=PANGO_MAC_PIKAFISH_ID;i->device_version=PANGO_MAC_PIKAFISH_VERSION;
  i->scratch_bytes=0x100000;i->max_timeout_us=1000000;i->features=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|PANGO_MAC_FEATURE_VISION32;
  if(!getenv("VISION_EXACT_OLD_DEVICE"))i->features|=PANGO_MAC_FEATURE_VISION32_EXACT;
  if(!getenv("VISION_TRANSFER_OLD_DRIVER"))i->features|=PANGO_MAC_FEATURE_VISION32_REUSE;
  return 0;
 }
 assert(cmd==PANGO_MAC_IOC_RUN_VISION32 && shadow);
 if(test_fail_after && total_jobs>=test_fail_after){errno=EIO;return -1;}
 struct pango_vision32_job *j=arg;unsigned sizes[5];
 assert(pango_vision32_sizes(j,0x100000,sizes) && (j->flags==2 || j->flags==4 || j->flags==5));
 if(getenv("VISION_EXACT_OLD_DEVICE"))assert(j->flags==2);
 /* Model a physical parameter lease and verify that its bytes are immutable.
  * The actual kernel function is independently exercised by driver harnesses. */
 {static unsigned generation,offsets[3],lengths[3];static unsigned char cached[1048576];
  unsigned at[3]={j->weights,j->params,j->lut},len[3]={sizes[1],sizes[3],sizes[4]};
  int hit=j->reserved[0]==PANGO_VISION32_REUSE_PARAMS && generation==j->model_generation &&
      !memcmp(at,offsets,sizeof(at)) && !memcmp(len,lengths,sizeof(len));
  if(hit)for(unsigned z=0;z<3;z++)assert(!memcmp(cached+at[z],shadow+at[z],len[z]));
  else for(unsigned z=0;z<3;z++)memcpy(cached+at[z],shadow+at[z],len[z]);
  generation=j->reserved[0]==PANGO_VISION32_REUSE_PARAMS?j->model_generation:0;
  memcpy(offsets,at,sizeof(at));memcpy(lengths,len,sizeof(len));j->frame_id=(unsigned)hit;
 }
 if(!total_jobs && (j->flags&4) && getenv("VISION_EXACT_CAPTURE"))capture_exact(j,getenv("VISION_EXACT_CAPTURE"));
 unsigned ow=(j->width+2*j->padding-j->kernel)/j->stride+1;
 unsigned oh=(j->height+2*j->padding-j->kernel)/j->stride+1;
 unsigned ci4=(j->cin+3)&~3u,k=j->cin*j->kernel*j->kernel;
 const int8_t *x=(const int8_t *)shadow+j->input,*w=(const int8_t *)shadow+j->weights;
 for(unsigned y=0;y<oh;y++)for(unsigned xx=0;xx<ow;xx++)for(unsigned o=0;o<j->cout;o++){
  int64_t dot=0;
  for(unsigned ky=0;ky<j->kernel;ky++)for(unsigned kx=0;kx<j->kernel;kx++){
   int iy=(int)(y*j->stride+ky)-(int)j->padding,ix=(int)(xx*j->stride+kx)-(int)j->padding;
   if(iy<0 || ix<0 || iy>=(int)j->height || ix>=(int)j->width)continue;
   unsigned wi=((o/8)*k+(ky*j->kernel+kx)*j->cin)*8+o%8;
   const int8_t *row=x+(iy*j->width+ix)*ci4;
   for(unsigned c=0;c<j->cin;c++)dot+=(int32_t)row[c]*w[wi+c*8];
  }
  assert(dot>=INT32_MIN && dot<=INT32_MAX);int32_t result=(int32_t)dot;
  if(j->flags==2)memcpy(shadow+j->output+4*((y*ow+xx)*j->cout+o),&result,4);
  else {
   int32_t bias;uint32_t scale,shift;
   memcpy(&bias,shadow+j->params+o*12,4);memcpy(&scale,shadow+j->params+o*12+4,4);memcpy(&shift,shadow+j->params+o*12+8,4);
   assert(scale==1 && shift<=62);int64_t value=dot+bias;
   if(value<INT32_MIN || value>INT32_MAX){errno=EIO;return -1;}
   uint64_t mag=value<0?(uint64_t)-value:(uint64_t)value,q=mag>>shift;
   if(shift){uint64_t rem=mag-(q<<shift),half=UINT64_C(1)<<(shift-1);if(rem>half || (rem==half && (q&1)))q++;}
   value=value<0?-(int64_t)q:(int64_t)q;
   int16_t v=value>32767?32767:value< -32768?-32768:(int16_t)value;
   if(j->flags==5)v=((const int8_t *)shadow+j->lut)[(int)v+32768];
   memcpy(shadow+j->output+2*((y*ow+xx)*j->cout+o),&v,2);
  }
 }
 total_jobs++;
 if(j->flags&4){exact_jobs++;exact_output_bytes+=sizes[2];}else raw_jobs++;
 j->status=2;j->error=0;j->cycles=0;return 0;
}
