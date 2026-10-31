#ifndef XIANGQI_LINUX_VIDEO_FB_H
#define XIANGQI_LINUX_VIDEO_FB_H

#include <stdint.h>

#define VIDEO_FB_REG_BASE       0x1fe11000u
#ifndef XQ_GUI_1080
#define VIDEO_FB0_PHYS          0x1b200000u
#define VIDEO_FB1_PHYS          0x1b400000u
#define VIDEO_FB_WIDTH          1280u
#define VIDEO_FB_HEIGHT         720u
#define VIDEO_FB_STRIDE_BYTES   2560u
#define VIDEO_FB_FRAME_BYTES    0x001c2000u
#define VIDEO_FB_SLOT_BYTES     0x00200000u

#endif

#define VIDEO_FB_ID             0x00u
#define VIDEO_FB_VERSION        0x04u
#define VIDEO_FB_CONTROL        0x08u
#define VIDEO_FB_STATUS         0x0cu
#define VIDEO_FB_FB0_BASE       0x10u
#define VIDEO_FB_FB1_BASE       0x14u
#define VIDEO_FB_STRIDE         0x18u
#define VIDEO_FB_SIZE           0x1cu
#define VIDEO_FB_BYTES          0x20u
#define VIDEO_FB_FRAME_COUNT    0x24u
#define VIDEO_FB_UFLOW_COUNT    0x28u

#define VIDEO_FB_CONTROL_ENABLE       (1u << 0)
#define VIDEO_FB_CONTROL_BUFFER1      (1u << 1)
#define VIDEO_FB_CONTROL_CLEAR_UFLOW  (1u << 8)

#define VIDEO_FB_STATUS_ACTIVE        (1u << 1)
#define VIDEO_FB_STATUS_FRONT1        (1u << 2)
#define VIDEO_FB_STATUS_UNDERFLOW     (1u << 3)
#define VIDEO_FB_STATUS_DMA_BUSY      (1u << 4)
#define VIDEO_FB_STATUS_DMA_ERROR     (1u << 5)

extern volatile uint32_t *xq_linux_video_regs;
extern volatile uint16_t *xq_linux_framebuffers[2];

static inline volatile uint16_t *video_fb_pixels(unsigned int buffer)
{
    return xq_linux_framebuffers[buffer & 1u];
}

static inline uint32_t video_fb_read(uint32_t offset)
{
    return xq_linux_video_regs[offset >> 2];
}

static inline void video_fb_control(int enable, unsigned int front_buffer,
                                    int clear_underflow)
{
    uint32_t value = enable ? VIDEO_FB_CONTROL_ENABLE : 0u;
    if (front_buffer & 1u)
        value |= VIDEO_FB_CONTROL_BUFFER1;
    if (clear_underflow)
        value |= VIDEO_FB_CONTROL_CLEAR_UFLOW;
    __sync_synchronize();
    xq_linux_video_regs[VIDEO_FB_CONTROL >> 2] = value;
    __sync_synchronize();
}

static inline void video_fb_present(unsigned int buffer)
{
    video_fb_control(1, buffer, 0);
}

#endif
