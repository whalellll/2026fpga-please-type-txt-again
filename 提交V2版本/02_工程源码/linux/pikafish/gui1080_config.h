#ifndef XQ_GUI1080_CONFIG_H
#define XQ_GUI1080_CONFIG_H

/* Apply with -include to every GUI translation unit, including mouse input. */
#define XQ_GUI_1080 1
#define VIDEO_FB0_PHYS         0x1b800000u
#define VIDEO_FB1_PHYS         0x1bc00000u
#define VIDEO_FB0_CPU_UNCACHED 0x9b800000u
#define VIDEO_FB1_CPU_UNCACHED 0x9bc00000u
#define VIDEO_FB_WIDTH         1920u
#define VIDEO_FB_HEIGHT        1080u
#define VIDEO_FB_STRIDE_BYTES  3840u
#define VIDEO_FB_FRAME_BYTES   4147200u
#define VIDEO_FB_SLOT_BYTES    0x00400000u

#endif
