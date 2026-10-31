#include <stdint.h>
#include "trained_conv_tile_vector.h"

#define UART (*(volatile uint32_t *)0x1fe001e0u)
#define REG(n) (*(volatile uint32_t *)(0x1fe10000u + (n)))
#define DDR_CPU 0x9b000000u
#define DDR_BUS 0x1b000000u
#define INPUT_OFF 0x00000u
#define WEIGHT_OFF 0x70000u
#define OUTPUT_OFF 0x80000u

static void putc(char c) { if (c == '\n') UART = '\r'; UART = (uint8_t)c; }
static void puts(const char *s) { while (*s) putc(*s++); }
static void hex(uint32_t v)
{
    static const char digits[] = "0123456789abcdef";
    int i;
    for (i = 7; i >= 0; --i) putc(digits[(v >> (i * 4)) & 15]);
}
static uint32_t counter(uint32_t index)
{
    REG(0x78) = index;
    return REG(0x7c);
}
static void copy_words(uint32_t offset, const unsigned char *src, uint32_t count)
{
    volatile uint32_t *dst = (volatile uint32_t *)(DDR_CPU + offset);
    uint32_t i;
    for (i = 0; i < count / 4u; ++i)
        dst[i] = ((uint32_t)src[i * 4u]) | ((uint32_t)src[i * 4u + 1u] << 8) |
                 ((uint32_t)src[i * 4u + 2u] << 16) |
                 ((uint32_t)src[i * 4u + 3u] << 24);
}
static int fail(const char *why, uint32_t value)
{
    puts("MAC_CONV_TRAINED_TILE_FAIL "); puts(why); putc('='); hex(value); putc('\n');
    return 1;
}
int main(void)
{
    volatile uint32_t *output = (volatile uint32_t *)(DDR_CPU + OUTPUT_OFF);
    uint32_t i, status = 0, cycles;
    if (REG(0x00) != 0x4d41434bu || REG(0x40) != 0x4d434f4eu ||
        REG(0x44) != 0x00030000u) return fail("abi", REG(0x44));
    copy_words(INPUT_OFF, tile_input, sizeof(tile_input));
    copy_words(WEIGHT_OFF, tile_weights, sizeof(tile_weights));
    for (i = 0; i < TILE_OUTPUT_BYTES / 4u; ++i) output[i] = 0xa5a5a5a5u;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    REG(0x48) = 8u;
    REG(0x4c) = (TILE_HEIGHT << 16) | TILE_WIDTH;
    REG(0x50) = (2u << 24) | (2u << 20) | (6u << 16) | 3u;
    REG(0x54) = 16u << 16;
    REG(0x58) = DDR_BUS + INPUT_OFF;
    REG(0x5c) = DDR_BUS + WEIGHT_OFF;
    REG(0x60) = DDR_BUS + OUTPUT_OFF;
    REG(0x64) = 27u;
    REG(0x68) = 0x4d434f4eu;
    REG(0x6c) = 0x8ff15d34u;
    REG(0x70) = 0x885fe98eu;
    for (i = 0; i < 16u; ++i) {
        REG(0x78) = 0x20u + i;
        REG(0x7c) = (uint32_t)tile_bias[i];
        REG(0x78) = 0x40u + i;
        REG(0x7c) = (uint32_t)tile_shift[i];
    }
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    REG(0x48) = 1u;
    for (i = 0; i < 1000000u; ++i) {
        status = REG(0x48);
        if (status & 6u) break;
    }
    if (!(status & 2u) || (status & 4u)) return fail("weight_status", status);
    REG(0x48) = 2u;
    if (!(REG(0x48) & 128u)) return fail("ready", REG(0x48));
    REG(0x48) = 8u;
    REG(0x48) = 16u;
    for (i = 0; i < 10000000u; ++i) {
        status = REG(0x48);
        if (status & (256u | 512u)) break;
    }
    if (!(status & 256u) || (status & 512u)) return fail("compute_status", status);
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    for (i = 0; i < TILE_OUTPUT_BYTES; ++i) {
        uint32_t value = (output[i / 4u] >> ((i % 4u) * 8u)) & 255u;
        if (value != tile_expected[i]) return fail("first_bad_byte", i);
    }
    if (counter(0) != 1024u || counter(1) != 3456u ||
        counter(2) != 2304u || counter(3) != 64u ||
        counter(12) != TILE_OUTPUT_BYTES)
        return fail("counter", counter(12));
    cycles = counter(13);
    if (cycles == 0u || cycles > 100000u) return fail("cycles", cycles);
    puts("MAC_CONV_TRAINED_TILE_BOARD_PASS output_crc32=");
    hex(TILE_OUTPUT_CRC32); puts(" compute_cycles="); hex(cycles); putc('\n');
    return 0;
}
