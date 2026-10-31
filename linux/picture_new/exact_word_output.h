#ifndef XQ_EXACT_WORD_OUTPUT_H
#define XQ_EXACT_WORD_OUTPUT_H
#include <stddef.h>
#include <stdint.h>

/* Compact S16 HWC -> NCHW in normal RAM. Each 2x2 transpose replaces four
 * halfword loads/stores with two word loads/stores; all 16 bits are retained.
 * Keep small pixel/channel windows, with two destination planes active at a
 * time. Ineligible calls leave the destination completely untouched. */
typedef uint32_t xqewo_word __attribute__((__may_alias__));
#ifndef XQEWO_NOTE
#define XQEWO_NOTE(pixels,channels) ((void)0)
#endif
static int xqewo_unpack(int16_t *dst,const void *src,unsigned channels,unsigned height,unsigned width)
{
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    if(!dst || !src || !channels || channels>256 || (channels&1u) ||
       !height || height>640 || !width || width>640 ||
       (((uintptr_t)dst|(uintptr_t)src)&3u))return 0;
    size_t pixels=(size_t)height*width;
    if(pixels&1u)return 0;
    size_t bytes=pixels*channels*2;
    uintptr_t to=(uintptr_t)dst,from=(uintptr_t)src;
    if(to<=from?from-to<bytes:to-from<bytes)return 0;
    const xqewo_word *s=src;xqewo_word *d=(void *)dst;
    size_t row=channels/2,plane=pixels/2;
    XQEWO_NOTE(pixels,channels);
    for(size_t pb=0;pb<pixels;pb+=8){
        size_t end=pixels-pb<8?pixels:pb+8;
        for(unsigned cb=0;cb<channels;cb+=8){
            unsigned ce=channels-cb<8?channels:cb+8;
            for(unsigned c=cb;c<ce;c+=2){
                const xqewo_word *r=s+pb*row+c/2;
                xqewo_word *a=d+(size_t)c*plane+pb/2,*b=a+plane;
                for(size_t p=pb;p<end;p+=2,r+=2*row){
                    uint32_t x=r[0],y=r[row];
                    *a++=(x&0xffffu)|(y<<16);
                    *b++=(x>>16)|(y&0xffff0000u);
                }
            }
        }
    }
    return 1;
#else
    (void)dst;(void)src;(void)channels;(void)height;(void)width;return 0;
#endif
}
#endif
