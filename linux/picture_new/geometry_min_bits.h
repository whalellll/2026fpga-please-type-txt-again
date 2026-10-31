#ifndef XQ_GEOMETRY_MIN_BITS_H
#define XQ_GEOMETRY_MIN_BITS_H
#include <stdint.h>
#include <string.h>
#include <math.h>
#ifndef XQ_GEOMETRY_MIN_BITS
#define XQ_GEOMETRY_MIN_BITS 0
#endif
#if XQ_GEOMETRY_MIN_BITS != 0 && XQ_GEOMETRY_MIN_BITS != 1
#error XQ_GEOMETRY_MIN_BITS_must_be_zero_or_one
#endif
static inline double xqgeom_min(double a,double b)
{
#if XQ_GEOMETRY_MIN_BITS
    uint64_t x,y;memcpy(&x,&a,8);memcpy(&y,&b,8);
    /* For two nonnegative finite binary64 values storage order is numeric
     * order. Their only zero sign is +0, and equal values have equal bits.
     * Negatives (including -0), infinities and NaNs keep the original fmin. */
    if(x<UINT64_C(0x7ff0000000000000) && y<UINT64_C(0x7ff0000000000000))
        return x<y?a:b;
#endif
    return fmin(a,b);
}
#endif
