/* Offline static game pages, with no real board, model or device access. */
#include "xinyi_fb.c"
#include <assert.h>
#include <stdlib.h>
volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];
static int microphone(void *context,int on){(void)context;(void)on;return 1;}
int main(int argc,char **argv)
{
    assert(argc==2);uint16_t *pixels=malloc(VIDEO_FB_FRAME_BYTES);assert(pixels);
    for(unsigned mode=0;mode<3;mode++){
        xy_backend backend={.microphone=microphone};xy_app app;
        xy_app_init(&app,&backend);assert(xy_navigate(&app,XY_GAME,(xy_mode)mode));
        app.has_board=app.voice_has_board=0;
        xy_fb_invalidate();xy_fb_render(&app,pixels);
        char path[1200];snprintf(path,sizeof(path),"%s/game-%u.rgb565",argv[1],mode);
        FILE *file=fopen(path,"wbx");assert(file);
        assert(fwrite(pixels,1,VIDEO_FB_FRAME_BYTES,file)==VIDEO_FB_FRAME_BYTES);
        assert(!fclose(file));
    }
    free(pixels);return 0;
}
