#include <stdint.h>

#define UART (*(volatile uint32_t *)0x1fe001e0u)
#define MAC_BASE 0x1fe10000u
#define DDR_BUS 0x1b000000u
#define DDR_CPU 0x9b000000u
#define INPUT_OFF  0x00000u
#define WEIGHT_OFF 0x70000u
#define OUTPUT_OFF 0x80000u
#define REG(n) (*(volatile uint32_t *)(MAC_BASE + (n)))

struct shape {
    uint16_t width, height, channels, output_channels;
    uint8_t kernel, stride, padding, tile;
};

static const struct shape shapes[] = {
    {8, 7, 3, 4, 1, 1, 0, 0},
    {7, 7, 5, 8, 3, 1, 1, 1},
    {7, 7, 3, 16, 6, 1, 2, 0},
    {320, 320, 3, 16, 6, 2, 2, 0}
};

static void putc(char c)
{
    if (c == '\n') UART = '\r';
    UART = (uint8_t)c;
}

static void puts(const char *s)
{
    while (*s) putc(*s++);
}

static void hex(uint32_t x)
{
    static const char digits[] = "0123456789abcdef";
    int i;
    for (i = 7; i >= 0; --i) putc(digits[(x >> (i * 4)) & 15u]);
}

static void dec(uint32_t x)
{
    char digits[10];
    int n = 0;
    do { digits[n++] = (char)('0' + x % 10u); x /= 10u; } while (x);
    while (n) putc(digits[--n]);
}

static uint32_t counter(uint32_t id)
{
    REG(0x78) = id;
    return REG(0x7c);
}

static uint32_t wait_status(uint32_t done, uint32_t error)
{
    uint32_t count;
    for (count = 0; count < 10000000u; ++count) {
        uint32_t status = REG(0x48);
        if (status & (done | error)) return status;
    }
    return 0xffffffffu;
}

static uint32_t input_byte(uint32_t byte_index, uint32_t case_index)
{
    return (byte_index * 37u + (byte_index >> 4) * 19u +
            (byte_index >> 9) * 7u + case_index * 13u) & 255u;
}

static uint32_t expected_tap_xor(const struct shape *s, uint32_t case_index)
{
    uint32_t tiles = (s->channels + 3u) / 4u;
    uint32_t ow = (s->width + 2u * s->padding - s->kernel) / s->stride + 1u;
    uint32_t oh = (s->height + 2u * s->padding - s->kernel) / s->stride + 1u;
    uint32_t check = 0, ox, oy, kx, ky, lane;
    for (oy = 0; oy < oh; ++oy)
        for (ox = 0; ox < ow; ++ox)
            for (ky = 0; ky < s->kernel; ++ky)
                for (kx = 0; kx < s->kernel; ++kx) {
                    int x = (int)(ox * s->stride + kx) - s->padding;
                    int y = (int)(oy * s->stride + ky) - s->padding;
                    uint32_t word = 0;
                    if (x >= 0 && x < s->width && y >= 0 && y < s->height)
                        for (lane = 0; lane < 4; ++lane) {
                            uint32_t channel = s->tile * 4u + lane;
                            if (channel < s->channels)
                                word |= input_byte(
                                    ((uint32_t)y * s->width + x) *
                                        tiles * 4u + channel,
                                    case_index) << (8u * lane);
                        }
                    check ^= word;
                }
    return check;
}

static int run_case(const struct shape *s, uint32_t case_index)
{
    volatile uint32_t *input = (volatile uint32_t *)(DDR_CPU + INPUT_OFF);
    volatile uint32_t *weight = (volatile uint32_t *)(DDR_CPU + WEIGHT_OFF);
    volatile uint32_t *output = (volatile uint32_t *)(DDR_CPU + OUTPUT_OFF);
    uint32_t tiles = (s->channels + 3u) / 4u;
    uint32_t pixels = (uint32_t)s->width * s->height;
    uint32_t lines = (s->channels * s->kernel * s->kernel + 3u) / 4u;
    uint32_t ow = (s->width + 2u * s->padding - s->kernel) / s->stride + 1u;
    uint32_t oh = (s->height + 2u * s->padding - s->kernel) / s->stride + 1u;
    uint32_t windows = ow * oh, taps = windows * s->kernel * s->kernel;
    uint32_t i, lane, status, expected;

    for (i = 0; i < pixels * tiles; ++i) {
        uint32_t word = 0;
        for (lane = 0; lane < 4; ++lane)
            word |= input_byte(i * 4u + lane, case_index) << (8u * lane);
        input[i] = word;
    }
    for (i = 0; i < lines * 32u; ++i) {
        uint32_t word = 0;
        for (lane = 0; lane < 4; ++lane)
            word |= (((i * 4u + lane) * 29u + case_index) & 255u) <<
                (8u * lane);
        weight[i] = word;
    }
    for (i = 0; i < 16; ++i) output[i] = 0xdeadbeefu;
    expected = expected_tap_xor(s, case_index);
    __asm__ volatile ("fence iorw, iorw" ::: "memory");

    REG(0x48) = 8u;
    REG(0x4c) = ((uint32_t)s->height << 16) | s->width;
    REG(0x50) = ((uint32_t)s->padding << 24) |
                ((uint32_t)s->stride << 20) |
                ((uint32_t)s->kernel << 16) | s->channels;
    REG(0x54) = ((uint32_t)s->output_channels << 16) | s->tile;
    REG(0x58) = DDR_BUS + INPUT_OFF;
    REG(0x5c) = DDR_BUS + WEIGHT_OFF;
    REG(0x60) = DDR_BUS + OUTPUT_OFF;
    REG(0x64) = lines;
    REG(0x68) = 0x4d434f4eu;
    REG(0x6c) = case_index;
    REG(0x70) = case_index + 1u;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    REG(0x48) = 1u;
    status = wait_status(2u, 4u);
    if (status & 4u || status == 0xffffffffu) goto fail;
    REG(0x48) = 2u;
    if (!(REG(0x48) & 128u)) { status = REG(0x48); goto fail; }
    if (counter(8) != case_index + 1u || counter(9) != s->tile ||
        counter(10) != lines) { status = REG(0x48); goto fail; }
    REG(0x48) = 8u;
    REG(0x48) = 4u;
    status = wait_status(16u, 32u);
    if (status & 32u || status == 0xffffffffu) goto fail;
    if (counter(0) != pixels * 4u || counter(1) != lines * 128u ||
        counter(2) != taps || counter(3) != windows ||
        counter(7) != expected || counter(11) == 0 || REG(0x74) == 0)
        goto fail;
    for (i = 0; i < 16; ++i)
        if (output[i] != 0xdeadbeefu) goto fail;
    puts("CONV_CASE_PASS id="); dec(case_index);
    puts(" taps="); dec(counter(2));
    puts(" input="); dec(counter(0));
    puts(" weight="); dec(counter(1));
    puts(" reuse="); dec(counter(3));
    puts(" cycles="); dec(REG(0x74));
    puts(" stalls="); dec(counter(4));
    puts(" tap_xor="); hex(counter(7));
    puts(" weight_digest="); hex(counter(11));
    putc('\n');
    return 0;
fail:
    puts("CONV_CASE_FAIL id="); dec(case_index);
    puts(" status="); hex(status);
    puts(" input="); dec(counter(0));
    puts(" weight="); dec(counter(1));
    puts(" taps="); dec(counter(2));
    puts(" reuse="); dec(counter(3));
    puts(" xor="); hex(counter(7));
    puts(" expected="); hex(expected);
    putc('\n');
    return 1;
}

static int32_t signed_byte(uint32_t value)
{
    return value < 128u ? (int32_t)value : (int32_t)value - 256;
}

static uint32_t requant(int32_t value, uint32_t shift)
{
    int32_t magnitude = value < 0 ? -value : value;
    int32_t rounded = (magnitude + (1 << (shift - 1u))) >> shift;
    if (value < 0) rounded = -rounded;
    if (rounded > 127) return 127u;
    if (rounded < -128) return 128u;
    return (uint8_t)rounded;
}

static uint32_t compute_input_byte(uint32_t index)
{
    return (index * 29u + (index / 7u) * 13u + 34u) & 255u;
}

static uint32_t compute_weight_byte(uint32_t oc, uint32_t scalar)
{
    uint32_t tap = scalar / 3u;
    uint32_t channel = scalar % 3u;
    uint32_t logical = ((oc * 3u + channel) * 6u + tap / 6u) * 6u + tap % 6u;
    return (uint8_t)(((int32_t)((logical * 11u +
            (logical / 108u) * 3u) & 15u)) - 8);
}

static int run_compute_case(void)
{
    volatile uint32_t *input = (volatile uint32_t *)(DDR_CPU + INPUT_OFF);
    volatile uint32_t *weight = (volatile uint32_t *)(DDR_CPU + WEIGHT_OFF);
    volatile uint32_t *output = (volatile uint32_t *)(DDR_CPU + OUTPUT_OFF);
    uint32_t i, oc, scalar, oy, ox, ky, kx, ci, status;
    uint32_t mismatches = 0, first = 0xffffffffu;

    for (i = 0; i < 49u; ++i) {
        uint32_t word = 0, lane;
        for (lane = 0; lane < 4u; ++lane)
            word |= compute_input_byte(i * 4u + lane) << (8u * lane);
        input[i] = word;
    }
    for (i = 0; i < 864u; ++i) weight[i] = 0;
    for (oc = 0; oc < 16u; ++oc)
        for (scalar = 0; scalar < 108u; ++scalar) {
            uint32_t index = (scalar / 4u) * 32u + oc;
            uint32_t shift = (scalar % 4u) * 8u;
            uint32_t word = weight[index];
            weight[index] = (word & ~(255u << shift)) |
                            (compute_weight_byte(oc, scalar) << shift);
        }
    for (i = 0; i < 36u; ++i) output[i] = 0xa5a5a5a5u;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");

    REG(0x48) = 8u;
    REG(0x4c) = (7u << 16) | 7u;
    REG(0x50) = (2u << 24) | (2u << 20) | (6u << 16) | 3u;
    REG(0x54) = (16u << 16);
    REG(0x58) = DDR_BUS + INPUT_OFF;
    REG(0x5c) = DDR_BUS + WEIGHT_OFF;
    REG(0x60) = DDR_BUS + OUTPUT_OFF;
    REG(0x64) = 27u;
    REG(0x68) = 0x4d434f4eu;
    REG(0x6c) = 3u;
    REG(0x70) = 5u;
    for (oc = 0; oc < 16u; ++oc) {
        REG(0x78) = 0x20u + oc;
        REG(0x7c) = oc * 13u - 50u;
        REG(0x78) = 0x40u + oc;
        REG(0x7c) = oc % 4u + 2u;
    }
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    REG(0x48) = 1u;
    status = wait_status(2u, 4u);
    if (status & 4u || status == 0xffffffffu) goto fail;
    REG(0x48) = 2u;
    if (!(REG(0x48) & 128u)) { status = REG(0x48); goto fail; }
    REG(0x48) = 8u;
    REG(0x48) = 16u;
    status = wait_status(256u, 512u);
    if (status & 512u || status == 0xffffffffu) goto fail;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    for (oy = 0; oy < 3u; ++oy)
        for (ox = 0; ox < 3u; ++ox)
            for (oc = 0; oc < 16u; ++oc) {
                int32_t sum = (int32_t)oc * 13 - 50;
                uint32_t offset = (oy * 3u + ox) * 16u + oc;
                uint32_t actual = (output[offset / 4u] >>
                                  ((offset % 4u) * 8u)) & 255u;
                for (ky = 0; ky < 6u; ++ky)
                    for (kx = 0; kx < 6u; ++kx)
                        for (ci = 0; ci < 3u; ++ci) {
                            int32_t x = (int32_t)(ox * 2u + kx) - 2;
                            int32_t y = (int32_t)(oy * 2u + ky) - 2;
                            uint32_t scalar_id = (ky * 6u + kx) * 3u + ci;
                            int32_t a = x < 0 || x >= 7 || y < 0 || y >= 7 ?
                                0 : signed_byte(compute_input_byte(
                                    ((uint32_t)y * 7u + (uint32_t)x) * 4u + ci));
                            int32_t w = signed_byte(compute_weight_byte(
                                oc, scalar_id));
                            sum += a * w;
                        }
                if (actual != requant(sum, oc % 4u + 2u)) {
                    if (first == 0xffffffffu) first = offset;
                    ++mismatches;
                }
            }
    if (mismatches || counter(0) != 196u || counter(1) != 3456u ||
        counter(2) != 324u || counter(3) != 9u ||
        counter(12) != 144u || counter(13) == 0u) goto fail;
    puts("MAC_CONV_COMPUTE_BOARD_PASS output=144 input=196 weight=3456 taps=324 reuse=9 compute_cycles=");
    dec(counter(13)); puts(" weight_cycles="); dec(counter(6)); putc('\n');
    return 0;
fail:
    puts("MAC_CONV_COMPUTE_BOARD_FAIL status="); hex(status);
    puts(" mismatch="); dec(mismatches);
    puts(" first="); hex(first);
    puts(" input="); dec(counter(0));
    puts(" weight="); dec(counter(1));
    puts(" output="); dec(counter(12));
    puts(" taps="); dec(counter(2));
    puts(" reuse="); dec(counter(3));
    putc('\n');
    return 1;
}

static uint32_t small_input_byte(uint32_t index, uint32_t seed)
{
    return (index * 7u + seed * 11u) & 255u;
}

static uint32_t small_weight_byte(const struct shape *s,
                                  uint32_t oc, uint32_t scalar)
{
    uint32_t tap = scalar / s->channels;
    uint32_t channel = scalar % s->channels;
    uint32_t logical = ((oc * s->channels + channel) * s->kernel +
                        tap / s->kernel) * s->kernel + tap % s->kernel;
    return (uint8_t)((int32_t)((logical * 3u + oc) & 15u) - 8);
}

static int run_compute_small(const struct shape *s, uint32_t seed)
{
    volatile uint32_t *input = (volatile uint32_t *)(DDR_CPU + INPUT_OFF);
    volatile uint32_t *weight = (volatile uint32_t *)(DDR_CPU + WEIGHT_OFF);
    volatile uint32_t *output = (volatile uint32_t *)(DDR_CPU + OUTPUT_OFF);
    uint32_t lines = (s->channels * s->kernel * s->kernel + 3u) / 4u;
    uint32_t scalar_count = s->channels * s->kernel * s->kernel;
    uint32_t ow = (s->width + 2u * s->padding - s->kernel) / s->stride + 1u;
    uint32_t oh = (s->height + 2u * s->padding - s->kernel) / s->stride + 1u;
    uint32_t bytes = ow * oh * s->output_channels;
    uint32_t i, lane, oc, scalar, oy, ox, ky, kx, ci, status;
    uint32_t first = 0xffffffffu, mismatches = 0;

    for (i = 0; i < (uint32_t)s->width * s->height; ++i) {
        uint32_t word = 0;
        for (lane = 0; lane < 4u; ++lane)
            word |= small_input_byte(i * 4u + lane, seed) << (8u * lane);
        input[i] = word;
    }
    for (i = 0; i < lines * 32u; ++i) weight[i] = 0;
    for (oc = 0; oc < s->output_channels; ++oc)
        for (scalar = 0; scalar < scalar_count; ++scalar) {
            uint32_t index = (scalar / 4u) * 32u + oc;
            uint32_t shift = (scalar % 4u) * 8u;
            uint32_t word = weight[index];
            weight[index] = (word & ~(255u << shift)) |
                (small_weight_byte(s, oc, scalar) << shift);
        }
    for (i = 0; i < (bytes + 3u) / 4u; ++i) output[i] = 0xaabbccddu;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");

    REG(0x48) = 8u;
    REG(0x4c) = ((uint32_t)s->height << 16) | s->width;
    REG(0x50) = ((uint32_t)s->padding << 24) |
                ((uint32_t)s->stride << 20) |
                ((uint32_t)s->kernel << 16) | s->channels;
    REG(0x54) = ((uint32_t)s->output_channels << 16);
    REG(0x58) = DDR_BUS + INPUT_OFF;
    REG(0x5c) = DDR_BUS + WEIGHT_OFF;
    REG(0x60) = DDR_BUS + OUTPUT_OFF;
    REG(0x64) = lines;
    REG(0x68) = 0x4d434f4eu;
    REG(0x6c) = seed;
    REG(0x70) = seed + 6u;
    for (oc = 0; oc < s->output_channels; ++oc) {
        REG(0x78) = 0x20u + oc;
        REG(0x7c) = oc * 13u - 50u;
        REG(0x78) = 0x40u + oc;
        REG(0x7c) = oc % 4u + 2u;
    }
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    REG(0x48) = 1u;
    status = wait_status(2u, 4u);
    if (status & 4u || status == 0xffffffffu) goto fail;
    REG(0x48) = 2u;
    if (!(REG(0x48) & 128u)) { status = REG(0x48); goto fail; }
    REG(0x48) = 8u;
    REG(0x48) = 16u;
    status = wait_status(256u, 512u);
    if (status & 512u || status == 0xffffffffu) goto fail;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    for (oy = 0; oy < oh; ++oy)
        for (ox = 0; ox < ow; ++ox)
            for (oc = 0; oc < s->output_channels; ++oc) {
                int32_t sum = (int32_t)oc * 13 - 50;
                uint32_t offset = (oy * ow + ox) * s->output_channels + oc;
                uint32_t actual = (output[offset / 4u] >>
                    ((offset % 4u) * 8u)) & 255u;
                for (ky = 0; ky < s->kernel; ++ky)
                    for (kx = 0; kx < s->kernel; ++kx)
                        for (ci = 0; ci < s->channels; ++ci) {
                            int32_t x = (int32_t)(ox * s->stride + kx) - s->padding;
                            int32_t y = (int32_t)(oy * s->stride + ky) - s->padding;
                            uint32_t scalar_id = (ky * s->kernel + kx) *
                                s->channels + ci;
                            int32_t a = x < 0 || x >= s->width ||
                                y < 0 || y >= s->height ? 0 : signed_byte(
                                    small_input_byte(
                                        ((uint32_t)y * s->width + (uint32_t)x) *
                                            4u + ci, seed));
                            int32_t w = signed_byte(small_weight_byte(
                                s, oc, scalar_id));
                            sum += a * w;
                        }
                if (actual != requant(sum, oc % 4u + 2u)) {
                    if (first == 0xffffffffu) first = offset;
                    ++mismatches;
                }
            }
    if (bytes % 4u)
        for (lane = bytes % 4u; lane < 4u; ++lane)
            if (((output[bytes / 4u] >> (lane * 8u)) & 255u) !=
                ((0xaabbccddu >> (lane * 8u)) & 255u)) ++mismatches;
    if (mismatches || counter(0) != s->width * s->height * 4u ||
        counter(1) != lines * 128u ||
        counter(2) != ow * oh * s->kernel * s->kernel ||
        counter(3) != ow * oh || counter(12) != bytes ||
        counter(13) == 0u) goto fail;
    puts("CONV_COMPUTE_CASE_PASS id="); dec(seed);
    puts(" output="); dec(counter(12));
    puts(" taps="); dec(counter(2));
    puts(" compute_cycles="); dec(counter(13));
    puts(" weight_cycles="); dec(counter(6)); putc('\n');
    return 0;
fail:
    puts("CONV_COMPUTE_CASE_FAIL id="); dec(seed);
    puts(" status="); hex(status);
    puts(" mismatches="); dec(mismatches);
    puts(" first="); hex(first); putc('\n');
    return 1;
}

static int run_full_first_layer_compute(void)
{
    volatile uint32_t *input = (volatile uint32_t *)(DDR_CPU + INPUT_OFF);
    volatile uint32_t *weight = (volatile uint32_t *)(DDR_CPU + WEIGHT_OFF);
    volatile uint32_t *output = (volatile uint32_t *)(DDR_CPU + OUTPUT_OFF);
    uint32_t i, lane, oc, scalar, status, crc = 0xffffffffu;

    for (i = 0; i < 102400u; ++i) {
        uint32_t word = 0;
        for (lane = 0; lane < 4u; ++lane)
            word |= compute_input_byte(i * 4u + lane) << (lane * 8u);
        input[i] = word;
        output[i] = 0xa5a5a5a5u;
    }
    for (i = 0; i < 864u; ++i) weight[i] = 0;
    for (oc = 0; oc < 16u; ++oc)
        for (scalar = 0; scalar < 108u; ++scalar) {
            uint32_t index = (scalar / 4u) * 32u + oc;
            uint32_t shift = (scalar % 4u) * 8u;
            uint32_t word = weight[index];
            weight[index] = (word & ~(255u << shift)) |
                            (compute_weight_byte(oc, scalar) << shift);
        }
    __asm__ volatile ("fence iorw, iorw" ::: "memory");

    REG(0x48) = 8u;
    REG(0x4c) = (320u << 16) | 320u;
    REG(0x50) = (2u << 24) | (2u << 20) | (6u << 16) | 3u;
    REG(0x54) = (16u << 16);
    REG(0x58) = DDR_BUS + INPUT_OFF;
    REG(0x5c) = DDR_BUS + WEIGHT_OFF;
    REG(0x60) = DDR_BUS + OUTPUT_OFF;
    REG(0x64) = 27u;
    REG(0x68) = 0x4d434f4eu;
    REG(0x6c) = 0x40u;
    REG(0x70) = 0x40u;
    for (oc = 0; oc < 16u; ++oc) {
        REG(0x78) = 0x20u + oc;
        REG(0x7c) = oc * 13u - 50u;
        REG(0x78) = 0x40u + oc;
        REG(0x7c) = oc % 4u + 2u;
    }
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    REG(0x48) = 1u;
    status = wait_status(2u, 4u);
    if (status & 4u || status == 0xffffffffu) goto fail;
    REG(0x48) = 2u;
    if (!(REG(0x48) & 128u)) { status = REG(0x48); goto fail; }
    REG(0x48) = 8u;
    REG(0x48) = 16u;
    status = wait_status(256u, 512u);
    if (status & 512u || status == 0xffffffffu) goto fail;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    for (i = 0; i < 102400u; ++i) {
        uint32_t word = output[i];
        for (lane = 0; lane < 4u; ++lane) {
            uint32_t bit;
            crc ^= (word >> (lane * 8u)) & 255u;
            for (bit = 0; bit < 8u; ++bit)
                crc = (crc >> 1) ^ ((crc & 1u) ? 0xedb88320u : 0u);
        }
    }
    crc ^= 0xffffffffu;
    if (crc != 0xeb240272u || counter(0) != 409600u ||
        counter(1) != 3456u || counter(2) != 921600u ||
        counter(3) != 25600u || counter(12) != 409600u ||
        counter(13) == 0u) goto fail;
    puts("MAC_CONV_FULL_FIRST_LAYER_PASS output=409600 input=409600 weight=3456 taps=921600 reuse=25600 crc=");
    hex(crc); puts(" compute_cycles="); dec(counter(13));
    puts(" weight_cycles="); dec(counter(6));
    puts(" stalls="); dec(counter(4)); putc('\n');
    return 0;
fail:
    puts("MAC_CONV_FULL_FIRST_LAYER_FAIL status="); hex(status);
    puts(" crc="); hex(crc);
    puts(" output="); dec(counter(12));
    puts(" taps="); dec(counter(2)); putc('\n');
    return 1;
}

int main(void)
{
    uint32_t i;
    if (REG(0x00) != 0x4d41434bu || REG(0x40) != 0x4d434f4eu ||
        (REG(0x44) != 0x00020000u && REG(0x44) != 0x00030000u)) {
        puts("MAC_CONV_MMIO_FAIL\n");
        return 1;
    }
    for (i = 0; i < sizeof(shapes) / sizeof(shapes[0]); ++i)
        if (run_case(&shapes[i], i)) return 1;
    puts("MAC_CONV_STAGE2_BOARD_PASS\n");
    if (REG(0x44) == 0x00030000u) {
        static const struct shape small_cases[] = {
            {2, 2, 4, 5, 1, 1, 0, 0},
            {3, 3, 4, 8, 3, 1, 1, 0},
            {1, 1, 4, 5, 1, 1, 0, 0},
            {1, 1, 4, 16, 1, 1, 0, 0}
        };
        if (run_compute_case()) return 1;
        for (i = 0; i < 4u; ++i)
            if (run_compute_small(&small_cases[i], i + 10u)) return 1;
        if (run_full_first_layer_compute()) return 1;
        puts("MAC_CONV_COMPUTE_SUITE_BOARD_PASS\n");
    }
    return 0;
}
