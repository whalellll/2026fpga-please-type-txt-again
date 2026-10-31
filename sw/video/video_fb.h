#ifndef SOC_VIDEO_FB_H
#define SOC_VIDEO_FB_H

#include <stdint.h>

#define VIDEO_FB_REG_BASE       0x1fe11000u
#ifndef XQ_GUI_1080
#define VIDEO_FB0_PHYS          0x1b200000u
#define VIDEO_FB1_PHYS          0x1b400000u
#define VIDEO_FB0_CPU_UNCACHED  0x9b200000u
#define VIDEO_FB1_CPU_UNCACHED  0x9b400000u
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

#ifdef VIDEO_FB_LINUX_MMAP
extern volatile uint32_t *xq_linux_video_regs;
extern volatile uint16_t *xq_linux_framebuffers[2];
#endif

/* Bare-metal v2 platform note: sub-word stores through the uncached CPU
 * alias (0x9bxxxxxx) stall the CPU (board-verified; 32-bit stores are
 * safe). RGB565 pixel writes are half-word wide, so bare-metal drawing
 * targets this cached DDR shadow and video_fb_present() copies the frame
 * to the live uncached framebuffer bank with full-word stores. The shadow
 * lives in otherwise-unused DDR below the Xiangqi model at 0x0f000000. */
#define VIDEO_FB_SHADOW_PHYS    0x0d000000u

static inline volatile uint16_t *video_fb_pixels(unsigned int buffer)
{
#ifdef VIDEO_FB_LINUX_MMAP
    return xq_linux_framebuffers[buffer ? 1u : 0u];
#else
    (void)buffer;
    return (volatile uint16_t *)(uintptr_t)VIDEO_FB_SHADOW_PHYS;
#endif
}

static inline uint32_t video_fb_read(uint32_t offset)
{
#ifdef VIDEO_FB_LINUX_MMAP
    return xq_linux_video_regs[offset >> 2];
#else
    return *(volatile uint32_t *)(uintptr_t)(VIDEO_FB_REG_BASE + offset);
#endif
}

static inline void video_fb_control(int enable, unsigned int front_buffer,
                                    int clear_underflow)
{
    uint32_t value = enable ? VIDEO_FB_CONTROL_ENABLE : 0u;
    if (front_buffer & 1u)
        value |= VIDEO_FB_CONTROL_BUFFER1;
    if (clear_underflow)
        value |= VIDEO_FB_CONTROL_CLEAR_UFLOW;
#ifdef __riscv
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
#else
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
#endif
#ifdef VIDEO_FB_LINUX_MMAP
    xq_linux_video_regs[VIDEO_FB_CONTROL >> 2] = value;
#else
    *(volatile uint32_t *)(uintptr_t)(VIDEO_FB_REG_BASE + VIDEO_FB_CONTROL) = value;
#endif
}

/* Call after finishing all RGB565 stores to the back buffer.  The
 * hardware applies the selected buffer only at a video frame boundary.
 * On the bare-metal v2 platform the shadow frame is copied to the live
 * uncached bank with word stores first (see the note above). */
static inline void video_fb_present(unsigned int buffer)
{
#ifndef VIDEO_FB_LINUX_MMAP
    {
        volatile uint32_t *dst = (volatile uint32_t *)(uintptr_t)
            (buffer ? VIDEO_FB1_CPU_UNCACHED : VIDEO_FB0_CPU_UNCACHED);
        const uint32_t *src = (const uint32_t *)(uintptr_t)VIDEO_FB_SHADOW_PHYS;
        uint32_t i;
        for (i = 0; i < VIDEO_FB_FRAME_BYTES / 4u; ++i)
            dst[i] = src[i];
    }
#endif
    video_fb_control(1, buffer, 0);
}

#endif
