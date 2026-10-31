#include <assert.h>
#include <stdio.h>
#include "soc.h"
#include "xq_camera_retry.h"
static uint32_t camera[32],fb[32],sys[8];static unsigned expected_background,calls;static int result;
static volatile uint32_t *reg(uint32_t address)
{
    if(address==CAMERA_BASE)return camera;
    if(address==FB_REG_BASE)return fb;
    assert(address==SYS_BASE);return sys;
}
#define PICTURE_BOOT_CAMERA_PTR(address) reg(address)
#include "../boot/v2_1_sd/source/picture_camera_boot.c"
uint32_t read_mtime_ticks32(void){return 1;}
void delay_cycles(uint32_t value){(void)value;}
int console_getc_timeout(uint32_t value){(void)value;return -1;}
void console_puts(const char *text){(void)text;}
void console_hex(uint32_t value){(void)value;}
void console_dec(uint32_t value){(void)value;}
void console_putc(char value){(void)value;}
int xqc_start_retry(xqc_camera *c,unsigned timeout,unsigned attempts,xqc_start_observer observe,void *ctx)
{
    assert(c->background==(int)expected_background && timeout==20000 && attempts==8);
    assert(c->now_ms(c->context)==0 && !c->poll(c->context,1));
    ++calls;observe(ctx,1,result,0);return result;
}
int main(void)
{
    camera[0]=CAMERA_ID_VALUE;camera[1]=CAMERA_VERSION_VALUE;
    assert(!picture_camera_preinit() && calls==1); /* CPU80 base CAM3 */
    camera[CAMERA_REG_CAPABILITIES/4]=CAMERA_CAP_BACKGROUND_CAPTURE;
    assert(picture_camera_preinit()==XQC_MODE && calls==1);
    camera[CAMERA_REG_BACKGROUND_FB0/4]=CAMERA_BACKGROUND_FB0_PHYS;
    camera[CAMERA_REG_BACKGROUND_FB1/4]=CAMERA_BACKGROUND_FB1_PHYS;expected_background=1;
    assert(!picture_camera_preinit() && calls==2);
    result=XQC_START;assert(picture_camera_preinit()==XQC_START && calls==3);
    camera[0]=0;assert(picture_camera_preinit()==XQC_ID && calls==3);
    puts("XQ_BOOT_PREINIT_TEST_PASS CPU80_base_or_E8_capability bounded_retry fatal_identity");return 0;
}
