#include "board_exposure.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
enum { BYTES=1280*720*3 };
static const float quad[8]={.25f,.2f,.75f,.2f,.75f,.8f,.25f,.8f};
static int stop_now(void *p){unsigned *n=p;return ++*n>=3;}
int main(void)
{
    uint8_t *guard=malloc(BYTES+2),*rgb=guard+1,*original=malloc(BYTES);
    assert(guard && original);guard[0]=0x37;guard[BYTES+1]=0xc9;
    xqex_plan plan;
    /* Changing the exterior from white to black must not dilute the board
     * interior measurement. This reproduces the exposure-estimation seam. */
    for(unsigned exterior=0;exterior<=255;exterior+=255){
        memset(rgb,(int)exterior,BYTES);
        for(unsigned y=144;y<576;y++)memset(rgb+((size_t)y*1280+320)*3,128,640*3);
        assert(xqex_plan_rgb(rgb,BYTES,quad,&plan));
        assert(plan.median==128 && plan.gain_q10==1280);
        assert(xqex_apply_rgb(rgb,BYTES,&plan,NULL,NULL));
        assert(rgb[(360u*1280+640)*3]==160);
    }
    /* The nearby underexposed case must not fall through a lower trigger
     * threshold. Bright frames and black frames retain every byte. */
    memset(rgb,144,BYTES);assert(xqex_plan_rgb(rgb,BYTES,quad,&plan));
    assert(plan.gain_q10>1024 && plan.gain_q10<1280);
    assert(xqex_apply_rgb(rgb,BYTES,&plan,NULL,NULL));assert(rgb[0]==160);
    const unsigned unchanged[]={0,160,204,255};
    for(unsigned i=0;i<sizeof(unchanged)/sizeof(*unchanged);i++){
        memset(rgb,(int)unchanged[i],BYTES);memcpy(original,rgb,BYTES);
        assert(xqex_plan_rgb(rgb,BYTES,quad,&plan) && plan.gain_q10==1024);
        assert(xqex_apply_rgb(rgb,BYTES,&plan,NULL,NULL));
        assert(!memcmp(rgb,original,BYTES));
    }
    /* Strong underexposure is capped; clipping never wraps to dark pixels. */
    memset(rgb,32,BYTES);assert(xqex_plan_rgb(rgb,BYTES,quad,&plan));
    assert(plan.gain_q10==1536);rgb[0]=255;
    assert(xqex_apply_rgb(rgb,BYTES,&plan,NULL,NULL));assert(rgb[0]==255 && rgb[1]==48);
    for(unsigned i=0;i<256;i++)rgb[i]=(uint8_t)i;
    assert(xqex_apply_rgb(rgb,BYTES,&plan,NULL,NULL));
    for(unsigned i=1;i<256;i++)assert(rgb[i]>=rgb[i-1]);
    unsigned calls=0;assert(!xqex_apply_rgb(rgb,BYTES,&plan,stop_now,&calls));
    assert(calls==3 && guard[0]==0x37 && guard[BYTES+1]==0xc9);
    /* Invalid proposals are not exposure samples. */
    float bad[8];memcpy(bad,quad,sizeof(bad));bad[0]=NAN;
    assert(!xqex_plan_rgb(rgb,BYTES,bad,&plan) && plan.gain_q10==1024);
    memcpy(bad,quad,sizeof(bad));bad[0]=-1;
    assert(!xqex_plan_rgb(rgb,BYTES,bad,&plan));
    memcpy(bad,quad,sizeof(bad));bad[2]=.1f;
    assert(!xqex_plan_rgb(rgb,BYTES,bad,&plan));
    assert(!xqex_plan_rgb(rgb,BYTES-1,quad,&plan));
    assert(!xqex_plan_rgb(NULL,BYTES,quad,&plan));
    assert(!xqex_plan_rgb(rgb,BYTES,quad,NULL));
    plan=(xqex_plan){128,1537,1024};assert(!xqex_apply_rgb(rgb,BYTES,&plan,NULL,NULL));
#if XQ_EXPOSURE_RETRY_R29
    memset(rgb,135,BYTES);
    xqex_set_target(172);assert(xqex_plan_rgb(rgb,BYTES,quad,&plan));
    assert(plan.gain_q10==1305);
    xqex_set_target(160);assert(xqex_plan_rgb(rgb,BYTES,quad,&plan));
    assert(plan.gain_q10==1214);
    xqex_set_target(0);assert(xqex_plan_rgb(rgb,BYTES,quad,&plan));
    assert(plan.gain_q10==1214);
#endif
    free(original);free(guard);puts("BOARD_EXPOSURE_BOUNDARIES_BACKGROUND_NOOP_GAIN_CANCEL_PASS");return 0;
}
