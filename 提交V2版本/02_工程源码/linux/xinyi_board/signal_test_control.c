#define _POSIX_C_SOURCE 200809L
#include "signal_test_control.h"
#include <signal.h>
#include <stdio.h>
static volatile sig_atomic_t pending_start,pending_space,pending_cancel;
static void receive(int number)
{
    if(number==SIGUSR1)pending_start=1;
    else if(number==SIGUSR2)pending_space=1;
    else if(number==SIGHUP)pending_cancel=1;
}
int xy_signal_test_attach(void)
{
    struct sigaction a={0};a.sa_handler=receive;sigemptyset(&a.sa_mask);
    return !sigaction(SIGUSR1,&a,NULL) && !sigaction(SIGUSR2,&a,NULL) && !sigaction(SIGHUP,&a,NULL);
}
void xy_signal_test_poll(xy_runtime *r)
{
    /* The idle GUI runs at 200 Hz. Do not introduce masking syscalls when
     * no command arrived; a signal racing this check waits for the next poll. */
    if(!pending_start && !pending_space && !pending_cancel)return;
    sigset_t set,old;sigemptyset(&set);sigaddset(&set,SIGUSR1);sigaddset(&set,SIGUSR2);sigaddset(&set,SIGHUP);
    if(sigprocmask(SIG_BLOCK,&set,&old))return;
    int start=pending_start,space=pending_space,cancel=pending_cancel;
    pending_start=pending_space=pending_cancel=0;
    if(sigprocmask(SIG_SETMASK,&old,NULL))return;
    if(!r)return;
    if(cancel){xy_runtime_cancel(r);puts("XINYI_SERIAL_TEST_ESC dispatched=1");return;}
    if(start){
        int okay=!r->fatal && !r->navigation_requested && !r->app.cancelling &&
            r->app.page==XY_HOME && r->app.job==XY_IDLE && xy_runtime_action(r,XY_ACTION_START);
        printf("XINYI_SERIAL_TEST_START accepted=%d\n",okay);
        return; /* A coalesced Space is discarded, never queued after navigation. */
    }
    if(space){
        int okay=!r->fatal && !r->navigation_requested && !r->app.cancelling &&
            r->app.page==XY_GAME && r->app.mode==XY_COACH && r->app.job==XY_IDLE &&
            xy_runtime_space(r,0);
        printf("XINYI_SERIAL_TEST_SPACE accepted=%d physical_key=0\n",okay);
    }
}
