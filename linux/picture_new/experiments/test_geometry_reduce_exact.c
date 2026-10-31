#include "geometry_reduce_exact.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>

static uint32_t random_state=0x49378912u;
static uint32_t next(void)
{random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;return random_state;}
static double number(uint64_t bits)
{double result;memcpy(&result,&bits,8);return result;}
static void equal(double a,double b)
{assert(!memcmp(&a,&b,8));}

int main(void)
{
    unsigned cases=0;
    const uint64_t edge[]={0,UINT64_C(0x8000000000000000),1,UINT64_C(0x8000000000000001),
        UINT64_C(0xfffffffffffff),UINT64_C(0x10000000000000),UINT64_C(0x35fffffffffffff),
        UINT64_C(0x360000000000000),UINT64_C(0x3ff0000000000000),UINT64_C(0x3fffffffffffffff),
        UINT64_C(0x4000000000000000),UINT64_C(0x4000000000000001),UINT64_C(0x7fefffffffffffff),
        UINT64_C(0xffefffffffffffff)};
    for(unsigned i=0;i<sizeof(edge)/sizeof(*edge);i++)for(unsigned j=0;j<sizeof(edge)/sizeof(*edge);j++){
        double a=number(edge[i]),b=number(edge[j]);
        equal(a-b,xqgeom_reduce_sub(a,b));equal(a+b,xqgeom_reduce_add(a,b));cases+=2;
    }
    for(unsigned i=0;i<800000;i++){
        unsigned e=1+next()%2046;
        uint64_t ma=((uint64_t)(next()&0xfffffu)<<32)|next();
        uint64_t mb=((uint64_t)(next()&0xfffffu)<<32)|next();
        double a=number(((uint64_t)e<<52)|ma);
        double b=number(((uint64_t)(e-(e>1 && (i&1)))<<52)|mb);
        equal(a-b,xqgeom_reduce_sub(a,b));equal(b-a,xqgeom_reduce_sub(b,a));
        equal(-a+b,xqgeom_reduce_add(-a,b));equal(a-b,xqgeom_reduce_add(-b,a));cases+=4;
        /* Actual reduction order, cancellation, fallback and sign branches. */
        double c=number(((uint64_t)(1+next()%2046)<<52)|ma),d=number(((uint64_t)e<<52)|mb);
        double reference=((a-b)-c)+d,actual=xqgeom_reduce4(a,b,c,d);
        equal(reference,actual);++cases;
    }
    printf("GEOMETRY_REDUCE_EXACT cases=%u PASS_NOT_BOARD\n",cases);return 0;
}
