#include "xq_roi_pipeline.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>
static uint64_t now(xqr_pipeline *p)
{return p->backend.now_ms?p->backend.now_ms(p->backend.context):0;}
static int cancelled(xqr_pipeline *p)
{return p->backend.cancelled && p->backend.cancelled(p->backend.context);}
int xqr_pipeline_open(xqr_pipeline *p,const xqr_backend *b)
{
    if(!p)return 0;
    memset(p,0,sizeof(*p));
    if(!b || (!b->validated && !b->synthetic_test) || !b->detector || !b->classifier ||
       (b->input_size!=320 && b->input_size!=640))return 0;
    p->backend=*b;
    p->rgb=malloc(1280u*720u*3u);p->input=malloc(3u*b->input_size*b->input_size);
    if(!p->rgb || !p->input){free(p->rgb);free(p->input);memset(p,0,sizeof(*p));return 0;}
    return 1;
}
int xqr_pipeline_close(xqr_pipeline *p)
{
    if(!p || __atomic_exchange_n(&p->busy,1,__ATOMIC_ACQUIRE))return 0;
    free(p->rgb);free(p->input);p->rgb=p->input=NULL;
    memset(&p->backend,0,sizeof(p->backend));p->last_capture_id=0;
    __atomic_store_n(&p->busy,0,__ATOMIC_RELEASE);return 1;
}
xqr_status xqr_pipeline_run(xqr_pipeline *p,const xqv_frame *f,uint64_t capture,
                           const xqr_manual *manual,uint64_t view,float threshold,
                           xqv_result *out,xqr_timing *timing)
{
    xqr_box boxes[300],fused[300],work[300],final[300];
    uint8_t patch[3*32*32];
    xqr_letterbox plan;
    xqr_timing stats={0};
    xqv_result result;
    uint64_t start,t;
    unsigned n=300,used=0,i,kept;
    xqr_status status=XQR_BAD_REQUEST;
    if(out)memset(out,0,sizeof(*out));
    if(timing)memset(timing,0,sizeof(*timing));
    if(!p || !out || !f || !capture || !manual || !isfinite(threshold) || threshold<0 || threshold>1)return status;
    if(__atomic_exchange_n(&p->busy,1,__ATOMIC_ACQUIRE))return XQR_BUSY;
    start=now(p);
    if(!p->rgb || !p->input || (!p->backend.validated && !p->backend.synthetic_test)){
        status=XQR_NO_MODEL;goto done;
    }
    if(capture<=p->last_capture_id || !f->rgb565 || f->bytes!=XQV_FRAME_BYTES || !view || manual->view_id!=view || !manual->grid.valid)goto done;
    p->last_capture_id=capture;
    stats.capture_id=capture;stats.frame_id=f->frame_id;stats.view_id=view;stats.synthetic_test=p->backend.synthetic_test;
    status=XQR_CANCELLED;if(cancelled(p))goto done;
    t=now(p);
    if(!xqr_rgb565(f,p->rgb,1280u*720u*3u)){status=XQR_BAD_REQUEST;goto done;}
    stats.rgb_ms=now(p)-t;t=now(p);
    if(!xqr_detector_input(p->rgb,manual->roi,p->backend.input_size,p->input,3u*p->backend.input_size*p->backend.input_size,&plan)){
        status=XQR_BAD_REQUEST;goto done;}
    stats.letterbox_ms=now(p)-t;status=XQR_CANCELLED;if(cancelled(p))goto done;
    t=now(p);
    if(p->backend.detector(p->backend.context,p->input,p->backend.input_size,boxes,&n)!=1 || n>300){status=XQR_DETECTOR_FAILED;goto done;}
    stats.detector_ms=now(p)-t;stats.proposals=n;
    for(i=0;i<n;i++) {
        float probabilities[15];unsigned count=0;
        status=XQR_CANCELLED;if(cancelled(p))goto done;
        if(!xqr_box_original(&plan,boxes+i)){status=XQR_DETECTOR_FAILED;goto done;}
        t=now(p);
        if(!xqr_piece_crop(p->rgb,boxes+i,patch,sizeof(patch))){status=XQR_BAD_REQUEST;goto done;}
        stats.crop_ms+=now(p)-t;t=now(p);
        if(p->backend.classifier(p->backend.context,patch,probabilities)!=1 ||
            !xqr_fuse(boxes+i,probabilities,1,fused+used,&count)){
            status=XQR_CLASSIFIER_FAILED;goto done;}
        stats.classifier_ms+=now(p)-t;stats.classified++;
        if(count)used+=count;else stats.background++;
    }
    status=XQR_CANCELLED;if(cancelled(p))goto done;
    t=now(p);
    if(!xqr_nms(fused,used,.001f,.6f,300,work,300,final,&kept)){status=XQR_CLASSIFIER_FAILED;goto done;}
    stats.nms_ms=now(p)-t;stats.retained=kept;t=now(p);
    if(!xqr_map(manual,view,final,kept,f->frame_id,threshold,&result,&stats.outside)){status=XQR_GEOMETRY_FAILED;goto done;}
    stats.map_ms=now(p)-t;
    if(cancelled(p)){status=XQR_CANCELLED;goto done;}
    result.is_stub=(uint8_t)(p->backend.synthetic_test!=0);*out=result;status=XQR_OK;
done:
    stats.total_ms=now(p)-start;
    if(timing)*timing=stats;
    __atomic_store_n(&p->busy,0,__ATOMIC_RELEASE);return status;
}
