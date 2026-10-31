/* Diagnostic only. Builder supplies byte-bound e544 Linux source and the real
 * stream with three auditable observation insertions. Never deployed C0. */
#define _GNU_SOURCE
#include "../voice_speech/xq_speech.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
typedef struct {uint32_t stage,sample_index,delta,fifo_status,rdtime_ticks;} uf_event;
_Alignas(4096) static uf_event uf_events[32];
static unsigned uf_count,uf_stage,uf_maxpolls;
static uint32_t uf_before,uf_last;
static void uf_reset(void)
{
 volatile unsigned char *p=(volatile unsigned char *)uf_events;
 for(unsigned i=0;i<sizeof(uf_events);i++)p[i]=0;
 uf_count=uf_stage=uf_maxpolls=0;uf_before=uf_last=0;
}
static void uf_begin(uint32_t before,unsigned samples)
{++uf_stage;uf_before=uf_last=before;uf_maxpolls+=samples/64;}
static inline void uf_observe(xqs_io *io,unsigned index,uint32_t value)
{
 if(value==uf_last || uf_count>=32)return;
 uint32_t ticks=0;
#ifdef __riscv
 __asm__ volatile("rdtime %0":"=r"(ticks));
#endif
 uint32_t fifo=io->status(io->context);
 uf_event *e=&uf_events[uf_count];
 e->stage=uf_stage;e->sample_index=index;e->delta=value-uf_before;
 e->fifo_status=fifo;e->rdtime_ticks=ticks;
 ++uf_count;uf_last=value;
}
static inline void uf_poll(xqs_io *io,unsigned index)
{if(uf_count<32)uf_observe(io,index,io->underflows(io->context));}
#define xqs_stream xqs_stream_reference
#include "../voice_speech/xq_speech.c"
#undef xqs_stream
#include "speech_uf_stream.inc"
#include "speech_uf_base_linux.inc"
#ifndef UF_NO_MAIN
static volatile sig_atomic_t uf_stopped;
static char irq_before[2048],irq_after[2048];
static int irq_before_bytes,irq_after_bytes;
static void uf_stop(int n){(void)n;uf_stopped=1;}
static int uf_cancel(void *p){(void)p;return uf_stopped;}
static uint64_t uf_wall(void)
{struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;return(uint64_t)t.tv_sec*1000000u+t.tv_nsec/1000u;}
static int irq_read(char *out)
{
 int fd=open("/proc/interrupts",O_RDONLY|O_CLOEXEC);if(fd<0)return -1;
 ssize_t n=read(fd,out,2047);int okay=!close(fd);if(n<0 || !okay)return -1;
 out[n]=0;return(int)n;
}
int main(int argc,char **argv)
{
 if(argc!=2 || argv[1][0]!='/')return 2;
 struct sigaction sa={0};sa.sa_handler=uf_stop;sigemptyset(&sa.sa_mask);
 if(sigaction(SIGALRM,&sa,NULL)||sigaction(SIGINT,&sa,NULL)||sigaction(SIGTERM,&sa,NULL))return 2;
 alarm(12);uf_reset();
 /* Both IRQ snapshots and every event page exist/touch before MCL_CURRENT. */
 memset(irq_before,0,sizeof(irq_before));memset(irq_after,0,sizeof(irq_after));
 irq_before_bytes=irq_read(irq_before);
 if(!xqs_linux_prepare_whole(argv[1])){xqs_linux_release();return 3;}
 xqs_phrase p={.tokens={XQS_CANNON,XQS_TWO,XQS_HORIZONTAL,XQS_FIVE},.count=4};uint32_t delta=0;
 uint64_t start=uf_wall();int okay=xqs_linux_play_whole(&p,argv[1],100,uf_cancel,NULL,&delta);
 uint64_t end=uf_wall();xqs_linux_release();irq_after_bytes=irq_read(irq_after);alarm(0);
 printf("R18_UF_DIAG base=e544_prime64 okay=%d payload_underflows=%u elapsed_us=%llu events=%u capacity=32 resolution_samples=64 extra_mmio_reads_max=%u not_production=1\n",okay,delta,(unsigned long long)(end-start),uf_count,uf_maxpolls);
 for(unsigned i=0;i<uf_count;i++){
  const uf_event *e=&uf_events[i];
  printf("R18_UF_EVENT stage=%s sample_index=%u delta=%u fifo_status=%08x rdtime_ticks=%u\n",e->stage==1?"silence":"payload",e->sample_index,e->delta,e->fifo_status,e->rdtime_ticks);
 }
 printf("R18_IRQ_BEFORE bytes=%d scope=prepare_play_cleanup\n%s\nR18_IRQ_AFTER bytes=%d\n%s\n",irq_before_bytes,irq_before_bytes>0?irq_before:"",irq_after_bytes,irq_after_bytes>0?irq_after:"");
 return !okay || delta || uf_stopped;
}
#endif
