#ifndef XQ_NATIVE_POST_H
#define XQ_NATIVE_POST_H
#include "xq_roi.h"
/* C ports of delivered line_refinement/automatic_orientation; experimental
 * until full host/device conformance. The Q16 geometry reference is included
 * unchanged in the implementation. No tracked FEN is used for inference. */
typedef struct {unsigned crossings,inliers;double median_residual,p95_residual;} xnp_refinement;
/* Stable Scheme A filter after detector NMS/original-coordinate mapping.
 * fused_score=detector_score*softmax <= detector_score. Preserve .05 ties.
 * No spatial filtering: it would change rejection/refinement evidence. */
int xnp_filter_candidates(xqr_box *,unsigned *count);
int xnp_load_rng(const char *,uint8_t data[91][240][4]);
int xnp_refine(const uint8_t *rgb,const double coarse[4][2],const xqr_box *,unsigned,
               const uint8_t rng[91][240][4],double refined[4][2],xnp_refinement *);
/* Original 240-trial/full-frame implementation, retained for offline controls. */
int xnp_refine_full(const uint8_t *,const double [4][2],const xqr_box *,unsigned,
                    const uint8_t [91][240][4],double [4][2],xnp_refinement *);
int xnp_coarse(const double corners[4][2],double image_h[9],xqr_roi *);
/* Strict candidate only: unknown orientation, off-grid, .10 boundary margin,
 * duplicate cells, invalid camps or piece counts reject instead of emitting FEN.
 * output corners are GUI a0,i0,i9,a9, pieces use red's bottom rank=0. */
int xnp_finish(const double corners[4][2],const xqr_box *,unsigned,
               uint32_t frame,xqv_result *,double gui_corners[4][2]);
#endif
