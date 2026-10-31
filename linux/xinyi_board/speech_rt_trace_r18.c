/* Bounded diagnostic translation unit. Includes the unchanged production Linux
 * playback implementation; timestamps only syscall boundaries outside FIFO.
 * Output happens after the complete production cleanup. Never a speed claim. */
#define _GNU_SOURCE
#include "../voice_speech/xq_whole_speech.h"
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

enum {
 T_PCM_OPEN,T_PCM_READ,T_PCM_CLOSE,T_LOCK_OPEN,T_FLOCK,T_MEM_OPEN,T_MMAP,
 T_POLICY,T_PARAM,T_MLOCK,T_RT_READ_OPEN,T_RT_READ,T_RT_READ_CLOSE,
 T_RT_DISABLE_OPEN,T_RT_DISABLE_WRITE,T_RT_DISABLE_CLOSE,T_SCHED_ENTER,
 T_SCHED_RESTORE,T_RT_RESTORE_OPEN,T_RT_RESTORE_WRITE,T_RT_RESTORE_CLOSE,
 T_MUNLOCK,T_MUNMAP,T_MEM_CLOSE,T_LOCK_CLOSE,T_COUNT
};
static const char *const trace_names[T_COUNT]={
 "pcm_open","pcm_read","pcm_close","lock_open","flock","mem_open","mmap",
 "sched_policy","sched_param","mlockall","rt_read_open","rt_read","rt_read_close",
 "rt_disable_open","rt_disable_write","rt_disable_close","sched_enter",
 "sched_restore","rt_restore_open","rt_restore_write","rt_restore_close",
 "munlockall","munmap","mem_close","lock_close"
};
static struct {uint64_t us;unsigned count,failed;int error;} trace_stages[T_COUNT];
static int trace_pcm_fd=-1,trace_lock_fd=-1,trace_mem_fd=-1,trace_budget_fd=-1;
static unsigned trace_budget_writes,trace_clock_errors;
static uint64_t trace_clock(void)
{
 int saved=errno;struct timespec t;uint64_t value=0;
 if(clock_gettime(CLOCK_MONOTONIC,&t))++trace_clock_errors;
 else value=(uint64_t)t.tv_sec*1000000u+(unsigned)t.tv_nsec/1000u;
 errno=saved;return value;
}
static void trace_finish(unsigned stage,uint64_t began,int failed,int error)
{
 uint64_t end=trace_clock();
 if(end>=began)trace_stages[stage].us+=end-began;
 else ++trace_clock_errors;
 ++trace_stages[stage].count;
 if(failed){++trace_stages[stage].failed;trace_stages[stage].error=error;}
 errno=error;
}
static void trace_reset(void)
{
 memset(trace_stages,0,sizeof(trace_stages));trace_clock_errors=trace_budget_writes=0;
 trace_pcm_fd=trace_lock_fd=trace_mem_fd=trace_budget_fd=-1;
}
/* Test-only backend aliases are supplied by the existing explicit device mocks.
 * The deployment build defines none and calls the exact libc/syscall entries. */
#ifndef XQRT_OPEN
#define XQRT_OPEN open
#define XQRT_CLOSE close
#define XQRT_FLOCK flock
#define XQRT_MMAP mmap
#define XQRT_MUNMAP munmap
#define XQRT_MLOCKALL mlockall
#define XQRT_MUNLOCKALL munlockall
#define XQRT_SYSCALL syscall
#endif
static int trace_open(const char *path,int flags,...)
{
 mode_t mode=0;unsigned stage=T_PCM_OPEN;
 if(flags&O_CREAT){va_list ap;va_start(ap,flags);mode=(mode_t)va_arg(ap,int);va_end(ap);}
 if(!strcmp(path,"/run/xqvoice-audio.lock"))stage=T_LOCK_OPEN;
 else if(!strcmp(path,"/dev/mem"))stage=T_MEM_OPEN;
 else if(!strcmp(path,"/proc/sys/kernel/sched_rt_runtime_us"))
  stage=(flags&O_WRONLY)?(trace_budget_writes?T_RT_RESTORE_OPEN:T_RT_DISABLE_OPEN):T_RT_READ_OPEN;
 uint64_t began=trace_clock();int r=XQRT_OPEN(path,flags,mode),error=errno;
 trace_finish(stage,began,r<0,error);
 if(r>=0){if(stage==T_LOCK_OPEN)trace_lock_fd=r;else if(stage==T_MEM_OPEN)trace_mem_fd=r;
  else if(stage==T_PCM_OPEN)trace_pcm_fd=r;else trace_budget_fd=r;}
 return r;
}
static int trace_close(int fd)
{
 unsigned stage=T_PCM_CLOSE;
 if(fd==trace_lock_fd)stage=T_LOCK_CLOSE;
 else if(fd==trace_mem_fd)stage=T_MEM_CLOSE;
 else if(fd==trace_budget_fd)stage=trace_budget_writes?(trace_budget_writes>1?T_RT_RESTORE_CLOSE:T_RT_DISABLE_CLOSE):T_RT_READ_CLOSE;
 uint64_t began=trace_clock();int r=XQRT_CLOSE(fd),error=errno;
 trace_finish(stage,began,r<0,error);
 if(fd==trace_lock_fd)trace_lock_fd=-1;
 if(fd==trace_mem_fd)trace_mem_fd=-1;
 if(fd==trace_pcm_fd)trace_pcm_fd=-1;
 if(fd==trace_budget_fd)trace_budget_fd=-1;
 return r;
}
static int trace_flock(int fd,int flags)
{uint64_t b=trace_clock();int r=XQRT_FLOCK(fd,flags),e=errno;trace_finish(T_FLOCK,b,r<0,e);return r;}
static void *trace_mmap(void *p,size_t n,int prot,int flags,int fd,off_t at)
{uint64_t b=trace_clock();void *r=XQRT_MMAP(p,n,prot,flags,fd,at);int e=errno;trace_finish(T_MMAP,b,r==MAP_FAILED,e);return r;}
static int trace_munmap(void *p,size_t n)
{uint64_t b=trace_clock();int r=XQRT_MUNMAP(p,n),e=errno;trace_finish(T_MUNMAP,b,r<0,e);return r;}
static int trace_mlockall(int flags)
{uint64_t b=trace_clock();int r=XQRT_MLOCKALL(flags),e=errno;trace_finish(T_MLOCK,b,r<0,e);return r;}
static int trace_munlockall(void)
{uint64_t b=trace_clock();int r=XQRT_MUNLOCKALL(),e=errno;trace_finish(T_MUNLOCK,b,r<0,e);return r;}
static ssize_t trace_read(int fd,void *p,size_t n)
{unsigned s=fd==trace_budget_fd?T_RT_READ:T_PCM_READ;uint64_t b=trace_clock();ssize_t r=read(fd,p,n);int e=errno;trace_finish(s,b,r<0,e);return r;}
static ssize_t trace_write(int fd,const void *p,size_t n)
{
 unsigned s=trace_budget_writes?T_RT_RESTORE_WRITE:T_RT_DISABLE_WRITE;
 uint64_t b=trace_clock();ssize_t r=write(fd,p,n);int e=errno;
 ++trace_budget_writes;trace_finish(s,b,r<0,e);return r;
}
static long trace_syscall(long number,...)
{
 va_list ap;int pid,policy=0;struct sched_param *p=NULL;unsigned s;
 va_start(ap,number);pid=va_arg(ap,int);
 if(number==SYS_sched_getscheduler)s=T_POLICY;
 else if(number==SYS_sched_getparam){s=T_PARAM;p=va_arg(ap,struct sched_param *);}
 else if(number==SYS_sched_setscheduler){policy=va_arg(ap,int);p=va_arg(ap,struct sched_param *);s=policy==SCHED_FIFO?T_SCHED_ENTER:T_SCHED_RESTORE;}
 else {va_end(ap);errno=ENOSYS;return -1;}
 va_end(ap);uint64_t began=trace_clock();long r;
 if(number==SYS_sched_getscheduler)r=XQRT_SYSCALL(number,pid);
 else if(number==SYS_sched_getparam)r=XQRT_SYSCALL(number,pid,p);
 else r=XQRT_SYSCALL(number,pid,policy,p);
 int error=errno;trace_finish(s,began,r<0,error);return r;
}
/* Function-like macros leave io.write and other structure fields untouched. */
#define open(...) trace_open(__VA_ARGS__)
#define close(...) trace_close(__VA_ARGS__)
#define flock(...) trace_flock(__VA_ARGS__)
#define mmap(...) trace_mmap(__VA_ARGS__)
#define munmap(...) trace_munmap(__VA_ARGS__)
#define mlockall(...) trace_mlockall(__VA_ARGS__)
#define munlockall(...) trace_munlockall(__VA_ARGS__)
#define read(...) trace_read(__VA_ARGS__)
#define write(...) trace_write(__VA_ARGS__)
#define syscall(...) trace_syscall(__VA_ARGS__)
#include "../voice_speech/xq_speech_linux.c"
#undef open
#undef close
#undef flock
#undef mmap
#undef munmap
#undef mlockall
#undef munlockall
#undef read
#undef write
#undef syscall
static void trace_emit(unsigned round,uint64_t elapsed,int okay,uint32_t underflows)
{
 printf("R18_RT_TRACE round=%u elapsed_us=%llu okay=%d underflows=%u clock_errors=%u scope=direct_shared_path_instrumented_excludes_helper_IPC\n",
  round,(unsigned long long)elapsed,okay,underflows,trace_clock_errors);
 printf("R18_RT_STAGES round=%u",round);
 for(unsigned i=0;i<T_COUNT;i++)if(trace_stages[i].count)
  printf(" %s=%llu/%u/%u/%d",trace_names[i],(unsigned long long)trace_stages[i].us,
   trace_stages[i].count,trace_stages[i].failed,trace_stages[i].error);
 puts(" format=us/count/fail/errno");
}
#ifndef XQRT_NO_MAIN
static volatile sig_atomic_t trace_stopped;
static void trace_stop(int n){(void)n;trace_stopped=1;}
static int trace_cancel(void *p){(void)p;return trace_stopped;}
int main(int argc,char **argv)
{
 if(argc!=2 || argv[1][0]!='/')return 2;
 struct sigaction sa={0};sa.sa_handler=trace_stop;sigemptyset(&sa.sa_mask);
 if(sigaction(SIGALRM,&sa,NULL)||sigaction(SIGINT,&sa,NULL)||sigaction(SIGTERM,&sa,NULL))return 2;
 unsetenv("XQVOICE_SPEECH_PROFILE");alarm(12);
 if(!xqs_linux_prepare_whole(argv[1]))return 3;
 xqs_phrase p={.tokens={XQS_CANNON,XQS_TWO,XQS_HORIZONTAL,XQS_FIVE},.count=4};int okay=1;
 for(unsigned round=0;round<2;round++){
  uint32_t underflows=0;trace_reset();uint64_t began=trace_clock();
  int played=xqs_linux_play_whole(&p,argv[1],100,trace_cancel,NULL,&underflows);
  uint64_t ended=trace_clock();trace_emit(round,ended>=began?ended-began:0,played,underflows);
  if(!played || underflows || trace_stopped || trace_clock_errors){okay=0;break;}
 }
 xqs_linux_release();alarm(0);return !okay;
}
#endif
