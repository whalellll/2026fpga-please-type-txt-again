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
#endif
