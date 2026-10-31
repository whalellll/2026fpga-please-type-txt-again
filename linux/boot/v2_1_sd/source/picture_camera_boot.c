#include "soc.h"
#include "xq_camera_retry.h"
#ifndef PICTURE_BOOT_CAMERA_PTR
#define PICTURE_BOOT_CAMERA_PTR(address) ((volatile uint32_t *)(uintptr_t)(address))
#endif
struct boot_clock { uint32_t previous; uint64_t elapsed; };
static uint64_t boot_ms(void *p)
{
    struct boot_clock *clock=p;
    uint32_t current=read_mtime_ticks32();
    clock->elapsed+=(uint32_t)(current-clock->previous);clock->previous=current;
    return clock->elapsed/(TIMEBASE_HZ/1000u);
}
static int boot_poll(void *p,int waiting)
{
    (void)p;
    if(waiting)delay_cycles(TIMEBASE_HZ/1000u);
    return console_getc_timeout(1u)==0x1b;
}
static void report(void *p,unsigned attempt,int result,uint32_t status)
{
    (void)p;console_puts("PICTURE_CAMERA_START attempt=");console_dec(attempt);
    console_puts(" result=");if(result<0)console_putc('-');console_dec(result<0?(uint32_t)-result:(uint32_t)result);
    console_puts(" status=");console_hex(status);console_putc('\n');
}
int picture_camera_preinit(void)
{
    struct boot_clock clock={read_mtime_ticks32(),0};
    xqc_camera camera={0};
    camera.camera=PICTURE_BOOT_CAMERA_PTR(CAMERA_BASE);
    camera.fb=PICTURE_BOOT_CAMERA_PTR(FB_REG_BASE);
    camera.sys=PICTURE_BOOT_CAMERA_PTR(SYS_BASE);
    camera.now_ms=boot_ms;camera.poll=boot_poll;camera.context=&clock;
    if(camera.camera[0]!=CAMERA_ID_VALUE || camera.camera[1]!=CAMERA_VERSION_VALUE)return XQC_ID;
    if(camera.camera[CAMERA_REG_CAPABILITIES/4]&CAMERA_CAP_BACKGROUND_CAPTURE) {
        if(camera.camera[CAMERA_REG_BACKGROUND_FB0/4]!=CAMERA_BACKGROUND_FB0_PHYS ||
           camera.camera[CAMERA_REG_BACKGROUND_FB1/4]!=CAMERA_BACKGROUND_FB1_PHYS)return XQC_MODE;
        camera.background=1;
    }
    return xqc_start_retry(&camera,20000,8,report,NULL);
}
