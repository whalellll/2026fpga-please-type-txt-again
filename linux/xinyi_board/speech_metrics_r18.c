/* Bounded real speech-task fork/exec timing, with a fixed legal move only.
 * Includes cold spawn when applicable; no camera, ASR, engine or GUI timing.
 * The caller must authenticate the paired helper/assets before running. */
#define _POSIX_C_SOURCE 200809L
#include "speech_task.h"
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static volatile sig_atomic_t stopped;
static void stop(int sig){(void)sig;stopped=1;}
static uint64_t wall_us(void)
{struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;return(uint64_t)t.tv_sec*1000000u+t.tv_nsec/1000u;}
static void initial(xq_search_board_t *b)
{
 static const uint8_t back[9]={5,4,3,2,1,2,3,4,5};memset(b,0,sizeof(*b));
 for(unsigned i=0;i<9;i++){b->squares[i]=back[i];b->squares[81+i]=back[i]|SIDE_BLACK;}
 for(unsigned i=0;i<9;i+=2){b->squares[27+i]=PIECE_P;b->squares[54+i]=PIECE_P|SIDE_BLACK;}
 b->squares[19]=b->squares[25]=PIECE_C;b->squares[64]=b->squares[70]=PIECE_C|SIDE_BLACK;
}
int main(int argc,char **argv)
{
 int prepared=argc==4 && !strcmp(argv[3],"--prepared");
 if((argc!=3 && !prepared) || argv[1][0]!='/' || argv[2][0]!='/')return 2;
 struct sigaction action={0};action.sa_handler=stop;sigemptyset(&action.sa_mask);
 if(sigaction(SIGINT,&action,NULL)||sigaction(SIGTERM,&action,NULL)||sigaction(SIGALRM,&action,NULL))return 2;
 alarm(20);xy_speech_task task;xq_search_board_t before;int okay=1;initial(&before);xy_speech_task_init(&task);
 const struct timespec tick={0,1000000};
 if(prepared){
  uint64_t began=wall_us();
  if(!xy_speech_task_prepare(&task,argv[1],argv[2]))return 3;
  while(task.state==XY_SPEECH_PREPARING && !stopped && wall_us()-began<5000000u){
   xy_speech_task_poll(&task);nanosleep(&tick,NULL);
  }
  printf("R18_SPEECH_TASK_PREPARED elapsed_us=%llu state=%d ready=%d starts=%u\n",
   (unsigned long long)(wall_us()-began),task.state,task.ready,task.starts);
  if(task.state!=XY_SPEECH_PREPARED || !task.ready)okay=0;
 }
 for(unsigned round=0;round<2;round++){
  uint64_t began=wall_us();
  if(!okay || stopped || !began || !xy_speech_task_start_move(&task,argv[1],argv[2],round+1,1,&before,"h2e2")){okay=0;break;}
  while(task.state==XY_SPEECH_STARTING || task.state==XY_SPEECH_RUNNING){
   xy_speech_task_poll(&task);
   if(stopped || wall_us()-began>5000000u){okay=0;xy_speech_task_cancel(&task,round+1,1);break;}
   nanosleep(&tick,NULL);
  }
  uint64_t ended=wall_us();
  printf("R18_SPEECH_TASK_PAIR index=%u cold=%u elapsed_us=%llu state=%d underflows=%u result_status=%u cleanup_confirmed=%d scope=fixed_result_ready_to_actual_helper_done_not_full_GUI\n",
   round,round==0 && !prepared,(unsigned long long)(ended-began),task.state,task.underflows,task.result_status,task.cleanup_confirmed);
  if(task.state!=XY_SPEECH_DONE || task.underflows || !task.cleanup_confirmed)okay=0;
  if(!okay)break;
 }
 uint64_t closing=wall_us();xy_speech_task_close(&task);
 while(task.pid>0 && wall_us()-closing<6500000u){xy_speech_task_poll(&task);nanosleep(&tick,NULL);}
 alarm(0);
 printf("R18_SPEECH_TASK_CLOSE pid=%d state=%d cleanup_confirmed=%d okay=%d\n",(int)task.pid,task.state,task.cleanup_confirmed,okay);
 return !okay || task.pid>0 || !task.cleanup_confirmed;
}
