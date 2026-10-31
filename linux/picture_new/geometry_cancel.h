#ifndef XQ_GEOMETRY_CANCEL_H
#define XQ_GEOMETRY_CANCEL_H
#include "xq_native_post.h"
enum {
    XQGC_START=1,XQGC_GRAY,XQGC_PIECES,XQGC_PREFIX_COLUMN,XQGC_PREFIX_ROW,
    XQGC_REDUCTION,XQGC_CONTRAST,XQGC_MASK,XQGC_SCORE,XQGC_GRID,
    XQGC_RANSAC,XQGC_REFIT,XQGC_FINAL
};
/* Optional current-call cancellation only. No shared/TLS state. Interrupted
 * work returns0 with zero corners/statistics, after freeing all scratch.
 * Without cancellation, preserve every original result/statistic bit. */
int xqcoach_refine_cancellable(const uint8_t *,const double [4][2],const xqr_box *,unsigned,
    const uint8_t [91][240][4],double [4][2],xnp_refinement *,int (*)(void *),void *);
#ifndef XQGC_NOTE
#define XQGC_NOTE(phase,index) ((void)0)
#endif
typedef struct {int (*cancelled)(void *);void *context;int stopped;} xqgeom_cancel_state;
static inline int xqgeom_cancel_poll(xqgeom_cancel_state *s,unsigned phase,size_t index)
{
    (void)phase;(void)index;
    if(!s || !s->cancelled)return 0;
    XQGC_NOTE(phase,index);
    if(!s->stopped && s->cancelled(s->context))s->stopped=1;
    return s->stopped;
}
#endif
