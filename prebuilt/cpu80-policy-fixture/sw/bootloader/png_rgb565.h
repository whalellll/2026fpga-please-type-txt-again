#ifndef PNG_RGB565_H
#define PNG_RGB565_H
#include <stdint.h>
#define PNG565_WIDTH 1280u
#define PNG565_HEIGHT 720u
#define PNG565_ROW_BYTES (PNG565_WIDTH*3u+1u)
#define PNG565_BYTES (8u+25u+12u+2u+PNG565_HEIGHT*(5u+PNG565_ROW_BYTES)+4u+12u)
typedef int (*png565_write_fn)(void *user,const uint8_t *bytes,uint32_t count);
typedef int (*png565_poll_fn)(void *user,uint32_t rows_done);
/* Encodes the exact top-to-bottom RGB565LE snapshot. No drawing, filtering,
 * scaling or cropping. RGB bits expand identically to the HDMI DMA.
 * IDAT is one zlib stream with one stored DEFLATE block per scanline.
 * file_crc may be NULL when the sink already checks the complete file stream;
 * PNG chunk CRCs and zlib Adler32 are always calculated. */
int png565_encode(const uint8_t *pixels,png565_write_fn write,void *user,
                  png565_poll_fn poll,uint32_t *file_crc);
#endif
