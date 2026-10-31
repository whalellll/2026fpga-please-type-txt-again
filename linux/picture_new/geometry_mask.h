#ifndef XQ_GEOMETRY_MASK_H
#define XQ_GEOMETRY_MASK_H
#include <stddef.h>
#include <stdint.h>

/* Caller supplies exactly 0/1 bytes. Edge replication is the frozen box_sum
 * rule. Column counts are <=31, window counts <=961; all arithmetic is exact.
 * Scratch is 2560 stack bytes, independent of image height, with no allocation. */
static int xqgeom_mask8_sum(const uint8_t *in,unsigned hy,unsigned hx,uint16_t *out,
                            unsigned width,unsigned height)
{
    uint16_t columns[1280];
    if(!in || !out || !width || !height || width>1280 || height>720 || hx>15 || hy>15)return 0;
    for(unsigned x=0;x<width;x++) {
        unsigned sum=0;
        for(int dy=-(int)hy;dy<=(int)hy;dy++) {
            unsigned y=dy<0?0:(unsigned)dy>=height?height-1:(unsigned)dy;
            sum+=in[(size_t)y*width+x];
        }
        columns[x]=(uint16_t)sum;
    }
    for(unsigned y=0;y<height;y++) {
        unsigned sum=0;
        for(int dx=-(int)hx;dx<=(int)hx;dx++) {
            unsigned x=dx<0?0:(unsigned)dx>=width?width-1:(unsigned)dx;
            sum+=columns[x];
        }
        out[(size_t)y*width]=(uint16_t)sum;
        for(unsigned x=1;x<width;x++) {
            unsigned leave=x>hx?x-hx-1:0,enter=x+hx<width?x+hx:width-1;
            sum=sum-columns[leave]+columns[enter];
            out[(size_t)y*width+x]=(uint16_t)sum;
        }
        if(y+1<height) {
            unsigned leave=y>hy?y-hy:0,enter=y+hy+1<height?y+hy+1:height-1;
            for(unsigned x=0;x<width;x++)
                columns[x]=(uint16_t)(columns[x]-in[(size_t)leave*width+x]+in[(size_t)enter*width+x]);
        }
    }
    return 1;
}
#endif
