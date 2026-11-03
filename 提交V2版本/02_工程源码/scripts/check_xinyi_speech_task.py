"""Real fork/exec speech worker protocol with explicit audio mocks; no board."""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess
R=Path(__file__).resolve().parents[1]
MOCK=r'''
#define _POSIX_C_SOURCE 200809L
#include "speech_task.h"
#include <assert.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>
static unsigned preparations;static char mode[512];
int xqs_linux_prepare(const char *directory){assert(!preparations++);assert(strlen(directory)<sizeof(mode));strcpy(mode,directory);return 1;}
void xqs_linux_release(void){assert(preparations==1);}
int xqs_linux_play(const xqs_phrase *p,const char *directory,unsigned volume,int(*cancel)(void*),void *c,uint32_t *underflows){
 assert(preparations==1 && p->count==5 && volume==100 && !strcmp(mode,directory));
 *underflows=0;
 if(strstr(mode,"crash"))_exit(7);
 if(strstr(mode,"wrong")){
  xy_speech_wire m={0};m.magic=XY_SPEECH_WIRE_MAGIC;m.kind=XYSP_RESULT;m.token=555;m.revision=666;m.count=5;
  assert(send(3,&m,sizeof(m),MSG_NOSIGNAL)==sizeof(m));
 }
 for(unsigned i=0;i<200;i++){
  struct timespec t={0,1000000};nanosleep(&t,NULL);
  if(!strstr(mode,"ignore") && cancel(c))return 0;
 }
 if(strstr(mode,"underflow"))*underflows=9;
 return 1;
}
'''
TEST=r'''
#define _POSIX_C_SOURCE 200809L
#include "speech_task.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
static int interrupt_wait;
pid_t __real_waitpid(pid_t,int*,int);
pid_t __wrap_waitpid(pid_t pid,int *status,int options){if(interrupt_wait){interrupt_wait=0;errno=EINTR;return -1;}return __real_waitpid(pid,status,options);}
static uint64_t wall(void){struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC,&t));return(uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static void nap(void){struct timespec t={0,1000000};nanosleep(&t,NULL);}
static void initial(xq_search_board_t*b){static const uint8_t back[9]={5,4,3,2,1,2,3,4,5};memset(b,0,sizeof(*b));for(unsigned i=0;i<9;i++){b->squares[i]=back[i];b->squares[81+i]=back[i]|SIDE_BLACK;}for(unsigned i=0;i<9;i+=2){b->squares[27+i]=PIECE_P;b->squares[54+i]=PIECE_P|SIDE_BLACK;}b->squares[19]=b->squares[25]=PIECE_C;b->squares[64]=b->squares[70]=PIECE_C|SIDE_BLACK;}
static void wait_state(xy_speech_task*t,int state){uint64_t limit=wall()+10000;while(t->state!=state && wall()<limit){(void)xy_speech_task_poll(t);nap();}if(t->state!=state)fprintf(stderr,"state=%d expected=%d pid=%ld protocol=%d cleanup=%d\n",t->state,state,(long)t->pid,t->protocol_error,t->cleanup_confirmed);assert(t->state==state);}
static void wait_dead(xy_speech_task*t){uint64_t limit=wall()+10000;while(t->pid>0 && wall()<limit){(void)xy_speech_task_poll(t);nap();}assert(t->pid==-1);errno=0;assert(waitpid(-1,NULL,WNOHANG)==-1 && errno==ECHILD);}
int main(int argc,char**argv){
 xy_speech_task t;xq_search_board_t b;pid_t resident;char path[1024];
 assert(argc==3);initial(&b);xy_speech_task_init(&t);
 assert(!xy_speech_task_start(&t,argv[1],argv[2],1,1,&b,"h2i3") && t.pid==-1);
 snprintf(path,sizeof(path),"%s/normal",argv[2]);
 assert(xy_speech_task_start(&t,argv[1],path,1,1,&b,"h2e2"));wait_state(&t,XY_SPEECH_DONE);
 interrupt_wait=1;(void)xy_speech_task_poll(&t);assert(!interrupt_wait && t.pid>0 && t.state==XY_SPEECH_DONE);
 assert(t.cleanup_confirmed && !t.underflows && t.ready && t.starts==1);resident=t.pid;
 b.side=1;assert(xy_speech_task_start(&t,argv[1],path,2,2,&b,"h9g7"));wait_state(&t,XY_SPEECH_DONE);
 assert(t.pid==resident && t.starts==1);
 assert(xy_speech_task_start(&t,argv[1],path,3,3,&b,"h9g7"));wait_state(&t,XY_SPEECH_RUNNING);
 assert(!xy_speech_task_cancel(&t,2,2) && t.state==XY_SPEECH_RUNNING);
 assert(xy_speech_task_cancel(&t,3,3));assert(t.state==XY_SPEECH_STOPPING && t.pid>0);
 wait_dead(&t);assert(t.state==XY_SPEECH_STOPPED && t.cleanup_confirmed);
 assert(xy_speech_task_start(&t,argv[1],path,4,4,&b,"h9g7"));
 assert(!xy_speech_task_cancel(&t,3,3));wait_state(&t,XY_SPEECH_DONE);assert(t.starts==2);
 assert(!xy_speech_task_close(&t));wait_dead(&t);assert(t.state==XY_SPEECH_STOPPED && t.cleanup_confirmed);
 xy_speech_task_init(&t);snprintf(path,sizeof(path),"%s/underflow",argv[2]);
 assert(xy_speech_task_start(&t,argv[1],path,5,5,&b,"h9g7"));wait_state(&t,XY_SPEECH_FAILED);
 assert(t.underflows==9 && t.cleanup_confirmed && t.pid>0);
 assert(!xy_speech_task_close(&t));wait_dead(&t);assert(t.state==XY_SPEECH_STOPPED && t.cleanup_confirmed);
 xy_speech_task_init(&t);snprintf(path,sizeof(path),"%s/crash",argv[2]);
 assert(xy_speech_task_start(&t,argv[1],path,6,6,&b,"h9g7"));wait_dead(&t);
 assert(t.state==XY_SPEECH_FAILED && !t.cleanup_confirmed);
 assert(!xy_speech_task_start(&t,argv[1],path,60,60,&b,"h9g7"));
 assert(xy_speech_task_close(&t) && t.state==XY_SPEECH_FAILED && !t.cleanup_confirmed);
 xy_speech_task_init(&t);snprintf(path,sizeof(path),"%s/wrong",argv[2]);
 assert(xy_speech_task_start(&t,argv[1],path,7,7,&b,"h9g7"));wait_dead(&t);
 assert(t.state==XY_SPEECH_FAILED && t.protocol_error);
 xy_speech_task_init(&t);snprintf(path,sizeof(path),"%s/ignore",argv[2]);
 assert(xy_speech_task_start(&t,argv[1],path,8,8,&b,"h9g7"));wait_state(&t,XY_SPEECH_RUNNING);
 assert(xy_speech_task_cancel(&t,8,8));t.deadline_ms=0;wait_dead(&t);
 assert(t.state==XY_SPEECH_FAILED && !t.cleanup_confirmed);
 puts("SPEECH_TASK_PASS exec resident-cache reuse, red/black legal input, fixed100, wrong-token reject, TERM+waitpid ack, late generation, underflow/crash/protocol/forced-kill failures, no orphans");
 return 0;
}
'''
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def lin(p):
 s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',type=Path,required=True)
 ap.add_argument('--rv32',action='store_true');ap.add_argument('--distro',default='Ubuntu-22.04');a=ap.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 for n in ['normal','underflow','crash','wrong','ignore']:(out/n).mkdir()
 (out/'mock.c').write_bytes(MOCK.encode());(out/'test.c').write_bytes(TEST.encode())
 names=['linux/xinyi_board/speech_task.c','linux/xinyi_board/speech_task.h','linux/xinyi_board/speech_worker.c',
 'linux/voice_speech/xq_speech.c','linux/voice_speech/xq_speech.h','linux/voice_speech/xq_speech_linux.c',
 'sw/xiangqi/xiangqi_search.c','sw/xiangqi/xiangqi_search.h','sw/xiangqi/xiangqi_pikafish_link.c','sw/xiangqi/xiangqi_pikafish_link.h']
 before={n:sha(R/n) for n in names};runs=[]
 def run(name,args):
  p=subprocess.run(['wsl','-d',a.distro,'--','sh','-c','ulimit -c 0\nexec '+shlex.join(args)],capture_output=True,timeout=90)
  (out/(name+'.stdout')).write_bytes(p.stdout);(out/(name+'.stderr')).write_bytes(p.stderr)
  runs.append({'name':name,'exit':p.returncode});assert p.returncode==0,(name,(p.stdout+p.stderr).decode(errors='replace')[-3500:])
 cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if a.rv32 else 'gcc'
 flags=['-std=gnu11','-O2','-Wall','-Wextra','-Werror','-pthread']
 if a.rv32:flags+=['-static','-march=rv32ima','-mabi=ilp32']
 inc=['-I'+lin(R/n) for n in ['linux/xinyi_board','linux/voice_speech','sw/xiangqi']]
 common=[R/'linux/voice_speech/xq_speech.c',R/'sw/xiangqi/xiangqi_search.c',R/'sw/xiangqi/xiangqi_pikafish_link.c']
 status='FAILED_PRESERVED'
 try:
  run('worker-mock-build',[cc,*flags,*inc,lin(R/'linux/xinyi_board/speech_worker.c'),lin(out/'mock.c'),'-o',lin(out/'worker-mock')])
  worker=out/'worker-mock'
  if a.rv32:
   worker=out/'worker-qemu';worker.write_bytes(('#!/bin/sh\nexec qemu-riscv32 '+shlex.quote(lin(out/'worker-mock'))+' "$@"\n').encode());run('shim-mode',['chmod','755',lin(worker)])
  run('parent-build',[cc,*flags,*inc,lin(out/'test.c'),lin(R/'linux/xinyi_board/speech_task.c'),*[lin(p) for p in common],'-Wl,--wrap=waitpid','-o',lin(out/'test')])
  run('process-tests',[*(['qemu-riscv32'] if a.rv32 else []),lin(out/'test'),lin(worker),lin(out)])
  run('worker-real-build',[cc,*flags,*inc,lin(R/'linux/xinyi_board/speech_worker.c'),*[lin(p) for p in common],lin(R/'linux/voice_speech/xq_speech_linux.c'),'-o',lin(out/'xinyi-speech-worker')])
  if a.rv32:
   run('elf-header',[cc.removesuffix('gcc')+'readelf','-h','-A',lin(out/'xinyi-speech-worker')])
  assert before=={n:sha(R/n) for n in names},'source changed during tests'
  status='SPEECH_TASK_HOST_OR_RV32_REAL_WORKER_PROTOCOL_AND_BUILD_PASS_NOT_BOARD'
 finally:
  record={'status':status,'rv32':a.rv32,'actual_board':False,'source_stable':status!='FAILED_PRESERVED','source_sha256':before,'runs':runs,
   'scope':'Actual fork/exec resident worker and fd3 protocol; audio/cache functions explicitly mocked for process tests; actual player linked only, no MMIO or hearing acceptance'}
  if (out/'xinyi-speech-worker').exists():record['real_worker_sha256']=sha(out/'xinyi-speech-worker')
  (out/'result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':status,'rv32':a.rv32}))
if __name__=='__main__':main()
