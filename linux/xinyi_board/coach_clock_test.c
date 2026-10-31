/* Host test-link wrapper: force every monotonic sample into a newer
 * millisecond. The old poll/stop subtraction then fails deterministically. */
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <time.h>
int __real_clock_gettime(clockid_t,struct timespec *);
int __wrap_clock_gettime(clockid_t clock,struct timespec *out)
{
    int rc=__real_clock_gettime(clock,out);
    static _Thread_local uint64_t previous;
    if(rc || clock!=CLOCK_MONOTONIC)return rc;
    uint64_t current=(uint64_t)out->tv_sec*1000u+(uint64_t)out->tv_nsec/1000000u;
    if(current<=previous)current=previous+1;
    previous=current;out->tv_sec=(time_t)(current/1000u);out->tv_nsec=(long)(current%1000u)*1000000L;
    return 0;
}
