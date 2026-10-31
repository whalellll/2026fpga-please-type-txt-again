#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define XQ_GEOMETRY_FAST 1
#ifndef XQ_GEOMETRY_SEED_BOUND
#define XQ_GEOMETRY_SEED_BOUND 1
#endif

static unsigned checks;
static uint32_t random_state=UINT32_C(0x78462109);
static uint32_t next_random(void)
{random_state=random_state*UINT32_C(1664525)+UINT32_C(1013904223);return random_state;}
static int round_even(double x)
{double mag=fabs(x);int n=(int)mag;if(mag-n>.5 || (mag-n==.5 && (n&1)))++n;return x<0?-n:n;}

static void compare(const double *score,unsigned width,int ox,int oy,const double p[2],
                    int x0,int x1,int y0,int y1)
{
    double expected=-INFINITY;int ex=0,ey=0;
    /* Independent unpruned oracle, using the frozen score expression and
     * strict update. The candidate below is extracted from production. */
    for(int y=y0;y<y1;y++)for(int x=x0;x<x1;x++) {
        double v=score[(size_t)y*width+(unsigned)x]-.0015*hypot(x+ox-p[0],y+oy-p[1]);
        if(v>expected){expected=v;ex=x;ey=y;}
    }
    double value=-INFINITY;int bx=0,by=0,ix=round_even(p[0]),iy=round_even(p[1]);
    (void)ix;(void)iy;
#include GEOMETRY_SEARCH_WINDOW_SOURCE
    assert(ex==bx && ey==by && !memcmp(&expected,&value,sizeof(value)));
    ++checks;
}

int main(void)
{
    double scores[64*64]={0},p[2]={1.5,0};
    /* ix=2, while equal maxima at x=1 and2 must choose the earlier x=1.
     * Changing upper<seed_bound to <= incorrectly discards both maxima. */
    compare(scores,4,0,0,p,0,4,0,1);
    for(unsigned w=1;w<=57;w++) {
        p[0]=11+(w/2)+.5;p[1]=7+.5;
        compare(scores,64,11,7,p,0,(int)w,0,3);
        compare(scores,64,11,7,p,0,0,0,3);
        compare(scores,64,11,7,p,0,(int)w,0,0);
    }
    for(unsigned test=0;test<512;test++) {
        unsigned width=8+next_random()%57,height=8+next_random()%57;
        for(size_t i=0;i<(size_t)width*height;i++) {
            uint32_t v=next_random();
            scores[i]=test%5==0?0:test%5==1?1:
                test%5==2?((int)(v%257)-128)/64.:(v%101)/100.;
        }
        int x0=(int)(next_random()%width),y0=(int)(next_random()%height);
        int x1=x0+1+(int)(next_random()%57),y1=y0+1+(int)(next_random()%57);
        if(x1>(int)width)x1=(int)width;
        if(y1>(int)height)y1=(int)height;
        p[0]=11+(int)(next_random()%128)-32+(next_random()&65535)/65536.;
        p[1]=7+(int)(next_random()%128)-32+(next_random()&65535)/65536.;
        compare(scores,width,11,7,p,x0,x1,y0,y1);
    }
    const double special[]={0.,-0.,NAN,INFINITY,-INFINITY,0x1p-1022,0x1p-1074,0x1p900,-0x1p900};
    for(unsigned test=0;test<sizeof(special)/sizeof(*special);test++) {
        for(unsigned i=0;i<64*64;i++)scores[i]=special[test];
        p[0]=11+1.5;p[1]=7+2.5;compare(scores,64,11,7,p,0,57,0,57);
        scores[0]=1;compare(scores,64,11,7,p,0,57,0,57);
    }
    printf("GEOMETRY_SEED_ACTUAL_SEARCH_FROZEN_BRUTE_BITS_TIES_EMPTY_SPECIALS_PASS cases=%u\n",checks);
    return 0;
}
