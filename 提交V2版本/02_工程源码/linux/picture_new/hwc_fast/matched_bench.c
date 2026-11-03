#define _POSIX_C_SOURCE 200809L
/* Same immutable benchmark and numeric work, with the product cancellation
 * callback installed before RUN. A signal requests normal driver abort/drain;
 * process exit alone is never a five-engine-idle acknowledgement. */
#include "xq_mac.h"
#include <signal.h>
static volatile sig_atomic_t bench_stop;
static int bench_cancelled(void *unused){(void)unused;return bench_stop!=0;}
static void bench_signal(int sig){(void)sig;bench_stop=1;}
static int bench_open(xqm_linux *);
#define xqm_linux_open bench_open
#define main immutable_bench_main
#include "integer_bench.c"
#undef main
#undef xqm_linux_open
static int bench_open(xqm_linux *device)
{
    int okay=xqm_linux_open(device);
    if(okay)device->io.cancelled=bench_cancelled;
    return okay;
}
#ifndef XQ_MATCHED_BENCH_ENTRY
#define XQ_MATCHED_BENCH_ENTRY main
#endif
int XQ_MATCHED_BENCH_ENTRY(int argc,char **argv)
{
    struct sigaction action={0};action.sa_handler=bench_signal;
    if(sigemptyset(&action.sa_mask) || sigaction(SIGTERM,&action,NULL) || sigaction(SIGINT,&action,NULL))return 2;
    bench_stop=0;
    return immutable_bench_main(argc,argv);
}
