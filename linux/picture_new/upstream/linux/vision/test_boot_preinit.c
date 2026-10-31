#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "soc.h"
#include "camera.h"
static uint32_t camera[32], fb[32], sys[8], ticks;
static unsigned console_reads, slow_clock, never_ready;
static uint32_t *reg(uint32_t address)
{
    if (address == CAMERA_BASE + CAMERA_REG_STATUS) {
        if (camera[2] == (CAMERA_CONTROL_ENABLE | CAMERA_CONTROL_STOP_REQUEST))
            camera[3] = CAMERA_STATUS_IDLE;
        else if (camera[2] == CAMERA_CONTROL_ENABLE && !never_ready)
            camera[3] = CAMERA_STATUS_ENABLED | CAMERA_STATUS_CMOS1_INIT_DONE |
                        CAMERA_STATUS_CMOS2_INIT_DONE | CAMERA_STATUS_FRAME_VALID;
    }
    if (address >= CAMERA_BASE && address < CAMERA_BASE + sizeof(camera))
        return &camera[(address - CAMERA_BASE) / 4];
    if (address >= FB_REG_BASE && address < FB_REG_BASE + sizeof(fb))
        return &fb[(address - FB_REG_BASE) / 4];
    if (address >= SYS_BASE && address < SYS_BASE + sizeof(sys))
        return &sys[(address - SYS_BASE) / 4];
    assert(0);
    return NULL;
}
#undef REG32
#define REG32(address) (*reg(address))
#define CAMERA_HOST_TEST 1
#include "../../sw/bootloader/camera.c"
uint32_t read_mtime_ticks32(void) { ticks += slow_clock ? TIMEBASE_HZ : 1; return ticks; }
void delay_cycles(uint32_t value) { ticks += value; }
int console_getc_timeout(uint32_t value) { (void)value; ++console_reads; return -1; }
void console_puts(const char *text) { (void)text; }
void console_hex(uint32_t value) { (void)value; }
void console_dec(uint32_t value) { (void)value; }
void console_putc(char value) { (void)value; }
uint64_t camera_sd_time_ms(void) { assert(0); return 0; }
int camera_sd_save(uint32_t a, uint32_t b, uint64_t c) { (void)a; (void)b; (void)c; assert(0); return -1; }
int camera_transfer(uint32_t a, const uint8_t *b, uint32_t c) { (void)a; (void)b; (void)c; assert(0); return -1; }
int main(void)
{
    ticks = TIMEBASE_HZ * 5u;
    camera[0] = CAMERA_ID_VALUE;
    camera[1] = CAMERA_VERSION_VALUE;
    sys[1] = 1;
    sys[3] = SYS_CAP_CAMERA;
    assert(camera_preinit() == 0);
    assert(camera[2] == CAMERA_CONTROL_ENABLE && console_reads == 0);
    camera[3] = CAMERA_STATUS_WRITER_BUSY | CAMERA_STATUS_STOPPING;
    assert(camera_preinit() == 0);
    assert(camera[2] == CAMERA_CONTROL_ENABLE && console_reads == 0);
    camera[0] = 0;
    assert(camera_preinit() == -1);
    camera[0] = CAMERA_ID_VALUE;
    camera[3] = 0;
    never_ready = slow_clock = 1;
    assert(camera_preinit() == -1);
    assert(camera[2] == 0 && console_reads == 0);
    puts("XQ_BOOT_PREINIT_TEST_PASS live-handoff no-console-read bounded-timeout");
    return 0;
}
