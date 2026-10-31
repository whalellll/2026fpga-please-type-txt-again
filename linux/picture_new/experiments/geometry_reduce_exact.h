#ifndef XQ_GEOMETRY_REDUCE_EXACT_H
#define XQ_GEOMETRY_REDUCE_EXACT_H
#include <stdint.h>
#include <string.h>

/* Unselected offline experiment. For nearby nonnegative normal operands the exact
 * difference fits in 53 bits. Preserve all other cases with native arithmetic,
 * including signed zeros, subnormals and nonfinite values. No reassociation of
 * the original ((a-b)-c)+d reduction is permitted. */
static inline double xqgeom_reduce_sub(double a,double b)
{
    uint64_t x,y;memcpy(&x,&a,8);memcpy(&y,&b,8);
    unsigned ex=(unsigned)(x>>52),ey=(unsigned)(y>>52);
    if(ex>=2047 || ey>=2047)return a-b;
    if(!y)return a;
    if(!x){y|=UINT64_C(0x8000000000000000);memcpy(&a,&y,8);return a;}
    uint64_t sign=0;
    if(x<y){uint64_t t=x;x=y;y=t;unsigned e=ex;ex=ey;ey=e;sign=UINT64_C(0x8000000000000000);}
    if(ey<=53 || ex-ey>1)return a-b;
    uint64_t mx=(x&UINT64_C(0xfffffffffffff))|UINT64_C(0x10000000000000);
    uint64_t my=(y&UINT64_C(0xfffffffffffff))|UINT64_C(0x10000000000000);
    if(ex!=ey && mx>my)return a-b;
    uint64_t difference=(mx<<(ex-ey))-my;
    if(!difference)return 0.;
    unsigned shift=(unsigned)__builtin_clzll(difference)-11u;
    x=sign|((uint64_t)(ey-shift)<<52)|((difference<<shift)&UINT64_C(0xfffffffffffff));
    memcpy(&a,&x,8);return a;
}

static inline double xqgeom_reduce_add(double a,double b)
{
    uint64_t x,y;memcpy(&x,&a,8);memcpy(&y,&b,8);
    if((x>>63) && !(y>>63) && ((x>>52)&2047u)<2047u && ((y>>52)&2047u)<2047u)
        return xqgeom_reduce_sub(b,-a);
    return a+b;
}

static inline double xqgeom_reduce4(double a,double b,double c,double d)
{
    double first=xqgeom_reduce_sub(a,b);
    double second=xqgeom_reduce_sub(first,c);
    return xqgeom_reduce_add(second,d);
}
#endif
