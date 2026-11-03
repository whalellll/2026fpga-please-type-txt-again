#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "xq_camera.h"

typedef struct {
    xqc_camera io;
    uint32_t camera[32], fb[32], sys[8];
    uint64_t time;
    int no_hold, no_stop, change_frame, cancel;
    int first_frame_race, nonhold_polls, hold_seen, invalid_hold;
    int no_background_ack, cancel_copy;
    unsigned wait_polls, copy_polls;
    uint32_t hold_first_frame_count;
} fake_camera;
static uint64_t now(void *p) { return ((fake_camera *)p)->time; }
static int poll(void *p, int waiting)
{
    fake_camera *f = p;
    uint32_t control = f->camera[CAMERA_REG_CONTROL / 4];
    if (waiting) f->wait_polls++; else f->copy_polls++;
    f->time++;
    if (control & CAMERA_CONTROL_STOP_REQUEST) {
        if (!f->no_stop) f->camera[CAMERA_REG_STATUS / 4] = CAMERA_STATUS_IDLE;
    } else if (control & CAMERA_CONTROL_ENABLE) {
        f->camera[CAMERA_REG_STATUS / 4] = CAMERA_STATUS_ENABLED |
            CAMERA_STATUS_CMOS1_INIT_DONE | CAMERA_STATUS_CMOS2_INIT_DONE |
            CAMERA_STATUS_FRAME_VALID;
        f->fb[3] = f->io.background ? 0u : 2u;
        if (!(control & CAMERA_CONTROL_SNAPSHOT_HOLD)) {
            f->hold_seen = f->invalid_hold = 0;
            ++f->nonhold_polls;
            f->camera[CAMERA_REG_FRAME_COUNT / 4] =
                f->first_frame_race ? (f->nonhold_polls < 6 ? 1u :
                                      f->nonhold_polls < 10 ? 2u : 6u) : 42u;
        }
        if (f->first_frame_race) {
            if (f->nonhold_polls < 6)
                f->camera[CAMERA_REG_STATUS / 4] |= CAMERA_STATUS_COMPLETED_BUFFER1;
            if (f->nonhold_polls >= 4) f->fb[3] = 6;
        }
        if ((control & CAMERA_CONTROL_SNAPSHOT_HOLD) && !f->hold_seen) {
            /* Real buffer controller latches invalid permanently if the
             * first camera frame has not replaced the previous GUI bank. */
            f->hold_seen = 1;
            f->hold_first_frame_count = f->camera[CAMERA_REG_FRAME_COUNT / 4];
            f->invalid_hold = !f->io.background && f->first_frame_race && f->nonhold_polls < 6;
        }
        if ((control & CAMERA_CONTROL_SNAPSHOT_HOLD) && !f->no_hold) {
            if (!f->invalid_hold)
                f->camera[CAMERA_REG_STATUS / 4] |= CAMERA_STATUS_SNAPSHOT_READY |
                                                   CAMERA_STATUS_SNAPSHOT_BUFFER1;
            if (f->change_frame) ++f->camera[7];
        }
    }
    if((control&CAMERA_CONTROL_BACKGROUND) && !f->no_background_ack)
        f->camera[CAMERA_REG_STATUS/4]|=CAMERA_STATUS_BACKGROUND_ACTIVE;
    return f->cancel || (f->cancel_copy && !waiting);
}
static void setup(fake_camera *f)
{
    unsigned i;
    memset(f, 0, sizeof(*f));
    f->camera[0] = CAMERA_ID_VALUE;
    f->camera[1] = CAMERA_VERSION_VALUE;
    f->sys[1] = 1;
    f->sys[3] = 8;
    f->camera[7] = 42;
    f->io.camera = f->camera;
    f->io.fb = f->fb;
    f->io.sys = f->sys;
    f->io.now_ms = now;
    f->io.poll = poll;
    f->io.context = f;
    for (i = 0; i < 2; ++i) {
        f->io.banks[i] = calloc(XQV_FRAME_BYTES, 1);
        assert(f->io.banks[i]);
    }
    f->io.snapshot = calloc(XQV_FRAME_BYTES, 1);
    assert(f->io.snapshot);
    for (i = 0; i < XQV_FRAME_BYTES / 4; ++i)
        f->io.banks[1][i] = i ^ 0x12345678u;
}
static void teardown(fake_camera *f)
{
    free((void *)f->io.banks[0]);
    free((void *)f->io.banks[1]);
    free((void *)f->io.snapshot);
}
int main(void)
{
    fake_camera f;
    xqv_frame frame;
    uint32_t *ram = malloc(XQV_FRAME_BYTES);
    unsigned i;
    assert(ram);
    setup(&f);
    for (i = 0; i < 20; ++i) {
        unsigned waits = f.wait_polls, copies = f.copy_polls;
        assert(xqc_capture(&f.io, ram, XQV_FRAME_BYTES, &frame) == XQC_OK);
        assert(frame.frame_id == 42 && frame.rgb565 == ram);
        assert(!memcmp(ram, (const void *)f.io.banks[1], XQV_FRAME_BYTES));
        assert(f.camera[2] == 0 && !f.io.poisoned);
        assert(f.wait_polls - waits < 8); /* hardware waits, not pixel copies */
        assert(f.copy_polls - copies == 113); /* one pass fills both copies */
        assert(!memcmp(ram,(const void *)f.io.snapshot,XQV_FRAME_BYTES));
    }
    assert(xqc_capture(&f.io, ram, 4, &frame) == XQC_ARGUMENT);
    f.no_hold = 1;
    assert(xqc_capture(&f.io, ram, XQV_FRAME_BYTES, &frame) == XQC_HOLD);
    assert(frame.rgb565 == NULL && f.camera[2] == 0);
    f.no_hold = 0;
    f.change_frame = 1;
    assert(xqc_capture(&f.io, ram, XQV_FRAME_BYTES, &frame) == XQC_CHANGED);
    assert(frame.rgb565 == NULL);
    f.change_frame = 0;
    f.cancel = 1;
    assert(xqc_capture(&f.io, ram, XQV_FRAME_BYTES, &frame) == XQC_CANCELLED);
    f.cancel = 0;
    /* Reclaim a STOPPING session; never clear control while DMA is busy. */
    f.camera[3] = CAMERA_STATUS_ENABLED | CAMERA_STATUS_STOPPING |
                  CAMERA_STATUS_WRITER_BUSY;
    assert(xqc_capture(&f.io, ram, XQV_FRAME_BYTES, &frame) == XQC_OK);
    f.no_stop = 1;
    f.camera[3] = CAMERA_STATUS_ENABLED | CAMERA_STATUS_WRITER_BUSY;
    assert(xqc_stop(&f.io) == XQC_STOP);
    assert(f.io.poisoned && (f.camera[2] & CAMERA_CONTROL_STOP_REQUEST));
    assert(xqc_capture(&f.io, ram, XQV_FRAME_BYTES, &frame) == XQC_STOP);
    teardown(&f);
    setup(&f);
    f.first_frame_race = 1;
    f.camera[7] = 1;
    f.fb[3] = 2; /* an already-active GUI does not acknowledge a camera frame */
    assert(xqc_capture(&f.io, ram, XQV_FRAME_BYTES, &frame) == XQC_OK);
    assert(f.hold_first_frame_count >= 6 && !f.invalid_hold); /* exposure settle */
    teardown(&f);
    setup(&f);
    f.io.background=1;f.fb[2]=5;
    for(i=0;i<20;++i) {
        assert(xqc_capture(&f.io,ram,XQV_FRAME_BYTES,&frame)==XQC_OK);
        assert(!memcmp(ram,(const void *)f.io.banks[1],XQV_FRAME_BYTES));
        assert(f.fb[2]==5 && f.camera[2]==(CAMERA_CONTROL_ENABLE|CAMERA_CONTROL_BACKGROUND));
    }
    assert(xqc_stop(&f.io)==XQC_OK && f.fb[2]==5);
    f.no_background_ack=1;f.camera[3]=CAMERA_STATUS_IDLE;
    assert(xqc_capture(&f.io,ram,XQV_FRAME_BYTES,&frame)==XQC_MODE);
    f.no_background_ack=0;f.cancel=1;
    assert(xqc_capture(&f.io,ram,XQV_FRAME_BYTES,&frame)==XQC_CANCELLED && f.fb[2]==5);
    f.cancel=0;f.cancel_copy=1;
    assert(xqc_capture(&f.io,ram,XQV_FRAME_BYTES,&frame)==XQC_CANCELLED);
    assert(!frame.rgb565 && f.fb[2]==5 && f.camera[2]==CAMERA_CONTROL_BACKGROUND);
    f.cancel_copy=0;f.no_hold=1;
    assert(xqc_capture(&f.io,ram,XQV_FRAME_BYTES,&frame)==XQC_HOLD);
    assert(!frame.rgb565 && f.fb[2]==5 && !f.io.poisoned);
    f.no_hold=0;f.change_frame=1;
    assert(xqc_capture(&f.io,ram,XQV_FRAME_BYTES,&frame)==XQC_CHANGED);
    assert(!frame.rgb565 && f.fb[2]==5);
    f.change_frame=0;f.no_stop=1;
    assert(xqc_capture(&f.io,ram,XQV_FRAME_BYTES,&frame)==XQC_OK);
    assert(xqc_stop(&f.io)==XQC_STOP && f.io.poisoned && f.fb[2]==5);
    assert(f.camera[2]==(CAMERA_CONTROL_BACKGROUND|CAMERA_CONTROL_ENABLE|CAMERA_CONTROL_STOP_REQUEST));
    assert(xqc_capture(&f.io,ram,XQV_FRAME_BYTES,&frame)==XQC_STOP && !frame.rgb565);
    teardown(&f);
    free(ram);
    puts("XQ_CAMERA_TEST_PASS legacy=20 background=20 unchanged-scanout warm-capture mode-timeout hold cancel drain quarantine");
    return 0;
}
