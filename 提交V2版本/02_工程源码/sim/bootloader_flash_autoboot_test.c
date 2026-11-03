#include <assert.h>
#include <stdio.h>
#include <string.h>
static int bootloader_console_main(void) __attribute__((unused));
#define main bootloader_console_main
/* Renaming main removes C's implicit return-0 rule. The console is unused here. */
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wreturn-type"
#include "../sw/bootloader/main.c"
#pragma GCC diagnostic pop
#undef main

/* Exercise the production startup decision and manual boot helper, with only
 * I/O and the terminal jump stubbed. Header/payload parsing is tested by the
 * real-CPU SPI read fixture, rather than duplicating its implementation here. */
static int header_result, key_result, load_result, waits, loads, jumps;
static uint32_t header_flags, waited_cycles;
static char output[512];
static size_t output_length;
int flash_read_header(image_header_t *h) {
    memset(h, 0, sizeof(*h)); h->flags = header_flags; return header_result;
}
int flash_load_image(image_header_t *h) {
    ++loads; memset(h, 0, sizeof(*h)); h->entry_addr = 0x00100000u;
    return load_result;
}
int console_getc_timeout(uint32_t cycles) {
    ++waits; waited_cycles = cycles; return key_result;
}
void console_putc(char c) {
    assert(output_length + 1 < sizeof(output));
    output[output_length++] = c; output[output_length] = 0;
}
void console_puts(const char *s) { while (*s) console_putc(*s++); }
void console_dec(uint32_t v) { (void)v; }
void console_hex(uint32_t v) { (void)v; }
void jump_to(uint32_t entry, uint32_t a0, uint32_t a1) {
    assert(entry == 0x00100000u && a0 == 0 && a1 == 0); ++jumps;
}
static void reset_case(void) {
    header_result = 0; header_flags = 1; key_result = -1; load_result = 0;
    waits = loads = jumps = 0; waited_cycles = 0;
    output_length = 0; output[0] = 0;
}
int main(void) {
    int error;
    assert(sizeof(image_header_t) == 32);
    for (error = -1; error >= -3; --error) {
        reset_case(); header_result = error; try_automatic_flashboot();
        assert(!waits && !loads && !jumps && !output_length);
    }
    reset_case(); header_flags = 2; try_automatic_flashboot();
    assert(!waits && !loads && !jumps);
    reset_case(); key_result = 0; try_automatic_flashboot();
    assert(waits == 1 && waited_cycles == SYS_CLOCK_HZ * 3u);
    assert(!loads && !jumps && strstr(output, "Autoboot stopped."));
    reset_case(); load_result = -4; try_automatic_flashboot();
    assert(waits == 1 && loads == 1 && !jumps);
    assert(strstr(output, "Flash image invalid"));
    reset_case(); try_automatic_flashboot();
    assert(waits == 1 && waited_cycles == SYS_CLOCK_HZ * 3u);
    assert(loads == 1 && jumps == 1);
    reset_case(); header_flags = 0; assert(do_flashboot() == 0);
    assert(!waits && loads == 1 && jumps == 1);
    puts("FLASH_AUTOBOOT_HOST_PASS header_errors=3 flags_off cancel timeout_jump load_failure manual_boot");
    return 0;
}
