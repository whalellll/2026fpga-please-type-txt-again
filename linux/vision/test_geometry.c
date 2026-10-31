#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "xq_geometry.h"

/* Synthetic coordinates exercise dispatch/provenance only. No image/model,
 * projection, QC correctness or golden bit-exact claim is made by this test. */
typedef struct {
    int board_ok, fit_ok, manual_ok, qc_ok, stale, wrong_source, bad_coordinate;
    int bad_corner, bad_fraction, bad_confidence, board_calls, fit_calls, manual_calls, shift_x;
    const xq_search_board_t *expected_reference;
} fixture;
static void geometry(const xqgeo_request *r, Geometry *g, xqgeo_source source)
{
    unsigned i;
    memset(g,0,sizeof(*g));
    g->source=source; g->confidence=900; g->fraction_bits=4;
    g->capture_id=r->capture_id; g->frame_id=r->frame->frame_id;
    for (i=0;i<90;++i) {
        g->intersections[i].x=(int32_t)(160+100*(i%9))*16;
        g->intersections[i].y=(int32_t)(630-60*(i/9))*16;
    }
    g->corners[0]=g->intersections[0]; g->corners[1]=g->intersections[8];
    g->corners[2]=g->intersections[89]; g->corners[3]=g->intersections[81];
}
static int board(void *context, const xqgeo_request *r, Geometry *g)
{
    fixture *f=context;
    ++f->board_calls;
    geometry(r,g,XQGEO_BOARD_MODEL);
    if (f->shift_x) {
        unsigned i;
        for (i=0;i<90;++i) g->intersections[i].x+=f->shift_x*16;
        for (i=0;i<4;++i) g->corners[i].x+=f->shift_x*16;
    }
    if (f->stale) --g->capture_id;
    if (f->wrong_source) g->source=XQGEO_CACHED;
    if (f->bad_coordinate) g->intersections[40].x=-1;
    if (f->bad_corner) ++g->corners[0].x;
    if (f->bad_fraction) g->fraction_bits=21;
    if (f->bad_confidence) g->confidence=1001;
    return f->board_ok;
}
static int fit(void *context, const xqgeo_request *r, Geometry *g)
{
    fixture *f=context;
    ++f->fit_calls;
    assert(r->reference==f->expected_reference);
    geometry(r,g,XQGEO_PIECE_FIT);
    return f->fit_ok;
}
static int manual(void *context, const xqgeo_request *r, Geometry *g)
{
    fixture *f=context;
    ++f->manual_calls;
    geometry(r,g,XQGEO_MANUAL);
    return f->manual_ok;
}
static int qc(void *context, const xqgeo_request *r, const Geometry *g)
{
    fixture *f=context;
    assert(r->capture_id==g->capture_id);
    return f->qc_ok;
}
int main(void)
{
    uint32_t pixel=0;
    xqv_frame frame={&pixel,XQV_FRAME_BYTES,7,1};
    xq_search_board_t reference;
    xqgeo_request request={&frame,&reference,1};
    fixture f={0};
    xqgeo_providers providers={board,fit,manual,qc,&f};
    xqgeo_state state;
    Geometry out,cached,zero;
    unsigned i;
    memset(&reference,0,sizeof(reference));
    memset(&zero,0,sizeof(zero));
    f.expected_reference=&reference; f.qc_ok=1;
    assert(!xqgeo_init(&state,&providers,0));
    providers.qc=NULL;
    assert(!xqgeo_init(&state,&providers,800));
    providers.qc=qc;
    assert(xqgeo_init(&state,&providers,800));
    assert(!xqgeo_cached(&state,&cached));
    assert(xqgeo_capture(&state,&request,&out)==XQGEO_RETAKE);
    /* Reprocessing one photograph cannot consume the three-capture budget. */
    assert(xqgeo_capture(&state,&request,&out)==XQGEO_BAD_REQUEST);
    assert(state.board_failures==1);
    ++request.capture_id;
    assert(xqgeo_capture(&state,&request,&out)==XQGEO_RETAKE);
    assert(!f.fit_calls && !f.manual_calls);
    ++request.capture_id; f.fit_ok=1;
    assert(xqgeo_capture(&state,&request,&out)==XQGEO_OK);
    assert(out.source==XQGEO_PIECE_FIT && f.fit_calls==1 && !f.manual_calls);
    assert(xqgeo_cached(&state,&cached));
    assert(cached.source==XQGEO_CACHED && cached.capture_id==request.capture_id);
    assert(!memcmp(cached.intersections,out.intersections,sizeof(out.intersections)));
    /* Board gets the very next chance, including after fallback. */
    ++request.capture_id; f.board_ok=1;
    assert(xqgeo_capture(&state,&request,&out)==XQGEO_OK);
    assert(out.source==XQGEO_BOARD_MODEL && state.board_failures==0);
    /* A reset hardware frame counter with a fresh capture token is valid. */
    ++request.capture_id; frame.frame_id=1;
    f.shift_x=100;
    assert(xqgeo_capture(&state,&request,&out)==XQGEO_OK);
    assert(out.intersections[0].x==260*16);
    cached=out;
    f.board_ok=0; f.fit_ok=0;
    for (i=0;i<3;++i) {
        ++request.capture_id;
        assert(xqgeo_capture(&state,&request,&out)==(i==2?XQGEO_MANUAL_REQUIRED:XQGEO_RETAKE));
        assert(!memcmp(&out,&zero,sizeof(out)));
    }
    assert(xqgeo_cached(&state,&out));
    assert(out.capture_id==cached.capture_id && out.frame_id==cached.frame_id);
    assert(out.capture_id!=request.capture_id); /* not usable as current geometry */
    assert(!f.manual_calls);
    f.manual_ok=1;
    f.qc_ok=0;
    assert(xqgeo_use_manual(&state,&request,&out)==XQGEO_MANUAL_REQUIRED);
    assert(!memcmp(&out,&zero,sizeof(out)));
    f.qc_ok=1;
    assert(xqgeo_use_manual(&state,&request,&out)==XQGEO_OK);
    assert(out.source==XQGEO_MANUAL && f.manual_calls==2);
    ++request.capture_id;
    assert(xqgeo_use_manual(&state,&request,&out)==XQGEO_BAD_REQUEST);
    /* QC, provenance, bounds and confidence rejection cannot publish output. */
    for (i=0;i<8;++i) {
        assert(xqgeo_init(&state,&providers,800));
        f.board_ok=1; f.fit_ok=0;
        f.qc_ok=i!=0; f.stale=i==1; f.wrong_source=i==2;
        f.bad_coordinate=i==3; f.bad_corner=i==4; f.bad_fraction=i==5;
        f.bad_confidence=i==6;
        if (i==7) state.threshold=950;
        memset(&out,0xff,sizeof(out));
        assert(xqgeo_capture(&state,&request,&out)==XQGEO_RETAKE);
        assert(!memcmp(&out,&zero,sizeof(out)));
        assert(!xqgeo_cached(&state,&cached));
    }
    /* No delivered fit registered: after three failures request manual. */
    providers.board_model=NULL; providers.piece_fit=NULL; providers.manual=NULL;
    assert(xqgeo_init(&state,&providers,800));
    for (i=0;i<3;++i) {
        ++request.capture_id;
        assert(xqgeo_capture(&state,&request,&out)==(i==2?XQGEO_MANUAL_REQUIRED:XQGEO_RETAKE));
    }
    assert(xqgeo_use_manual(&state,&request,&out)==XQGEO_MANUAL_REQUIRED);
    /* Require an immutable frame and a current tracked board. */
    ++request.capture_id; request.reference=NULL;
    assert(xqgeo_capture(&state,&request,&out)==XQGEO_BAD_REQUEST);
    assert(!strcmp(xqgeo_source_name(XQGEO_BOARD_MODEL),"board_model"));
    assert(!strcmp(xqgeo_source_name(XQGEO_PIECE_FIT),"piece_fit"));
    assert(!strcmp(xqgeo_source_name(XQGEO_CACHED),"cached"));
    assert(!strcmp(xqgeo_source_name(XQGEO_MANUAL),"manual"));
    puts("XQ_GEOMETRY_TEST_PASS synthetic dispatch provenance retry fit manual cache stale QC");
    return 0;
}
