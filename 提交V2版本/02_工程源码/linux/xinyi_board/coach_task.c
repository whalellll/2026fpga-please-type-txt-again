#define _GNU_SOURCE
#include "coach_task.h"
#include "crc32_fast.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define FRAME_BYTES 1843200u
#define TMPFS_MAGIC_VALUE 0x01021994
enum task_state { STARTUP,IDLE,ACTIVE,RELEASE,STOPPING,POISON,DEAD };
struct xy_coach_task {
    xy_coach_config cfg;
    enum task_state state;
    char directory[64],worker[PATH_MAX],models[PATH_MAX];
    int dirfd,pipefd,memfd,child_status,reaped,term_sent,kill_sent;
    pid_t pid;
    volatile uint32_t *v321;
    uint64_t deadline,stop_time;
    unsigned idle_sequence,release_idle,pipe_bytes;
    int saw_ready,release_ack,pending_kind,cancelling,terminal_sent;
    char line[1024];size_t line_used;
    int line_overflow;
    uint32_t token,consumed_token;
    xqcoach_identity identity;
    xqcoach_result pending;
    unsigned remote_status;
    pthread_t writer;
    int writer_active,writer_result,published;
    atomic_int writer_done,writer_cancel;
    const unsigned char *input;
};
static uint64_t now_ms(void)
{
    struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);
    return (uint64_t)t.tv_sec*1000u+(unsigned long)t.tv_nsec/1000000u;
}
static unsigned duration(unsigned n,unsigned fallback){return n?n:fallback;}
static int regular_at(xy_coach_task *t,const char *name,int flags)
{
    struct stat s;int fd=openat(t->dirfd,name,flags|O_CLOEXEC|O_NOFOLLOW,0600);
    if(fd<0)return -1;
    if(fstat(fd,&s) || !S_ISREG(s.st_mode) || s.st_uid!=geteuid() || s.st_nlink!=1){close(fd);errno=EPROTO;return -1;}
    return fd;
}
static int write_bytes(int fd,const void *data,size_t size)
{
    const unsigned char *p=data;
    while(size){ssize_t n=write(fd,p,size);if(n<0 && errno==EINTR)continue;
        if(n<=0)return 0;
        p+=n;size-=(size_t)n;}
    return 1;
}
static void *write_frame(void *arg)
{
    xy_coach_task *t=arg;int fd=-1,rc=-1;uint32_t crc=0xffffffffu;
    char request[256];size_t size=xqcoach_encode_request(&t->identity,request,sizeof(request));
    fd=regular_at(t,"frame.rgb565.part",O_WRONLY|O_CREAT|O_EXCL);
    if(fd<0 || !size)goto done;
    for(size_t offset=0;offset<FRAME_BYTES;offset+=4096){
        size_t n=FRAME_BYTES-offset;if(n>4096)n=4096;
        if(atomic_load_explicit(&t->writer_cancel,memory_order_acquire))goto done;
        crc=crc32_fast(crc,t->input+offset,(uint32_t)n);
        if(!write_bytes(fd,t->input+offset,n))goto done;
    }
    if((crc^0xffffffffu)!=t->identity.crc)goto done;
    if(close(fd)){fd=-1;goto done;}fd=-1;
    if(atomic_load_explicit(&t->writer_cancel,memory_order_acquire))goto done;
    if(renameat(t->dirfd,"frame.rgb565.part",t->dirfd,"frame.rgb565"))goto done;
    fd=regular_at(t,"request.txt.part",O_WRONLY|O_CREAT|O_EXCL);
    if(fd<0 || !write_bytes(fd,request,size))goto done;
    if(close(fd)){fd=-1;goto done;}fd=-1;
    if(atomic_load_explicit(&t->writer_cancel,memory_order_acquire))goto done;
    if(renameat(t->dirfd,"request.txt.part",t->dirfd,"request.txt"))goto done;
    t->published=1;rc=1;
done:
    if(fd>=0)close(fd);
    t->writer_result=rc;
    atomic_store_explicit(&t->writer_done,1,memory_order_release);
    return NULL;
}
static int join_writer(xy_coach_task *t)
{
    if(!t->writer_active)return 1;
    if(!atomic_load_explicit(&t->writer_done,memory_order_acquire))return 0;
    int rc=pthread_tryjoin_np(t->writer,NULL);
    if(rc)return 0;
    t->writer_active=0;t->input=NULL;t->consumed_token=t->token;return 1;
}
static int drained(xy_coach_task *t)
{
    if(t->cfg.vision_drained)return t->cfg.vision_drained(t->cfg.context)==1;
    if(!t->v321 || t->v321[0x40/4]!=0x56333231u)return 0;
    atomic_thread_fence(memory_order_seq_cst);
    return !(t->v321[0x44/4]&1u);
}
static void unlink_request(xy_coach_task *t)
{(void)unlinkat(t->dirfd,"request.txt",0);}
static void begin_stop(xy_coach_task *t,int kind)
{
    if(t->state==STOPPING || t->state==POISON || t->state==DEAD)return;
    t->pending_kind=kind;t->state=STOPPING;t->stop_time=now_ms();
    atomic_store_explicit(&t->writer_cancel,1,memory_order_release);
    unlink_request(t);
    if(!t->reaped){(void)kill(-t->pid,SIGTERM);(void)kill(t->pid,SIGTERM);t->term_sent=1;}
}
static void read_child(xy_coach_task *t)
{
    if(t->reaped)return;
    pid_t answer=waitpid(t->pid,&t->child_status,WNOHANG);
    if(answer==t->pid)t->reaped=1;
    /* ECHILD cannot establish our waitpid contract; retain quarantine. */
}
/* Diagnostic counters only. Never forward raw child text: it can contain
 * live identity or a position. These records do not authorize a result/ACK. */
static void report_stage(const char *line)
{
    unsigned ms=0,jobs=0,count=0,status=0,loaded=0,mask=0,cpu=0;int n=0;
    if(sscanf(line,"XQ_NATIVE_STAGE board_done ms=%7u jobs=%7u%n",&ms,&jobs,&n)==2 &&
       n>0 && !line[n] && ms<=7200000 && jobs<=2000000){
        printf("XINYI_COACH_STAGE phase=board elapsed_ms=%u jobs=%u\n",ms,jobs);return;
    }
    n=0;
    if(sscanf(line,"XQ_NATIVE_STAGE detector_done ms=%7u jobs=%7u proposals=%3u%n",&ms,&jobs,&count,&n)==3 &&
       n>0 && !line[n] && ms<=7200000 && jobs<=2000000 && count<=300){
        printf("XINYI_COACH_STAGE phase=detector elapsed_ms=%u jobs=%u proposals=%u\n",ms,jobs,count);return;
    }
    n=0;
    if(sscanf(line,"XQ_NATIVE_STAGE classifier_done ms=%7u fixed=%3u%n",&ms,&count,&n)==2 &&
       n>0 && !line[n] && ms<=7200000 && count<=300){
        printf("XINYI_COACH_STAGE phase=classifier elapsed_ms=%u candidates=%u\n",ms,count);return;
    }
    n=0;
    unsigned prep=0,graph=0,io=0,post=0,refine=0,assign=0;
    if(sscanf(line,"XQ_NATIVE_PROFILE prepare_ms=%7u graph_ms=%7u ioctl_ms=%7u post_ms=%7u refine_ms=%7u assign_ms=%7u%n",
        &prep,&graph,&io,&post,&refine,&assign,&n)==6 && n>0 && !line[n] && prep<=7200000 && graph<=7200000 &&
        io<=graph && post<=7200000 && refine<=7200000 && assign<=7200000){
        printf("XINYI_COACH_PROFILE prepare_ms=%u graph_ms=%u ioctl_ms=%u post_ms=%u refine_ms=%u assign_ms=%u\n",prep,graph,io,post,refine,assign);return;
    }
    n=0;
    if(sscanf(line,"XQ_NATIVE_RECOGNITION status=%1u models_loaded=%1u executed_mask=%1u cpu_reference=%1u%n",
              &status,&loaded,&mask,&cpu,&n)==4 && n>0 && !strncmp(line+n," board_ms=",10) &&
       loaded==3 && mask<=7 && cpu<=1)
        printf("XINYI_COACH_TERMINAL native_status=%u executed_mask=%u cpu_reference=%u\n",status,mask,cpu);
}
static void line_received(xy_coach_task *t)
{
    t->line[t->line_used]=0;
    if(!t->line_overflow){
        if(!strcmp(t->line,"XQ_COACH_READY models=3 backend=" XQCOACH_BACKEND " stateless=1 EXPERIMENTAL"))t->saw_ready=1;
        else if(!strcmp(t->line,"XQ_COACH_IDLE"))++t->idle_sequence;
        else if(t->state==ACTIVE && t->saw_ready)report_stage(t->line);
    }
    t->line_used=0;t->line_overflow=0;
}
static int drain_pipe(xy_coach_task *t)
{
    char buf[1024];unsigned budget=8192;
    while(budget){ssize_t n=read(t->pipefd,buf,sizeof(buf));
        if(n<0 && errno==EINTR)continue;
        if(n<0)return errno==EAGAIN || errno==EWOULDBLOCK;
        if(!n)return 1;
        budget-=(unsigned)n;t->pipe_bytes+=(unsigned)n;
        if(t->pipe_bytes>1048576u)return 0;
        for(ssize_t i=0;i<n;++i){if(buf[i]=='\n')line_received(t);
            else if(t->line_used<sizeof(t->line)-1)t->line[t->line_used++]=buf[i];
            else t->line_overflow=1;}
    }
    return 1;
}
/* 0 absent, 1 complete valid, -1 invalid. Private atomic result rename means
 * malformed/partial files are fatal; no retry can mask an identity failure. */
static int read_result(xy_coach_task *t,xqcoach_result *out,unsigned *status)
{
    struct stat s;char *text;int fd=regular_at(t,"result.txt",O_RDONLY);
    if(fd<0)return errno==ENOENT?0:-1;
    if(fstat(fd,&s) || s.st_size<=0 || s.st_size>=XQCOACH_PACKET_BYTES){close(fd);return -1;}
    text=malloc((size_t)s.st_size);if(!text){close(fd);return -1;}
    size_t used=0;int okay=1;
    while(used<(size_t)s.st_size){ssize_t n=read(fd,text+used,(size_t)s.st_size-used);
        if(n<0 && errno==EINTR)continue;
        if(n<=0){okay=0;break;}used+=(size_t)n;}
    char extra;ssize_t more=read(fd,&extra,1);close(fd);
    xqcoach_parse_status parsed=XQCOACH_INVALID;
    if(okay && more==0){
        parsed=xqcoach_parse_result(text,used,&t->identity,out,status);
        if(parsed==XQCOACH_INVALID && xqcoach_parse_partial(text,used,&t->identity,out)==XQCOACH_ACCEPTED){
            parsed=XQCOACH_ACCEPTED;*status=5;
        }
    }
    free(text);return parsed==XQCOACH_INVALID?-1:1;
}
static int emit(xy_coach_task *t,xy_coach_event *event,xqcoach_result *out,int kind,int safe)
{
    if((kind==XY_COACH_RESULT || kind==XY_COACH_PARTIAL) && out)*out=t->pending;
    *event=(xy_coach_event){(xy_coach_event_type)kind,t->token,t->remote_status,
        !t->writer_active && t->consumed_token==t->token,safe,
        t->state==IDLE,t->reaped};
    return 1;
}
static int clean_files(xy_coach_task *t)
{
    static const char *const names[]={"request.txt","request.txt.part","frame.rgb565","frame.rgb565.part","result.txt","result.txt.part"};
    for(unsigned i=0;i<sizeof(names)/sizeof(names[0]);++i)
        if(unlinkat(t->dirfd,names[i],0) && errno!=ENOENT)return 0;
    return 1;
}
xy_coach_task *xy_coach_open(const xy_coach_config *cfg)
{
    xy_coach_task *t=NULL;struct statfs fs;struct stat s;int pipefds[2]={-1,-1},nullfd=-1;
    if(!cfg || !cfg->worker_path || !cfg->models_path || cfg->worker_path[0]!='/' || cfg->models_path[0]!='/' ||
        strlen(cfg->worker_path)>=PATH_MAX || strlen(cfg->models_path)>=PATH_MAX || statfs("/run",&fs) || fs.f_type!=TMPFS_MAGIC_VALUE)return NULL;
    if(stat(cfg->worker_path,&s) || !S_ISREG(s.st_mode) || access(cfg->worker_path,X_OK) ||
        stat(cfg->models_path,&s) || !S_ISDIR(s.st_mode))return NULL;
    t=calloc(1,sizeof(*t));if(!t)return NULL;
    t->dirfd=t->pipefd=t->memfd=-1;t->cfg=*cfg;
    strcpy(t->worker,cfg->worker_path);strcpy(t->models,cfg->models_path);
    strcpy(t->directory,"/run/xinyi-coach.XXXXXX");
    if(!mkdtemp(t->directory) || chmod(t->directory,0700))goto fail;
    t->dirfd=open(t->directory,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(t->dirfd<0 || fstat(t->dirfd,&s) || s.st_uid!=geteuid() || (s.st_mode&0777)!=0700 ||
        fstatfs(t->dirfd,&fs) || fs.f_type!=TMPFS_MAGIC_VALUE)goto fail;
    if(!cfg->vision_drained){
        t->memfd=open("/dev/mem",O_RDONLY|O_SYNC|O_CLOEXEC);if(t->memfd<0)goto fail;
        void *map=mmap(NULL,4096,PROT_READ,MAP_SHARED,t->memfd,0x1fe10000);
        if(map==MAP_FAILED)goto fail;
        t->v321=map;
        if(t->v321[0x40/4]!=0x56333231u)goto fail;
    }
    nullfd=open("/dev/null",O_RDONLY|O_CLOEXEC);
    if(nullfd<0 || pipe2(pipefds,O_CLOEXEC))goto fail;
    long maxfd=sysconf(_SC_OPEN_MAX);if(maxfd<0 || maxfd>65536)maxfd=65536;
    pid_t parent=getpid();t->pid=fork();
    if(t->pid<0)goto fail;
    if(t->pid==0){
        (void)setpgid(0,0);(void)prctl(PR_SET_PDEATHSIG,SIGKILL);
        if(getppid()!=parent)_exit(125);
        if(dup2(nullfd,STDIN_FILENO)<0 || dup2(pipefds[1],STDOUT_FILENO)<0 || dup2(pipefds[1],STDERR_FILENO)<0)_exit(126);
        /* Child performs only async-safe setup before exec; no heap or stdio. */
        for(int fd=3;fd<maxfd;++fd)close(fd);
        char *const argv[]={t->worker,"--driver","--models",t->models,"--serve",t->directory,NULL};
        execv(t->worker,argv);_exit(127);
    }
    (void)setpgid(t->pid,t->pid);
    close(nullfd);nullfd=-1;
    close(pipefds[1]);pipefds[1]=-1;t->pipefd=pipefds[0];pipefds[0]=-1;
    if(fcntl(t->pipefd,F_SETFL,fcntl(t->pipefd,F_GETFL)|O_NONBLOCK)<0){
        kill(-t->pid,SIGKILL);kill(t->pid,SIGKILL);while(waitpid(t->pid,NULL,0)<0 && errno==EINTR){};goto fail;}
    t->state=STARTUP;t->deadline=now_ms()+duration(cfg->startup_ms,120000);
    atomic_init(&t->writer_done,0);atomic_init(&t->writer_cancel,0);return t;
fail:
    if(pipefds[0]>=0)close(pipefds[0]);
    if(pipefds[1]>=0)close(pipefds[1]);
    if(nullfd>=0)close(nullfd);
    if(t){if(t->pipefd>=0)close(t->pipefd);if(t->v321)munmap((void *)t->v321,4096);
        if(t->memfd>=0)close(t->memfd);
        if(t->dirfd>=0)close(t->dirfd);
        if(t->directory[0])rmdir(t->directory);
        free(t);}return NULL;
}
int xy_coach_ready(const xy_coach_task *t){return t && t->state==IDLE && !t->reaped;}
long xy_coach_worker_pid(const xy_coach_task *t){return t?(long)t->pid:-1;}
int xy_coach_start(xy_coach_task *t,uint32_t token,const xy_platform_frame *frame)
{
    if(!xy_coach_ready(t) || !drained(t) || !frame || !token || frame->token!=token || !frame->rgb565 ||
        frame->bytes!=FRAME_BYTES || ((uintptr_t)frame->rgb565&3u) || !clean_files(t))return 0;
    t->token=token;t->input=(const unsigned char *)frame->rgb565;
    if(!xqcoach_identity_init(&t->identity,token,frame->frame_id,frame->crc32))return 0;
    t->consumed_token=0;t->writer_result=0;t->published=0;t->cancelling=0;
    t->release_ack=0;t->remote_status=0;t->pending_kind=XY_COACH_FATAL;
    t->pipe_bytes=0;atomic_store(&t->writer_done,0);atomic_store(&t->writer_cancel,0);
    if(pthread_create(&t->writer,NULL,write_frame,t)){t->input=NULL;return 0;}
    t->writer_active=1;t->state=ACTIVE;t->deadline=now_ms()+duration(t->cfg.request_ms,7200000);return 1;
}
int xy_coach_consumed(xy_coach_task *t,uint32_t token)
{if(!t || !token || t->token!=token)return 0;(void)join_writer(t);return !t->writer_active && t->consumed_token==token;}
int xy_coach_cancel(xy_coach_task *t,uint32_t token)
{
    if(!t || !token || token!=t->token || (t->state!=ACTIVE && t->state!=RELEASE) || t->cancelling)return 0;
    t->cancelling=1;t->pending_kind=XY_COACH_CANCELLED;
    atomic_store_explicit(&t->writer_cancel,1,memory_order_release);
    /* Keep an existing release generation if normal consumption already
     * removed request; this closes the result/cancel handoff race. */
    if(t->state!=RELEASE){t->release_idle=t->idle_sequence;t->release_ack=0;}
    t->state=RELEASE;t->deadline=now_ms()+duration(t->cfg.cancel_ms,2500);unlink_request(t);return 1;
}
int xy_coach_poll(xy_coach_task *t,xy_coach_event *event,xqcoach_result *out)
{
    if(!t || !event)return 0;
    (void)join_writer(t);read_child(t);
    if(!drain_pipe(t) && t->state!=STOPPING && t->state!=POISON && t->state!=DEAD)begin_stop(t,XY_COACH_FATAL);
    uint64_t now=now_ms();
    if(t->state==DEAD)return 0;
    if(t->state==POISON){
        /* A later explicit caller recovery may make close safe; no second ack. */
        return 0;
    }
    if(t->state!=STOPPING && t->reaped)begin_stop(t,XY_COACH_FATAL);
    if(t->state==STARTUP){
        if(t->saw_ready && t->idle_sequence && drained(t)){
            t->state=IDLE;return emit(t,event,out,XY_COACH_READY,1);}
        if(now>=t->deadline)begin_stop(t,XY_COACH_FATAL);
    } else if(t->state==ACTIVE){
        if(!t->writer_active && t->writer_result!=1)begin_stop(t,XY_COACH_FATAL);
        else if(!t->writer_active){
            unsigned status=UINT_MAX;xqcoach_result result={0};int r=read_result(t,&result,&status);
            if(r<0)begin_stop(t,XY_COACH_FATAL);
            else if(r){
                t->remote_status=status;
                if(status!=0 && status!=5)begin_stop(t,XY_COACH_FATAL);
                else {if(!status || result.count)t->pending=result;
                    t->pending_kind=!status?XY_COACH_RESULT:result.count?XY_COACH_PARTIAL:XY_COACH_GEOMETRY_REJECT;
                    t->release_idle=t->idle_sequence;t->release_ack=0;
                    t->state=RELEASE;t->deadline=now+duration(t->cfg.cancel_ms,2500);unlink_request(t);}
            }
        }
        if(t->state==ACTIVE && now>=t->deadline)begin_stop(t,XY_COACH_FATAL);
    }
    if(t->state==RELEASE){
        if(!t->writer_active){
            unlink_request(t);
            if(!t->published){begin_stop(t,t->cancelling?XY_COACH_CANCELLED:XY_COACH_FATAL);}
            else {
                unsigned status=UINT_MAX;xqcoach_result ignored;int r=read_result(t,&ignored,&status);
                if(r<0)begin_stop(t,XY_COACH_FATAL);
                else if(r && status==9)t->release_ack=1;
                else if(r && status!=0 && status!=5)begin_stop(t,XY_COACH_FATAL);
                if(t->state==RELEASE && t->release_ack && t->idle_sequence>t->release_idle && drained(t)){
                    int kind=t->pending_kind;t->state=IDLE;return emit(t,event,out,kind,1);}
            }
        }
        if(t->state==RELEASE && now>=t->deadline)begin_stop(t,t->cancelling?XY_COACH_CANCELLED:XY_COACH_FATAL);
    }
    if(t->state==STOPPING){
        unlink_request(t);read_child(t);
        /* begin_stop may have run after this poll's earlier clock sample.
         * Refresh before subtracting: crossing one millisecond must never
         * underflow unsigned elapsed into an immediate unsafe-timeout event. */
        now=now_ms();
        uint64_t elapsed=now>=t->stop_time?now-t->stop_time:0;
        unsigned term=duration(t->cfg.term_ms,1000),drain=duration(t->cfg.drain_ms,2000);
        if(!t->reaped && !t->kill_sent && elapsed>=term){
            kill(-t->pid,SIGKILL);kill(t->pid,SIGKILL);t->kill_sent=1;}
        if(t->reaped && !t->writer_active && drained(t)){
            int kind=t->pending_kind;t->state=DEAD;return emit(t,event,out,kind,1);}
        if(elapsed>=(uint64_t)term+drain){
            t->state=POISON;return emit(t,event,out,XY_COACH_UNDRAINED,0);}
    }
    return 0;
}
int xy_coach_close(xy_coach_task *t)
{
    if(!t)return 1;
    if(t->state==POISON){
        (void)join_writer(t);read_child(t);
        if(t->writer_active || !t->reaped || !drained(t))return 0;
        t->state=DEAD;
    }
    if(t->state!=DEAD)begin_stop(t,XY_COACH_CANCELLED);
    uint64_t until=now_ms()+duration(t->cfg.term_ms,1000)+duration(t->cfg.drain_ms,2000)+100;
    while(t->state!=DEAD && t->state!=POISON && now_ms()<until){
        xy_coach_event event;(void)xy_coach_poll(t,&event,NULL);
        struct timespec pause={0,1000000};nanosleep(&pause,NULL);}
    if(t->state!=DEAD || t->writer_active || !t->reaped || !drained(t))return 0;
    if(!clean_files(t))return 0;
    if(rmdir(t->directory))return 0;
    close(t->dirfd);close(t->pipefd);
    if(t->v321)munmap((void *)t->v321,4096);
    if(t->memfd>=0)close(t->memfd);
    free(t);return 1;
}
