#include "xq_camera_retry.h"
#include <limits.h>
#include <string.h>
int xqc_capture_until_ready(xqc_camera *c,uint32_t *ram,size_t bytes,xqv_frame *out,
                           xqc_start_observer observe,void *context)
{
    unsigned attempt=0;
    if(out)memset(out,0,sizeof(*out));
    if(!out || !c || !c->camera || !c->now_ms || !c->poll || !ram ||
       ((uintptr_t)ram&3u) || bytes!=XQV_FRAME_BYTES)return XQC_ARGUMENT;
    for(;;) {
        int r;unsigned polls=0;uint32_t status;
        if(attempt<UINT_MAX)++attempt;
        memset(out,0,sizeof(*out));
        if(c->poll(c->context,0))return XQC_CANCELLED;
        r=xqc_start(c,5000);
        if(!r) {
            uint32_t before=c->camera[CAMERA_REG_FRAME_COUNT/4u];
            uint64_t begin=c->now_ms(c->context);
            /* The legacy HDMI bank may trail the newest completed bank by
             * one frame. Two publications ensure either held bank is fresh
             * for this request. Do not accept sticky FRAME_VALID alone. */
            while((uint32_t)(c->camera[CAMERA_REG_FRAME_COUNT/4u]-before)<2u) {
                if(c->poll(c->context,1)){r=XQC_CANCELLED;break;}
                status=c->camera[CAMERA_REG_STATUS/4u];
                if(status&CAMERA_STATUS_DDR_ERROR){r=XQC_DDR;break;}
                if(status&(CAMERA_STATUS_SCCB_NACK|CAMERA_STATUS_FRAME_ERROR)) {r=XQC_START;break;}
                if(c->now_ms(c->context)-begin>=2000 || ++polls>=2000){r=XQC_START;break;}
            }
            if(!r)r=xqc_capture(c,ram,bytes,out);
        }
        status=c->camera[CAMERA_REG_STATUS/4u];
        if(r && !c->poisoned && r!=XQC_ID && r!=XQC_ARGUMENT && r!=XQC_STOP) {
            if(xqc_stop(c)!=XQC_OK)r=XQC_STOP;
        }
        if(r==XQC_START && (status&CAMERA_STATUS_DDR_ERROR))r=XQC_DDR;
        if(!r && (out->rgb565!=ram || out->bytes!=bytes))r=xqc_stop(c)==XQC_OK?XQC_CHANGED:XQC_STOP;
        if(r)memset(out,0,sizeof(*out));
        if(observe)observe(context,attempt,r,status);
        if(!r || (r!=XQC_START && r!=XQC_HOLD && r!=XQC_CHANGED) || c->poisoned)return r;
        /* Sensor reset remains asserted after a confirmed drain. Esc/TERM
         * still works between attempts; extra Space presses stay busy. */
        for(unsigned wait=0;wait<200;wait++)if(c->poll(c->context,1))return XQC_CANCELLED;
    }
}
