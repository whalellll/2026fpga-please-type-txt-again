#define _POSIX_C_SOURCE 200809L
#include "graph_profile.h"
#ifdef XQ_GRAPH_PROFILE
#include <string.h>
#include <stdio.h>
#include <time.h>
static xqg_profile counters;
static uint64_t ticks(clockid_t id)
{
    struct timespec t;
    if(clock_gettime(id,&t)){counters.clock_failures++;return 0;}
    return (uint64_t)t.tv_sec*UINT64_C(1000000000)+(unsigned)t.tv_nsec;
}
void xqg_profile_reset(void) { memset(&counters,0,sizeof(counters)); }
void xqg_profile_read(xqg_profile *out) { if(out)*out=counters; }
xqg_mark xqg_begin(void)
{
    xqg_mark m={ticks(CLOCK_MONOTONIC),ticks(CLOCK_PROCESS_CPUTIME_ID)};return m;
}
void xqg_end(enum xqg_phase phase,xqg_mark m,uint64_t values)
{
    xqg_mark end=xqg_begin();
    if(phase>=XQG_PHASES || end.wall<m.wall || end.cpu<m.cpu){counters.clock_failures++;return;}
    counters.wall[phase]+=end.wall-m.wall;counters.cpu[phase]+=end.cpu-m.cpu;
    counters.calls[phase]++;counters.values[phase]+=values;
}
void xqg_profile_report(unsigned model,int okay,xqg_mark start)
{
    static const char *names[XQG_PHASES]={
        "quant","dequant","int_requant","sigmoid","maxpool","nearest","bilinear",
        "concat","add","avgpool","identity","relu","weight_layout","input_layout",
        "output_layout_requant","staging_zero","submit","integer_gap"};
    xqg_mark end=xqg_begin();
    /* One optional, aggregate record per graph. No frame/request/tensor data.
     * On a real device submit includes driver copies, queueing and polling. */
    printf("PN05_GRAPH_PROFILE kind=%u okay=%d wall_ns=%llu cpu_ns=%llu clock_errors=%llu",
        model,okay,(unsigned long long)(end.wall-start.wall),
        (unsigned long long)(end.cpu-start.cpu),(unsigned long long)counters.clock_failures);
    for(unsigned i=0;i<XQG_PHASES;i++)printf(" %s_wall_ns=%llu %s_cpu_ns=%llu",names[i],
        (unsigned long long)counters.wall[i],names[i],(unsigned long long)counters.cpu[i]);
    putchar('\n');
}
#endif
