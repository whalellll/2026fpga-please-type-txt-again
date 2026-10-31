#include "board_exposure.h"
#include <math.h>

enum { W=1280, H=720, BYTES=W*H*3, TARGET=160,
       UNITY=1024, MAX_GAIN=1536, SIDE=32 };
#if XQ_EXPOSURE_RETRY_R29
static unsigned selected_target=TARGET;
void xqex_set_target(unsigned target){selected_target=target==172?172:TARGET;}
#endif

int xqex_plan_rgb(const uint8_t *rgb,size_t bytes,const float q[8],xqex_plan *out)
{
    unsigned histogram[256]={0};
    if(!out)return 0;
    *out=(xqex_plan){0,UNITY,0};
    if(!rgb || bytes!=BYTES || !q)return 0;
    /* Reject invalid or tiny proposals. Do not clamp an invalid proposal to
     * the image boundary and then infer exposure from unrelated pixels. */
    for(unsigned i=0;i<8;i++)if(!isfinite(q[i]) || q[i]<0 || q[i]>1)return 0;
    double area=0;
    for(unsigned i=0;i<4;i++){
        unsigned j=(i+1)%4,k=(i+2)%4;
        double ax=(double)q[2*j]-q[2*i],ay=(double)q[2*j+1]-q[2*i+1];
        double bx=(double)q[2*k]-q[2*j],by=(double)q[2*k+1]-q[2*j+1];
        if(ax*by-ay*bx<=0)return 0;
        area+=(double)q[2*i]*q[2*j+1]-(double)q[2*j]*q[2*i+1];
    }
    if(area<.02)return 0;
    /* Sample the interior of the proposal, rather than the white tabletop
     * or black equipment outside it. A median limits piece/line influence.
     * Fixed 32x32 samples keep work and stack use bounded. */
    for(unsigned y=0;y<SIDE;y++)for(unsigned x=0;x<SIDE;x++){
        double u=.2+.6*(x+.5)/SIDE,v=.2+.6*(y+.5)/SIDE;
        double weights[4]={(1-u)*(1-v),u*(1-v),u*v,(1-u)*v};
        double px=0,py=0;
        for(unsigned i=0;i<4;i++){px+=weights[i]*q[2*i];py+=weights[i]*q[2*i+1];}
        unsigned ix=(unsigned)(px*W),iy=(unsigned)(py*H);
        if(ix>=W)ix=W-1;
        if(iy>=H)iy=H-1;
        const uint8_t *p=rgb+((size_t)iy*W+ix)*3;
        histogram[(77u*p[0]+150u*p[1]+29u*p[2])>>8]++;
    }
    unsigned n=0,median=0;
    for(;median<255;median++){n+=histogram[median];if(n>=SIDE*SIDE/2)break;}
    out->median=median;out->samples=SIDE*SIDE;
    /* Stateless, one pass per frame. Apply a continuous gain up to the
     * target, leaving normally exposed images exactly alone. */
#if XQ_EXPOSURE_RETRY_R29
    unsigned target=selected_target;
    if(median>=target || !median)return 1;
    unsigned gain=(target*UNITY+median/2)/median;
#else
    if(median>=TARGET || !median)return 1;
    unsigned gain=(TARGET*UNITY+median/2)/median;
#endif
    out->gain_q10=gain<MAX_GAIN?gain:MAX_GAIN;
    return 1;
}

int xqex_apply_rgb(uint8_t *rgb,size_t bytes,const xqex_plan *plan,
                   int (*cancel)(void *),void *context)
{
    uint8_t lut[256];
    if(!rgb || bytes!=BYTES || !plan || plan->gain_q10<UNITY ||
       plan->gain_q10>MAX_GAIN || plan->samples!=SIDE*SIDE)return 0;
    if(cancel && cancel(context))return 0;
    if(plan->gain_q10==UNITY)return 1;
    for(unsigned i=0;i<256;i++){
        unsigned v=(i*plan->gain_q10+UNITY/2)/UNITY;
        lut[i]=(uint8_t)(v>255?255:v);
    }
    for(unsigned y=0;y<H;y++){
        if(!(y%16) && cancel && cancel(context))return 0;
        uint8_t *row=rgb+(size_t)y*W*3;
        for(unsigned x=0;x<W*3;x++)row[x]=lut[row[x]];
    }
    return 1;
}
