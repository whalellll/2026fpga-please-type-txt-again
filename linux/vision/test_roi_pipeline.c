#include "xq_roi_pipeline.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef struct {xqr_box boxes[32];unsigned n,calls;int cancel,failure;uint64_t clock;} fake;
static int detector(void *opaque,const uint8_t *input,unsigned size,xqr_box *out,unsigned *n)
{
    fake *f=opaque;
    assert(input && size==640 && *n>=f->n);
    memcpy(out,f->boxes,f->n*sizeof(*out));*n=f->n;f->calls=0;
    return !f->failure;
}
static int classifier(void *opaque,const uint8_t *input,float out[15])
{
    fake *f=opaque;
    assert(input && f->calls<f->n);memset(out,0,15*sizeof(float));
    out[f->boxes[f->calls++].class_id]=1;
    return 1;
}
static int cancelled(void *opaque){return ((fake *)opaque)->cancel;}
static uint64_t clock_ms(void *opaque){return ++((fake *)opaque)->clock;}
int main(void)
{
    xqr_pipeline pipeline={0};xqr_timing timing;xqv_result result;
    xqr_manual manual;
    xq_search_board_t board,actual;
    double corners[4][2]={{200,650},{1000,650},{1000,50},{200,50}};
    fake f={0};
    xqr_backend backend={&f,640,0,1,detector,classifier,cancelled,clock_ms};
    uint32_t *pixels=calloc(1280u*720u,2);unsigned i;
    xqv_frame frame={pixels,XQV_FRAME_BYTES,67,0};
    assert(pixels && xqr_manual_init(&manual,(xqr_roi){0,0,1280,720},corners,9));
    assert(xqv_parse_fen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",&board));
    for(i=0;i<90;i++)if(board.squares[i]) {
        double x,y;unsigned p=board.squares[i];
        assert(xqg_project(&manual.grid,i%9,i/9,&x,&y));
        f.boxes[f.n++]=(xqr_box){(float)x/2-2,(float)y/2+140-2,(float)x/2+2,(float)y/2+140+2,.9f,
            (p&7u)-1+((p&SIDE_BLACK)?7u:0u)};
    }
    assert(xqr_pipeline_run(&pipeline,&frame,1,&manual,9,.05f,&result,&timing)==XQR_NO_MODEL);
    assert(xqr_pipeline_open(&pipeline,&backend));
    __atomic_store_n(&pipeline.busy,1,__ATOMIC_RELEASE);
    assert(xqr_pipeline_run(&pipeline,&frame,1,&manual,9,.05f,&result,&timing)==XQR_BUSY);
    assert(!xqr_pipeline_close(&pipeline));
    __atomic_store_n(&pipeline.busy,0,__ATOMIC_RELEASE);
    assert(xqr_pipeline_run(&pipeline,&frame,1,&manual,9,.05f,&result,&timing)==XQR_OK);
    assert(result.is_stub && result.frame_id==67 && timing.classified==32 && timing.capture_id==1);
    assert(xqv_result_board(&result,67,&actual) && !memcmp(actual.squares,board.squares,90));
    assert(xqr_pipeline_run(&pipeline,&frame,1,&manual,9,.05f,&result,&timing)==XQR_BAD_REQUEST && !result.abi_version);
    f.cancel=1;
    assert(xqr_pipeline_run(&pipeline,&frame,2,&manual,9,.05f,&result,&timing)==XQR_CANCELLED && !result.abi_version);
    f.cancel=0;f.failure=1;
    assert(xqr_pipeline_run(&pipeline,&frame,3,&manual,9,.05f,&result,&timing)==XQR_DETECTOR_FAILED && !result.abi_version);
    assert(xqr_pipeline_run(&pipeline,&frame,4,&manual,10,.05f,&result,&timing)==XQR_BAD_REQUEST);
    assert(xqr_pipeline_close(&pipeline));free(pixels);
    backend.synthetic_test=0;
    assert(!xqr_pipeline_open(&pipeline,&backend));
    puts("XQ_ROI_PIPELINE_TEST_PASS callbacks=synthetic_only no_model_fallback=pass");return 0;
}
