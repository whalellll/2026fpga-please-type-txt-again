/* Execute the production snapshot routine with MMIO and console events mocked.
 * Frame buffers use their actual uncached addresses in a Windows host process. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include "../sw/bootloader/soc.h"
#include "../sw/bootloader/camera.h"

static uint32_t fb_status, cam_control, cam_status, cam_frame, clock_now;
static uint32_t hud_control,hud_words[8],hud_payload_accesses;
static int mode, busy_count, copy_polls, crc_polls;
enum { BUSY_ALL, ESC_FIRST_FRAME, ESC_COPY, ESC_CRC };
static uint32_t *mock_register(uint32_t address)
{
    if (address == FB_REG_BASE + 0x0cu) return &fb_status;
    if (address == CAMERA_BASE + CAMERA_REG_CONTROL) return &cam_control;
    if (address == CAMERA_BASE + CAMERA_REG_STATUS) return &cam_status;
    if (address == CAMERA_BASE + CAMERA_REG_SNAPSHOT_FRAME_COUNT) return &cam_frame;
    if (address == CAMERA_BASE + 0x20u) return &hud_control;
    if (address >= CAMERA_BASE + 0x30u && address < CAMERA_BASE + 0x50u) {
        ++hud_payload_accesses;return &hud_words[(address-CAMERA_BASE-0x30u)/4u];
    }
    assert(!"unexpected snapshot MMIO access");
    return &cam_status;
}
#undef REG32
#define REG32(address) (*mock_register(address))
#define CAMERA_HOST_TEST 1
#undef WAIT_TIMEOUT
#include "../sw/bootloader/camera.c"

/* The host test calls camera_snapshot directly; these production save
 * backends are intentionally outside its scope, but GCC may retain the
 * camera command wrapper in this translation unit. */
uint64_t camera_sd_time_ms(void) { assert(0 && "save backend called"); return 0; }
int camera_sd_save(uint32_t frame, uint32_t crc, uint64_t uptime_ms)
{
    (void)frame; (void)crc; (void)uptime_ms;
    assert(0 && "save backend called");
    return -1;
}
int camera_transfer(uint32_t frame, const uint8_t *pixels, uint32_t crc)
{
    (void)frame; (void)pixels; (void)crc;
    assert(0 && "transfer backend called");
    return -1;
}

uint32_t read_mtime_ticks32(void) { return ++clock_now; }
void console_puts(const char *text)
{
    assert(strcmp(text, "Camera busy; one photo at a time.\n") == 0);
    ++busy_count;
}
int console_getc_timeout(uint32_t cycles)
{
    (void)cycles;
    if (!(fb_status & FB_STATUS_ACTIVE_ENABLE)) {
        if (mode == ESC_FIRST_FRAME) return 0x1b;
        fb_status = FB_STATUS_ACTIVE_ENABLE;
        return ' ';
    }
    if (cam_control & CAMERA_CONTROL_SNAPSHOT_HOLD) {
        if (copy_polls++ == 0) return mode == ESC_COPY ? 0x1b : ' ';
        return -1;
    }
    if (crc_polls++ == 0) {
        /* Preview writers can replace BOTH live banks after release. */
        memset((void *)(uintptr_t)FB0_CPU_ALIAS, 0xa5, FB_FRAME_BYTES);
        memset((void *)(uintptr_t)FB1_CPU_ALIAS, 0x5a, FB_FRAME_BYTES);
        return mode == ESC_CRC ? 0x1b : ' ';
    }
    return -1;
}

static void prepare(int test_mode, int bank)
{
    unsigned i;
    uint8_t *source = (uint8_t *)(uintptr_t)(bank ? FB1_CPU_ALIAS : FB0_CPU_ALIAS);
    mode = test_mode;
    busy_count = copy_polls = crc_polls = 0;
    fb_status = 0;
    cam_control = CAMERA_CONTROL_ENABLE;
    cam_status = CAMERA_STATUS_SNAPSHOT_READY |
        (bank ? CAMERA_STATUS_SNAPSHOT_BUFFER1 : 0u);
    cam_frame = 42u + (uint32_t)bank;
    clock_now = 0;
    for (i = 0; i < FB_FRAME_BYTES; ++i) source[i] = (uint8_t)(i * 13u + bank * 71u);
}

int main(void)
{
    void *banks[3];
    uint8_t *expected = malloc(FB_FRAME_BYTES);
    uint32_t addresses[] = { FB0_CPU_ALIAS, FB1_CPU_ALIAS, CAMERA_SNAPSHOT_CPU_ALIAS };
    uint32_t frame, crc, expected_crc;
    int bank, index;
    /* A busy CDC mailbox must return immediately and leave its in-flight
     * text untouched. Retrying after acknowledgement submits one payload. */
    hud_control=0x80000000u;hud_payload_accesses=0;
    memset(hud_words,0xa5,sizeof(hud_words));
    assert(camera_hud_try("SAVING 50%",1)==0);
    assert(hud_control==0x80000000u&&hud_payload_accesses==0);
    for(index=0;index<8;index++)assert(hud_words[index]==0xa5a5a5a5u);
    hud_control=0;assert(camera_hud_try("SAVING 50%",1)==1);
    assert(hud_control==1&&hud_payload_accesses==8);
    assert(hud_words[0]==0x49564153u&&hud_words[1]==0x3520474eu);
    assert(hud_words[2]==0x20202530u&&hud_words[7]==0x20202020u);
    assert(expected != NULL);
    for (index = 0; index < 3; ++index) {
        banks[index] = VirtualAlloc((void *)(uintptr_t)addresses[index], FB_FRAME_BYTES,
                                   MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
        assert(banks[index] == (void *)(uintptr_t)addresses[index]);
    }
    for (bank = 0; bank < 2; ++bank) {
        prepare(BUSY_ALL, bank);
        memcpy(expected, banks[bank], FB_FRAME_BYTES);
        expected_crc = crc32_update(0xffffffffu, expected, FB_FRAME_BYTES) ^ 0xffffffffu;
        assert(camera_snapshot(&frame, &crc) == 0);
        assert(frame == 42u + (uint32_t)bank && crc == expected_crc);
        assert(cam_control == CAMERA_CONTROL_ENABLE && busy_count == 3);
        assert(memcmp(expected, banks[2], FB_FRAME_BYTES) == 0);
        assert((uint32_t)crc_polls == (FB_FRAME_BYTES + 4095u) / 4096u);
    }
    for (index = ESC_FIRST_FRAME; index <= ESC_CRC; ++index) {
        prepare(index, 0);
        assert(camera_snapshot(&frame, &crc) == 1);
        assert(cam_control == CAMERA_CONTROL_ENABLE);
        if (index == ESC_COPY) assert(copy_polls == 1 && crc_polls == 0);
        if (index == ESC_CRC) assert(crc_polls == 1);
    }
    for (index = 0; index < 3; ++index) assert(VirtualFree(banks[index], 0, MEM_RELEASE));
    free(expected);
    puts("BOOTLOADER_CAMERA_SNAPSHOT_BUSY_ESC_CRC_PASS");
    puts("BOOTLOADER_CAMERA_HUD_TRY_BUSY_PAYLOAD_PRESERVED_PASS");
    return 0;
}
