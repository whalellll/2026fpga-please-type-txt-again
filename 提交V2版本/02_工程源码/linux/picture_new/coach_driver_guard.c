#include "coach_driver_guard.h"
#include "pango_mac_uapi.h"
#include <errno.h>
#include <stdarg.h>

static int in_flight,unproven_drain;
int __real_ioctl(int,unsigned long,...);

/* The current kernel aborts on timeout but may return while accepted AXI
 * traffic drains. ioctl return alone is therefore not an idle proof. This
 * build-specific wrapper never changes numerical execution or error handling. */
int __wrap_ioctl(int fd,unsigned long request,...)
{
    va_list args;void *argument;
    va_start(args,request);argument=va_arg(args,void *);va_end(args);
    int vision=request==PANGO_MAC_IOC_RUN_VISION32;
    if(vision){
        in_flight=1;
        /* A spatial tile can reuse its job structure. An ioctl rejected
         * before copyout must not inherit the preceding tile's DONE proof. */
        if(argument)((struct pango_vision32_job *)argument)->status=0;
    }
    int result=__real_ioctl(fd,request,argument),saved_errno=errno;
    if(vision){
        const struct pango_vision32_job *job=argument;
        if(!job || (job->status&3u)!=2u)unproven_drain=1;
        in_flight=0;
    }
    errno=saved_errno;return result;
}
int xqcoach_driver_quiescent(void)
{return !in_flight && !unproven_drain;}
