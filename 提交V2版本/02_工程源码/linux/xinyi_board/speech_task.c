#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
#include "speech_task.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static uint64_t now_ms(void)
{
    struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return UINT64_MAX;
    return (uint64_t)t.tv_sec*1000u+(unsigned)t.tv_nsec/1000000u;
}
void xy_speech_task_init(xy_speech_task *t)
{if(t){memset(t,0,sizeof(*t));t->pid=-1;t->fd=-1;t->state=XY_SPEECH_IDLE;}}
static void close_channel(xy_speech_task *t)
{
    if(t->fd>=0)close(t->fd);
    t->fd=-1;t->ready=0;t->incoming_used=t->outgoing_used=t->outgoing_sent=0;
}
static void fail_protocol(xy_speech_task *t)
{
    if(!t->protocol_error){
        uint64_t now=now_ms();t->deadline_ms=now==UINT64_MAX?0:now+5000u;
        if(t->pid>0)(void)kill(t->pid,SIGTERM);
    }
    t->protocol_error=1;t->state=XY_SPEECH_STOPPING;t->cleanup_confirmed=0;
    t->outgoing_used=t->outgoing_sent=0;
}
static int flush(xy_speech_task *t)
{
    while(t->outgoing_sent<t->outgoing_used){
        ssize_t n=send(t->fd,t->outgoing+t->outgoing_sent,t->outgoing_used-t->outgoing_sent,MSG_NOSIGNAL|MSG_DONTWAIT);
        if(n>0){t->outgoing_sent+=(size_t)n;continue;}
        if(n<0 && errno==EINTR)continue;
        if(n<0 && (errno==EAGAIN || errno==EWOULDBLOCK))return 1;
        return 0;
    }
    t->outgoing_used=t->outgoing_sent=0;return 1;
}
static int queue_frame(xy_speech_task *t,const xy_speech_wire *frame)
{
    if(t->outgoing_used)return 0;
    memcpy(t->outgoing,frame,sizeof(*frame));t->outgoing_used=sizeof(*frame);t->outgoing_sent=0;
    return flush(t);
}
static int spawn(xy_speech_task *t)
{
    int pair[2],nullfd,flags;pid_t child;struct rlimit limit;
    if(access(t->worker,X_OK) || access(t->pcm_directory,R_OK))return 0;
    if(getrlimit(RLIMIT_NOFILE,&limit))return 0;
    if(socketpair(AF_UNIX,SOCK_STREAM|SOCK_CLOEXEC,0,pair))return 0;
    nullfd=open("/dev/null",O_RDWR|O_CLOEXEC);if(nullfd<0){close(pair[0]);close(pair[1]);return 0;}
    flags=fcntl(pair[0],F_GETFL,0);
    if(flags<0 || fcntl(pair[0],F_SETFL,flags|O_NONBLOCK)){close(pair[0]);close(pair[1]);close(nullfd);return 0;}
    child=fork();
    if(child<0){close(pair[0]);close(pair[1]);close(nullfd);return 0;}
    if(!child){
        if(dup2(nullfd,STDIN_FILENO)<0 || dup2(nullfd,STDOUT_FILENO)<0 ||
           dup2(nullfd,STDERR_FILENO)<0 || dup2(pair[1],3)<0)_exit(126);
        if(fcntl(3,F_SETFD,0)<0)_exit(126);
#ifdef SYS_close_range
        if(syscall(SYS_close_range,4u,~0u,0u)<0)
#endif
            for(rlim_t fd=4;fd<limit.rlim_cur;fd++)close((int)fd);
        execl(t->worker,t->worker,"--pcm",t->pcm_directory,(char *)NULL);_exit(127);
    }
    close(pair[1]);close(nullfd);t->pid=child;t->fd=pair[0];t->starts++;
    t->ready=t->bye_received=t->result_received=0;
    t->cleanup_confirmed=0;t->incoming_used=t->outgoing_used=t->outgoing_sent=0;
    return 1;
}
int xy_speech_task_start(xy_speech_task *t,const char *worker,const char *directory,
    uint32_t token,uint32_t revision,const xq_search_board_t *before,const char *iccs)
{
    xqs_phrase p;
    if(!t || !worker || worker[0]!='/' || !directory || directory[0]!='/' ||
       strlen(worker)>=sizeof(t->worker) || strlen(directory)>=sizeof(t->pcm_directory) ||
       !token || !revision || !before || (before->side!=0 && before->side!=1) ||
       !iccs || !xqs_move_phrase(before,iccs,&p) || !p.count || p.count>96 ||
       t->state==XY_SPEECH_STARTING || t->state==XY_SPEECH_RUNNING || t->state==XY_SPEECH_STOPPING ||
       t->cancelling || t->closing)return 0;
    if(t->state==XY_SPEECH_FAILED && t->pid<=0 && t->starts && !t->cleanup_confirmed)return 0;
    if(t->pid>0 && (!t->ready || strcmp(t->worker,worker) || strcmp(t->pcm_directory,directory)))return 0;
    memcpy(t->worker,worker,strlen(worker)+1);memcpy(t->pcm_directory,directory,strlen(directory)+1);
    memset(&t->request,0,sizeof(t->request));t->request.magic=XY_SPEECH_WIRE_MAGIC;t->request.kind=XYSP_RUN;
    t->request.token=token;t->request.revision=revision;t->request.count=p.count;
    memcpy(t->request.tokens,p.tokens,p.count);
    t->token=token;t->revision=revision;t->result_received=0;t->result_status=t->underflows=0;
    t->cleanup_confirmed=0;t->protocol_error=0;
    if(t->pid<=0 && !spawn(t)){t->state=XY_SPEECH_FAILED;return 0;}
    t->state=t->ready?XY_SPEECH_RUNNING:XY_SPEECH_STARTING;
    uint64_t now=now_ms();t->deadline_ms=now==UINT64_MAX?0:now+(t->ready?45000u:10000u);
    if(t->ready && !queue_frame(t,&t->request)){fail_protocol(t);return 0;}
    return 1;
}
int xy_speech_task_cancel(xy_speech_task *t,uint32_t token,uint32_t revision)
{
    if(!t || token!=t->token || revision!=t->revision || t->pid<=0 ||
       (t->state!=XY_SPEECH_STARTING && t->state!=XY_SPEECH_RUNNING && t->state!=XY_SPEECH_STOPPING &&
        t->state!=XY_SPEECH_DONE && t->state!=XY_SPEECH_FAILED))return 0;
    if(!t->cancelling){
        uint64_t now=now_ms();t->deadline_ms=now==UINT64_MAX?0:now+5000u;
        t->cancelling=1;t->state=XY_SPEECH_STOPPING;(void)kill(t->pid,SIGTERM);
    }
    return 1;
}
static int frame(xy_speech_task *t,const xy_speech_wire *m)
{
    if(m->magic!=XY_SPEECH_WIRE_MAGIC || m->reserved)return 0;
    for(unsigned i=0;i<96;i++)if(m->tokens[i])return 0;
    if(m->kind==XYSP_READY){
        if(t->ready || m->token || m->revision || m->count || m->status || m->underflows)return 0;
        t->ready=1;
        if(t->state==XY_SPEECH_STARTING){
            uint64_t now=now_ms();t->deadline_ms=now==UINT64_MAX?0:now+45000u;
            t->state=XY_SPEECH_RUNNING;return queue_frame(t,&t->request);
        }
        return t->state==XY_SPEECH_STOPPING;
    }
    if(m->kind==XYSP_BYE){
        if(m->token || m->revision || m->count || m->underflows)return 0;
        t->bye_received=1;t->cleanup_confirmed=m->status==0;return 1;
    }
    if(m->kind==XYSP_ERROR){
        if(!m->status || m->status>4 || m->count || m->underflows ||
           !((!m->token && !m->revision && t->state==XY_SPEECH_STARTING) ||
             (m->token==t->token && m->revision==t->revision &&
              (t->state==XY_SPEECH_RUNNING || t->state==XY_SPEECH_STOPPING))))return 0;
        t->result_status=m->status;return 1;
    }
    if(m->kind!=XYSP_RESULT && m->kind!=XYSP_IDLE_FRAME)return 0;
    if(m->token!=t->token || m->revision!=t->revision)return 0;
    if(m->kind==XYSP_RESULT){
        if(t->result_received || m->count!=t->request.count || m->status>4)return 0;
        t->result_received=1;t->result_status=m->status;t->underflows=m->underflows;return 1;
    }
    if(!t->result_received || m->count || m->status || m->underflows)return 0;
    t->ready=1;t->cleanup_confirmed=1;
    if(!t->cancelling && !t->closing && !t->protocol_error)
        t->state=!t->result_status && !t->underflows?XY_SPEECH_DONE:XY_SPEECH_FAILED;
    return 1;
}
int xy_speech_task_poll(xy_speech_task *t)
{
    int before,status=0,eof=0;pid_t ended;
    if(!t || t->pid<=0)return 0;
    before=t->state;
    if(!flush(t))fail_protocol(t);
    if(t->fd>=0)for(;;){
        ssize_t n=read(t->fd,t->incoming+t->incoming_used,sizeof(t->incoming)-t->incoming_used);
        if(n>0){
            t->incoming_used+=(size_t)n;
            if(t->incoming_used==sizeof(t->incoming)){
                xy_speech_wire message;memcpy(&message,t->incoming,sizeof(message));t->incoming_used=0;
                if(!frame(t,&message)){fail_protocol(t);break;}
            }
        }else if(!n){eof=1;break;}
        else if(errno==EINTR)continue;
        else if(errno==EAGAIN || errno==EWOULDBLOCK)break;
        else {eof=1;break;}
    }
    do{ended=waitpid(t->pid,&status,WNOHANG);}while(ended<0 && errno==EINTR);
    if(ended==t->pid){
        t->wait_status=status;t->pid=-1;close_channel(t);
        if((t->cancelling || t->closing) && !t->protocol_error && t->bye_received &&
           t->cleanup_confirmed && WIFEXITED(status) && WEXITSTATUS(status)==0)t->state=XY_SPEECH_STOPPED;
        else t->state=XY_SPEECH_FAILED;
        t->cancelling=t->closing=0;
    }else if(ended<0){
        t->pid=-1;close_channel(t);t->state=XY_SPEECH_FAILED;t->cleanup_confirmed=0;
    }else if((t->state==XY_SPEECH_STARTING || t->state==XY_SPEECH_RUNNING) && now_ms()>=t->deadline_ms){
        fail_protocol(t);
    }else if((t->cancelling || t->closing || t->protocol_error) && now_ms()>=t->deadline_ms){
        (void)kill(t->pid,SIGKILL);t->protocol_error=1;t->cleanup_confirmed=0;
    }else if(eof && !t->bye_received)fail_protocol(t);
    return before!=t->state;
}
int xy_speech_task_close(xy_speech_task *t)
{
    if(!t)return 0;
    if(t->pid<=0){
        if(t->state!=XY_SPEECH_FAILED){t->state=XY_SPEECH_STOPPED;if(!t->starts)t->cleanup_confirmed=1;}
        close_channel(t);return 1;
    }
    if(!t->closing){
        uint64_t now=now_ms();t->deadline_ms=now==UINT64_MAX?0:now+5000u;t->closing=1;
        if(t->state==XY_SPEECH_STARTING || t->state==XY_SPEECH_RUNNING || t->state==XY_SPEECH_STOPPING)
            (void)xy_speech_task_cancel(t,t->token,t->revision);
        else {
            xy_speech_wire quit={0};quit.magic=XY_SPEECH_WIRE_MAGIC;quit.kind=XYSP_QUIT;
            t->state=XY_SPEECH_STOPPING;if(!queue_frame(t,&quit))fail_protocol(t);
        }
    }
    return 0;
}
