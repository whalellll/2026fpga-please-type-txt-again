#ifndef XQ_CAMERA_H
#define XQ_CAMERA_H
#include "xq_vision.h"
#include "camera.h"

/* Only these volatile uint32_t views may touch device/uncached memory. */
typedef struct {
    volatile uint32_t *camera, *fb, *sys;
    volatile uint32_t *banks[2], *snapshot;
    uint64_t (*now_ms)(void *);
    /* waiting=1 may sleep while waiting for hardware. Copy-loop cancellation
     * checks pass zero: nanosleep rounds to Linux ticks on this platform. */
    int (*poll)(void *, int waiting);
    void *context;
    int poisoned; /* writer did not drain; do not redraw/reuse its buffers */
    int background; /* private capture banks; preserve GUI scanout on stop */
} xqc_camera;
enum { XQC_OK = 0, XQC_CANCELLED = 1, XQC_ID = -1, XQC_DDR = -2,
       XQC_START = -3, XQC_HOLD = -4, XQC_CHANGED = -5,
       XQC_STOP = -6, XQC_ARGUMENT = -7, XQC_MODE = -8 };
int xqc_start(xqc_camera *, unsigned timeout_ms);
int xqc_stop(xqc_camera *);
int xqc_capture(xqc_camera *, uint32_t *ordinary_ram, size_t bytes,
                xqv_frame *out);

/* Linux wrapper: exclusive advisory camera owner, /dev/mem O_SYNC mappings.
 * MAC registers and scratch are never mapped by the camera client. */
typedef struct {
    xqc_camera io;
    int fd, lock_fd;
    void *maps[8];
    int (*cancel)(void *);
    void *cancel_context;
} xqc_linux;
int xqc_linux_open(xqc_linux *, int (*cancel)(void *), void *context);
int xqc_linux_close(xqc_linux *);
#endif
