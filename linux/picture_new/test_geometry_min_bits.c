/* Compare the selected min with the unchanged linked libm, including payloads. */
#include "geometry_min_bits.h"
#include <stdio.h>
#include <stdlib.h>
static uint64_t cases;
static double value(uint64_t u){double d;memcpy(&d,&u,8);return d;}
static uint64_t bits(double d){uint64_t u;memcpy(&u,&d,8);return u;}
static double (*volatile original)(double,double)=fmin;
static void one(uint64_t x,uint64_t y)
{
    double a=value(x),b=value(y),expected=original(a,b),actual=xqgeom_min(a,b);
    ++cases;
    if(bits(expected)!=bits(actual)){
        fprintf(stderr,"MIN_BITS_MISMATCH a=%llx b=%llx old=%llx new=%llx\n",
            (unsigned long long)x,(unsigned long long)y,(unsigned long long)bits(expected),(unsigned long long)bits(actual));exit(3);
    }
}
int main(void)
{
    const uint64_t edge[]={0,UINT64_C(0x8000000000000000),1,UINT64_C(0x8000000000000001),
        UINT64_C(0x000fffffffffffff),UINT64_C(0x0010000000000000),UINT64_C(0x3ff0000000000000),
        UINT64_C(0x3ff0000000000001),UINT64_C(0xbff0000000000000),UINT64_C(0x7fefffffffffffff),
        UINT64_C(0x7ff0000000000000),UINT64_C(0xfff0000000000000),UINT64_C(0x7ff8000000000042),
        UINT64_C(0xfff8000000000086),UINT64_C(0x7ff0000000000001)};
    for(unsigned i=0;i<sizeof(edge)/sizeof(*edge);i++)for(unsigned j=0;j<sizeof(edge)/sizeof(*edge);j++)one(edge[i],edge[j]);
    uint64_t random=UINT64_C(0x8325aef74d39b641);
    for(unsigned i=0;i<200000;i++){
        random^=random<<13;random^=random>>7;random^=random<<17;
        uint64_t x=random,y=(random<<1)|(random>>63);
        one(x,y);one(x,x);one(x,0);one(0,x);one(x&UINT64_C(0x7fffffffffffffff),y&UINT64_C(0x7fffffffffffffff));
    }
    printf("GEOMETRY_MIN_BITS_NUMERIC_PASS cases=%llu flag=%d\n",(unsigned long long)cases,XQ_GEOMETRY_MIN_BITS);
    return 0;
}
