#define _GNU_SOURCE
#include "engine_bridge.h"
#include "xiangqi_pikafish_link.h"
#include "xq_speech.h"
#include "crc32_fast.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static uint64_t milliseconds(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
    return (uint64_t)t.tv_sec*1000u+(unsigned)t.tv_nsec/1000000u;
}
static void close_fd(int *fd){if(*fd>=0)close(*fd);*fd=-1;}
void xy_engine_init(xy_engine *e)
{
    if(!e)return;
    memset(e,0,sizeof(*e));e->pid=e->input=e->output=-1;
    e->state=XY_ENGINE_STOPPED;e->timeout_ms=180000;
}
int xy_engine_notation(const xq_search_board_t *b,const char *iccs,char *out,size_t bytes)
{
    static const char *const text[]={"零","一","二","三","四","五","六","七","八","九",
        "十","百","千","点","红","黑","帅","将","士","象","马","车","炮","兵","卒",
        "进","退","平","前","后","中"};
    xqs_phrase p;size_t used=0;
    if(!b || !out || !bytes || !xqs_move_phrase(b,iccs,&p))return 0;
    for(unsigned i=0;i<p.count;i++){
        if(!i && (p.tokens[i]==XQS_RED || p.tokens[i]==XQS_BLACK))continue;
        if(p.tokens[i]>=sizeof(text)/sizeof(text[0]))return 0;
        size_t n=strlen(text[p.tokens[i]]);
        if(n>=bytes-used)return 0;
        memcpy(out+used,text[p.tokens[i]],n);used+=n;
    }
    out[used]=0;return 1;
}
static int spawn_service(xy_engine *e,const char *executable)
{
    int to[2],from[2];
    if(socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,to))return 0;
    if(socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,from)){close(to[0]);close(to[1]);return 0;}
    pid_t parent=getpid(),pid=fork();
    if(pid<0){close(to[0]);close(to[1]);close(from[0]);close(from[1]);return 0;}
    if(!pid){
        if(prctl(PR_SET_PDEATHSIG,SIGKILL) || getppid()!=parent)_exit(125);
        if(dup2(to[0],STDIN_FILENO)<0 || dup2(from[1],3)<0)_exit(125);
        /* dup2 is a no-op when the source is already 3. */
        if(fcntl(3,F_SETFD,0)<0)_exit(125);
        int list[]={to[0],to[1],from[0],from[1]};
        for(unsigned i=0;i<4;i++)if(list[i]!=0 && list[i]!=3)close(list[i]);
        int sink=open("/dev/null",O_WRONLY);
        if(sink<0 || dup2(sink,1)<0 || dup2(sink,2)<0)_exit(125);
        if(sink>3)close(sink);
        /* Runtime logs can contain live FEN. Only the private fd3 protocol
         * returns to this process; no live position is logged to UART. */
        char *const argv[]={(char *)executable,"--protocol-fd3",NULL};
        execv(executable,argv);_exit(127);
    }
    close(to[0]);close(from[1]);e->pid=pid;e->input=to[1];e->output=from[0];
    if(fcntl(e->input,F_SETFL,O_NONBLOCK)<0 || fcntl(e->output,F_SETFL,O_NONBLOCK)<0){
        e->fault=1;xy_engine_cancel(e);return 0;
    }
    e->state=XY_ENGINE_STARTING;return 1;
}
int xy_engine_start(xy_engine *e,const char *exe,uint32_t token,uint32_t revision,
                    const xq_search_board_t *board,unsigned nodes)
{
    char fen[128];uint8_t identity[91];
    if(!e || !exe || *exe!='/' || !token || !revision || !board ||
       nodes<16 || nodes>1000000 || (board->side!=0 && board->side!=1) ||
       (e->state!=XY_ENGINE_STOPPED && e->state!=XY_ENGINE_FAILED && e->state!=XY_ENGINE_READY) ||
       (e->state==XY_ENGINE_FAILED && e->pid>0) || !xq_pikafish_board_to_fen(board,fen,sizeof(fen)))return 0;
    memcpy(identity,board->squares,90);identity[90]=(uint8_t)board->side;
    e->board_crc=crc32_fast(0xffffffffu,identity,sizeof(identity))^0xffffffffu;
    int n=snprintf(e->pending,sizeof(e->pending),"XQ_ENGINE_REQUEST_V1 %u %u %08x %u %s\n",
                   token,revision,e->board_crc,nodes,fen);
    if(n<0 || n>=(int)sizeof(e->pending))return 0;
    e->pending_bytes=(size_t)n;e->token=token;e->revision=revision;e->nodes=nodes;
    e->position=*board;e->used=0;e->fault=e->cancel_requested=0;
    memset(&e->reply,0,sizeof(e->reply));e->started_ms=milliseconds();
    if(!e->started_ms)return 0;
    if(e->pid<=0 && !spawn_service(e,exe))return 0;
    if(e->state==XY_ENGINE_READY)e->state=XY_ENGINE_BUSY;
    return 1;
}
int xy_engine_cancel(xy_engine *e)
{
    if(!e)return 0;
    if(e->pid<=0){e->state=e->fault?XY_ENGINE_FAILED:XY_ENGINE_STOPPED;return 1;}
    if(e->state!=XY_ENGINE_STOPPING){
        e->cancel_requested=1;e->cancel_ms=milliseconds();e->state=XY_ENGINE_STOPPING;
        e->pending_bytes=0;memset(&e->reply,0,sizeof(e->reply));
        kill(e->pid,SIGTERM);
    }
    return 1;
}
static int accept_line(xy_engine *e)
{
    e->line[e->used]=0;
    if(e->state==XY_ENGINE_STARTING && !strcmp(e->line,"XQ_ENGINE_READY_V1")){
        e->state=XY_ENGINE_BUSY;return 1;
    }
    if(e->state!=XY_ENGINE_BUSY || e->pending_bytes)return 0;
    xy_engine_reply r={0};char magic[32],move[8];unsigned okay,wins,draws,losses,wdl;
    int end=0;
    if(sscanf(e->line,"%31s %u %u %x %u %7s %d %u %u %u %u %u %u %n",magic,
        &r.token,&r.revision,&r.board_crc,&okay,move,&r.score_cp,&r.nodes,&wins,&draws,&losses,
        &r.elapsed_us,&wdl,&end)!=13 || strcmp(magic,"XQ_ENGINE_RESULT_V1") || !end || e->line[end] ||
        r.token!=e->token || r.revision!=e->revision || r.board_crc!=e->board_crc || okay!=1 ||
        strlen(move)!=4 || move[0]<'a' || move[0]>'i' || move[2]<'a' || move[2]>'i' ||
        move[1]<'0' || move[1]>'9' || move[3]<'0' || move[3]>'9' ||
        wdl>1 || wins>1000 || draws>1000 || losses>1000 || (wdl && wins+draws+losses!=1000))return 0;
    r.move.from=(uint8_t)((move[1]-'0')*9+move[0]-'a');
    r.move.to=(uint8_t)((move[3]-'0')*9+move[2]-'a');
    if(!xq_search_is_legal(&e->position,r.move))return 0;
    memcpy(r.iccs,move,5);
    /* Ambiguous spoken notation is explicit failure, never an invented move. */
    if(!xy_engine_notation(&e->position,move,r.notation,sizeof(r.notation)))return 0;
    r.okay=1;r.have_wdl=(int)wdl;r.red_win_permille=UINT32_MAX;
    if(wdl){unsigned side_rate=wins+draws/2;r.red_win_permille=e->position.side?1000-side_rate:side_rate;}
    e->reply=r;e->state=XY_ENGINE_DONE;return 1;
}
xy_engine_state xy_engine_poll(xy_engine *e)
{
    if(!e)return XY_ENGINE_FAILED;
    if(e->pid<=0)return e->state;
    int status=0;pid_t ended=waitpid(e->pid,&status,WNOHANG);
    if(ended==e->pid || (ended<0 && errno==ECHILD)){
        e->pid=-1;e->wait_status=status;close_fd(&e->input);close_fd(&e->output);
        e->pending_bytes=e->used=0;
        e->state=e->cancel_requested && !e->fault?XY_ENGINE_STOPPED:XY_ENGINE_FAILED;
        return e->state;
    }
    uint64_t now=milliseconds();
    if(e->state==XY_ENGINE_STOPPING){
        if(now-e->cancel_ms>=500)kill(e->pid,SIGKILL);
        return e->state;
    }
    if(!now || ((e->state==XY_ENGINE_STARTING || e->state==XY_ENGINE_BUSY) && now-e->started_ms>=e->timeout_ms)){
        e->fault=1;xy_engine_cancel(e);return e->state;
    }
    if(e->state==XY_ENGINE_BUSY && e->pending_bytes){
        ssize_t n=send(e->input,e->pending,e->pending_bytes,MSG_NOSIGNAL);
        if(n>0){memmove(e->pending,e->pending+n,e->pending_bytes-(size_t)n);e->pending_bytes-=(size_t)n;}
        else if(n<0 && errno!=EINTR && errno!=EAGAIN){e->fault=1;xy_engine_cancel(e);return e->state;}
    }
    unsigned budget=4096;
    while(budget-- && e->state!=XY_ENGINE_DONE){
        char c;ssize_t n=read(e->output,&c,1);
        if(n<0 && (errno==EAGAIN || errno==EINTR))break;
        if(n<=0){e->fault=1;xy_engine_cancel(e);break;}
        if(c=='\n'){
            if(!accept_line(e)){e->fault=1;xy_engine_cancel(e);break;}
            e->used=0;
        }else if(c=='\r' || !c || e->used+1>=sizeof(e->line)){
            e->fault=1;xy_engine_cancel(e);break;
        }else e->line[e->used++]=c;
    }
    return e->state;
}
int xy_engine_take(xy_engine *e,xy_engine_reply *out)
{
    if(!e || !out || e->state!=XY_ENGINE_DONE)return 0;
    *out=e->reply;memset(&e->reply,0,sizeof(e->reply));e->state=XY_ENGINE_READY;return 1;
}
int xy_engine_dispose(xy_engine *e)
{
    if(!e)return 0;
    xy_engine_cancel(e);
    for(unsigned i=0;i<1200 && e->pid>0;i++){
        xy_engine_poll(e);struct timespec t={0,1000000};if(e->pid>0)nanosleep(&t,NULL);
    }
    return e->pid<=0;
}
