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
static int fail_lock;
static unsigned future_locks,unlocks,audio_opens;
#if XINYI_BATTLE_R17
static unsigned current_locks;
static int fail_prepare_lock,fail_pcm_malloc;
static int force_pcm_eof,force_pcm_extra;
static void *fake_pcm_malloc(size_t bytes)
{if(fail_pcm_malloc){fail_pcm_malloc=0;return NULL;}return malloc(bytes);}
#endif
static int16_t expected_first_sample=1000;
static unsigned expected_stream_count=32;
static unsigned expected_prime_samples=64;
static long rt_budget=950000;
const char *const xqs_names[XQS_COUNT]={[XQS_WELCOME]="welcome"
#if XINYI_BATTLE_R17
 ,[XQS_CANNON]="cannon",[XQS_TWO]="two",[XQS_HORIZONTAL]="horizontal",[XQS_FIVE]="five"
#endif
};
static int fake_open(const char *name,int flags,...)
{
 (void)flags;
 if(!strcmp(name,"/proc/sys/kernel/sched_rt_runtime_us"))return flags&O_WRONLY?104:103;
#if XINYI_BATTLE_R17
 if(strcmp(name,"/dev/mem") && strcmp(name,"/run/xqvoice-audio.lock"))return open(name,flags,0600);
#endif
 assert(!strcmp(name,"/dev/mem") || !strcmp(name,"/run/xqvoice-audio.lock"));
 if(!strcmp(name,"/dev/mem")){++audio_opens;return 101;}return 102;
}
static int fake_close(int fd){
#if XINYI_BATTLE_R17
 if(fd<101 || fd>104)return close(fd);
#endif
 assert(fd>=101 && fd<=104);return 0;}
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
{
 if(fd==103)return fake_read(fd,p,bytes);
#if XINYI_BATTLE_R17
 if(force_pcm_eof && bytes>1){force_pcm_eof=0;return 0;}
 if(force_pcm_extra && bytes==1){force_pcm_extra=0;*(unsigned char *)p=0;return 1;}
#endif
 return __real_read(fd,p,bytes);
}
#if XINYI_BATTLE_R17 && defined(__GLIBC__)
/* glibc FORTIFY may call this checked entry instead of read under ASan/O2.
 * Keep the check and the explicit fake proc fd; never reach a real RT sysctl. */
ssize_t __real___read_chk(int,void *,size_t,size_t);
ssize_t __wrap___read_chk(int fd,void *p,size_t bytes,size_t capacity)
{assert(bytes<=capacity);return __wrap_read(fd,p,bytes);}
#endif
ssize_t __wrap_write(int fd,const void *p,size_t bytes)
{return fd==104?fake_write(fd,p,bytes):__real_write(fd,p,bytes);}
static int fake_flock(int fd,int flags){assert(fd==102 && flags==(LOCK_EX|LOCK_NB));return fail_lock?-1:0;}
static void *fake_mmap(void *address,size_t bytes,int protection,int flags,int fd,off_t offset)
{
 assert(!address && bytes==4096 && protection==(PROT_READ|PROT_WRITE));
 assert(flags==MAP_SHARED && fd==101 && offset==0x1fe00000u);
 return registers;
}
static int fake_munmap(void *address,size_t bytes)
{assert((uintptr_t)address==((uintptr_t)registers&~(uintptr_t)4095) && bytes==4096);return 0;}
static int fake_mlockall(int flags){
#if XINYI_BATTLE_R17
 if(flags==MCL_CURRENT){++current_locks;locked=1;if(fail_prepare_lock){fail_prepare_lock=0;errno=ENOMEM;return -1;}return 0;}
#endif
 assert(flags==(MCL_CURRENT|MCL_FUTURE));++future_locks;locked=1;return 0;}
static int fake_munlockall(void){assert(locked);++unlocks;locked=0;return 0;}
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
 if(count==expected_prime_samples){unsigned i;for(i=0;i<count;i++)assert(!samples[i]);++primed;*delta=7;return 1;}
 assert(count==expected_stream_count && samples[0]==expected_first_sample);
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
#if XINYI_BATTLE_R17
#define malloc fake_pcm_malloc
#endif
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
#if XINYI_BATTLE_R17
#undef malloc
#endif
int main(void)
{
 char directory[]="/tmp/xq-speech-linux-XXXXXX",path[128];unsigned i;FILE *file;
 xqs_phrase phrase={{XQS_WELCOME},1};uint32_t delta=99;
 assert(mkdtemp(directory));assert(snprintf(path,sizeof(path),"%s/welcome.pcm",directory)>0);
 file=fopen(path,"wb");assert(file);
 for(i=0;i<32;i++){assert(fputc(0x10,file)!=EOF);assert(fputc(0x27,file)!=EOF);}
 assert(!fclose(file));
 registers[0x600/4]=0x41554431u;registers[0x600/4+1]=0x00010000u;
#ifdef __riscv
 /* The real RV32 path validates the system CPU frequency before rdtime.
    A zero-filled host MMIO fixture must not bypass that guard. */
 assert(!xqs_linux_play(&phrase,directory,10,NULL,NULL,&delta));
#endif
 registers[(0x300+0x14)/4]=60000000u;
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
 registers[0x600/4+1]=0x00020000u;
 rt_budget= -1;budget_writes=0;
 assert(xqs_linux_play(&phrase,directory,10,NULL,NULL,&delta));
 assert(!locked && !realtime && rt_budget== -1 && streamed==3 && !budget_writes);
 registers[0x600/4+1]=0x00030000u;
 assert(!xqs_linux_play(&phrase,directory,10,NULL,NULL,&delta));
 assert(!locked && !realtime && rt_budget==-1);
 registers[0x600/4+1]=0x00020000u;
 fail_lock=1;i=kernel_calls;
 assert(!xqs_linux_play(&phrase,directory,10,NULL,NULL,&delta));
 assert(kernel_calls==(int)i && !locked && !realtime && rt_budget==-1);
 fail_lock=0;registers[0x600/4+4]=1;
 assert(!xqs_linux_play(&phrase,directory,10,NULL,NULL,&delta));
 assert(!locked && !realtime && rt_budget==-1);
 registers[0x600/4+4]=0;
 /* Keep the ENOSYS exports referenced so -Werror also checks their prototypes. */
 assert(fake_sched_getscheduler(0)==-1 && fake_sched_getparam(0,NULL)==-1 && fake_sched_setscheduler(0,0,NULL)==-1);
 assert(fake_syscall(SYS_sched_getscheduler,0)==SCHED_OTHER);
 assert(!unlink(path));
 /* Cached immutable clip remains playable without opening its file again. */
 assert(xqs_linux_play(&phrase,directory,10,NULL,NULL,&delta));
 xqs_linux_release();assert(!rmdir(directory));
 puts("XQ_SPEECH_LINUX_TEST_PASS musl-ENOSYS raw-syscalls RT-budget restore-on-failure");
 return 0;
}
