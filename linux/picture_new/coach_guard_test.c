#include "coach_driver_guard.h"
#include "pango_mac_uapi.h"
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

int __wrap_ioctl(int,unsigned long,...);
static unsigned returned_status;static int returned_result,leave_status;
int __real_ioctl(int fd,unsigned long request,...)
{
    (void)fd;va_list args;va_start(args,request);
    struct pango_vision32_job *job=va_arg(args,void *);va_end(args);
    assert(!xqcoach_driver_quiescent());
    assert(request==PANGO_MAC_IOC_RUN_VISION32);
    if(!leave_status)job->status=returned_status;
    errno=returned_result?ETIMEDOUT:EBUSY;return returned_result;
}
int main(int argc,char **argv)
{
    struct pango_vision32_job job={0};assert(xqcoach_driver_quiescent());
    returned_status=2;
    assert(!__wrap_ioctl(7,PANGO_MAC_IOC_RUN_VISION32,&job));
    assert(errno==EBUSY && xqcoach_driver_quiescent());
    if(argc==2 && !strcmp(argv[1],"stale")){
        returned_result=-1;leave_status=1;
        assert(__wrap_ioctl(7,PANGO_MAC_IOC_RUN_VISION32,&job)==-1);
        assert(!xqcoach_driver_quiescent());
        puts("XQCOACH_GUARD_PREVIOUS_DONE_CANNOT_PROVE_FAILED_NEW_JOB_DRAIN_PASS");
        return 0;
    }
    returned_result=-1;
    assert(__wrap_ioctl(7,PANGO_MAC_IOC_RUN_VISION32,&job)==-1);
    assert(errno==ETIMEDOUT && xqcoach_driver_quiescent()); /* Error, but DONE/non-BUSY proves drain. */
    returned_status=argc==2 && !strcmp(argv[1],"busy")?1u:0u;
    assert(__wrap_ioctl(7,PANGO_MAC_IOC_RUN_VISION32,&job)==-1);
    assert(errno==ETIMEDOUT && !xqcoach_driver_quiescent());
    returned_status=2;returned_result=0;
    assert(!__wrap_ioctl(7,PANGO_MAC_IOC_RUN_VISION32,&job));
    assert(!xqcoach_driver_quiescent()); /* No silent reset of unresolved DMA. */
    puts("XQCOACH_GUARD_DONE_ERRORS_BUSY_UNKNOWN_AND_STICKY_REJECT_PASS");return 0;
}
