#include "geometry_exact.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
static uint64_t random_state=UINT64_C(0xabf01a39395911e1),divisions,additions;
static uint64_t random_bits(void)
{random_state^=random_state<<13;random_state^=random_state>>7;random_state^=random_state<<17;return random_state;}
static int same(double a,double b)
{uint64_t x,y;memcpy(&x,&a,8);memcpy(&y,&b,8);return x==y || (isnan(a)&&isnan(b));}
static void divide(uint64_t bits,unsigned d)
{double a;memcpy(&a,&bits,8);volatile double divisor=d;assert(same(a/divisor,xqgeom_div(a,d)));++divisions;}
static void add(uint64_t x,uint64_t y)
{double a,b;memcpy(&a,&x,8);memcpy(&b,&y,8);volatile double operand=b;assert(same(a+operand,xqgeom_add(a,b)));++additions;}
static void mask(unsigned w,unsigned h,unsigned hx,unsigned hy,unsigned pattern)
{
    size_t n=(size_t)w*h;double *in=malloc(n*8),*out=malloc(n*8);assert(in && out);
    for(size_t i=0;i<n;i++)in[i]=pattern<2?pattern:(random_bits()&1);
    assert(xqgeom_mask_sum(in,hy,hx,out,w,h));
    for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++) {
        unsigned expected=0;
        if(pattern<2)expected=pattern*(2*hx+1)*(2*hy+1);
        else for(int dy=-(int)hy;dy<=(int)hy;dy++)for(int dx=-(int)hx;dx<=(int)hx;dx++){
            int xx=(int)x+dx,yy=(int)y+dy;
            if(xx<0)xx=0;
            if(yy<0)yy=0;
            if(xx>=(int)w)xx=(int)w-1;
            if(yy>=(int)h)yy=(int)h-1;
            expected+=(unsigned)in[(size_t)yy*w+(unsigned)xx];
        }
        assert(same(out[(size_t)y*w+x],expected));
    }
    free(in);free(out);
}
int main(void)
{
    for(unsigned d=1;d<=1024;d++) {
        for(unsigned j=0;j<1024;j++)divide(random_bits(),d);
        for(unsigned e=1;e<2047;e+=17) {
            uint64_t b=(uint64_t)e<<52;divide(b,d);divide(b+1,d);divide(b+UINT64_C(0xfffffffffffff),d);
            unsigned k=0,t=d-1;while(t){k++;t>>=1;}
            uint64_t m=(uint64_t)d<<(53-k);
            for(int delta=-2;delta<=2;delta++) {
                uint64_t z=m+delta;
                if(z>=UINT64_C(0x10000000000000) && z<UINT64_C(0x20000000000000))divide(b+(z&UINT64_C(0xfffffffffffff)),d);
            }
        }
    }
    for(unsigned i=0;i<2000000;i++) {
        uint64_t a=random_bits(),b=random_bits();add(a,b);add(a&UINT64_C(0x7fffffffffffffff),b&UINT64_C(0x7fffffffffffffff));
    }
    for(unsigned e=1;e<2046;e+=7)for(unsigned d=0;d<70;d++)for(unsigned i=0;i<8;i++) {
        uint64_t a=(uint64_t)e<<52,b=(uint64_t)(e>d?e-d:1)<<52;
        if(i&1)a|=UINT64_C(0xfffffffffffff);
        if(i&2)b|=UINT64_C(0xfffffffffffff);
        if(i&4){a|=1;b|=1;}
        add(a,b);
    }
    const uint64_t edge[]={0,UINT64_C(0x8000000000000000),1,UINT64_C(0xfffffffffffff),
        UINT64_C(0x7ff0000000000000),UINT64_C(0xfff0000000000000),UINT64_C(0x7ff8000000000001)};
    for(unsigned i=0;i<sizeof(edge)/8;i++) {
        for(unsigned j=0;j<sizeof(edge)/8;j++)add(edge[i],edge[j]);
        for(unsigned d=1;d<=1024;d++)divide(edge[i],d);
    }
    unsigned shapes[][4]={{1,1,0,0},{1,1,15,15},{2,3,13,1},{31,17,1,13},{64,31,13,1}};
    for(unsigned k=0;k<sizeof(shapes)/sizeof(shapes[0]);k++)for(unsigned pattern=0;pattern<3;pattern++)
        mask(shapes[k][0],shapes[k][1],shapes[k][2],shapes[k][3],pattern);
    mask(1280,720,13,1,0);mask(1280,720,1,13,1);
    double unused=0;assert(!xqgeom_mask_sum(&unused,1,13,&unused,0,1));
    assert(!xqgeom_mask_sum(&unused,16,1,&unused,1,1));
    printf("GEOMETRY_EXACT_DIV_ADD_MASK_PASS divisions=%llu additions=%llu\n",
        (unsigned long long)divisions,(unsigned long long)additions);return 0;
}
