/* Independent full 320x320x3 / 6x6 stride-2 INT32+S8 board oracle. */
#include <stdint.h>
#include <stdio.h>

static int32_t s8(uint32_t value)
{
    return value < 128 ? (int32_t)value : (int32_t)value - 256;
}

static uint32_t source_byte(uint32_t index)
{
    return (index * 29u + (index / 7u) * 13u + 34u) & 255u;
}

static uint32_t weight_byte(uint32_t oc, uint32_t scalar)
{
    uint32_t tap = scalar / 3u;
    uint32_t channel = scalar % 3u;
    uint32_t logical = ((oc * 3u + channel) * 6u + tap / 6u) * 6u + tap % 6u;
    return (uint8_t)((int32_t)((logical * 11u +
        (logical / 108u) * 3u) & 15u) - 8);
}

static uint8_t requant(int32_t value, uint32_t shift)
{
    int32_t magnitude = value < 0 ? -value : value;
    int32_t rounded = (magnitude + (1 << (shift - 1u))) >> shift;
    if (value < 0) rounded = -rounded;
    if (rounded > 127) return 127;
    if (rounded < -128) return 128;
    return (uint8_t)rounded;
}

int main(void)
{
    uint32_t crc = 0xffffffffu, ox, oy, oc, ky, kx, ci;
    uint8_t first[16] = {0}, last[16] = {0};

    for (oy = 0; oy < 160u; ++oy)
        for (ox = 0; ox < 160u; ++ox)
            for (oc = 0; oc < 16u; ++oc) {
                int32_t sum = (int32_t)oc * 13 - 50;
                uint8_t value;
                uint32_t i, bit;

                for (ky = 0; ky < 6u; ++ky)
                    for (kx = 0; kx < 6u; ++kx)
                        for (ci = 0; ci < 3u; ++ci) {
                            int32_t x = (int32_t)(ox * 2u + kx) - 2;
                            int32_t y = (int32_t)(oy * 2u + ky) - 2;
                            uint32_t scalar = (ky * 6u + kx) * 3u + ci;
                            int32_t a = x < 0 || x >= 320 || y < 0 || y >= 320 ?
                                0 : s8(source_byte(((uint32_t)y * 320u +
                                    (uint32_t)x) * 4u + ci));
                            sum += a * s8(weight_byte(oc, scalar));
                        }
                value = requant(sum, oc % 4u + 2u);
                i = (oy * 160u + ox) * 16u + oc;
                if (i < 16u) first[i] = value;
                if (i >= 409600u - 16u) last[i - (409600u - 16u)] = value;
                crc ^= value;
                for (bit = 0; bit < 8u; ++bit)
                    crc = (crc >> 1) ^ ((crc & 1u) ? 0xedb88320u : 0u);
            }
    crc ^= 0xffffffffu;
    if (crc != 0xeb240272u) {
        fprintf(stderr, "full-layer reference CRC changed: %08x\n", crc);
        return 1;
    }
    printf("YOLO_FIRST_LAYER_BOARD_ORACLE_PASS output_bytes=409600 crc32=%08x first=", crc);
    for (oc = 0; oc < 16u; ++oc) printf("%02x", first[oc]);
    printf(" last=");
    for (oc = 0; oc < 16u; ++oc) printf("%02x", last[oc]);
    putchar('\n');
    return 0;
}
