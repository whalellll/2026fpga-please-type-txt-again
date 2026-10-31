#define VIDEO_FB_LINUX_MMAP
#define XQ_PICTURE_INPUT
#ifdef __TINYC__
/* Host-only RAM renderer test; TinyCC has no GCC atomic builtin. */
#define __atomic_thread_fence(order) ((void)0)
#endif
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include "../pikafish/xiangqi_fb_gui_linux.c"
volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];
uint8_t xq_linux_video_dirty_rows[VIDEO_FB_HEIGHT];
void xq_linux_video_copy(unsigned int buffer){(void)buffer;}
int main(int argc, char **argv)
{
    xq_search_board_t board;
    unsigned i, nonempty = 0;
    volatile uint16_t *fb;
    memset(&board, 0, sizeof(board));
    fb = malloc(VIDEO_FB_FRAME_BYTES);
    assert(fb);
    draw_scene(fb, &board, -1, -1, 0, 0, 0, XQ_FB_STATE_READY);
    {
        uint32_t *live=malloc(VIDEO_FB_FRAME_BYTES),regs[12]={0};
        assert(live);
        for(i=0;i<VIDEO_FB_FRAME_BYTES/4;i++)live[i]=0xdeadbeefu;
        memset(xq_linux_video_dirty_rows,0,sizeof(xq_linux_video_dirty_rows));
        put_pixel(fb,5,123,C_GOLD);
        assert(xq_linux_video_dirty_rows[123] && !xq_linux_video_dirty_rows[122]);
        video_fb_copy_dirty_rows(live,(const uint32_t *)(uintptr_t)fb,xq_linux_video_dirty_rows);
        assert(live[122*(VIDEO_FB_WIDTH/2)]==0xdeadbeefu);
        assert(!memcmp(live+123*(VIDEO_FB_WIDTH/2),
                       (const uint32_t *)(uintptr_t)fb+123*(VIDEO_FB_WIDTH/2),VIDEO_FB_STRIDE_BYTES));
        assert(!xq_linux_video_dirty_rows[123]);
        regs[0]=FB_ID_VALUE;regs[VIDEO_FB_FB0_BASE/4]=VIDEO_FB0_PHYS;regs[VIDEO_FB_FB1_BASE/4]=VIDEO_FB1_PHYS;
        xq_linux_video_regs=regs;display_started=1;
        xq_fb_gui_picture_diagnostic(NULL,NULL,NULL,NULL);
        assert(display_started && xq_fb_gui_init() && display_started);
        video_fb_copy_dirty_rows(live,(const uint32_t *)(uintptr_t)fb,xq_linux_video_dirty_rows);
        assert(!memcmp(live,(const void *)fb,VIDEO_FB_FRAME_BYTES));
        free(live);display_started=0;
    }
    xq_fb_gui_picture_feedback("请", "", "");
    draw_picture_feedback(fb);
    {
        unsigned x,y,min_x=1280,max_x=0,min_y=720,max_y=0;
        for (y=458;y<494;++y) for (x=736;x<770;++x) if (fb[y*VIDEO_FB_WIDTH+x]==C_GOLD) {
            if (x<min_x) min_x=x;
            if (x>max_x) max_x=x;
            if (y<min_y) min_y=y;
            if (y>max_y) max_y=y;
        }
        assert(max_x>=min_x+17 && max_y>=min_y+17); /* readable doubled CJK */
    }
    xq_fb_gui_picture_feedback("请把黑方车从b9走到c7", "不确定 请再按一次空格", "桩识别 无真实模型");
    draw_picture_feedback(fb);
    for (i = 0; i < ARRAY_COUNT(xqp_glyphs); ++i) {
        unsigned j;
        for (j = 0; j < 16; ++j) nonempty |= xqp_glyphs[i].rows[j];
    }
    assert(nonempty);
    /* Confirm that CJK text has pixels in the first prompt's row range. */
    nonempty = 0;
    for (i = 466 * VIDEO_FB_WIDTH + 736; i < 482 * VIDEO_FB_WIDTH; ++i)
        if (fb[i] == C_GOLD) ++nonempty;
    assert(nonempty > 100);
    {
        uint32_t *pixels=malloc(XQV_FRAME_BYTES);
        xqp_metrics metrics;
        xqv_result result;
        xqg_detection boxes[32];
        assert(pixels);
        memset(&metrics,0,sizeof(metrics)); memset(&result,0,sizeof(result));
        memset(boxes,0,sizeof(boxes));
        for (i=0; i<XQV_FRAME_BYTES/4; ++i) pixels[i]=(i&65535u)|((i&65535u)<<16);
        metrics.has_frame=1; metrics.is_stub=1; metrics.comparisons=3; metrics.matches=2;
        xq_fb_gui_picture_diagnostic(pixels,boxes,&result,&metrics);
        draw_diagnostic_scene(fb);
        assert(fb[XQP_IMAGE_Y*VIDEO_FB_WIDTH+XQP_IMAGE_X]==0);
        assert(fb[XQP_IMAGE_Y*VIDEO_FB_WIDTH+XQP_IMAGE_X+1]==1);
        assert(fb[(XQP_IMAGE_Y+1)*VIDEO_FB_WIDTH+XQP_IMAGE_X]==1280);
        if (argc==2) {
            char path[1024]; FILE *output;
            snprintf(path,sizeof(path),"%s-diagnostic.rgb565",argv[1]);
            output=fopen(path,"wb"); assert(output);
            assert(fwrite((const void *)fb,1,VIDEO_FB_FRAME_BYTES,output)==VIDEO_FB_FRAME_BYTES);
            assert(!fclose(output));
        }
        xq_fb_gui_picture_diagnostic(NULL,NULL,NULL,NULL);
        {
            uint32_t *rectified=malloc(320u*360u*2u);
            assert(rectified);
            for(i=0;i<320u*360u/2;i++)rectified[i]=0x12341234u;
            metrics.preview_only=1;metrics.manual_geometry=1;
            xq_fb_gui_picture_topview(rectified);
            xq_fb_gui_picture_diagnostic(pixels,boxes,&result,&metrics);
            draw_diagnostic_scene(fb);
            assert(fb[(XQP_IMAGE_Y+5)*VIDEO_FB_WIDTH+XQP_IMAGE_X+165]==0x1234);
            assert(fb[(XQP_IMAGE_Y+5)*VIDEO_FB_WIDTH+XQP_IMAGE_X+160]==C_GREEN);
            xq_fb_gui_picture_topview(NULL);free(rectified);
        }
        xq_fb_gui_picture_diagnostic(NULL,NULL,NULL,NULL);
        free(pixels);
    }
    if (argc==2) {
        char path[1024]; FILE *output;
        xq_fb_gui_picture_feedback("拍摄完毕 正在识别", "请稍候 请勿重复按键", "桩识别 无真实模型");
        draw_scene(fb,&board,-1,-1,0,0,0,XQ_FB_STATE_READY);
        snprintf(path,sizeof(path),"%s-board.rgb565",argv[1]);
        output=fopen(path,"wb"); assert(output);
        assert(fwrite((const void *)fb,1,VIDEO_FB_FRAME_BYTES,output)==VIDEO_FB_FRAME_BYTES);
        assert(!fclose(output));
    }
    free((void *)fb);
    puts("XQ_PICTURE_RENDERER_TEST_PASS Chinese-prompts ordinary-RAM");
    return 0;
}
