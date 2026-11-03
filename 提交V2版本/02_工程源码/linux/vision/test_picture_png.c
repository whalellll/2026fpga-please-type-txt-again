#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "png_rgb565.h"
static int emit(void *file, const uint8_t *data, uint32_t count)
{ return fwrite(data, 1, count, file) == count ? 0 : -1; }
int main(int argc, char **argv)
{
    uint16_t *ram = malloc(PNG565_WIDTH * PNG565_HEIGHT * 2u);
    uint32_t y, x, crc;
    FILE *file;
    assert(argc == 2 && ram);
    for (y = 0; y < PNG565_HEIGHT; ++y)
        for (x = 0; x < PNG565_WIDTH; ++x)
            ram[y * PNG565_WIDTH + x] = (uint16_t)(
                ((x * 31u / 1279u) << 11) | ((y * 63u / 719u) << 5) |
                ((x + y) * 31u / 1998u));
    file = fopen(argv[1], "wb");
    assert(file && !png565_encode((const uint8_t *)ram, emit, file, NULL, &crc));
    assert(!fclose(file));
    free(ram);
    printf("XQ_PICTURE_PNG_SYNTHETIC crc32=%08x\n", crc);
    return 0;
}
