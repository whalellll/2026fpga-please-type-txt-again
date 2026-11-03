#include "xq_camera.h"
#include <string.h>

#define FB_CONTROL 2u
#define FB_STATUS 3u
#define C_STATUS (CAMERA_REG_STATUS / 4u)
#define C_CONTROL (CAMERA_REG_CONTROL / 4u)
#define C_FRAME (CAMERA_REG_SNAPSHOT_FRAME_COUNT / 4u)
#define READY (CAMERA_STATUS_CMOS1_INIT_DONE | CAMERA_STATUS_CMOS2_INIT_DONE | CAMERA_STATUS_FRAME_VALID)
#define ERRORS (CAMERA_STATUS_SCCB_NACK | CAMERA_STATUS_DDR_ERROR | CAMERA_STATUS_FRAME_ERROR)

static void fence_io(void)
{
#ifdef __riscv
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
#elif defined(__GNUC__)
    __sync_synchronize();
#endif
}
static void control(xqc_camera *c, uint32_t value)
{
    fence_io();
    c->camera[C_CONTROL] = value | (c->background ? CAMERA_CONTROL_BACKGROUND : 0u);
    fence_io();
}
static int expired(xqc_camera *c, uint64_t start, unsigned timeout)
{
    return c->now_ms(c->context) - start >= timeout;
}

int xqc_stop(xqc_camera *c)
{
    uint64_t start = c->now_ms(c->context);
    uint32_t status = c->camera[C_STATUS];
    unsigned polls = 0;
    if (!(status & (CAMERA_STATUS_ENABLED | CAMERA_STATUS_WRITER_BUSY |
                    CAMERA_STATUS_STOPPING)) && !(c->camera[C_CONTROL] & 1u)) {
        control(c, 0);
        return XQC_OK;
    }
    control(c, CAMERA_CONTROL_ENABLE | CAMERA_CONTROL_STOP_REQUEST);
    while (!(c->camera[C_STATUS] & CAMERA_STATUS_IDLE)) {
        if (expired(c, start, 2000) || ++polls >= 2000) {
            c->poisoned = 1;
            return XQC_STOP;
        }
        /* Cancellation must not cut a native DDR burst short. */
        (void)c->poll(c->context, 1);
    }
    control(c, 0);
    if(!c->background)c->fb[FB_CONTROL] = 0;
    fence_io();
    c->poisoned = 0;
    return XQC_OK;
}

int xqc_start(xqc_camera *c, unsigned timeout_ms)
{
    uint64_t start = c->now_ms(c->context);
    uint32_t status;
    unsigned polls = 0;
    int r;
    if (c->poisoned) return XQC_STOP;
    if (!(c->sys[3] & 8u) || c->camera[0] != CAMERA_ID_VALUE ||
        c->camera[1] != CAMERA_VERSION_VALUE) return XQC_ID;
    status = c->camera[C_STATUS];
    if ((status & (CAMERA_STATUS_STOPPING | ERRORS)) ||
        (c->camera[C_CONTROL] & CAMERA_CONTROL_STOP_REQUEST) ||
        (!(status & CAMERA_STATUS_ENABLED) && (status & CAMERA_STATUS_WRITER_BUSY))) {
        r = xqc_stop(c);
        if (r) return r;
    }
    while (!(c->sys[1] & 1u)) {
        if (c->poll(c->context, 1)) return XQC_CANCELLED;
        if (expired(c, start, timeout_ms) || ++polls >= timeout_ms) return XQC_DDR;
    }
    if(c->background &&
       (!(c->camera[C_CONTROL]&CAMERA_CONTROL_BACKGROUND) ||
        !(c->camera[C_STATUS]&CAMERA_STATUS_BACKGROUND_ACTIVE))) {
        // Reclaim an inherited legacy session, configure while idle, then
        // wait for the native DDR domain to commit the private-bank mode.
        r=xqc_stop(c);
        if(r)return r;
        control(c,0);
        while(!(c->camera[C_STATUS]&CAMERA_STATUS_BACKGROUND_ACTIVE) ||
              !(c->camera[C_CONTROL]&CAMERA_CONTROL_BACKGROUND)) {
            if(c->poll(c->context,1))return XQC_CANCELLED;
            if(expired(c,start,timeout_ms) || ++polls>=timeout_ms)return XQC_MODE;
        }
    }
    /* Also re-enable scanout after a previous GUI exit. The camera mux owns
     * page selection while ENABLE is high; GUI may not write its pages. */
    if(!c->background)c->fb[FB_CONTROL] = 1u;
    control(c, CAMERA_CONTROL_ENABLE); /* releases an inherited HOLD */
    for (;;) {
        if (c->poll(c->context, 1)) return XQC_CANCELLED;
        status = c->camera[C_STATUS];
        if (status & ERRORS) return XQC_START;
        /* ACTIVE may still describe the previous GUI bank. The hardware
         * latches an invalid HOLD if its first camera bank is not displayed
         * yet. Two published frames guarantee both banks belong to this
         * session, including the one HDMI was scanning at the request.
         * Cold session frames 1-2 were nearly black on the board; wait for
         * six published frames so sensor auto-exposure can settle as well. */
        if ((status & READY) == READY && (c->background || (c->fb[FB_STATUS] & 2u)) &&
            c->camera[CAMERA_REG_FRAME_COUNT / 4u] >= 6u) return XQC_OK;
        if (expired(c, start, timeout_ms) || ++polls >= timeout_ms) return XQC_START;
    }
}

int xqc_capture(xqc_camera *c, uint32_t *ram, size_t bytes, xqv_frame *out)
{
    uint64_t start;
    uint32_t status, frame = 0, bank, i;
    int r, stop;
    if (!out) return XQC_ARGUMENT;
    memset(out, 0, sizeof(*out));
    if (!c || !ram || ((uintptr_t)ram & 3u) || bytes != XQV_FRAME_BYTES)
        return XQC_ARGUMENT;
    if (c->poisoned) return XQC_STOP;
    start = c->now_ms(c->context);
    r = xqc_start(c, 5000);
    if (r == XQC_ID) return r;
    if (r) goto done;
    control(c, CAMERA_CONTROL_ENABLE | CAMERA_CONTROL_SNAPSHOT_HOLD);
    {
        uint64_t hold_start = c->now_ms(c->context);
        unsigned polls = 0;
        while (!(c->camera[C_STATUS] & CAMERA_STATUS_SNAPSHOT_READY)) {
            if (c->poll(c->context, 1)) { r = XQC_CANCELLED; goto done; }
            if (expired(c, hold_start, 2000) || ++polls >= 2000 || (c->camera[C_STATUS] & ERRORS)) {
                r = XQC_HOLD;
                goto done;
            }
        }
    }
    fence_io();
    status = c->camera[C_STATUS];
    bank = (status & CAMERA_STATUS_SNAPSHOT_BUFFER1) != 0;
    frame = c->camera[C_FRAME];
    /* Do not replace either loop with memcpy/memset. Volatile full-word
     * loads/stores are required even if the source/destination is RGB565. */
    for (i = 0; i < XQV_FRAME_BYTES / 4u; ++i) {
        uint32_t word = c->banks[bank][i];
        c->snapshot[i] = word;
        ram[i] = word;
        if (!(i & 4095u) && c->poll(c->context, 0)) { r = XQC_CANCELLED; goto done; }
    }
    fence_io();
    status = c->camera[C_STATUS];
    if (!(status & CAMERA_STATUS_SNAPSHOT_READY) ||
        ((status & CAMERA_STATUS_SNAPSHOT_BUFFER1) != 0) != bank ||
        c->camera[C_FRAME] != frame || (status & ERRORS)) {
        r = XQC_CHANGED;
        goto done;
    }
    control(c, CAMERA_CONTROL_ENABLE);
    /* The ordinary-RAM copy was filled from the same locked bank word.
     * Expose it only after READY/bank/frame verification; no second full
     * uncached snapshot read is needed. */
done:
    // A successful background snapshot lives in ordinary RAM and the private
    // snapshot aperture. Private camera banks may now resume without touching
    // GUI pages; keep the sensor/exposure warm between Space captures.
    if(!r && c->background) {
        out->rgb565=ram;out->bytes=bytes;out->frame_id=frame;out->captured_ms=start;
        return XQC_OK;
    }
    /* Always drain before returning framebuffer ownership to the GUI. */
    stop = xqc_stop(c);
    if (stop) return stop;
    if (r) return r;
    out->rgb565 = ram;
    out->bytes = bytes;
    out->frame_id = frame;
    out->captured_ms = start;
    return XQC_OK;
}
