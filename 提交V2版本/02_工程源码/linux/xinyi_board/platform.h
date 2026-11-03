#ifndef XINYI_BOARD_PLATFORM_H
#define XINYI_BOARD_PLATFORM_H
#include <stddef.h>
#include <stdint.h>
#include "clock_contract.h"
#include "xq_camera.h"

typedef struct xy_platform xy_platform;
typedef enum { XY_PLATFORM_CAPTURE, XY_PLATFORM_PREVIEW_START,
               XY_PLATFORM_PREVIEW_STOP } xy_platform_operation;
typedef enum { XY_PLATFORM_OK, XY_PLATFORM_CANCELLED, XY_PLATFORM_FAILED,
               XY_PLATFORM_UNDRAINED } xy_platform_result;
typedef struct {
    uint32_t token;
    xy_platform_operation operation;
    xy_platform_result result;
    int camera_result,drained,display_restored,preview_active;
} xy_platform_event;
typedef struct {
    uint32_t token,frame_id,crc32;
    uint64_t captured_ms;
    const uint32_t *rgb565;
    size_t bytes;
} xy_platform_frame;
typedef struct {
    int key; /* Only Space(32)/Esc(27); retired R/C events are ignored. */
    unsigned mouse_x,mouse_y;
    int left_click,right_click,mouse_valid;
    uint64_t key_first_ms;
} xy_platform_input;

/* Target integrated60 has one camera/GUI video mux: preview owns the whole
 * HDMI source, with centered 1280x720 pixels and black margins. No composition
 * with the product page; no E8 private capture banks. Hardware identity and
 * no-map reservation coverage must pass before any DDR mapping is exposed. */
enum { XY_PLATFORM_EXCLUSIVE_PREVIEW=1u, XY_PLATFORM_GUI_WIDTH=1920,
       XY_PLATFORM_GUI_HEIGHT=1080, XY_PLATFORM_GUI_BYTES=4147200 };
xy_platform *xy_platform_open(void);
/* Returns zero and retains mappings/lock on an undrained writer. Never free
 * such a platform or start another owner. Reset/recovery is an explicit caller
 * decision; unsafe cancellation never receives a drained completion event. */
int xy_platform_close(xy_platform *);
unsigned xy_platform_capabilities(const xy_platform *);
uint32_t xy_platform_cpu_hz(const xy_platform *);
volatile uint16_t *xy_platform_pixels(xy_platform *,unsigned page);
volatile uint32_t *xy_platform_video_regs(xy_platform *);
/* 1 presented; 2 deferred because exclusive camera preview owns HDMI;
 * 0 error/undrained. frame writes must use the existing 32-bit-safe renderer. */
int xy_platform_present(xy_platform *,unsigned page);
int xy_platform_take_invalidation(xy_platform *);

int xy_platform_capture_start(xy_platform *,uint32_t token);
int xy_platform_preview_start(xy_platform *,uint32_t token);
int xy_platform_preview_stop(xy_platform *,uint32_t token);
int xy_platform_cancel(xy_platform *,uint32_t token);
/* Nonblocking completion; returns one event exactly once after join. CANCELLED
 * is emitted only after drain succeeded. UNDRAINED is a fatal status, not ack. */
int xy_platform_poll(xy_platform *,xy_platform_event *);
/* Successful capture stays immutable in ordinary RAM. Pin until the coach IPC
 * writer has consumed it. No new capture while pinned; never logs frame/CRC. */
int xy_platform_frame_acquire(xy_platform *,uint32_t token,xy_platform_frame *);
int xy_platform_frame_release(xy_platform *,uint32_t token);

int xy_platform_read_input(xy_platform *,xy_platform_input *);
void xy_platform_discard_input(xy_platform *);
int xy_platform_terminal_attach(xy_platform *,int fd);
int xy_platform_terminal_key(xy_platform *);
void xy_platform_terminal_restore(xy_platform *);

/* Read-only contract helpers are shared with focused host tests. They accept
 * paths only for fixture inspection and never change actual mapping ranges. */
int xy_platform_reservations_cover(const char *device_tree_root);
int xy_platform_validate_mmio(const volatile uint32_t *camera,
    const volatile uint32_t *video,const volatile uint32_t *sys_page);

#ifdef XY_PLATFORM_TEST
xy_platform *xy_platform_test_attach(xqc_camera *,volatile uint32_t *sys_page,
    volatile uint16_t *gui0,volatile uint16_t *gui1);
void xy_platform_test_set_preview(xy_platform *,int);
#endif
#endif
