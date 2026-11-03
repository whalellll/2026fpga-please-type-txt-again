#define _POSIX_C_SOURCE 200809L
#include "process.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

/* Explicit synthetic protocol/pipe fixture; never a benchmark score. */
int main(int argc,char **argv)
{
    if(argc>1){
        assert(!strcmp(argv[1],"--target-ms"));
        puts("SYNTHETIC OUTPUT FIXTURE ONLY\nCompiler version : fixture\nControl:\033[0m");
        for(unsigned i=0;i<450;i++)printf("fixture line %03u: bounded output, not executed iterations or measured time\n",i);
        puts("XY_CM_RESULT kind=host valid=1 perf_iterations=300 perf_ticks=30000000000 validation_iterations=110 validation_ticks=11000000000 timer_hz=1000000000 cpu_hz=0 identity=0000000000000000000000000000000000000000000000000000000000000000");
        return 0;
    }
    xy_cm_process p;xy_cm_process_init(&p);
    assert(xy_cm_process_start(&p,argv[0],17,45000,0,"0000000000000000000000000000000000000000000000000000000000000000"));
    for(unsigned i=0;i<500 && p.pid>0;i++){
        (void)xy_cm_process_poll(&p);const struct timespec nap={0,1000000};nanosleep(&nap,0);
    }
    assert(p.pid==-1 && p.status==XY_CM_DONE && p.valid && !p.is_board);
    assert(p.output_used==XY_CM_LOG_BYTES-1 && p.output_truncated && !p.line_failed);
    assert(strstr(p.output,"Compiler version : fixture") && strstr(p.output,"Control:?[0m"));
    xy_app a={0};a.job=XY_COREMARK;a.token=17;
    assert(xy_cm_process_apply(&p,&a) && a.job==XY_IDLE && !a.coremark_measured);
    assert(a.coremark_log_truncated && a.coremark_log_used==p.output_used);
    assert(!strcmp(a.coremark_log,p.output));
    puts("COREMARK_OUTPUT_PIPE_PASS_SYNTHETIC_ONLY bounded_truncation control_sanitizing parse_tail waitpid host_never_scores");
    return 0;
}
