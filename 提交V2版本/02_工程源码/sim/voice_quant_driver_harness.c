#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include "pango_voice_uapi.h"
typedef uint32_t u32;typedef int64_t ktime_t;
#define __user
#define IS_ERR(p) (!(p))
#define PTR_ERR(p) (-ENOMEM)
struct pango_voice_dev {
 unsigned char *regs;bool cnn_supported,cnn_loaded,cnn_quant_supported,cnn_quant_loaded;
 u32 cnn_k,cnn_cout,cnn_generation;
};
static unsigned char regs[256];static unsigned writes,starts,mode,params;
static int64_t ticks;
static void *memdup_user(const void *p,size_t n){void *q=malloc(n);if(q)memcpy(q,p,n);return q;}
static int copy_to_user(void *p,const void *q,size_t n){memcpy(p,q,n);return 0;}
static void kfree(void *p){free(p);}
static uint32_t get_unaligned_le32(const void *p){uint32_t v;memcpy(&v,p,4);return v;}
static void mb(void){}static void wmb(void){}static void rmb(void){}static void cpu_relax(void){}static void cond_resched(void){}
static ktime_t ktime_get(void){return ++ticks;}
static ktime_t ktime_add_us(ktime_t a,u32 b){return a+b;}
static int ktime_compare(ktime_t a,ktime_t b){return (a>b)-(a<b);}
static void writel(u32 value,void *p){
 unsigned off=(unsigned)((unsigned char *)p-regs);assert(off<256 && !(off&3));writes++;
 memcpy(regs+off,&value,4);
 if(off==0x88){
  if(value&2){u32 zero=0;memcpy(regs+0x8c,&zero,4);}
  if(value&4){u32 zero=0;memcpy(regs+0xb4,&zero,4);params=0;}
  if(value&1){u32 status=mode==1?1:mode==2?6:2;memcpy(regs+0x8c,&status,4);starts++;}
 }
 if(off==0x94){u32 count=get_unaligned_le32(regs+0xb4)+1;memcpy(regs+0xb4,&count,4);}
 if(off==0xcc){u32 index=get_unaligned_le32(regs+0xc0);params|=1u<<index;memcpy(regs+0xe0,&params,4);}
}
static u32 readl(const void *p){
 unsigned off=(unsigned)((const unsigned char *)p-regs);assert(off<256 && !(off&3));
 if(off==0xb0)return get_unaligned_le32(regs+0xbc)?(u32)-2:42;
 return get_unaligned_le32(p);
}
/* ACTUAL_VOICE_CNN_IOCTL */
int main(void){
 struct pango_voice_dev v={.regs=regs,.cnn_supported=true,.cnn_quant_supported=true};
 struct pango_voice_cnn_model model={.abi_version=1,.k=8,.cout=2};
 struct pango_voice_cnn_quant q={.abi_version=1,.cout=2,.clamp_lo=(u32)-32768,.clamp_hi=32767,
  .multiplier={1,1073741824},.shift={1,60}};
 struct pango_voice_cnn_tile t={.abi_version=1,.pixels=3,.timeout_us=100};
 assert(!voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_MODEL,(unsigned long)&model));
 q.generation=t.generation=model.generation;
 assert(voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_QTILE,(unsigned long)&t)==-EOPNOTSUPP);
 unsigned before=writes;q.generation++;
 assert(voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_QUANT,(unsigned long)&q)==-ESTALE && writes==before);q.generation--;
 q.multiplier[0]=0;
 assert(voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_QUANT,(unsigned long)&q)==-EINVAL && writes==before);q.multiplier[0]=1;
 q.shift[1]=61;
 assert(voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_QUANT,(unsigned long)&q)==-EINVAL && writes==before);q.shift[1]=60;
 q.reserved[0]=1;
 assert(voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_QUANT,(unsigned long)&q)==-EINVAL && writes==before);q.reserved[0]=0;
 assert(!voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_QUANT,(unsigned long)&q) && v.cnn_quant_loaded);
 assert(!voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_QTILE,(unsigned long)&t) && starts==1);
 assert(t.status==2 && (int32_t)t.output[5]==-2 && !t.output[6]);
 assert(!voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_TILE,(unsigned long)&t) && t.output[0]==42);
 before=writes;t.generation++;
 assert(voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_QTILE,(unsigned long)&t)==-ESTALE && writes==before);t.generation--;
 mode=1;t.timeout_us=2;memset(t.output,0xa5,sizeof(t.output));
 assert(voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_QTILE,(unsigned long)&t)==-ETIMEDOUT);
 assert(!v.cnn_loaded && !v.cnn_quant_loaded && t.output[0]==0xa5a5a5a5);
 assert(voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_QTILE,(unsigned long)&t)==-ENODATA);
 model.generation=0;mode=0;
 assert(!voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_MODEL,(unsigned long)&model));
 assert(model.generation==2 && !v.cnn_quant_loaded);
 q.generation=model.generation;
 assert(!voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_QUANT,(unsigned long)&q));
 t.generation=model.generation;mode=2;
 assert(voice_ioctl_locked(&v,PANGO_VOICE_IOC_CNN_QTILE,(unsigned long)&t)==-EIO);
 assert(!v.cnn_loaded && !v.cnn_quant_loaded);
 puts("ACTUAL_VOICE_QUANT_DRIVER_GENERATION_REJECT_TIMEOUT_AND_RAW_PASS");return 0;
}
