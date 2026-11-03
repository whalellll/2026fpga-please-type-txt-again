#define _POSIX_C_SOURCE 200809L
#include "process.h"
#include <assert.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static const char identity[]="0000000000000000000000000000000000000000000000000000000000000000";
typedef struct {xy_cm_process process;const char *exe;} context;
static int mic(void *p,int enabled) {(void)p;return !enabled;}
static int start(void *p,uint32_t token,unsigned ms)
{
    context *c=p;
    return xy_cm_process_start(&c->process,c->exe,token,ms,0,identity);
}
static void cancel(void *p,xy_job job,uint32_t token)
{
    context *c=p;
    assert(job==XY_COREMARK && c->process.token==token);
    assert(xy_cm_process_cancel(&c->process));
}
static void pause_ms(unsigned ms)
{struct timespec t={(time_t)(ms/1000),(long)(ms%1000)*1000000};(void)nanosleep(&t,NULL);}
int main(int argc,char **argv)
{
    xy_app app;
    context c;
    xy_backend backend={0};
    pid_t child;
    unsigned loops;
    double preset;
    assert(argc==2 || (argc==3 && !strcmp(argv[2],"--cancel-only")));
    c.exe=argv[1];xy_cm_process_init(&c.process);
    backend.context=&c;backend.microphone=mic;backend.coremark=start;backend.cancel=cancel;
    xy_app_init(&app,&backend);preset=app.coremark_per_mhz;
    assert(xy_coremark_begin(&app,XY_COREMARK_BOARD));
    child=c.process.pid;pause_ms(180);
    (void)xy_cm_process_poll(&c.process);
    assert(xy_cancel(&app));
    for(loops=0;loops<200 && c.process.pid>0;++loops) {
        pause_ms(10);(void)xy_cm_process_poll(&c.process);
    }
    assert(c.process.pid==-1 && c.process.status==XY_CM_CANCELLED);
    assert(xy_cm_process_apply(&c.process,&app) && app.job==XY_IDLE && !app.cancelling);
    errno=0;assert(waitpid(child,NULL,WNOHANG)==-1 && errno==ECHILD);
    errno=0;assert(kill(child,0)==-1 && errno==ESRCH);
    assert(!app.coremark_measured && app.coremark_per_mhz==preset);
    puts("XINYI_COREMARK_CANCEL_PASS real_algorithm_child TERM_wait no_orphan no_score");fflush(stdout);
    if(argc==3) {
        /* A completion reaped just before the UI processes Esc must still
         * acknowledge cancellation, and must never publish a late score. */
        app.job=XY_COREMARK;app.cancelling=1;c.process.status=XY_CM_DONE;
        c.process.token=app.token;
        assert(xy_cm_process_apply(&c.process,&app) && app.job==XY_IDLE && !app.cancelling);
        assert(!app.coremark_measured && app.coremark_per_mhz==preset);
        puts("XINYI_COREMARK_CANCEL_RACE_PASS late_done_acknowledged no_score");
        return 0;
    }
    assert(xy_coremark_begin(&app,XY_COREMARK_BOARD));
    for(loops=0;loops<3000 && c.process.pid>0;++loops) {
        pause_ms(50);(void)xy_cm_process_poll(&c.process);
        (void)xy_cm_process_apply(&c.process,&app);
    }
    printf("HOST_ALGORITHM scope=host status=%u valid=%d board=%d phase=%s iterations=%llu perf_ticks=%llu validation_ticks=%llu\n",
        c.process.status,c.process.valid,c.process.is_board,c.process.phase,
        (unsigned long long)c.process.perf_iterations,(unsigned long long)c.process.perf_ticks,
        (unsigned long long)c.process.validation_ticks);
    assert(c.process.pid==-1 && c.process.status==XY_CM_DONE && c.process.valid);
    assert(c.process.output_used && strstr(c.process.output,"Compiler version") &&
        strstr(c.process.output,"Correct operation validated.") &&
        strstr(app.coremark_log,"XY_CM_RESULT") && !app.coremark_log_truncated);
    assert(!c.process.is_board && !app.coremark_measured && app.coremark_per_mhz==preset);
    assert(app.job==XY_IDLE);
    xy_cm_process_dispose(&c.process);
    puts("XINYI_COREMARK_PROCESS_PASS real_iterations performance_validation_CRC elapsed_ge_10s nonblocking_progress host_never_scores");
    return 0;
}
