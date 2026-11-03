#include "xq_camera_retry.h"
int xqc_start_retry(xqc_camera *c,unsigned total_ms,unsigned max_attempts,
                   xqc_start_observer observe,void *context)
{
    uint64_t begin;
    unsigned attempt;
    int result=XQC_START;
    if(!c || !c->camera || !c->now_ms || !c->poll || !total_ms ||
       total_ms>60000 || !max_attempts || max_attempts>16)return XQC_ARGUMENT;
    begin=c->now_ms(c->context);
    for(attempt=1;attempt<=max_attempts;attempt++) {
        uint64_t elapsed=c->now_ms(c->context)-begin;
        uint32_t status;
        unsigned remaining,wait;
        if(elapsed>=total_ms)break;
        remaining=total_ms-(unsigned)elapsed;
        result=xqc_start(c,remaining<5000?remaining:5000);
        status=c->camera[CAMERA_REG_STATUS/4u];
        if(observe)observe(context,attempt,result,status);
        if(result==XQC_OK || result==XQC_ID || result==XQC_STOP)return result;
        if(xqc_stop(c)!=XQC_OK)return XQC_STOP;
        if(result!=XQC_START || !(status&CAMERA_STATUS_SCCB_NACK) ||
           (status&(CAMERA_STATUS_DDR_ERROR|CAMERA_STATUS_FRAME_ERROR)) ||
           attempt==max_attempts)return result;
        /* Keep RESET asserted between attempts; poll retains Esc semantics. */
        for(wait=0;wait<200;wait++) {
            if(c->now_ms(c->context)-begin>=total_ms)return result;
            if(c->poll(c->context,1))return XQC_CANCELLED;
        }
    }
    return result;
}
