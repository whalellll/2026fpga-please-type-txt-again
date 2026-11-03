#define _GNU_SOURCE
#include "xq_speech.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

_Alignas(4096) static uint32_t registers[1024];
static int locked,realtime,streamed,primed,libc_calls,kernel_calls,fail_enter,fail_stream;
static int fail_budget_read,fail_budget_write,budget_writes;
static long rt_budget=950000;
const char *const xqs_names[XQS_COUNT]={[XQS_WELCOME]="welcome"};
static int fake_open(const char *name,int flags,...)
{
 (void)flags;
 if(!strcmp(name,"/proc/sys/kernel/sched_rt_runtime_us"))return flags&O_WRONLY?104:103;
 assert(!strcmp(name,"/dev/mem") || !strcmp(name,"/run/xq-speech.lock"));
 return !strcmp(name,"/dev/mem")?101:102;
}
static int fake_close(int fd){assert(fd>=101 && fd<=104);return 0;}
static ssize_t fake_read(int fd,void *p,size_t bytes)
{assert(fd==103 && bytes==31);if(fail_budget_read){errno=EACCES;return -1;}return snprintf(p,bytes,"%ld\n",rt_budget);}
static ssize_t fake_write(int fd,const void *p,size_t bytes)
{
 assert(fd==104 && bytes && !realtime);++budget_writes;
 if(fail_budget_write){fail_budget_write=0;errno=EACCES;return -1;}
 rt_budget=strtol(p,NULL,10);return (ssize_t)bytes;
}
/* Link with --wrap=read,--wrap=write; macros would also rename io.write. */
ssize_t __real_read(int,void *,size_t);
ssize_t __real_write(int,const void *,size_t);
ssize_t __wrap_read(int fd,void *p,size_t bytes)
{return fd==103?fake_read(fd,p,bytes):__real_read(fd,p,bytes);}
ssize_t __wrap_write(int fd,const void *p,size_t bytes)
{return fd==104?fake_write(fd,p,bytes):__real_write(fd,p,bytes);}
static int fake_flock(int fd,int flags){assert(fd==102 && flags==(LOCK_EX|LOCK_NB));return 0;}
static void *fake_mmap(void *address,size_t bytes,int protection,int flags,int fd,off_t offset)
{
 assert(!address && bytes==4096 && protection==(PROT_READ|PROT_WRITE));
 assert(flags==MAP_SHARED && fd==101 && offset==0x1fe00000u);
 return registers;
}
static int fake_munmap(void *address,size_t bytes)
{assert((uintptr_t)address==((uintptr_t)registers&~(uintptr_t)4095) && bytes==4096);return 0;}
static int fake_mlockall(int flags){assert(flags==(MCL_CURRENT|MCL_FUTURE));locked=1;return 0;}
static int fake_munlockall(void){assert(locked);locked=0;return 0;}
/* Match the pinned target musl: these exported functions never enter Linux. */
static int fake_sched_getscheduler(pid_t pid){(void)pid;++libc_calls;errno=ENOSYS;return -1;}
static int fake_sched_getparam(pid_t pid,struct sched_param *p)
{(void)pid;(void)p;++libc_calls;errno=ENOSYS;return -1;}
static int fake_sched_setscheduler(pid_t pid,int policy,const struct sched_param *p)
{(void)pid;(void)policy;(void)p;++libc_calls;errno=ENOSYS;return -1;}
static long fake_syscall(long number,...)
{
 va_list args;int policy;struct sched_param *p;
 va_start(args,number);assert(va_arg(args,int)==0);++kernel_calls;
 if(number==SYS_sched_getscheduler){va_end(args);return SCHED_OTHER;}
 if(number==SYS_sched_getparam){p=va_arg(args,struct sched_param *);p->sched_priority=0;va_end(args);return 0;}
 assert(number==SYS_sched_setscheduler);
 policy=va_arg(args,int);p=va_arg(args,struct sched_param *);va_end(args);
 if(policy==SCHED_FIFO){
  assert(locked && rt_budget== -1 && p->sched_priority==10);
  if(fail_enter){errno=EPERM;return -1;}
  realtime=1;
 }else{assert(policy==SCHED_OTHER && p->sched_priority==0 && realtime);realtime=0;}
 return 0;
}
int xqs_stream(xqs_io *io,const int16_t *samples,unsigned count,uint32_t *delta)
{
 assert(locked && realtime && rt_budget== -1 && io->context);
 assert(io->status && io->underflows && io->write && io->cancel && io->now_us);
 if(count==64){unsigned i;for(i=0;i<count;i++)assert(!samples[i]);++primed;*delta=7;return 1;}
 assert(count==32 && samples[0]==1000);
 ++streamed;*delta=0;return !fail_stream;
}
#define open fake_open
#define close fake_close
#define flock fake_flock
#define mmap fake_mmap
#define munmap fake_munmap
#define mlockall fake_mlockall
#define munlockall fake_munlockall
#define sched_getscheduler fake_sched_getscheduler
#define sched_getparam fake_sched_getparam
#define sched_setscheduler fake_sched_setscheduler
#define syscall fake_syscall
#include "xq_speech_linux.c"
#undef open
#undef close
#undef flock
#undef mmap
#undef munmap
#undef mlockall
#undef munlockall
#undef sched_getscheduler
#undef sched_getparam
#undef sched_setscheduler
#undef syscall
int main(void)
{
 char directory[]="/tmp/xq-speech-linux-XXXXXX",path[128];unsigned i;FILE *file;
 xqs_phrase phrase={{XQS_WELCOME},1};uint32_t delta=99;
 assert(mkdtemp(directory));assert(snprintf(path,sizeof(path),"%s/welcome.pcm",directory)>0);
 file=fopen(path,"wb");assert(file);
 for(i=0;i<32;i++){assert(fputc(0x10,file)!=EOF);assert(fputc(0x27,file)!=EOF);}
 assert(!fclose(file));
 registers[0x600/4]=0x41554431u;registers[0x600/4+1]=0x00010000u;
 assert(xqs_linux_play(&phrase,directory,10,NULL,NULL,&delta));
 assert(!locked && !realtime && rt_budget==950000 && !libc_calls && kernel_calls==4 && streamed==1 && primed==1 && !delta);
 fail_enter=1;
 assert(!xqs_linux_play(&phrase,directory,10,NULL,NULL,&delta));
 assert(!locked && !realtime && rt_budget==950000 && streamed==1);
 fail_enter=0;fail_stream=1;
 assert(!xqs_linux_play(&phrase,directory,10,NULL,NULL,&delta));
 assert(!locked && !realtime && rt_budget==950000 && streamed==2);
 fail_stream=0;fail_budget_read=1;
 assert(!xqs_linux_play(&phrase,directory,10,NULL,NULL,&delta));
 assert(!locked && !realtime && rt_budget==950000 && streamed==2);
 fail_budget_read=0;fail_budget_write=1;budget_writes=0;
 assert(!xqs_linux_play(&phrase,directory,10,NULL,NULL,&delta));
 assert(!locked && !realtime && rt_budget==950000 && streamed==2 && budget_writes==2);
 rt_budget= -1;budget_writes=0;
 assert(xqs_linux_play(&phrase,directory,10,NULL,NULL,&delta));
 assert(!locked && !realtime && rt_budget== -1 && streamed==3 && !budget_writes);
 /* Keep the ENOSYS exports referenced so -Werror also checks their prototypes. */
 assert(fake_sched_getscheduler(0)==-1 && fake_sched_getparam(0,NULL)==-1 && fake_sched_setscheduler(0,0,NULL)==-1);
 assert(fake_syscall(SYS_sched_getscheduler,0)==SCHED_OTHER);
 assert(!unlink(path) && !rmdir(directory));
 puts("XQ_SPEECH_LINUX_TEST_PASS musl-ENOSYS raw-syscalls RT-budget restore-on-failure");
 return 0;
}
