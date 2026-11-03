#define _GNU_SOURCE
#include "xq_speech.h"
#include <sys/mman.h>
#include <sys/file.h>
#include <sched.h>
#include <sys/syscall.h>
#include <unistd.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <errno.h>
#include <string.h>

typedef struct { int16_t *samples;unsigned count; } pcm_clip;
static pcm_clip pcm_cache[XQS_COUNT];
static char pcm_directory[512];
static unsigned pcm_cache_bytes;
void xqs_linux_release(void)
{
 for(unsigned i=0;i<XQS_COUNT;i++){free(pcm_cache[i].samples);pcm_cache[i].samples=NULL;pcm_cache[i].count=0;}
 pcm_directory[0]=0;pcm_cache_bytes=0;
}
static int select_directory(const char *dir)
{
 if(!dir || !*dir || strlen(dir)>=sizeof(pcm_directory))return 0;
 if(strcmp(pcm_directory,dir)){xqs_linux_release();memcpy(pcm_directory,dir,strlen(dir)+1);}
 return 1;
}
static int load_clip(unsigned token)
{
 char path[512];FILE *f;long bytes;int16_t *samples;
 if(token>=XQS_COUNT || !xqs_names[token])return 0;
 if(pcm_cache[token].samples)return 1;
 if(snprintf(path,sizeof(path),"%s/%s.pcm",pcm_directory,xqs_names[token])>=(int)sizeof(path))return 0;
 f=fopen(path,"rb");if(!f)return 0;
 if(fseek(f,0,SEEK_END) || (bytes=ftell(f))<=0 || bytes>16000*20 || bytes%2 ||
    (unsigned)bytes>2097152u-pcm_cache_bytes || fseek(f,0,SEEK_SET)){fclose(f);return 0;}
 samples=malloc((size_t)bytes);if(!samples){fclose(f);return 0;}
 int okay=fread(samples,1,(size_t)bytes,f)==(size_t)bytes;
 if(fclose(f))okay=0;
 if(!okay){free(samples);return 0;}
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
 for(unsigned i=0;i<(unsigned)bytes/2;i++) {
  unsigned char *p=(unsigned char *)samples+2u*i;
  unsigned value=p[0]|((unsigned)p[1]<<8);samples[i]=(int16_t)value;
 }
#endif
 pcm_cache[token].samples=samples;pcm_cache[token].count=(unsigned)bytes/2;
 pcm_cache_bytes+=(unsigned)bytes;return 1;
}
int xqs_linux_prepare(const char *dir)
{
 if(!select_directory(dir))return 0;
 for(unsigned i=0;i<=XQS_MIDDLE;i++)if(!load_clip(i)){xqs_linux_release();return 0;}
 return 1;
}
static uint64_t wall_us(void)
{
 struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
 return (uint64_t)t.tv_sec*1000000u+(unsigned)t.tv_nsec/1000u;
}

static const char rt_budget_path[]="/proc/sys/kernel/sched_rt_runtime_us";
static int read_rt_budget(char value[32],long *budget)
{
 int fd=open(rt_budget_path,O_RDONLY|O_CLOEXEC);ssize_t bytes;char *end;
 if(fd<0)return 0;
 bytes=read(fd,value,31);
 if(close(fd) || bytes<=0 || bytes>=31)return 0;
 value[bytes]=0;errno=0;*budget=strtol(value,&end,10);
 if(errno || end==value || (*end && strcmp(end,"\n")) || *budget< -1)return 0;
 return 1;
}
static int write_rt_budget(const char *value)
{
 int fd=open(rt_budget_path,O_WRONLY|O_CLOEXEC),okay;
 size_t bytes=strlen(value);
 if(fd<0)return 0;
 okay=write(fd,value,bytes)==(ssize_t)bytes;
 if(close(fd))okay=0;
 return okay;
}

typedef struct {
 volatile uint32_t *regs;
 int (*cancel)(void *);void *context;
#ifdef __riscv
 uint32_t cpu_hz,clock_start;
#endif
} playback;
static uint32_t status(void *p) { return ((playback *)p)->regs[4]; }
static uint32_t underflows(void *p) { return ((playback *)p)->regs[7]; }
static void write_sample(void *p,uint32_t sample) { ((playback *)p)->regs[3]=sample; }
static int cancel(void *p) { playback *a=p; return a->cancel && a->cancel(a->context); }
static uint64_t now_us(void *p)
{
#ifdef __riscv
 playback *a=p;uint32_t ticks;
 /* On this frozen V3.5 CPU TIME reads CPU cycles, not SYS/CLINT ticks.
  * A 30 s phrase fits inside the low counter's wrap at <=100 MHz.
  * Avoid an ECALL in a FIFO loop with only 1 ms of queued audio. */
 __asm__ volatile("rdtime %0":"=r"(ticks));
 return (uint64_t)(uint32_t)(ticks-a->clock_start)*1000000u/a->cpu_hz;
#else
 struct timespec t;
 (void)p;
 if (clock_gettime(CLOCK_MONOTONIC,&t)) return UINT64_MAX;
 return (uint64_t)t.tv_sec*1000000+(unsigned)t.tv_nsec/1000;
#endif
}
int xqs_linux_play(const xqs_phrase *phrase,const char *dir,unsigned volume,
                    int (*cancel_fn)(void *),void *context,uint32_t *delta)
{
 int lock=-1,fd=-1,policy=-1,locked=0,realtime=0,okay=0,budget_changed=0;
 char old_budget[32];long budget;
 struct sched_param previous,priority;
 playback a;
 int16_t *samples=NULL;
 unsigned used=0,total=0,i,cache_hits=0;
 uint64_t began=wall_us(),prepared=0,setup=0,ended=0;
 int16_t silence[64]={0};uint32_t priming_underflows=0;
 xqs_io io;
 a.regs=MAP_FAILED; a.cancel=cancel_fn; a.context=context;
 if (!phrase || !phrase->count || phrase->count>96 || !dir || volume<1 || volume>100 || !delta) return 0;
 *delta=0;
 if(cancel_fn && cancel_fn(context))goto done;
 /* Exact-size phrase buffer; cached block reads replace per-byte stdio.
  * All allocation/copying still precedes the original realtime FIFO path. */
 if(!select_directory(dir))goto done;
 for(i=0;i<phrase->count;i++) {
  unsigned token=phrase->tokens[i];
  if(token>=XQS_COUNT)goto done;
  if(pcm_cache[token].samples)++cache_hits;
  if(!load_clip(token) || pcm_cache[token].count>480000u-total)goto done;
  total+=pcm_cache[token].count;
 }
 samples=malloc(total*sizeof(*samples));
 if (!samples) goto done;
 for (i=0; i<phrase->count; ++i) {
  pcm_clip *clip=&pcm_cache[phrase->tokens[i]];
  if(volume==100){memcpy(samples+used,clip->samples,clip->count*sizeof(*samples));used+=clip->count;}
  else for(unsigned j=0;j<clip->count;j++)samples[used++]=(int16_t)((int32_t)clip->samples[j]*(int)volume/100);
 }
 prepared=wall_us();
 lock=open("/run/xqvoice-audio.lock",O_CREAT|O_RDWR|O_CLOEXEC,0600);
 if (lock<0 || flock(lock,LOCK_EX|LOCK_NB)) goto done;
 fd=open("/dev/mem",O_RDWR|O_SYNC|O_CLOEXEC); if (fd<0) goto done;
 a.regs=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,(off_t)0x1fe00000u);
 if (a.regs==MAP_FAILED) goto done;
#ifdef __riscv
 a.cpu_hz=a.regs[(0x300+0x14)/4];
 if(a.cpu_hz<1000000u || a.cpu_hz>100000000u)goto done;
#endif
 a.regs+=0x600/4;
 if (a.regs[0]!=0x41554431u || (a.regs[1]!=0x00010000u && a.regs[1]!=0x00020000u)) goto done;
 /* The pinned RV32 musl exports these POSIX sched_* names as ENOSYS stubs.
  * Linux implements the syscalls (also used by the board's BusyBox chrt).
  * Target the current thread, and restore its exact previous policy/priority. */
 policy=(int)syscall(SYS_sched_getscheduler,0);
 if (policy<0 || syscall(SYS_sched_getparam,0,&previous)) goto done;
 if (mlockall(MCL_CURRENT|MCL_FUTURE)) goto done;
 locked=1;
 /* Busy-polling this 16-sample FIFO needs the whole CPU during a phrase.
  * The default 950 ms / 1 s RT quota otherwise inserts 50 ms holes. Hold
  * our owner lock, save the exact value, and restore it on every exit. */
 if(!read_rt_budget(old_budget,&budget))goto done;
 if(budget>=0){
  budget_changed=1;
  if(!write_rt_budget("-1\n"))goto done;
 }
 priority.sched_priority=10;
 if (syscall(SYS_sched_setscheduler,0,SCHED_FIFO,&priority)) goto done;
 realtime=1;
 setup=wall_us();
 /* STATUS is checked for every sample, including the initial FIFO prefill.
  * CONTROL only clears counters in this ABI; do not reset global evidence. */
 io.context=&a; io.status=status; io.underflows=underflows; io.write=write_sample;
 io.now_us=now_us; io.cancel=cancel;
#ifdef __riscv
 __asm__ volatile("rdtime %0":"=r"(a.clock_start));
#endif
 /* Prime the MMIO store path, callbacks and their stack/code pages with
  * 4 ms of silence before counting underflows in the spoken payload. */
 if(!xqs_stream(&io,silence,64,&priming_underflows))goto done;
 okay=xqs_stream(&io,samples,used,delta);
 /* Keep the shared audio owner until the last queued sample has drained. */
 if(okay){
  uint64_t started=now_us(&a);
  while(status(&a)&31u){
   if(now_us(&a)-started>=100000u || cancel(&a)){okay=0;break;}
  }
 }
done:
 if (realtime && syscall(SYS_sched_setscheduler,0,policy,&previous)) okay=0;
 if (budget_changed && !write_rt_budget(old_budget)) okay=0;
 if (locked) (void)munlockall();
 if (a.regs!=MAP_FAILED) munmap((void *)((uintptr_t)a.regs&~(uintptr_t)4095),4096);
 if (fd>=0) close(fd);
 if (lock>=0) close(lock);
 free(samples);
 ended=wall_us();
 const char *profile=getenv("XQVOICE_SPEECH_PROFILE");
 if(profile && !strcmp(profile,"1"))
  fprintf(stderr,"XQ_SPEECH_PROFILE okay=%d samples=%u audio_us=%llu cache_hits=%u/%u prepare_us=%llu setup_us=%llu playback_cleanup_us=%llu total_us=%llu\n",
   okay,used,(unsigned long long)used*1000000u/16000u,cache_hits,phrase?phrase->count:0,
   (unsigned long long)(prepared>=began?prepared-began:0),
   (unsigned long long)(setup>=prepared && prepared?setup-prepared:0),
   (unsigned long long)(ended>=setup && setup?ended-setup:0),(unsigned long long)(ended-began));
 if(priming_underflows)fprintf(stderr,"XQ_SPEECH_PREFILL silent_samples=64 underflows=%u\n",priming_underflows);
 return okay;
}
