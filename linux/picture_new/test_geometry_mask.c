#include <stddef.h>
#include "geometry_mask.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

static unsigned tests,values;
static void check(unsigned w,unsigned h,unsigned hy,unsigned hx,unsigned mode)
{
    uint8_t *in=malloc((size_t)w*h);
    uint16_t *out=malloc((size_t)w*h*sizeof(*out));
    assert(in && out);
    for(size_t i=0;i<(size_t)w*h;i++)
        in[i]=mode==0?0:mode==1?1:mode==2?(i%w==0 || i%w==w-1 || i/w==0 || i/w==h-1):
              mode==3?(i%w==w/2 && i/w==h/2):((i*1664525u+1013904223u)>>16)&1;
    assert(xqgeom_mask8_sum(in,hy,hx,out,w,h));
    for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++) {
        unsigned expected=0;
        /* Independent direct neighborhood reference; no integral or sliding. */
        for(int dy=-(int)hy;dy<=(int)hy;dy++)for(int dx=-(int)hx;dx<=(int)hx;dx++) {
            int iy=(int)y+dy,ix=(int)x+dx;
            if(iy<0)iy=0;
            if(iy>=(int)h)iy=(int)h-1;
            if(ix<0)ix=0;
            if(ix>=(int)w)ix=(int)w-1;
            expected+=in[(size_t)iy*w+(unsigned)ix];
        }
        assert(out[(size_t)y*w+x]==expected);++values;
    }
    ++tests;free(in);free(out);
}
int main(void)
{
    const unsigned shapes[][2]={{1,1},{1,17},{31,1},{2,3},{17,19},{37,29}};
    for(unsigned shape=0;shape<6;shape++)for(unsigned hy=0;hy<=15;hy+=3)
        for(unsigned hx=0;hx<=15;hx+=3)for(unsigned mode=0;mode<5;mode++)
            check(shapes[shape][0],shapes[shape][1],hy,hx,mode);
    /* The exact product windows and maximum dimensions get full edge coverage. */
    check(1280,720,1,13,4);check(1280,720,13,1,4);
    check(1280,1,15,15,1);check(1,720,15,15,1);
    uint8_t input[1]={1};uint16_t output=1234;
    assert(!xqgeom_mask8_sum(NULL,0,0,&output,1,1));
    assert(!xqgeom_mask8_sum(input,0,0,NULL,1,1));
    assert(!xqgeom_mask8_sum(input,0,0,&output,0,1));
    assert(!xqgeom_mask8_sum(input,0,0,&output,1,0));
    assert(!xqgeom_mask8_sum(input,0,0,&output,1281,1));
    assert(!xqgeom_mask8_sum(input,0,0,&output,1,721));
    assert(!xqgeom_mask8_sum(input,16,0,&output,1,1));
    assert(!xqgeom_mask8_sum(input,0,16,&output,1,1));
    assert(output==1234);
    printf("GEOMETRY_MASK8_DIRECT_REFERENCE_PASS cases=%u values=%u scratch_bytes=2560\n",tests,values);
    return 0;
}
