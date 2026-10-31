#define _POSIX_C_SOURCE 200809L
#include "graph_bilinear_s16.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
/* Independent verbatim arithmetic from frozen xq_native_graph.c type6.
 * Test deliberately retains its FP32 coordinates and operation ordering. */
static void reference(const float *a,unsigned planes,unsigned ih,unsigned iw,float *out)
{
    unsigned oh=ih*2,ow=iw*2;
    for(unsigned p=0;p<planes;p++)for(unsigned y=0;y<oh;y++)for(unsigned x=0;x<ow;x++){
        const float *base=a+(size_t)p*ih*iw;
        float sy=fmaxf(0,(y+.5f)*.5f-.5f),sx=fmaxf(0,(x+.5f)*.5f-.5f);
        unsigned y0=(unsigned)sy,x0=(unsigned)sx,y1=y0+1<ih?y0+1:y0,x1=x0+1<iw?x0+1:x0;
        float fy=sy-y0,fx=sx-x0;
        out[(size_t)p*oh*ow+y*ow+x]=
            (1.f-fy)*((1.f-fx)*base[y0*iw+x0]+fx*base[y0*iw+x1])+
            fy*((1.f-fx)*base[y1*iw+x0]+fx*base[y1*iw+x1]);
    }
}
static uint32_t rng=UINT32_C(0xc2759461);
static int16_t random_code(void)
{rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return (int16_t)(rng&65535);}
static uint64_t now(void)
{struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC,&t));return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;}
static uint64_t compared;
static void check(int16_t *q,unsigned batch,unsigned channels,unsigned h,unsigned w,int exponent,int bench)
{
    size_t count=(size_t)batch*channels*h*w;
    float *a=malloc(count*4),*ref=malloc(count*16),*out=malloc(count*16);assert(a && ref && out);
    for(size_t i=0;i<count;i++)a[i]=ldexpf(q[i],exponent);
    xqg_tensor t={.q16=q,.f32=a,.count=count,.exponent=exponent};
    uint64_t start=now();reference(a,batch*channels,h,w,ref);uint64_t middle=now();
    assert(xqg_bilinear_s16_eligible(&t,batch,channels,h,w));
    assert(xqg_bilinear_s16(&t,batch,channels,h,w,out));uint64_t end=now();
    assert(!memcmp(ref,out,count*16));compared+=count*4;
    if(bench)printf("BILINEAR_S16_TIMING_NOT_BOARD reference_ns=%llu candidate_ns=%llu values=%llu\n",
        (unsigned long long)(middle-start),(unsigned long long)(end-middle),(unsigned long long)(count*4));
    free(a);free(ref);free(out);
}
int main(void)
{
    int16_t *q=malloc(65536*2);assert(q);
    const int exponents[]={-120,-119,-112,-32,-8,-1,0,1,32,110,112};
    /* Exhaust every S16 value, including both signed extrema and zero. */
    for(unsigned i=0;i<65536;i++)q[i]=(int16_t)((int)i-32768);
    for(unsigned e=0;e<sizeof(exponents)/sizeof(exponents[0]);e++)check(q,256,256,1,1,exponents[e],0);
    /* All four-corner combinations of cancellation/extreme/zero edges. */
    const int16_t edges[]={-32768,-32767,-128,-1,0,1,127,32766,32767};
    unsigned at=0;
    for(unsigned a=0;a<9;a++)for(unsigned b=0;b<9;b++)for(unsigned c=0;c<9;c++)for(unsigned d=0;d<9;d++){
        q[at++]=edges[a];q[at++]=edges[b];q[at++]=edges[c];q[at++]=edges[d];
    }
    for(unsigned e=0;e<sizeof(exponents)/sizeof(exponents[0]);e++)check(q,1,6561,2,2,exponents[e],0);
    const unsigned shapes[][4]={{1,3,1,7},{2,3,9,1},{1,3,3,5},{3,2,8,17},{1,16,24,24},{1,4,48,48}};
    for(unsigned s=0;s<sizeof(shapes)/sizeof(shapes[0]);s++){
        const unsigned *v=shapes[s];for(unsigned i=0;i<v[0]*v[1]*v[2]*v[3];i++)q[i]=random_code();
        for(unsigned e=0;e<sizeof(exponents)/sizeof(exponents[0]);e++)check(q,v[0],v[1],v[2],v[3],exponents[e],s==4 && exponents[e]==-8);
    }
    float sentinel[16];memset(sentinel,0xa5,sizeof(sentinel));float old[16];memcpy(old,sentinel,sizeof(old));
    xqg_tensor bad={.q16=q,.count=4,.exponent=113};
    assert(!xqg_bilinear_s16(&bad,1,1,2,2,sentinel));
    bad.exponent=-121;assert(!xqg_bilinear_s16(&bad,1,1,2,2,sentinel));
    bad.exponent=0;bad.count=3;assert(!xqg_bilinear_s16(&bad,1,1,2,2,sentinel));
    bad.count=4;bad.q16=NULL;assert(!xqg_bilinear_s16(&bad,1,1,2,2,sentinel));
    assert(!xqg_bilinear_s16(NULL,1,1,2,2,sentinel));
    assert(!memcmp(old,sentinel,sizeof(old)));
    free(q);printf("BILINEAR_S16_FROZEN_FLOAT_BIT_EQUAL_PASS_NOT_BOARD compared=%llu\n",(unsigned long long)compared);return 0;
}
