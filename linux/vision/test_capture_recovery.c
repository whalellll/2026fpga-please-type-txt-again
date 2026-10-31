#include "xq_camera_retry.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {
    xqc_camera io;uint32_t camera[32],fb[8],sys[8];uint64_t time,cancel_at;
    unsigned failures,active,failed,stuck,no_stop,changed,attempts;
} fixture;
static uint64_t now(void *p){return ((fixture *)p)->time;}
static int poll(void *p,int waiting)
{
    fixture *f=p;uint32_t control=f->camera[CAMERA_REG_CONTROL/4];(void)waiting;++f->time;
    if(control&CAMERA_CONTROL_STOP_REQUEST) {
        if(!f->no_stop){f->camera[CAMERA_REG_STATUS/4]=CAMERA_STATUS_IDLE;f->active=f->failed=0;}
    } else if(control&CAMERA_CONTROL_ENABLE) {
        if(!f->active){f->active=1;if(f->failures){--f->failures;f->failed=1;}}
        f->camera[CAMERA_REG_STATUS/4]=f->failed?CAMERA_STATUS_ENABLED|CAMERA_STATUS_SCCB_NACK:15u;
        f->fb[3]=2;
        if(!f->failed) {
            if(!(control&CAMERA_CONTROL_SNAPSHOT_HOLD) && !f->stuck)++f->camera[CAMERA_REG_FRAME_COUNT/4];
            if(control&CAMERA_CONTROL_SNAPSHOT_HOLD) {
                f->camera[CAMERA_REG_STATUS/4]|=CAMERA_STATUS_SNAPSHOT_READY|CAMERA_STATUS_SNAPSHOT_BUFFER1;
                f->camera[CAMERA_REG_SNAPSHOT_FRAME_COUNT/4]=f->camera[CAMERA_REG_FRAME_COUNT/4]+(f->changed?(uint32_t)f->time:0u);
                f->io.banks[1][0]=f->camera[CAMERA_REG_FRAME_COUNT/4];
            }
        }
    }
    return f->cancel_at && f->time>=f->cancel_at;
}
static void setup(fixture *f)
{
    memset(f,0,sizeof(*f));f->camera[0]=CAMERA_ID_VALUE;f->camera[1]=CAMERA_VERSION_VALUE;
    f->camera[CAMERA_REG_FRAME_COUNT/4]=42;f->sys[1]=1;f->sys[3]=8;
    f->io.camera=f->camera;f->io.fb=f->fb;f->io.sys=f->sys;f->io.now_ms=now;f->io.poll=poll;f->io.context=f;
    f->io.banks[0]=calloc(XQV_FRAME_BYTES,1);f->io.banks[1]=calloc(XQV_FRAME_BYTES,1);f->io.snapshot=calloc(XQV_FRAME_BYTES,1);
    assert(f->io.banks[0] && f->io.banks[1] && f->io.snapshot);
}
static void destroy(fixture *f){free((void *)f->io.banks[0]);free((void *)f->io.banks[1]);free((void *)f->io.snapshot);}
static void observe(void *p,unsigned attempt,int result,uint32_t status)
{fixture *f=p;(void)result;(void)status;assert(attempt==++f->attempts);}
int main(void)
{
    fixture f;xqv_frame frame;uint32_t *ram=malloc(XQV_FRAME_BYTES);assert(ram);
    setup(&f);f.failures=12;
    assert(xqc_capture_until_ready(&f.io,ram,XQV_FRAME_BYTES,&frame,observe,&f)==XQC_OK);
    assert(f.attempts==13 && frame.rgb565==ram && frame.bytes==XQV_FRAME_BYTES && frame.frame_id>42);
    assert(ram[0]==frame.frame_id && !memcmp(ram,(const void *)f.io.snapshot,XQV_FRAME_BYTES));destroy(&f);
    setup(&f);f.stuck=1;f.cancel_at=4500;
    assert(xqc_capture_until_ready(&f.io,ram,XQV_FRAME_BYTES,&frame,observe,&f)==XQC_CANCELLED);
    assert(!frame.rgb565 && !frame.bytes && f.attempts>=2);destroy(&f);
    setup(&f);f.changed=1;f.cancel_at=1200;
    assert(xqc_capture_until_ready(&f.io,ram,XQV_FRAME_BYTES,&frame,observe,&f)==XQC_CANCELLED);
    assert(!frame.rgb565);destroy(&f);
    setup(&f);f.failures=1;f.no_stop=1;
    assert(xqc_capture_until_ready(&f.io,ram,XQV_FRAME_BYTES,&frame,observe,&f)==XQC_STOP);
    assert(f.io.poisoned && !frame.rgb565 && f.attempts==1);destroy(&f);
    setup(&f);f.camera[0]^=1;
    assert(xqc_capture_until_ready(&f.io,ram,XQV_FRAME_BYTES,&frame,observe,&f)==XQC_ID && f.attempts==1);destroy(&f);
    free(ram);puts("XQ_CAPTURE_RECOVERY_TEST_PASS failures12_then_fresh_success stale_reject changed_reject cancel unsafe_drain_fatal identity_fatal");return 0;
}
