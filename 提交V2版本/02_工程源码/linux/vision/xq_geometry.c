#include "xq_geometry.h"
#include <string.h>

static int request_valid(const xqgeo_request *r)
{
    return r && r->frame && r->frame->rgb565 &&
           r->frame->bytes==XQV_FRAME_BYTES && r->reference && r->capture_id;
}
static int point_valid(xqgeo_point p, unsigned bits)
{
    return p.x>=0 && p.y>=0 && (int64_t)p.x<((int64_t)XQV_WIDTH<<bits) &&
           (int64_t)p.y<((int64_t)XQV_HEIGHT<<bits);
}
static int produced(xqgeo_state *s, const xqgeo_request *r, xqgeo_produce_fn producer,
                    xqgeo_source source, Geometry *out)
{
    static const unsigned corner_index[4]={0,8,89,81};
    Geometry candidate;
    unsigned i;
    memset(&candidate,0,sizeof(candidate));
    if (!producer || producer(s->providers.context,r,&candidate)!=1 ||
        candidate.source!=source || candidate.capture_id!=r->capture_id ||
        candidate.frame_id!=r->frame->frame_id || candidate.fraction_bits>20 ||
        candidate.confidence>1000 || candidate.confidence<s->threshold) return 0;
    for (i=0;i<90;++i)
        if (!point_valid(candidate.intersections[i],candidate.fraction_bits)) return 0;
    for (i=0;i<4;++i)
        if (candidate.corners[i].x!=candidate.intersections[corner_index[i]].x ||
            candidate.corners[i].y!=candidate.intersections[corner_index[i]].y) return 0;
    /* The delivered validator owns geometric reasonableness. Presence/bounds
     * checks above cannot stand in for its convexity/aspect/area rules. */
    if (s->providers.qc(s->providers.context,r,&candidate)!=1) return 0;
    s->cached=candidate; s->has_cached=1;
    *out=candidate;
    return 1;
}
int xqgeo_init(xqgeo_state *s, const xqgeo_providers *p, uint16_t threshold)
{
    if (!s) return 0;
    memset(s,0,sizeof(*s));
    if (!p || !p->qc || !threshold || threshold>1000) return 0;
    s->providers=*p; s->threshold=threshold;
    return 1;
}
xqgeo_event xqgeo_capture(xqgeo_state *s, const xqgeo_request *r, Geometry *out)
{
    if (!out) return XQGEO_BAD_REQUEST;
    memset(out,0,sizeof(*out));
    if (!s || !s->providers.qc || !request_valid(r) || r->capture_id<=s->last_capture_id)
        return XQGEO_BAD_REQUEST;
    s->last_capture_id=r->capture_id; s->last_frame_id=r->frame->frame_id;
    if (produced(s,r,s->providers.board_model,XQGEO_BOARD_MODEL,out)) {
        s->board_failures=0;
        return XQGEO_OK;
    }
    if (s->board_failures<3) ++s->board_failures;
    if (s->board_failures<3) return XQGEO_RETAKE;
    if (produced(s,r,s->providers.piece_fit,XQGEO_PIECE_FIT,out)) return XQGEO_OK;
    return XQGEO_MANUAL_REQUIRED;
}
xqgeo_event xqgeo_use_manual(xqgeo_state *s, const xqgeo_request *r, Geometry *out)
{
    if (!out) return XQGEO_BAD_REQUEST;
    memset(out,0,sizeof(*out));
    if (!s || !s->providers.qc || !request_valid(r) ||
        r->capture_id!=s->last_capture_id || r->frame->frame_id!=s->last_frame_id)
        return XQGEO_BAD_REQUEST;
    return produced(s,r,s->providers.manual,XQGEO_MANUAL,out)?XQGEO_OK:XQGEO_MANUAL_REQUIRED;
}
int xqgeo_cached(const xqgeo_state *s, Geometry *out)
{
    if (!out) return 0;
    memset(out,0,sizeof(*out));
    if (!s || !s->has_cached) return 0;
    *out=s->cached; out->source=XQGEO_CACHED;
    return 1;
}
const char *xqgeo_source_name(xqgeo_source source)
{
    switch (source) {
    case XQGEO_BOARD_MODEL: return "board_model";
    case XQGEO_PIECE_FIT: return "piece_fit";
    case XQGEO_CACHED: return "cached";
    case XQGEO_MANUAL: return "manual";
    default: return "none";
    }
}
