#ifndef SOC_BOOTLOADER_CAMERA_H
#define SOC_BOOTLOADER_CAMERA_H

#include <stdint.h>

/* Camera controller MMIO contract.
 *
 * ENABLE starts a camera session.  The hardware keeps the text display active
 * until FRAME_VALID, then owns framebuffer enable/page flips automatically.
 * SNAPSHOT_HOLD latches the complete bank HDMI was scanning at the request.
 * SNAPSHOT_READY means all previously accepted writes have drained and that
 * latched bank will not be overwritten until hold is released.  Software may
 * copy it into a private DDR snapshot before releasing hold.
 * To stop, software keeps ENABLE set while asserting STOP_REQUEST and waits
 * for IDLE before clearing CONTROL.  IDLE means the stop has been observed and
 * all captured data/native DDR writes have drained; it must stay low during a
 * running session even in the gaps between bursts.  A rising ENABLE starts a
 * fresh session and clears session-local completion/error state.
 */
#define CAMERA_ID_VALUE                  0x43414d33u /* "CAM3" */
#define CAMERA_VERSION_VALUE             0x00010003u

#define CAMERA_REG_ID                    0x00u
#define CAMERA_REG_VERSION               0x04u
#define CAMERA_REG_CONTROL               0x08u
#define CAMERA_REG_STATUS                0x0cu
#define CAMERA_REG_FRAME_COUNT           0x10u
#define CAMERA_REG_DROPPED_FRAME_COUNT   0x14u
#define CAMERA_REG_BAD_LINE_COUNT        0x18u
#define CAMERA_REG_SNAPSHOT_FRAME_COUNT  0x1cu

#define CAMERA_CONTROL_ENABLE            (1u << 0)
#define CAMERA_CONTROL_STOP_REQUEST      (1u << 1)
#define CAMERA_CONTROL_SNAPSHOT_HOLD      (1u << 2)

#define CAMERA_STATUS_ENABLED            (1u << 0)
#define CAMERA_STATUS_CMOS1_INIT_DONE     (1u << 1)
#define CAMERA_STATUS_CMOS2_INIT_DONE     (1u << 2)
#define CAMERA_STATUS_FRAME_VALID         (1u << 3)
#define CAMERA_STATUS_WRITER_BUSY         (1u << 4)
#define CAMERA_STATUS_IDLE                (1u << 5)
#define CAMERA_STATUS_STOPPING            (1u << 6)
#define CAMERA_STATUS_COMPLETED_BUFFER1   (1u << 7)
#define CAMERA_STATUS_SCCB_NACK           (1u << 8)
#define CAMERA_STATUS_FRAME_ERROR         (1u << 9)
#define CAMERA_STATUS_DDR_ERROR           (1u << 10)
#define CAMERA_STATUS_SNAPSHOT_READY      (1u << 11)
#define CAMERA_STATUS_SNAPSHOT_BUFFER1    (1u << 12)

int camera_command(void);
int camera_sd_command(void);
int camera_sd_save(uint32_t frame,uint32_t raw_crc,uint64_t uptime_ms);
uint64_t camera_sd_time_ms(void);
/* style: 0 disabled, 1 yellow, 3 green, 5 red. Returns if pending timeout. */
void camera_hud(const char *text,uint32_t style);
int camera_hud_try(const char *text,uint32_t style);
/* Caller provides at least384 bytes. No labels and no fabricated RTC date. */
uint32_t camera_sd_metadata(char *b,uint32_t frame,uint32_t raw_crc,uint32_t png_crc,uint64_t ms);

#endif
