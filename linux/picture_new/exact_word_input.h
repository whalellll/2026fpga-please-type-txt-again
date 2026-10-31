#ifndef XQ_EXACT_WORD_INPUT_H
#define XQ_EXACT_WORD_INPUT_H
#include <stddef.h>
#include <stdint.h>

/* Normal RAM only: four contiguous NCHW pixels from four channels become
 * four HWC words. The caller retains padding/halo and cancellation policy.
 * Ineligible shapes/addresses leave the destination entirely untouched. */
typedef uint32_t xqew_word __attribute__((__may_alias__));
#ifndef XQEW_NOTE
#define XQEW_NOTE(pixels,channels) ((void)0)
#endif
static int xqew_pack(uint8_t *dst,const int8_t *src,unsigned channels,unsigned height,unsigned width)
{
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    size_t pixels=(size_t)height*width;
    if(!dst || !src || !channels || channels>512 || !height || height>640 || !width || width>640 ||
       (channels&3u) || (pixels&3u) ||
       (((uintptr_t)dst|(uintptr_t)src)&3u))return 0;
    size_t bytes=pixels*channels;uintptr_t to_addr=(uintptr_t)dst,from_addr=(uintptr_t)src;
    if(to_addr<=from_addr?from_addr-to_addr<bytes:to_addr-from_addr<bytes)return 0;
    const xqew_word *s=(const void *)src;xqew_word *d=(void *)dst;
    size_t plane=pixels/4,groups=channels/4;
    XQEW_NOTE(pixels,channels);
    for(size_t p=0;p<pixels;p+=4)for(unsigned c=0;c<channels;c+=4){
        size_t at=(size_t)c*plane+p/4,to=p*groups+c/4;
        uint32_t a=s[at],b=s[at+plane],cc=s[at+2*plane],e=s[at+3*plane];
        d[to]=(a&255u)|((b&255u)<<8)|((cc&255u)<<16)|(e<<24);
        d[to+groups]=((a>>8)&255u)|(b&0xff00u)|((cc&0xff00u)<<8)|((e&0xff00u)<<16);
        d[to+2*groups]=((a>>16)&255u)|((b>>8)&0xff00u)|(cc&0xff0000u)|((e&0xff0000u)<<8);
        d[to+3*groups]=(a>>24)|((b>>16)&0xff00u)|((cc>>8)&0xff0000u)|(e&0xff000000u);
    }
    return 1;
#else
    (void)dst;(void)src;(void)channels;(void)height;(void)width;return 0;
#endif
}
#endif
