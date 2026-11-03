/* TEST ONLY: fake transport/graph/driver; never linked into the product.
 * No neural calculation or FPGA claim. Each mock ioctl blocks until cancel,
 * then waits 120ms to represent drain before returning DONE/non-BUSY. */
#define _POSIX_C_SOURCE 200809L
#include "xq_native_graph.h"
#include "coach_driver_guard.h"
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/ioctl.h>

static const xqm_transport *active;
int __wrap_ioctl(int,unsigned long,...);
static void pause_ms(long ms){const struct timespec t={ms/1000,(ms%1000)*1000000};nanosleep(&t,NULL);}
int __wrap_xqm_linux_open(xqm_linux *context)
{
    memset(context,0,sizeof(*context));context->fd=123;
    context->io.shadow=calloc(1,0x100000);context->io.bytes=0x100000;context->io.context=context;
    context->features=PANGO_MAC_FEATURE_PRIVATE_SHADOW|PANGO_MAC_FEATURE_SERIALIZED|PANGO_MAC_FEATURE_VISION32;
#if XQ_HWC_DETECTOR
    context->features|=PANGO_MAC_FEATURE_VISION32_EXACT;
#endif
    return context->io.shadow!=NULL;
}
void __wrap_xqm_linux_close(xqm_linux *context)
{free(context->io.shadow);memset(context,0,sizeof(*context));context->fd=-1;}
#ifdef __GLIBC__
int ioctl(int fd,unsigned long request,...)
#else
int ioctl(int fd,int request,...)
#endif
{
    (void)fd;va_list args;va_start(args,request);
    struct pango_vision32_job *job=va_arg(args,void *);va_end(args);
    assert((uint32_t)request==(uint32_t)PANGO_MAC_IOC_RUN_VISION32 && active && !xqcoach_driver_quiescent());
    puts("XQ_COACH_TEST_IOCTL_ENTER hostmock=1");fflush(stdout);
    for(unsigned i=0;i<400 && !active->cancelled(active->context);i++)pause_ms(20);
    if(!active->cancelled(active->context)){errno=ETIMEDOUT;job->status=1;return -1;}
    pause_ms(120); /* No ACK is allowed during this drain interval. */
    if(getenv("XQCOACH_TEST_UNPROVEN")){
        job->status=1;errno=ETIMEDOUT;
        puts("XQ_COACH_TEST_IOCTL_RETURN_UNPROVEN hostmock=1");fflush(stdout);return -1;
    }
    job->status=2;job->error=0;job->cycles=17;
    puts("XQ_COACH_TEST_IOCTL_RETURN_DONE hostmock=1");fflush(stdout);return 0;
}
int __wrap_xqn_run(xqn_model *model,const xqm_transport *transport,unsigned batch,
                   const float *input,int cpu,xqm_stats *stats)
{
    (void)model;(void)batch;(void)input;assert(!cpu && transport && transport->cancelled);
    active=transport;memset(stats,0,sizeof(*stats));struct pango_vision32_job job={0};
    int result=__wrap_ioctl(123,PANGO_MAC_IOC_RUN_VISION32,&job);active=NULL;
    if(!result){stats->jobs=1;stats->cycles=job.cycles;}
    return 0; /* Cancellation ends the graph; original worker frees its buffers. */
}
