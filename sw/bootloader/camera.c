#include "soc.h"
#include "camera.h"
#include "crc32_fast.h"

#define CAMERA_START_TIMEOUT_CYCLES (TIMEBASE_HZ * 10u)
#define CAMERA_STOP_TIMEOUT_CYCLES  (TIMEBASE_HZ * 2u)
#define CAMERA_POLL_CYCLES          (TIMEBASE_HZ / 1000u)
#define CAMERA_DDR_GUARD_CYCLES     (TIMEBASE_HZ * 5u)
#define CAMERA_SNAPSHOT_TIMEOUT     (TIMEBASE_HZ * 2u)

#define FB_REG_CONTROL              0x08u
#define FB_REG_STATUS               0x0cu
#define FB_STATUS_ACTIVE_ENABLE     (1u << 1)

#define WAIT_READY                  0
#define WAIT_CANCELLED              1
#define WAIT_TIMEOUT               -1

static void io_fence(void)
{
#ifndef CAMERA_HOST_TEST
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
#endif
}

static uint32_t camera_read(uint32_t offset)
{
    return REG32(CAMERA_BASE + offset);
}

static void camera_write_control(uint32_t value)
{
    REG32(CAMERA_BASE + CAMERA_REG_CONTROL) = value;
    io_fence();
}

static void framebuffer_disable(void)
{
    REG32(FB_REG_BASE + FB_REG_CONTROL) = 0u;
    io_fence();
}

static int timeout_expired(uint32_t start, uint32_t timeout)
{
    return (uint32_t)(read_mtime_ticks32() - start) >= timeout;
}

static int poll_escape(void)
{
    return console_getc_timeout(CAMERA_POLL_CYCLES) == 0x1b;
}

/* The controller holds both banks after draining any admitted frame.  Only
 * then can software copy the published bank through the uncached DDR alias.
 * HDMI continues scanning its complete bank throughout this short pause. */
static int camera_snapshot(uint32_t *frame, uint32_t *crc)
{
    volatile const uint32_t *source;
    volatile uint32_t *target = (volatile uint32_t *)(uintptr_t)CAMERA_SNAPSHOT_CPU_ALIAS;
    uint32_t status, start = read_mtime_ticks32(), i, buffer;
    int key;

    // The request must refer to a CMOS2 frame actually visible on HDMI.
    while (!(REG32(FB_REG_BASE + FB_REG_STATUS) & FB_STATUS_ACTIVE_ENABLE)) {
        key = console_getc_timeout(CAMERA_POLL_CYCLES);
        if (key == 0x1b) return 1;
        if (key == ' ') console_puts("Camera busy; one photo at a time.\n");
        if (timeout_expired(start, CAMERA_SNAPSHOT_TIMEOUT)) return -1;
    }
    camera_write_control(CAMERA_CONTROL_ENABLE | CAMERA_CONTROL_SNAPSHOT_HOLD);
    start = read_mtime_ticks32();
    while (!(camera_read(CAMERA_REG_STATUS) & CAMERA_STATUS_SNAPSHOT_READY)) {
        key = console_getc_timeout(CAMERA_POLL_CYCLES);
        if (key == 0x1b) {
            camera_write_control(CAMERA_CONTROL_ENABLE);
            return 1;
        }
        if (key == ' ') console_puts("Camera busy; one photo at a time.\n");
        if (timeout_expired(start, CAMERA_SNAPSHOT_TIMEOUT) ||
            (camera_read(CAMERA_REG_STATUS) & CAMERA_STATUS_DDR_ERROR)) {
            camera_write_control(CAMERA_CONTROL_ENABLE);
            return -1;
        }
    }
    status = camera_read(CAMERA_REG_STATUS);
    buffer = (status & CAMERA_STATUS_SNAPSHOT_BUFFER1) != 0u;
    *frame = camera_read(CAMERA_REG_SNAPSHOT_FRAME_COUNT);
    source = (volatile const uint32_t *)(uintptr_t)
        (buffer ? FB1_CPU_ALIAS : FB0_CPU_ALIAS);
    for (i = 0; i < FB_FRAME_BYTES / 4u; ++i) {
        target[i] = source[i];
        if ((i & 4095u) == 0u) {
            key = console_getc_timeout(1u);
            if (key == 0x1b) {
                camera_write_control(CAMERA_CONTROL_ENABLE);
                return 1;
            }
            if (key == ' ') console_puts("Camera busy; one photo at a time.\n");
        }
    }
    io_fence();
    if (!(camera_read(CAMERA_REG_STATUS) & CAMERA_STATUS_SNAPSHOT_READY) ||
        camera_read(CAMERA_REG_SNAPSHOT_FRAME_COUNT) != *frame) {
        camera_write_control(CAMERA_CONTROL_ENABLE);
        return -1;
    }
    camera_write_control(CAMERA_CONTROL_ENABLE);
    *crc = 0xffffffffu;
    for (i = 0; i < FB_FRAME_BYTES; i += 4096u) {
        *crc = crc32_fast(*crc,
                (const void *)(uintptr_t)(CAMERA_SNAPSHOT_CPU_ALIAS + i),
                FB_FRAME_BYTES - i < 4096u ? FB_FRAME_BYTES - i : 4096u);
        key = console_getc_timeout(1u);
        if (key == 0x1b) return 1;
        if (key == ' ') console_puts("Camera busy; one photo at a time.\n");
    }
    *crc ^= 0xffffffffu;
    return 0;
}

/* The existing DDR bridge deliberately avoids status reads during early PHY
 * training.  Respect the same five-second guard used by netboot, but count it
 * inside the camera command's ten-second startup deadline. */
static int wait_for_ddr(uint32_t start)
{
    uint32_t now = read_mtime_ticks32();

    while (now < CAMERA_DDR_GUARD_CYCLES &&
           !timeout_expired(start, CAMERA_START_TIMEOUT_CYCLES)) {
        uint32_t remaining = CAMERA_DDR_GUARD_CYCLES - now;
        int c = console_getc_timeout(
            remaining < CAMERA_POLL_CYCLES ? remaining : CAMERA_POLL_CYCLES);
        if (c == 0x1b)
            return WAIT_CANCELLED;
        now = read_mtime_ticks32();
    }

    while (!timeout_expired(start, CAMERA_START_TIMEOUT_CYCLES)) {
        if (REG32(SYS_BASE + 4u) & 1u)
            return WAIT_READY;
        if (poll_escape())
            return WAIT_CANCELLED;
    }
    return WAIT_TIMEOUT;
}

/* Returns only after the native writer is safe to disconnect, or after a
 * bounded timeout.  CONTROL is cleared even on timeout so a failed command
 * cannot leave the camera or framebuffer selected indefinitely. */
static int camera_stop(void)
{
    uint32_t start = read_mtime_ticks32();
    int idle = 0;

    camera_write_control(CAMERA_CONTROL_ENABLE |
                         CAMERA_CONTROL_STOP_REQUEST);
    while (!timeout_expired(start, CAMERA_STOP_TIMEOUT_CYCLES)) {
        if (camera_read(CAMERA_REG_STATUS) & CAMERA_STATUS_IDLE) {
            idle = 1;
            break;
        }
        delay_cycles(CAMERA_POLL_CYCLES);
    }

    camera_write_control(0u);
    framebuffer_disable();
    return idle ? 0 : -1;
}

static void print_camera_error(const char *message, uint32_t status)
{
    console_puts(message);
    console_puts(" status=");
    console_hex(status);
    console_putc('\n');
}

static void camera_hud_commit(const char *text,uint32_t style)
{
 uint32_t word,i,j;int ended=0;
 for(i=0;i<8;i++){
  word=0;
  for(j=0;j<4;j++){
   uint8_t ch=' ';
   if(!ended){if(*text)ch=(uint8_t)*text++;else ended=1;}
   word|=(uint32_t)ch<<(j*8u);
  }
  REG32(CAMERA_BASE+0x30u+i*4u)=word;
 }
 io_fence();REG32(CAMERA_BASE+0x20u)=style;io_fence();
}
int camera_hud_try(const char *text,uint32_t style)
{
 if(REG32(CAMERA_BASE+0x20u)&0x80000000u)return 0;
 camera_hud_commit(text,style);return 1;
}
void camera_hud(const char *text,uint32_t style)
{
 uint32_t start=read_mtime_ticks32();
 while(!camera_hud_try(text,style))
  if(timeout_expired(start,TIMEBASE_HZ/10u))return;
}

static int camera_run(int save_to_sd)
{
    uint32_t start;
    uint32_t status;
    int wait_result;
    int runtime_error = 0;

    if (!(REG32(SYS_BASE + 12u) & SYS_CAP_CAMERA)) {
        console_puts("Camera controller is not present in this bitstream.\n");
        return -1;
    }
    if (camera_read(CAMERA_REG_ID) != CAMERA_ID_VALUE ||
        camera_read(CAMERA_REG_VERSION) != CAMERA_VERSION_VALUE) {
        console_puts("Camera controller ID/version mismatch.\n");
        return -1;
    }

    /* Recover a previous interrupted session without ever cutting off an
     * in-flight native DDR burst. */
    status = camera_read(CAMERA_REG_STATUS);
    if (status & (CAMERA_STATUS_ENABLED | CAMERA_STATUS_WRITER_BUSY |
                  CAMERA_STATUS_STOPPING)) {
        if (camera_stop()) {
            console_puts("Previous camera session did not stop safely.\n");
            return -1;
        }
    } else {
        camera_write_control(0u);
        framebuffer_disable();
    }

    camera_hud("",0);
    console_puts("Starting camera; press Esc to cancel.\n");
    start = read_mtime_ticks32();
    wait_result = wait_for_ddr(start);
    if (wait_result == WAIT_CANCELLED) {
        console_puts("Camera start cancelled; terminal remains active.\n");
        return 1;
    }
    if (wait_result == WAIT_TIMEOUT) {
        console_puts("Camera start timed out waiting for DDR; terminal remains active.\n");
        return -1;
    }

    camera_write_control(CAMERA_CONTROL_ENABLE);
    for (;;) {
        status = camera_read(CAMERA_REG_STATUS);
        if ((status & (CAMERA_STATUS_CMOS1_INIT_DONE |
                       CAMERA_STATUS_CMOS2_INIT_DONE |
                       CAMERA_STATUS_FRAME_VALID)) ==
            (CAMERA_STATUS_CMOS1_INIT_DONE |
             CAMERA_STATUS_CMOS2_INIT_DONE | CAMERA_STATUS_FRAME_VALID))
            break;
        if (status & (CAMERA_STATUS_SCCB_NACK | CAMERA_STATUS_DDR_ERROR)) {
            print_camera_error("Camera failed during startup;", status);
            if (camera_stop())
                console_puts("Camera safe stop timed out; reset/power-down was not confirmed.\n");
            return -1;
        }
        if (poll_escape()) {
            if (camera_stop())
                console_puts("Camera safe stop timed out; reset/power-down was not confirmed.\n");
            else
                console_puts("Camera start cancelled; terminal restored.\n");
            return 1;
        }
        if (timeout_expired(start, CAMERA_START_TIMEOUT_CYCLES)) {
            print_camera_error("Camera initialization/first frame timed out;", status);
            if (camera_stop())
                console_puts("Camera safe stop timed out; reset/power-down was not confirmed.\n");
            return -1;
        }
    }

    console_puts("Camera is live on HDMI. Space: save CMOS2 PNG; Esc: stop.\n");
    if(save_to_sd){console_puts("Destination: SD /CAMERA; keep card inserted until terminal restored.\n");camera_hud("SD READY - SPACE TO SAVE",1);}
    for (;;) {
        int key = console_getc_timeout(CAMERA_POLL_CYCLES);
        if (key == 0x1b)
            break;
        if (key == ' ') {
            uint32_t frame, crc;
            uint64_t uptime_ms=save_to_sd?camera_sd_time_ms():0;
            int result;
            if(save_to_sd)camera_hud("CAPTURING",1);
            console_puts("Capturing complete CMOS2 frame...\n");
            result = camera_snapshot(&frame, &crc);
            if(save_to_sd&&result<0)camera_hud("ERROR SNAPSHOT",5);
            if (!result) {
                console_puts("Saving frame "); console_dec(frame);
                console_puts("; further Space presses are busy.\n");
                result = save_to_sd?camera_sd_save(frame,crc,uptime_ms):
                    camera_transfer(frame,(const uint8_t *)(uintptr_t)CAMERA_SNAPSHOT_CPU_ALIAS,crc);
            }
            if (result == 1) break;
            if (result == 0) console_puts(save_to_sd?"Photo saved and verified on SD.\n":"Photo saved by PC.\n");
            else {
                console_puts("Photo failed; preview remains live. Retry with Space.\n");
            }
        }
        status = camera_read(CAMERA_REG_STATUS);
        if (!(status & CAMERA_STATUS_ENABLED) ||
            (status & (CAMERA_STATUS_SCCB_NACK | CAMERA_STATUS_DDR_ERROR))) {
            runtime_error = 1;
            break;
        }
    }

    camera_hud("",0);
    status = camera_read(CAMERA_REG_STATUS);
    if (camera_stop()) {
        print_camera_error(
            "Camera safe stop timed out; reset/power-down was not confirmed;",
            status);
        return -1;
    }
    if (runtime_error) {
        print_camera_error("Camera stopped after a hardware error;", status);
        return -1;
    }

    console_puts("Camera stopped; bootloader terminal restored.\n");
    return 0;
}
int camera_command(void){return camera_run(0);}
int camera_sd_command(void){return camera_run(1);}
