#include "platform.c"
#include <assert.h>
int main(void)
{
    uint32_t sys[1024]={0};xy_platform p={0};xy_platform_input in;
    p.sys_page=sys;volatile uint32_t *hid=sys+0x400/4;
    hid[0x0c/4]=(360u<<11)|150;
    assert(xy_platform_read_input(&p,&in) && in.mouse_sample && !in.mouse_valid);
    hid[0x08/4]=16;hid[0x1c/4]++;
    assert(xy_platform_read_input(&p,&in) && in.mouse_valid && !in.left_down && !in.left_click);
    hid[0x08/4]=17;hid[0x28/4]=1;hid[0x1c/4]++;
    assert(xy_platform_read_input(&p,&in) && in.left_down && in.left_click);
    assert(xy_platform_read_input(&p,&in) && in.left_down && !in.left_click);
    hid[0x08/4]=16;hid[0x1c/4]++;
    assert(xy_platform_read_input(&p,&in) && !in.left_down && !in.left_click);
    hid[0x28/4]=2;hid[0x1c/4]++;
    assert(xy_platform_read_input(&p,&in) && in.left_click && !in.left_down); /* Short click. */
    p.left_count=65535;hid[0x28/4]=0;
    assert(xy_platform_read_input(&p,&in) && in.left_click);
    hid[0x0c/4]=2047;hid[0x28/4]=1;
    assert(xy_platform_read_input(&p,&in) && !in.mouse_valid && !in.left_click);
    puts("ACTUAL_HID_SNAPSHOT_BUTTON_HOLD_RELEASE_SHORT_CLICK_COUNTER_WRAP_UNSEEN_AND_RANGE_PASS_NOT_BOARD");return 0;
}
