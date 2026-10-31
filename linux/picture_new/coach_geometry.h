#ifndef XQCOACH_GEOMETRY_H
#define XQCOACH_GEOMETRY_H
#include "coach_protocol.h"
#include "xq_native_post.h"
/* Compile coach_geometry.c INSTEAD OF xq_native_post.c. It includes that
 * immutable implementation and reuses the exact same private project/rounding
 * arithmetic. Strict refinement must already have passed on this capture.
 * All candidates must pass the original orientation and .10 margin guards;
 * duplicates and class-count limits are deliberately deferred to xy_repair.
 * Failure leaves *out untouched. No previous board or geometry is consulted. */
int xqcoach_map_candidates(const double corners[4][2],const xqr_box *,unsigned,
                           const xqcoach_identity *,xqcoach_result *);
/* Product-only estimate after strict refinement rejection. Coarse orientation
 * is still required; out-of-board candidates remain unmapped (255/255).
 * No strict success, previous-frame geometry, invented pieces or guard pass. */
int xqcoach_estimate_candidates(const double corners[4][2],const xqr_box *,unsigned,
                           const xqcoach_identity *,xqcoach_result *);
/* Optional grid-worker safeguard. A same-frame model proposal is tried only
 * if every candidate passes the existing strict mapping guards. Its refinement
 * and final mapping must also pass unchanged; otherwise retain the grid path.
 * No board layout, piece count, history or relaxed geometry gate is consulted.
 * Cancellation invalidates the attempt. used_model is zero on grid fallback. */
int xqcoach_refine_model_first(const uint8_t *,const double grid[4][2],
    const double model[4][2],const xqr_box *,unsigned,const uint8_t [91][240][4],
    const xqcoach_identity *,double [4][2],xnp_refinement *,
    int (*cancelled)(void *),void *,unsigned *used_model);
#endif
