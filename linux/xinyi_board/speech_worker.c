#define _POSIX_C_SOURCE 200809L
#include "speech_task.h"
#if XINYI_COACH_MOVE_AUDIO
#include "../voice_speech/xq_move_speech.h"
#endif
#if XINYI_BATTLE_R17
#include "../voice_speech/xq_whole_speech.h"
#endif
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

static volatile sig_atomic_t stop_requested;
static void stop(int signal_number){(void)signal_number;stop_requested=1;}
static int cancelled(void *unused){(void)unused;return stop_requested!=0;}
static int write_frame(uint32_t kind,uint32_t token,uint32_t revision,uint32_t status,uint32_t count,uint32_t underflows)
{
    xy_speech_wire m={0};size_t sent=0;m.magic=XY_SPEECH_WIRE_MAGIC;
    m.kind=kind;m.token=token;m.revision=revision;m.status=status;m.count=count;m.underflows=underflows;
    while(sent<sizeof(m)){
        ssize_t n=send(3,(uint8_t*)&m+sent,sizeof(m)-sent,MSG_NOSIGNAL);
        if(n>0){sent+=(size_t)n;continue;}
        if(n<0 && errno==EINTR)continue;
        return 0;
    }
    return 1;
}
static int read_frame(xy_speech_wire *m)
{
    size_t used=0;
    while(used<sizeof(*m)){
        ssize_t n=read(3,(uint8_t*)m+used,sizeof(*m)-used);
        if(n>0){used+=(size_t)n;continue;}
        if(n<0 && errno==EINTR){if(stop_requested)return 0;continue;}
        return 0;
    }
    return 1;
}
static int rt_budget(long *value)
{
    char bytes[32],*end;int fd=open("/proc/sys/kernel/sched_rt_runtime_us",O_RDONLY|O_CLOEXEC);ssize_t n;
    if(fd<0)return 0;
    n=read(fd,bytes,31);int okay=close(fd)==0;
    if(!okay || n<=0 || n>31)return 0;
    bytes[n]=0;errno=0;*value=strtol(bytes,&end,10);
    return !errno && end!=bytes && (!*end || !strcmp(end,"\n")) && *value>=-1;
}
int main(int argc,char **argv)
{
    struct sigaction action={0};int safe=1,code=0;
    if(argc!=3 || strcmp(argv[1],"--pcm") || !argv[2][0])return 2;
    action.sa_handler=stop;sigemptyset(&action.sa_mask);
    if(sigaction(SIGTERM,&action,NULL) || sigaction(SIGINT,&action,NULL))return 2;
    (void)signal(SIGPIPE,SIG_IGN);
    if(!
#if XINYI_BATTLE_R17
       xqs_linux_prepare_whole(argv[2])
#else
       xqs_linux_prepare(argv[2])
#endif
      ){code=1;(void)write_frame(XYSP_ERROR,0,0,3,0,0);goto done;}
    if(stop_requested)goto done;
    if(!write_frame(XYSP_READY,0,0,0,0,0)){code=1;goto done;}
    while(!stop_requested){
        xy_speech_wire request;xqs_phrase phrase={0};long before,after;uint32_t underflows=0,status;int okay;
        if(!read_frame(&request))break;
        if(request.magic!=XY_SPEECH_WIRE_MAGIC || request.reserved){code=1;break;}
        if(request.kind==XYSP_QUIT){
            if(request.token || request.revision || request.status || request.count || request.underflows){code=1;break;}
            break;
        }
        int move_only=0;
#if XINYI_COACH_MOVE_AUDIO
        move_only=request.kind==XYSP_RUN_MOVE;
#if XINYI_BATTLE_R17
        move_only|=request.kind==XYSP_RUN_WHOLE;
#endif
#endif
        if((request.kind!=XYSP_RUN && !move_only) || !request.token || !request.revision || request.status ||
           request.underflows || !request.count || request.count>96){code=1;break;}
#if XINYI_COACH_MOVE_AUDIO
        if(move_only && request.count!=4){code=1;break;}
#endif
        for(unsigned i=0;i<96;i++){
            if(i<request.count){if(request.tokens[i]>=XQS_COUNT){code=1;break;}
#if XINYI_COACH_MOVE_AUDIO
                if(move_only && !xqs_move_token(request.tokens[i])){code=1;break;}
#endif
            }
            else if(request.tokens[i]){code=1;break;}
        }
        if(code)break;
        phrase.count=request.count;memcpy(phrase.tokens,request.tokens,request.count);
#if XINYI_BATTLE_R17
        if(request.kind==XYSP_RUN_WHOLE && !xqs_whole_tokens(&phrase)){code=1;break;}
#endif
        if(!rt_budget(&before)){code=1;(void)write_frame(XYSP_ERROR,request.token,request.revision,3,0,0);break;}
#if XINYI_COACH_MOVE_AUDIO
#if XINYI_BATTLE_R17
        if(request.kind==XYSP_RUN_WHOLE)okay=xqs_linux_play_whole(&phrase,argv[2],100,cancelled,NULL,&underflows);
        else
#endif
        if(move_only)okay=xqs_linux_play_move(&phrase,argv[2],100,cancelled,NULL,&underflows);
        else
#endif
        okay=xqs_linux_play(&phrase,argv[2],100,cancelled,NULL,&underflows);
        if(!rt_budget(&after) || after!=before){safe=0;code=1;status=4;}
        else status=stop_requested?2:okay && !underflows?0:1;
        if(!write_frame(XYSP_RESULT,request.token,request.revision,status,request.count,underflows)){code=1;break;}
        if(!safe || stop_requested)break;
        if(!write_frame(XYSP_IDLE_FRAME,request.token,request.revision,0,0,0)){code=1;break;}
    }
done:
    xqs_linux_release();
    if(!write_frame(XYSP_BYE,0,0,safe?0:4,0,0))code=1;
    close(3);return code;
}
