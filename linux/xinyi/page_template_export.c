/* Offline exporter: render the real scalar pages, never access a device. */
#include "xinyi_fb.c"
#include <assert.h>
#include <stdlib.h>
volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];
static int microphone(void *context,int enabled)
{(void)context;(void)enabled;return 1;}
int main(int argc,char **argv)
{
    assert(argc==2);uint16_t *pixels=malloc(VIDEO_FB_FRAME_BYTES);assert(pixels);
    for(unsigned page=0;page<4;page++){
        xy_backend backend={.microphone=microphone};xy_app app;
        xy_app_init(&app,&backend);
        if(page)assert(xy_navigate(&app,(xy_page)page,XY_COACH));
        xy_fb_invalidate();xy_fb_render(&app,pixels);
        char path[1200];snprintf(path,sizeof(path),"%s/page-%u.rgb565",argv[1],page);
        FILE *file=fopen(path,"wbx");assert(file);
        assert(fwrite(pixels,1,VIDEO_FB_FRAME_BYTES,file)==VIDEO_FB_FRAME_BYTES);
        assert(!fclose(file));
    }
    free(pixels);return 0;
}
