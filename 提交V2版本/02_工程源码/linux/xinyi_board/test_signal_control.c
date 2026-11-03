#define _POSIX_C_SOURCE 200809L
#include "signal_test_control.h"
#include <assert.h>
#include <signal.h>
#include <stdio.h>
static unsigned starts,spaces,cancels;
static unsigned mask_calls;
int __real_sigprocmask(int,const sigset_t *,sigset_t *);
int __wrap_sigprocmask(int how,const sigset_t *set,sigset_t *old)
{mask_calls++;return __real_sigprocmask(how,set,old);}
int xy_runtime_action(xy_runtime *r,xy_pointer_event a)
{assert(a==XY_ACTION_START);starts++;r->app.page=XY_GAME;return 1;}
int xy_runtime_space(xy_runtime *r,uint64_t t)
{assert(!t);spaces++;r->app.job=XY_CAPTURE;return 1;}
void xy_runtime_cancel(xy_runtime *r){cancels++;r->app.cancelling=1;}
int main(void)
{
    xy_runtime r={0};assert(xy_signal_test_attach());
    xy_signal_test_poll(&r);assert(!mask_calls);
    raise(SIGUSR2);xy_signal_test_poll(&r);assert(!spaces);
    raise(SIGUSR1);raise(SIGUSR2);xy_signal_test_poll(&r);assert(starts==1 && !spaces);
    raise(SIGUSR2);xy_signal_test_poll(&r);assert(spaces==1);
    raise(SIGUSR2);xy_signal_test_poll(&r);assert(spaces==1); /* busy is not queued */
    r.app.job=XY_IDLE;mask_calls=0;xy_signal_test_poll(&r);assert(spaces==1 && !mask_calls);
    r.app.mode=XY_VOICE;raise(SIGUSR2);xy_signal_test_poll(&r);assert(spaces==1);
    r.app.mode=XY_COACH;raise(SIGUSR2);raise(SIGHUP);xy_signal_test_poll(&r);assert(cancels==1 && spaces==1);
    raise(SIGUSR2);xy_signal_test_poll(&r);assert(spaces==1);
    r.app.cancelling=0;r.fatal=1;raise(SIGUSR2);xy_signal_test_poll(&r);assert(spaces==1);
    puts("SERIAL_TEST_START_SPACE_BUSY_VOICE_CANCEL_PRIORITY_NO_QUEUE_PASS_NOT_BOARD");return 0;
}
