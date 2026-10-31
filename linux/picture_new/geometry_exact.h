#ifndef XQ_GEOMETRY_EXACT_H
#define XQ_GEOMETRY_EXACT_H
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* The geometry caller supplies masks containing exactly +0 or 1. All
 * original binary64 prefixes are exact integers below 2^21. Word sums and
 * their final conversion therefore retain the original output bits. */
static int xqgeom_mask_sum(const double *in,unsigned hy,unsigned hx,double *out,
                           unsigned width,unsigned height)
{
    unsigned pw=width+2*hx,ph=height+2*hy,stride=pw+1;
    uint32_t *integral;
    if(!width || !height || width>1280 || height>720 || hx>15 || hy>15)return 0;
    integral=calloc((size_t)(ph+1)*stride,sizeof(*integral));
    if(!integral)return 0;
    for(unsigned x=0;x<pw;x++) {
        int ix=(int)x-(int)hx;uint32_t v=0;
        if(ix<0)ix=0;
        if(ix>=(int)width)ix=(int)width-1;
        for(unsigned y=0;y<ph;y++) {
            int iy=(int)y-(int)hy;uint64_t bits;
            if(iy<0)iy=0;
            if(iy>=(int)height)iy=(int)height-1;
            memcpy(&bits,in+(size_t)iy*width+(unsigned)ix,sizeof(bits));
            v+=(bits!=0);integral[(size_t)(y+1)*stride+x+1]=v;
        }
    }
    for(unsigned y=0;y<=ph;y++) {
        uint32_t v=0;
        for(unsigned x=0;x<=pw;x++){v+=integral[(size_t)y*stride+x];integral[(size_t)y*stride+x]=v;}
    }
    for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++) {
        unsigned b=y+2*hy+1,r=x+2*hx+1;
        uint32_t count=integral[(size_t)b*stride+r]-integral[(size_t)y*stride+r]-
            integral[(size_t)b*stride+x]+integral[(size_t)y*stride+x];
        out[(size_t)y*width+x]=count;
    }
    free(integral);return 1;
}

/* Exact round-to-nearest/ties-even binary64 division by a small integer.
 * The RV32 path uses three ordinary 32-bit divisions. General inputs retain
 * native C arithmetic. Geometry never observes floating exception flags. */
static inline __attribute__((always_inline)) double xqgeom_div(double a,unsigned d)
{
    uint64_t bits;memcpy(&bits,&a,8);
    unsigned e=(unsigned)(bits>>52),k=0,t=d-1;
    if(e<=10 || e>=2047 || !d || d>1024)return a/(double)d;
    while(t){++k;t>>=1;}
    uint64_t m=(bits&UINT64_C(0xfffffffffffff))|UINT64_C(0x10000000000000);
    if(m>=((uint64_t)d<<(53-k)))--k;
    uint64_t n=m<<k;
    uint32_t upper=(uint32_t)(n>>32),low=(uint32_t)n;
    uint32_t qhi=upper/d,rem=upper-qhi*d;
    uint32_t digit=(rem<<16)|(low>>16),qmid=digit/d;
    rem=digit-qmid*d;digit=(rem<<16)|(low&65535u);
    uint32_t qlo=digit/d;rem=digit-qlo*d;
    uint64_t q=((uint64_t)qhi<<32)|((uint64_t)qmid<<16)|qlo;
    if(2*rem>d || (2*rem==d && (q&1)))++q;
    e-=k;
    if(q==UINT64_C(0x20000000000000)){q>>=1;++e;}
    bits=((uint64_t)e<<52)|(q&UINT64_C(0xfffffffffffff));
    double out;memcpy(&out,&bits,8);return out;
}

/* Exact addition for nonnegative normal prefixes. General values retain
 * native C arithmetic. Three guard bits include every discarded sticky bit. */
static inline double xqgeom_add(double a,double b)
{
    uint64_t x,y;memcpy(&x,&a,8);memcpy(&y,&b,8);
    unsigned ex=(unsigned)(x>>52),ey=(unsigned)(y>>52);
    if(ex>=2046 || ey>=2046 || (!ex && x) || (!ey && y))return a+b;
    if(!x)return b;
    if(!y)return a;
    if(x<y){uint64_t t=x;x=y;y=t;unsigned e=ex;ex=ey;ey=e;}
    unsigned distance=ex-ey;
    uint64_t ma=((x&UINT64_C(0xfffffffffffff))|UINT64_C(0x10000000000000))<<3;
    uint64_t mb=((y&UINT64_C(0xfffffffffffff))|UINT64_C(0x10000000000000))<<3;
    if(distance>=64)mb=1;
    else if(distance)mb=(mb>>distance)|((mb<<(64-distance))!=0);
    uint64_t sum=ma+mb;
    if(sum&UINT64_C(0x100000000000000)){sum=(sum>>1)|(sum&1);++ex;}
    uint64_t q=sum>>3;unsigned remainder=(unsigned)sum&7;
    if(remainder>4 || (remainder==4 && (q&1)))++q;
    if(q==UINT64_C(0x20000000000000)){q>>=1;++ex;}
    x=((uint64_t)ex<<52)|(q&UINT64_C(0xfffffffffffff));
    double out;memcpy(&out,&x,8);return out;
}
#endif
