#define _GNU_SOURCE
#include "process.h"
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static uint64_t millis(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
    return (uint64_t)t.tv_sec*1000u+(unsigned)t.tv_nsec/1000000u;
}
void xy_cm_process_init(xy_cm_process *p)
{memset(p,0,sizeof(*p));p->pid=-1;p->fd=-1;}
static void signal_child(xy_cm_process *p,int sig)
{
    if(p->pid>0) { (void)kill(-p->pid,sig); (void)kill(p->pid,sig); }
}
int xy_cm_process_start(xy_cm_process *p,const char *exe,uint32_t token,
                        unsigned target,uint32_t cpu_hz,const char *identity)
{
    int pipes[2],flags;
    char target_text[16],cpu_text[16];
    pid_t parent=getpid(),child;
    if(!p || p->pid>0 || !exe || exe[0]!='/' || !token || target<30000 ||
       target>60000 || !identity || strlen(identity)>80 ||
       strspn(identity,"0123456789abcdefABCDEF-_.")!=strlen(identity))return 0;
    xy_cm_process_init(p);
    if(pipe(pipes))return 0;
    (void)snprintf(target_text,sizeof(target_text),"%u",target);
    (void)snprintf(cpu_text,sizeof(cpu_text),"%u",cpu_hz);
    child=fork();
    if(child==0) {
        int null_fd,fd;
        char *const args[]={(char *)exe,"--target-ms",target_text,"--cpu-hz",cpu_text,
                            "--identity",(char *)identity,NULL};
        (void)setpgid(0,0);
        if(prctl(PR_SET_PDEATHSIG,SIGKILL) || getppid()!=parent)_exit(126);
        if(dup2(pipes[1],STDOUT_FILENO)<0 || dup2(pipes[1],STDERR_FILENO)<0)_exit(126);
        null_fd=open("/dev/null",O_RDONLY);
        if(null_fd>=0)(void)dup2(null_fd,STDIN_FILENO);
#ifdef __NR_close_range
        if(syscall(__NR_close_range,3u,~0u,0u))
#endif
        {
            long max_fd=sysconf(_SC_OPEN_MAX);
            if(max_fd<0)max_fd=1024;
            for(fd=3;fd<max_fd;++fd)(void)close(fd);
        }
        execv(exe,args);
        _exit(127);
    }
    close(pipes[1]);
    if(child<0) {close(pipes[0]);return 0;}
    (void)setpgid(child,child);
    flags=fcntl(pipes[0],F_GETFL,0);
    if(flags<0 || fcntl(pipes[0],F_SETFL,flags|O_NONBLOCK)<0) {
        (void)kill(-child,SIGKILL);(void)kill(child,SIGKILL);
        while(waitpid(child,NULL,0)<0 && errno==EINTR){} close(pipes[0]);return 0;
    }
    (void)fcntl(pipes[0],F_SETFD,FD_CLOEXEC);
    p->pid=child;p->fd=pipes[0];p->status=XY_CM_RUNNING;p->token=token;
    p->target_ms=target;p->cpu_hz=cpu_hz;p->start_ms=millis();
    (void)snprintf(p->identity,sizeof(p->identity),"%s",identity);
    (void)snprintf(p->phase,sizeof(p->phase),"calibration");
    return 1;
}
static void parse_line(xy_cm_process *p)
{
    if(!strncmp(p->line,"XY_CM_PHASE phase=",18)) {
        (void)sscanf(p->line,"XY_CM_PHASE phase=%23s",p->phase);
    } else if(!strncmp(p->line,"XY_CM_RESULT ",13)) {
        char identity[81],kind[24];
        unsigned valid,cpu_hz,timer_hz,n=0;
        uint64_t vi;
        int used=0;
        if(p->saw_result) {p->line_failed=1;return;}
        n=(unsigned)sscanf(p->line,"XY_CM_RESULT kind=%23s valid=%u perf_iterations=%" SCNu64
            " perf_ticks=%" SCNu64 " validation_iterations=%" SCNu64 " validation_ticks=%" SCNu64
            " timer_hz=%u cpu_hz=%u identity=%80s%n",kind,&valid,&p->perf_iterations,
            &p->perf_ticks,&vi,&p->validation_ticks,&timer_hz,&cpu_hz,identity,&used);
        if(n!=9 || p->line[used]!=0 || cpu_hz!=p->cpu_hz || strcmp(identity,p->identity) ||
           timer_hz!=1000000000u || valid!=1 || !p->perf_iterations || !vi ||
           p->perf_ticks<10000000000ULL || p->validation_ticks<10000000000ULL ||
           p->perf_ticks>120000000000ULL || p->validation_ticks>120000000000ULL) {
            p->line_failed=1;return;
        }
        p->saw_result=1;p->valid=1;
        (void)snprintf(p->kind,sizeof(p->kind),"%s",kind);
#if defined(__riscv) && __riscv_xlen==32
        p->is_board=!strcmp(kind,"riscv32-linux") && cpu_hz && strlen(identity)==64 &&
            strspn(identity,"0123456789abcdefABCDEF")==64;
#endif
    }
}
static void read_output(xy_cm_process *p)
{
    char bytes[4096];
    ssize_t count;
    unsigned i;
    if(p->fd<0)return;
    count=read(p->fd,bytes,sizeof(bytes));
    if(count<=0)return;
    p->total_bytes+=(size_t)count;
    if(p->total_bytes>65536) {p->line_failed=1;return;}
    for(i=0;i<(unsigned)count;++i) {
        unsigned char ch=(unsigned char)bytes[i];
        if(ch!='\r'){
            if(p->output_used+1<sizeof(p->output)){
                p->output[p->output_used++]=(ch=='\n' || (ch>=32 && ch<=126))?(char)ch:'?';
                p->output[p->output_used]=0;
            }else p->output_truncated=1;
        }
        if(bytes[i]=='\n') {
            p->line[p->line_used]=0;parse_line(p);p->line_used=0;
        } else if(bytes[i]!='\r') {
            if(p->line_used+1<sizeof(p->line))p->line[p->line_used++]=bytes[i];
            else p->line_failed=1;
        }
    }
}
xy_cm_status xy_cm_process_poll(xy_cm_process *p)
{
    pid_t done;
    uint64_t now;
    if(!p || p->pid<=0)return p?p->status:XY_CM_FAILED;
    now=millis();p->elapsed_ms=(unsigned)(now-p->start_ms);
    if(p->status==XY_CM_RUNNING) {
        unsigned progress=(unsigned)((uint64_t)p->elapsed_ms*1000u/p->target_ms);
        p->progress=progress>950?950:progress;
        if(p->elapsed_ms>150000 || p->line_failed) {
            p->status=XY_CM_CANCEL_REQUESTED;p->cancel_ms=now;signal_child(p,SIGTERM);
            p->line_failed=1;
        }
    }
    if(p->status==XY_CM_CANCEL_REQUESTED && now-p->cancel_ms>=500)signal_child(p,SIGKILL);
    read_output(p);
    done=waitpid(p->pid,&p->wait_status,WNOHANG);
    if(done==p->pid) {
        /* A child's complete output is <=64KiB and fits the kernel pipe. Read
         * the finite tail after wait; never spin or block on a live child. */
        unsigned i;
        for(i=0;i<16;++i)read_output(p);
        close(p->fd);p->fd=-1;p->pid=-1;
        if(p->status==XY_CM_CANCEL_REQUESTED)
            p->status=p->line_failed?XY_CM_FAILED:XY_CM_CANCELLED;
        else if(WIFEXITED(p->wait_status) && WEXITSTATUS(p->wait_status)==0 &&
                p->saw_result && p->valid && !p->line_failed)
            {p->status=XY_CM_DONE;p->progress=1000;}
        else p->status=XY_CM_FAILED;
    } else if(done<0 && errno!=EINTR) {
        close(p->fd);p->fd=-1;p->pid=-1;p->status=XY_CM_FAILED;
    }
    return p->status;
}
int xy_cm_process_cancel(xy_cm_process *p)
{
    if(!p || p->pid<=0 || p->status!=XY_CM_RUNNING)return 0;
    p->status=XY_CM_CANCEL_REQUESTED;p->cancel_ms=millis();signal_child(p,SIGTERM);
    return 1;
}
void xy_cm_process_dispose(xy_cm_process *p)
{
    struct timespec interval={0,10000000};
    unsigned i;
    if(!p)return;
    if(p->pid>0)(void)xy_cm_process_cancel(p);
    for(i=0;i<100 && p->pid>0;++i) {
        (void)xy_cm_process_poll(p);
        if(p->pid>0)(void)nanosleep(&interval,NULL);
    }
    if(p->pid>0) {
        signal_child(p,SIGKILL);
        while(waitpid(p->pid,NULL,0)<0 && errno==EINTR){}
        p->pid=-1;
        if(p->fd>=0)close(p->fd);
        p->fd=-1;p->status=XY_CM_CANCELLED;
    }
}
int xy_cm_process_apply(xy_cm_process *p,xy_app *a)
{
    if(!p || !a || p->token!=a->token || a->job!=XY_COREMARK)return 0;
    int changed=0;
    if(a->coremark_log_used!=p->output_used || a->coremark_log_truncated!=p->output_truncated){
        memcpy(a->coremark_log,p->output,p->output_used+1);
        a->coremark_log_used=p->output_used;a->coremark_log_truncated=p->output_truncated;
        changed=1;
    }
    if(p->status==XY_CM_RUNNING) {
        unsigned elapsed=a->coremark_elapsed_ms,progress=a->coremark_progress;
        if(xy_coremark_progress(a,p->token,p->elapsed_ms,p->progress))
            changed|=elapsed!=a->coremark_elapsed_ms || progress!=a->coremark_progress;
        return changed;
    }
    if((a->cancelling && p->pid<=0 && (p->status==XY_CM_DONE ||
        p->status==XY_CM_FAILED || p->status==XY_CM_CANCELLED)) || p->status==XY_CM_CANCELLED ||
       (p->status==XY_CM_FAILED && a->cancelling))
        return xy_cancel_complete(a,p->token) || changed;
    if(p->status==XY_CM_DONE || p->status==XY_CM_FAILED) {
        int result=xy_coremark_complete(a,p->token,p->status==XY_CM_DONE && p->is_board,
            p->perf_iterations,p->perf_ticks,1000000000u,p->cpu_hz,p->identity);
        if(p->status==XY_CM_DONE && !p->is_board)
            (void)snprintf(a->message,sizeof(a->message),"主机算法校验通过，未写入板测成绩");
        return result || changed;
    }
    return changed;
}
