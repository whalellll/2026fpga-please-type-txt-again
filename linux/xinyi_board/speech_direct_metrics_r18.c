/* Finite diagnostic of the production prepared-whole playback path.
 * Excludes fork/exec/IPC and GUI. Never count this as whole-product latency. */
#define _POSIX_C_SOURCE 200809L
#include "../voice_speech/xq_whole_speech.h"
#include <signal.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t stopped;
static void stop(int n){(void)n;stopped=1;}
static int cancel(void *unused){(void)unused;return stopped;}
static uint64_t wall_us(void)
{struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;return(uint64_t)t.tv_sec*1000000u+t.tv_nsec/1000u;}
int main(int argc,char **argv)
{
 if(argc!=2 || argv[1][0]!='/')return 2;
 struct sigaction action={0};action.sa_handler=stop;sigemptyset(&action.sa_mask);
 if(sigaction(SIGALRM,&action,NULL)||sigaction(SIGINT,&action,NULL)||sigaction(SIGTERM,&action,NULL))return 2;
 alarm(12);if(!xqs_linux_prepare_whole(argv[1]))return 3;
 xqs_phrase p={.tokens={XQS_CANNON,XQS_TWO,XQS_HORIZONTAL,XQS_FIVE},.count=4};int okay=1;
 for(unsigned round=0;round<2;round++){
  uint32_t underflows=0;uint64_t began=wall_us();
  int played=xqs_linux_play_whole(&p,argv[1],100,cancel,NULL,&underflows);
  printf("R18_DIRECT_AUDIO index=%u elapsed_us=%llu okay=%d underflows=%u scope=direct_shared_playback_excludes_process_and_GUI\n",
   round,(unsigned long long)(wall_us()-began),played,underflows);
  if(!played || underflows || stopped){okay=0;break;}
 }
 xqs_linux_release();alarm(0);return !okay;
}
