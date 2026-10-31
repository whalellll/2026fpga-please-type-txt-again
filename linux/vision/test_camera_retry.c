#include "xq_camera_retry.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static uint32_t registers[32];
static uint64_t ticks;
static unsigned starts,stops,failures,cancel_at,unsafe_stop,observed;
static int error_kind;
static uint64_t now(void *p){(void)p;return ticks;}
static int poll(void *p,int waiting){(void)p;ticks+=waiting;return cancel_at && ticks>=cancel_at;}
int xqc_start(xqc_camera *c,unsigned timeout)
{
    (void)c;++starts;ticks+=timeout<100?timeout:100;
    registers[CAMERA_REG_STATUS/4]=starts<=failures?CAMERA_STATUS_ENABLED|CAMERA_STATUS_SCCB_NACK:15;
    if(error_kind) {
        registers[CAMERA_REG_STATUS/4]|=CAMERA_STATUS_DDR_ERROR;
        return error_kind;
    }
    return starts<=failures?XQC_START:XQC_OK;
}
int xqc_stop(xqc_camera *c){(void)c;++stops;return unsafe_stop?XQC_STOP:XQC_OK;}
static void observe(void *p,unsigned attempt,int result,uint32_t status)
{(void)p;(void)result;(void)status;assert(attempt==++observed);}
static xqc_camera setup(void)
{
    xqc_camera c;memset(&c,0,sizeof(c));c.camera=registers;c.now_ms=now;c.poll=poll;
    ticks=starts=stops=failures=cancel_at=unsafe_stop=observed=0;error_kind=0;return c;
}
int main(void)
{
    xqc_camera cap=setup();failures=2;
    assert(xqc_start_retry(&cap,18000,3,observe,NULL)==XQC_OK && starts==3 && stops==2 && observed==3);
    cap=setup();failures=100;
    assert(xqc_start_retry(&cap,18000,3,observe,NULL)==XQC_START && starts==3 && stops==3 && observed==3);
    xqc_camera c=setup();failures=3;
    assert(xqc_start_retry(&c,20000,8,observe,NULL)==XQC_OK);
    assert(starts==4 && stops==3 && observed==4);
    c=setup();failures=100;
    assert(xqc_start_retry(&c,20000,8,NULL,NULL)==XQC_START && starts==8 && stops==8);
    c=setup();failures=100;
    assert(xqc_start_retry(&c,400,8,NULL,NULL)==XQC_START && starts==2 && ticks<=400);
    c=setup();failures=100;error_kind=XQC_START;
    assert(xqc_start_retry(&c,20000,8,NULL,NULL)==XQC_START && starts==1 && stops==1);
    c=setup();failures=100;unsafe_stop=1;
    assert(xqc_start_retry(&c,20000,8,NULL,NULL)==XQC_STOP && starts==1);
    c=setup();failures=100;cancel_at=110;
    assert(xqc_start_retry(&c,20000,8,NULL,NULL)==XQC_CANCELLED && starts==1);
    c=setup();error_kind=XQC_ID;
    assert(xqc_start_retry(&c,20000,8,NULL,NULL)==XQC_ID && !stops);
    assert(xqc_start_retry(&c,0,8,NULL,NULL)==XQC_ARGUMENT);
    puts("XQ_CAMERA_RETRY_TEST_PASS nack_only deadline attempts safe_drain cancel");return 0;
}
