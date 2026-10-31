#ifndef XQIH_RGB8_DIRECT_H
#define XQIH_RGB8_DIRECT_H
#include <stdint.h>

#define XQIH_RGB8_INPUT_BYTES (3u*640u*640u)

/* This is the frozen normalize_rgb expression followed by the unchanged
 * quantizer. No reciprocal multiplication or approximate integer formula. */
static int xqih_rgb8_palette(int exponent,int8_t palette[256])
{
    float colors[256];
    for(unsigned color=0;color<256;color++)colors[color]=(float)color/255.f;
    return xqi_quantize(colors,256,exponent,palette);
}

static int xqih_rgb8_input(const xqm_transport *io,const uint8_t *source,size_t bytes,
                          int exponent,void **destination)
{
#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error XQ_HWC_RGB8_DIRECT_requires_the_frozen_little_endian_host_or_RV32_ABI
#endif
    *destination=NULL;
    if(!source || bytes!=XQIH_RGB8_INPUT_BYTES)return 0;
    uint32_t *words=malloc(640u*640u*sizeof(*words));
    if(!words)return -1;
    int8_t palette[256],colors[3][32];
    if(!xqih_rgb8_palette(exponent,palette))goto fail;
    for(unsigned y=0;y<640;y++) {
        /* Retain three row-boundary cancellation opportunities per y.
         * Failure never exposes any partly packed bytes to the graph. */
        for(unsigned c=0;c<3;c++)if(stopped(io))goto fail;
        size_t row=(size_t)y*640;
        /* The 409600-byte planes share the frozen CPU's cache index. Read
         * one contiguous 32-byte piece of each plane before packing, rather
         * than alternating three same-set lines for every individual pixel. */
        for(unsigned first=0;first<640;first+=32) {
            for(unsigned c=0;c<3;c++) {
                const uint8_t *input=source+(size_t)c*640u*640u+row+first;
                for(unsigned x=0;x<32;x++)colors[c][x]=palette[input[x]];
            }
            for(unsigned x=0;x<32;x++)
                words[row+first+x]=(uint32_t)(uint8_t)colors[0][x] |
                    ((uint32_t)(uint8_t)colors[1][x]<<8) | ((uint32_t)(uint8_t)colors[2][x]<<16);
        }
    }
    *destination=words;return 1;
fail:
    free(words);return 0;
}
#endif
