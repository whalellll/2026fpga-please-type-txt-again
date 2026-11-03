#define _GNU_SOURCE
#include "coach_task.h"
#include "crc32_fast.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static uint64_t now_ms(void)
{struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return(uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static void pause_ms(void){struct timespec t={0,1000000};nanosleep(&t,NULL);}
static int checker(void *p){return *(int *)p;}
static void directory(long pid,char *out,size_t cap)
{
    char path[80],args[8192];snprintf(path,sizeof(path),"/proc/%ld/cmdline",pid);
    int fd=open(path,O_RDONLY);assert(fd>=0);ssize_t n=read(fd,args,sizeof(args));close(fd);assert(n>0);
    size_t i=0;
    while(i<(size_t)n && strncmp(args+i,"/run/xinyi-coach.",17))i+=strlen(args+i)+1;
    assert(i<(size_t)n && strlen(args+i)<cap);strcpy(out,args+i);
    assert(!strncmp(out,"/run/xinyi-coach.",17));
    struct stat s;struct statfs fs;assert(!stat(out,&s) && (s.st_mode&0777)==0700 && s.st_uid==geteuid());
    assert(!statfs(out,&fs) && fs.f_type==0x01021994);
}
static xy_coach_task *start(const char *worker,const char *base,const char *mode,int *idle)
{
    char models[4096];assert(snprintf(models,sizeof(models),"%s/%s",base,mode)<(int)sizeof(models));
    assert(!mkdir(models,0700) || errno==EEXIST);
    xy_coach_config config={worker,models,3000,3000,300,300,1500,checker,idle};
    xy_coach_task *t=xy_coach_open(&config);assert(t);return t;
}
static xy_coach_event terminal(xy_coach_task *t,xqcoach_result *out)
{
    xy_coach_event event;uint64_t deadline=now_ms()+5000;
    while(now_ms()<deadline){if(xy_coach_poll(t,&event,out))return event;pause_ms();}
    assert(!"coach event deadline");return event;
}
static void ready(xy_coach_task *t)
{xy_coach_event e=terminal(t,NULL);assert(e.type==XY_COACH_READY && e.drained && xy_coach_ready(t));}
static xy_platform_frame frame(uint32_t token)
{
    uint32_t *p=mmap(NULL,1843200,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);assert(p!=MAP_FAILED);
    for(unsigned i=0;i<1843200/4;++i)p[i]=i*1664525u+token;
    xy_platform_frame f={token,123+token,0,0,p,1843200};
    f.crc32=crc32_fast(0xffffffffu,p,1843200)^0xffffffffu;return f;
}
static void consume(xy_coach_task *t,xy_platform_frame *f)
{
    uint64_t end=now_ms()+2000;while(!xy_coach_consumed(t,f->token) && now_ms()<end)pause_ms();
    assert(xy_coach_consumed(t,f->token));assert(!munmap((void *)f->rgb565,f->bytes));f->rgb565=NULL;
}
static void reaped(long pid){int status;assert(waitpid((pid_t)pid,&status,WNOHANG)==-1 && errno==ECHILD);}
static void wait_file(long pid,const char *name)
{
    char path[256],dir[128];directory(pid,dir,sizeof(dir));
    assert(snprintf(path,sizeof(path),"%s/%s",dir,name)<(int)sizeof(path));
    uint64_t deadline=now_ms()+2000;
    while(access(path,F_OK) && now_ms()<deadline)pause_ms();
    assert(!access(path,F_OK));
}
int main(int argc,char **argv)
{
    assert(argc==3 || (argc==4 && !strcmp(argv[3],"clock-negative")));
    int clock_negative=argc==4;
    int idle=1;char private_dir[128];xqcoach_result result,before;
    xy_coach_task *t=start(argv[1],argv[2],"normal",&idle);ready(t);
    long pid=xy_coach_worker_pid(t);directory(pid,private_dir,sizeof(private_dir));
    for(unsigned i=1;i<=2;++i){
        xy_platform_frame f=frame(i);assert(xy_coach_start(t,i,&f));assert(!xy_coach_start(t,i,&f));
        consume(t,&f);xy_coach_event e=terminal(t,&result);
        assert(e.type==XY_COACH_RESULT && e.token==i && e.consumed && e.drained && e.resident_ready && !e.worker_reaped);
        assert(result.count==300 && result.identity.token==i && xy_coach_worker_pid(t)==pid && xy_coach_ready(t));
    }
    assert(xy_coach_close(t));reaped(pid);assert(access(private_dir,F_OK) && errno==ENOENT);
    puts("XINYI_COACH_REUSE_PASS tmpfs0700 pin_until_join 300_candidates two_requests_same_pid release9_idle_busy0");
    t=start(argv[1],argv[2],"geometry-once",&idle);ready(t);pid=xy_coach_worker_pid(t);xy_platform_frame f=frame(3);
    assert(xy_coach_start(t,3,&f));consume(t,&f);before=result;
    xy_coach_event e=terminal(t,&result);assert(e.type==XY_COACH_GEOMETRY_REJECT && e.remote_status==5 && e.drained);
    assert(!memcmp(&result,&before,sizeof(result)) && xy_coach_ready(t) && e.resident_ready && !e.worker_reaped);
    assert(xy_coach_worker_pid(t)==pid);
    f=frame(4);assert(xy_coach_start(t,4,&f));consume(t,&f);e=terminal(t,&result);
    assert(e.type==XY_COACH_RESULT && e.remote_status==0 && e.token==4 && e.consumed && e.drained && e.resident_ready && !e.worker_reaped);
    assert(result.identity.token==4 && result.count==300 && xy_coach_worker_pid(t)==pid && xy_coach_ready(t));
    assert(xy_coach_close(t));reaped(pid);
    puts("XINYI_COACH_GEOMETRY_PASS wire5_prior_result_untouched same_pid_next_request_success");
    const char *partial_modes[]={"partial-once","estimated-once"};
    for(unsigned i=0;i<2;i++){
        t=start(argv[1],argv[2],partial_modes[i],&idle);ready(t);pid=xy_coach_worker_pid(t);f=frame(5);
        assert(xy_coach_start(t,5,&f));consume(t,&f);e=terminal(t,&result);
        assert(e.type==XY_COACH_PARTIAL && e.remote_status==5 && e.drained && e.resident_ready && result.count==3 && result.estimated==i);
        assert(result.candidates[0].file==(i?4:255));
        f=frame(6);assert(xy_coach_start(t,6,&f));consume(t,&f);e=terminal(t,&result);
        assert(e.type==XY_COACH_RESULT && !result.estimated && result.count==300 && result.identity.token==6 && xy_coach_worker_pid(t)==pid);
        assert(xy_coach_close(t));reaped(pid);
    }
    puts("XINYI_COACH_PARTIAL_ESTIMATE_RELEASE9_IDLE_BUSY0_REUSE_NO_STALE_PASS");
    const char *bad[]={"body-crc","backend","token","frame","raw-crc","truncate","status6","unsolicited9"};
    for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);++i){
        t=start(argv[1],argv[2],bad[i],&idle);ready(t);pid=xy_coach_worker_pid(t);f=frame(10+i);
        assert(xy_coach_start(t,f.token,&f));consume(t,&f);result=before;e=terminal(t,&result);
        if(clock_negative && i==0 && e.type==XY_COACH_UNDRAINED && !e.drained){
            /* The old bug emits unsafe-timeout before its killed worker can
             * be reaped. Cleanup still waits for the actual safe close. */
            uint64_t end=now_ms()+4000;int closed=0;
            while(!(closed=xy_coach_close(t)) && now_ms()<end)pause_ms();
            assert(closed);reaped(pid);
            puts("XINYI_COACH_CLOCK_NEGATIVE_CONTROL_CONFIRMED old_unsigned_underflow");return 0;
        }
        if(e.type!=XY_COACH_FATAL || !e.drained || !e.worker_reaped || memcmp(&result,&before,sizeof(result)))
            fprintf(stderr,"synthetic mode=%s type=%d drained=%d reaped=%d unchanged=%d\n",bad[i],e.type,e.drained,e.worker_reaped,!memcmp(&result,&before,sizeof(result)));
        assert(e.type==XY_COACH_FATAL && e.drained && e.worker_reaped && !memcmp(&result,&before,sizeof(result)));
        assert(!xy_coach_ready(t));reaped(pid);assert(xy_coach_close(t));
    }
    puts("XINYI_COACH_REJECT_PASS body_crc backend token frame raw_crc truncated status6_fatal reaped");
    t=start(argv[1],argv[2],"cancel",&idle);ready(t);pid=xy_coach_worker_pid(t);f=frame(30);
    assert(xy_coach_start(t,30,&f));consume(t,&f);
    /* Empty fixed .part is a synthetic-only acquisition marker. */
    wait_file(pid,"result.txt.part");
    assert(!xy_coach_cancel(t,29) && xy_coach_cancel(t,30));e=terminal(t,&result);
    assert(e.type==XY_COACH_CANCELLED && e.drained && e.resident_ready && !e.worker_reaped && e.consumed);
    assert(xy_coach_worker_pid(t)==pid && xy_coach_close(t));reaped(pid);
    puts("XINYI_COACH_CANCEL_PASS same_identity9_idle_busy0 no_early_ack");
    t=start(argv[1],argv[2],"stall",&idle);ready(t);pid=xy_coach_worker_pid(t);f=frame(31);
    assert(xy_coach_start(t,31,&f));consume(t,&f);wait_file(pid,"result.txt.part");
    assert(xy_coach_cancel(t,31));e=terminal(t,&result);
    assert(e.type==XY_COACH_CANCELLED && e.drained && e.worker_reaped && !e.resident_ready);reaped(pid);assert(xy_coach_close(t));
    puts("XINYI_COACH_KILL_PASS term_ignored kill_waitpid_busy0");
    t=start(argv[1],argv[2],"normal",&idle);ready(t);pid=xy_coach_worker_pid(t);f=frame(33);
    assert(xy_coach_start(t,33,&f));consume(t,&f);wait_file(pid,"result.txt");
    assert(xy_coach_cancel(t,33));e=terminal(t,&result);
    assert(e.type==XY_COACH_CANCELLED && e.drained && e.resident_ready && !e.worker_reaped);
    assert(xy_coach_close(t));reaped(pid);
    puts("XINYI_COACH_CANCEL_RACE_PASS normal_result_published_release9_idle_required");
    t=start(argv[1],argv[2],"normal",&idle);ready(t);pid=xy_coach_worker_pid(t);f=frame(32);
    assert(xy_coach_start(t,32,&f));assert(xy_coach_cancel(t,32));e=terminal(t,&result);
    if(e.type!=XY_COACH_CANCELLED || !e.drained || !e.consumed)
        fprintf(stderr,"synthetic writer-cancel type=%d consumed=%d drained=%d reaped=%d status=%u\n",e.type,e.consumed,e.drained,e.worker_reaped,e.remote_status);
    assert(e.type==XY_COACH_CANCELLED && e.drained && e.consumed);
    assert(xy_coach_consumed(t,32));assert(!munmap((void *)f.rgb565,f.bytes));assert(xy_coach_close(t));reaped(pid);
    puts("XINYI_COACH_WRITER_CANCEL_PASS joins_before_consumed_or_ack");
    t=start(argv[1],argv[2],"body-crc",&idle);ready(t);pid=xy_coach_worker_pid(t);f=frame(40);
    assert(xy_coach_start(t,40,&f));consume(t,&f);idle=0;e=terminal(t,&result);
    if(e.type!=XY_COACH_UNDRAINED || e.drained || !e.worker_reaped)
        fprintf(stderr,"synthetic unknown-busy type=%d drained=%d reaped=%d idle=%d\n",e.type,e.drained,e.worker_reaped,idle);
    assert(e.type==XY_COACH_UNDRAINED && !e.drained && e.worker_reaped);reaped(pid);
    assert(!xy_coach_close(t) && !xy_coach_ready(t));idle=1;assert(xy_coach_close(t));
    puts("XINYI_COACH_UNDRAINED_PASS busy_unknown_quarantine no_cancel_ack explicit_recovery");
    t=start(argv[1],argv[2],"startup-exit",&idle);pid=xy_coach_worker_pid(t);e=terminal(t,&result);
    assert(e.type==XY_COACH_FATAL && e.drained && e.worker_reaped);assert(xy_coach_close(t));reaped(pid);
    puts("XINYI_COACH_HOST_PASS synthetic_only no_models no_board no_uart_payload");return 0;
}
