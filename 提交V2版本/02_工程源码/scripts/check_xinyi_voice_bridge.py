"""Actual voice_2 session + product bridge; synthetic ASR/engine/audio tasks."""
from pathlib import Path
import argparse,hashlib,json,shlex,subprocess

R=Path(__file__).resolve().parents[1]
FAKE=r'''
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void result(unsigned id,int code,const char *text){
 printf("XQW1 RESULT %u %d ",id,code);
 if(!*text)putchar('-');
 for(const unsigned char *p=(const unsigned char*)text;*p;p++)printf("%02x",*p);
 puts(" request_us=9000000 cnn_us=10000 decode_us=1000 tail_valid=1 endpoint_to_result_us=20000 last_voice_to_result_us=470000 feature_tail_us=9000");
 printf("XQW1 IDLE %u\n",id);
}
int main(int argc,char **argv){
 char line[2300],kind,path[2050],mode[1025];unsigned id,active=0;
 (void)argv;if(argc!=5)return 2;setvbuf(stdout,NULL,_IOLBF,0);
 fputs("VOICE2_SMALL_ACCEL_ACTIVE synthetic device only\n",stderr);
 puts("XQW1 READY pid=1 model_loads=1 model_checks=1 mac_opens=0");
 while(fgets(line,sizeof(line),stdin)){
  if(sscanf(line,"XQW1 %c %u %2049s",&kind,&id,path)!=3)return 3;
  if(kind=='Q'){puts("XQW1 BYE");return 0;}
  if(kind=='C'){if(active==id){result(id,0,"马二进三");active=0;}continue;}
  size_t n=strlen(path);if(n%2u || n/2u>=sizeof(mode))return 4;
  for(size_t i=0;i<n;i+=2u){unsigned x;if(sscanf(path+i,"%2x",&x)!=1)return 5;mode[i/2u]=(char)x;}
  mode[n/2u]=0;active=id;printf("XQW1 STAGE %u LISTENING\n",id);
  if(!strcmp(mode,"idle") || !strcmp(mode,"late"))continue;
  printf("XQW1 STAGE %u INFERENCING\n",id);
  if(!strcmp(mode,"two"))result(id,0,"兵五进一");
  else if(!strcmp(mode,"illegal"))result(id,0,"帅五进九");
  else if(!strcmp(mode,"empty"))result(id,25,"");
  else result(id,0,"马二进三");
  active=0;
 }
 return 0;
}
'''
TEST=r'''
#define _POSIX_C_SOURCE 200809L
#include "voice_bridge.h"
#include "xqvoice_notation.h"
#include "xq_speech.h"
#include "xiangqi_pikafish_link.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
typedef struct {xy_voice_bridge v;xy_app app;unsigned engine,speech,engine_cancel,speech_cancel;uint32_t token,rev;} fixture;
static uint64_t wall(void){struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC,&t));return (uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static void nap(void){struct timespec t={0,1000000};nanosleep(&t,NULL);}
static int mic(void *c,int on){return xy_voice_bridge_enable(&((fixture*)c)->v,on);}
static int voice(void *c,uint32_t token,const char *text){return xy_voice_bridge_command(&((fixture*)c)->v,token,text);}
static void cancel(void *c,xy_job job,uint32_t token){assert(job==XY_VOICE_COMMAND);xy_voice_bridge_cancel(&((fixture*)c)->v,token);}
static int engine(void *c,uint32_t token,uint32_t revision,const xq_search_board_t *b){
 fixture *f=c;assert(b->side==1 && !f->v.session.worker_busy && !f->v.session.need_send);
 ++f->engine;f->token=token;f->rev=revision;return 1;
}
static void cancel_engine(void *c,uint32_t token,uint32_t revision){fixture*f=c;assert(token==f->token && revision==f->rev);++f->engine_cancel;}
static int speech(void *c,uint32_t token,uint32_t revision,const xq_search_board_t *b,const char *iccs){
 fixture*f=c;xqs_phrase p;assert(b->side==1 && !f->v.session.worker_busy && xqs_move_phrase(b,iccs,&p));
 assert(p.tokens[0]==XQS_BLACK);++f->speech;f->token=token;f->rev=revision;return 1;
}
static void cancel_speech(void*c,uint32_t token,uint32_t revision){fixture*f=c;assert(token==f->token && revision==f->rev);++f->speech_cancel;}
static void wait_phase(fixture *f,int phase){uint64_t limit=wall()+4000;while(f->v.phase!=phase && wall()<limit){(void)xy_voice_bridge_poll(&f->v);nap();}if(f->v.phase!=phase)fprintf(stderr,"phase=%d expected=%d engines=%u commands=%u asr_state=%d result=%s halted=%d\n",f->v.phase,phase,f->engine,f->app.voice_commands,f->v.session.state,f->v.session.result_text,f->v.halted);assert(f->v.phase==phase);}
static void wait_idle(fixture *f){uint64_t limit=wall()+4000;while((f->app.job!=XY_IDLE || f->v.phase!=XYVB_IDLE) && wall()<limit){(void)xy_voice_bridge_poll(&f->v);nap();}assert(f->app.job==XY_IDLE && f->v.phase==XYVB_IDLE);}
static void notation(fixture *f){
 const struct {const char *spoken,*iccs;int side;} cases[]={
  {"马二进三","h0g2",0},{"炮二平五","h2e2",0},{"马八进七","h9g7",1},
  {"炮八平五","h7e7",1},{"兵五进一","e3e4",0},{"炮二退一","h2h1",0},
  {"炮二进一","h2h3",0},{"仕六进五","d0e1",0},{"相七进五","c0e2",0},
  {"士四进五","d9e8",1},{"象三进五","c9e7",1},{"卒五进一","e6e5",1}};
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++){
  xq_search_board_t b=f->v.board;b.side=cases[i].side;
  xqvoice_command_t command;xq_search_move_t move,expected;xqs_phrase p;
  assert(xqvoice_phrase(cases[i].spoken,&command));
  assert(xqvoice_resolve_move(&b,&command,&move)==1 && xq_pikafish_parse_move(cases[i].iccs,&expected));
  assert(move.from==expected.from && move.to==expected.to && xqs_move_phrase(&b,cases[i].iccs,&p));
  assert(p.count==5 && p.tokens[2]==command.source_file && p.tokens[4]==command.target);
  assert(p.tokens[3]==(command.action==XQVOICE_ACTION_JIN?XQS_FORWARD:command.action==XQVOICE_ACTION_TUI?XQS_BACKWARD:XQS_HORIZONTAL));
 }
 puts("PRODUCT_NOTATION_PASS red9-file blackfile+1,12 moves ASR and speech token agreement");
}
int main(int argc,char **argv){
 fixture f={0};xy_voice_bridge_ops ops={&f,engine,cancel_engine,speech,cancel_speech};
 xy_backend backend={0};backend.context=&f;backend.microphone=mic;backend.voice_command=voice;backend.cancel=cancel;
 assert(argc==3);assert(!setenv("XQVOICE_RUNTIME",argv[1],1) && !setenv("XQVOICE_MODEL",argv[2],1));
 assert(!setenv("XQVOICE_AUDIO_DEVICE","one",1));
 xy_voice_bridge_init(&f.v,&f.app,&ops);xy_app_init(&f.app,&backend);notation(&f);
 assert(f.app.microphone_ready && !f.app.microphone_enabled && xy_navigate(&f.app,XY_GAME,XY_VOICE));
 assert(f.app.voice_tail_ms==UINT_MAX);
 wait_phase(&f,XYVB_ENGINE);assert(f.engine==1 && f.app.voice_commands==1 && !f.app.voice_successes);
 assert(!f.v.board.squares[7] && f.v.board.squares[24]==PIECE_N && f.v.board.side==1);
 uint32_t token=f.token,rev=f.rev;
 assert(!xy_voice_bridge_engine_reply(&f.v,token+1,rev,1,"h9g7","马八进七",600,100,22000));
 assert(f.v.external_active && !f.speech);
 assert(xy_voice_bridge_engine_reply(&f.v,token,rev,1,"h9g7","马八进七",600,100,22000));
 assert(f.v.phase==XYVB_SPEECH && f.speech==1 && !f.app.voice_successes && !f.v.board.side);
 assert(!xy_voice_bridge_speech_reply(&f.v,f.token,f.rev+1,1));
 assert(xy_voice_bridge_speech_reply(&f.v,f.token,f.rev,1));
 assert(f.app.job==XY_IDLE && f.app.voice_successes==1 && f.app.voice_tail_ms==470);
 assert(f.app.voice_engine_us==22000 && f.app.voice_engine_stats_valid);
 assert(!setenv("XQVOICE_AUDIO_DEVICE","two",1));
 for(unsigned i=0;i<10;i++){(void)xy_voice_bridge_poll(&f.v);nap();}
 assert(!f.v.session.worker_busy);wait_phase(&f,XYVB_ENGINE);
 assert(f.engine==2 && f.app.voice_commands==2 && !f.v.board.squares[31] && f.v.board.squares[40]==PIECE_P);
 assert(xy_voice_bridge_engine_reply(&f.v,f.token,f.rev,1,"b9c7","马二进三",700,200,21000));
 assert(xy_voice_bridge_speech_reply(&f.v,f.token,f.rev,1));
 assert(f.app.voice_successes==2 && f.app.voice_commands==2 && f.speech==2);
 assert(!setenv("XQVOICE_AUDIO_DEVICE","illegal",1));
 uint64_t limit=wall()+4000;while(f.app.voice_commands<3 && wall()<limit){(void)xy_voice_bridge_poll(&f.v);nap();}
 wait_idle(&f);assert(f.app.voice_commands==3 && f.app.voice_successes==2 && f.engine==2);
 xq_search_board_t before=f.v.board;
 assert(!setenv("XQVOICE_AUDIO_DEVICE","late",1));limit=wall()+4000;
 while((!f.v.session.listening_ready || !f.v.session.worker_busy) && wall()<limit){(void)xy_voice_bridge_poll(&f.v);nap();}
 assert(f.v.session.worker_busy && xy_navigate(&f.app,XY_GAME,XY_COACH));
 assert(!f.app.microphone_enabled && !f.v.session.worker_busy && !memcmp(&before,&f.v.board,sizeof(before)));
 assert(xy_voice_bridge_reset(&f.v));assert(!setenv("XQVOICE_AUDIO_DEVICE","one",1));
 assert(xy_navigate(&f.app,XY_GAME,XY_VOICE));wait_phase(&f,XYVB_ENGINE);
 token=f.token;rev=f.rev;before=f.v.board;
 assert(xy_navigate(&f.app,XY_GAME,XY_COACH) && f.app.cancelling && f.engine_cancel==1);
 (void)xy_voice_bridge_poll(&f.v);assert(f.app.mode==XY_VOICE && f.app.cancelling);
 assert(!xy_voice_bridge_engine_reply(&f.v,token,rev,1,"h9g7","late",500,1,1));
 assert(!memcmp(&before,&f.v.board,sizeof(before)));(void)xy_voice_bridge_poll(&f.v);
 assert(!f.app.cancelling && f.app.mode==XY_COACH && !f.app.microphone_enabled && f.app.token!=token);
 assert(!xy_voice_bridge_engine_stopped(&f.v,token,rev));
 assert(xy_voice_bridge_reset(&f.v) && xy_navigate(&f.app,XY_GAME,XY_VOICE));wait_phase(&f,XYVB_ENGINE);
 assert(xy_voice_bridge_engine_reply(&f.v,f.token,f.rev,1,"h9g7","马八进七",500,1,1));
 token=f.token;rev=f.rev;
 assert(xy_navigate(&f.app,XY_HOME,XY_COACH) && f.speech_cancel==1 && f.app.cancelling);
 assert(xy_voice_bridge_speech_stopped(&f.v,token,rev));(void)xy_voice_bridge_poll(&f.v);
 assert(f.app.page==XY_HOME && !f.app.microphone_enabled && !f.app.cancelling);
 assert(!xy_voice_bridge_speech_reply(&f.v,token,rev,1));
 assert(xy_voice_bridge_close(&f.v));
 puts("VOICE_BRIDGE_PASS two rounds, mic exclusive, async engine/speech, tail470-not-request9000, mode switch and late cancel gated");
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
 (out/'fake.c').write_bytes(FAKE.encode());(out/'test.c').write_bytes(TEST.encode())
 names=['linux/xinyi_board/voice_bridge.c','linux/xinyi_board/voice_bridge.h','linux/xinyi_board/voice_notation.c',
 'linux/xinyi/xinyi_product.c','linux/xinyi/xinyi_product.h','linux/voice_ctc/xqvoice_session.c','linux/voice_ctc/xqvoice_session.h',
 'linux/voice_speech/xq_speech.c','linux/voice_speech/xq_speech.h','sw/xiangqi/xiangqi_search.c','sw/xiangqi/xiangqi_search.h',
 'sw/xiangqi/xiangqi_pikafish_link.c','sw/xiangqi/xiangqi_pikafish_link.h','linux/voice/xqvoice_protocol.h','linux/voice/xqvoice_notation.h']
 before={n:sha(R/n) for n in names};runs=[]
 def run(name,args,timeout=45):
  cmd='ulimit -c 0\nexec '+shlex.join(args)
  p=subprocess.run(['wsl','-d',a.distro,'--','sh','-c',cmd],capture_output=True,timeout=timeout)
  (out/(name+'.stdout')).write_bytes(p.stdout);(out/(name+'.stderr')).write_bytes(p.stderr)
  runs.append({'name':name,'exit':p.returncode});assert p.returncode==0,(name,(p.stdout+p.stderr).decode(errors='replace')[-3000:])
 cc='/opt/toolchain/bin/riscv32-linux-musl-gcc' if a.rv32 else 'gcc'
 flags=['-std=gnu11','-O2','-Wall','-Wextra','-Werror','-pthread']
 if a.rv32:flags+=['-static','-march=rv32ima','-mabi=ilp32']
 inc=['-I'+lin(R/n) for n in ['linux/xinyi_board','linux/xinyi','linux/voice_ctc','linux/voice_speech','linux/voice','sw/xiangqi']]
 status='FAILED_PRESERVED'
 try:
  run('fake-build',[cc,*flags,lin(out/'fake.c'),'-o',lin(out/'fake')])
  worker=out/'fake'
  if a.rv32:
   worker=out/'fake-qemu';worker.write_bytes(('#!/bin/sh\nexec qemu-riscv32 '+shlex.quote(lin(out/'fake'))+' "$@"\n').encode())
   run('shim-mode',['chmod','755',lin(worker)])
  sources=[n for n in names if n.endswith('.c')]
  run('bridge-build',[cc,*flags,*inc,lin(out/'test.c'),*[lin(R/n) for n in sources],'-lm','-o',lin(out/'test')])
  run('bridge-run',[*(['qemu-riscv32'] if a.rv32 else []),lin(out/'test'),lin(worker),lin(R/'linux/voice_ctc/balanced24.bin')])
  assert before=={n:sha(R/n) for n in names},'source changed'
  status='VOICE_BRIDGE_HOST_OR_RV32_TWO_ROUNDS_NOTATION_CANCEL_PASS_NOT_BOARD'
 finally:
  (out/'result.json').write_text(json.dumps({'status':status,'rv32':a.rv32,'actual_board':False,'source_stable':status!='FAILED_PRESERVED',
    'source_sha256':before,'runs':runs,'scope':'Real voice_2 session and product/controller; synthetic ASR, engine and playback tasks'},indent=2)+'\n',encoding='utf-8')
  print(json.dumps({'status':status,'rv32':a.rv32}))
if __name__=='__main__':main()
