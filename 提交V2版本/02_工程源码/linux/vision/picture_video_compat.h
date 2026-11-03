#ifndef XQ_PICTURE_VIDEO_COMPAT_H
#define XQ_PICTURE_VIDEO_COMPAT_H
/* Include after the selected video_fb.h. Private rollback renderer support;
 * keep main's frozen sw/video header exact and avoid mixing two video ABIs. */
#if defined(VIDEO_FB_LINUX_MMAP) && defined(XQ_PICTURE_INPUT)
extern uint8_t xq_linux_video_dirty_rows[VIDEO_FB_HEIGHT];
void xq_linux_video_copy(unsigned int buffer);
static inline void video_fb_copy_dirty_rows(volatile uint32_t *dst,
                                           const uint32_t *src,uint8_t *rows)
{
    for(unsigned y=0;y<VIDEO_FB_HEIGHT;y++)if(rows[y]){
        for(unsigned x=0;x<VIDEO_FB_WIDTH/2;x++){
            unsigned index=y*(VIDEO_FB_WIDTH/2)+x;dst[index]=src[index];
        }
        rows[y]=0;
    }
}
static inline void picture_video_fb_present(unsigned int buffer)
{xq_linux_video_copy(buffer);video_fb_present(buffer);}
#define video_fb_present picture_video_fb_present
#endif
#endif
