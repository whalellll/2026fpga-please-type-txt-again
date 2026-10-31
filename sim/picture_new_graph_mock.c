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
 fprintf(stderr,"PICTURE_GRAPH_MOCK_JOBS=%u\n",total_jobs);return 0;
}
int __wrap_ioctl(int fd,unsigned long cmd,...){
 va_list ap;va_start(ap,cmd);void *arg=va_arg(ap,void *);va_end(ap);assert(fd==771);
 if(cmd==PANGO_MAC_IOC_GET_INFO){
  struct pango_mac_info *i=arg;memset(i,0,sizeof(*i));i->abi_version=1;
  i->device_id=PANGO_MAC_PIKAFISH_ID;i->device_version=PANGO_MAC_PIKAFISH_VERSION;
  i->scratch_bytes=0x100000;i->features=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|PANGO_MAC_FEATURE_VISION32;return 0;
 }
 assert(cmd==PANGO_MAC_IOC_RUN_VISION32 && shadow);
 struct pango_vision32_job *j=arg;unsigned sizes[5];
 assert(pango_vision32_sizes(j,0x100000,sizes) && j->flags==2);
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
  memcpy(shadow+j->output+4*((y*ow+xx)*j->cout+o),&result,4);
 }
 total_jobs++;j->status=2;j->error=0;j->cycles=0;return 0;
}
