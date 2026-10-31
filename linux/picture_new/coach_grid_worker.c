#define _POSIX_C_SOURCE 200809L
/* Explicit experimental worker entry. Immutable upstream worker/math remain
 * unchanged; only RGB lifetime and the corner proposal seam are adapted. */
#include "xq_native_graph.h"
#include "xq_roi.h"
#include "board_grid_recovery.h"
#include "coach_geometry.h"
#if defined(XQ_GEOMETRY_CANCEL) && XQ_GEOMETRY_CANCEL
#include "geometry_cancel.h"
#endif
#include <stdlib.h>
#ifndef XQ_GRID_MODEL_GUARD
#define XQ_GRID_MODEL_GUARD 0
#endif
#if XQ_GRID_MODEL_GUARD != 0 && XQ_GRID_MODEL_GUARD != 1
#error XQ_GRID_MODEL_GUARD_must_be_zero_or_one
#endif
static const uint8_t *grid_current_rgb;
static int grid_rgb565(const xqv_frame *,uint8_t *,size_t);
static int grid_corners(const xqn_model *,float [8]);
static void grid_free(void *);
#if defined(XQ_BOARD_EXPOSURE_R27) && XQ_BOARD_EXPOSURE_R27
static void grid_exposure_refresh(const uint8_t *);
#define XQ_BOARD_EXPOSURE_REFRESH grid_exposure_refresh
#endif
#if XQ_GRID_MODEL_GUARD
static const uint8_t *grid_original_rgb;
static double grid_original_corners[4][2];
#endif
#if XQ_GRID_MODEL_GUARD || (defined(XQ_GEOMETRY_CANCEL) && XQ_GEOMETRY_CANCEL)
static int grid_refine(const uint8_t *,const double [4][2],const xqr_box *,unsigned,
    const uint8_t [91][240][4],double [4][2],xnp_refinement *);
#define xnp_refine grid_refine
#endif
#define xqr_rgb565 grid_rgb565
#define xqn_board_corners grid_corners
#define free grid_free
#if (defined(XQ_DETECTOR_LAZY_BOX) && XQ_DETECTOR_LAZY_BOX) || \
    (defined(XQ_HWC_RGB8_DIRECT) && XQ_HWC_RGB8_DIRECT)
#include "coach_decode_worker.c"
#else
#include "../../artifacts/vision-model-20261020-adapter/runtime/xq_native_worker.c"
#endif
#undef free
#undef xqn_board_corners
#undef xqr_rgb565
#if XQ_GRID_MODEL_GUARD || (defined(XQ_GEOMETRY_CANCEL) && XQ_GEOMETRY_CANCEL)
#undef xnp_refine
#endif
static int grid_rgb565(const xqv_frame *frame,uint8_t *rgb,size_t bytes)
{
    grid_current_rgb=NULL;
#if XQ_GRID_MODEL_GUARD
    grid_original_rgb=NULL;
#endif
    int okay=xqr_rgb565(frame,rgb,bytes);
    if(okay)grid_current_rgb=rgb;
    return okay;
}
#if defined(XQ_BOARD_EXPOSURE_R27) && XQ_BOARD_EXPOSURE_R27
static void grid_exposure_refresh(const uint8_t *rgb)
{
    grid_current_rgb=rgb;
#if XQ_GRID_MODEL_GUARD
    grid_original_rgb=NULL;
#endif
}
#endif
static void grid_free(void *p)
{
    if(p==grid_current_rgb)grid_current_rgb=NULL;
#if XQ_GRID_MODEL_GUARD
    if(p==grid_original_rgb)grid_original_rgb=NULL;
#endif
    free(p);
}
static int grid_corners(const xqn_model *model,float output[8])
{
    const uint8_t *rgb=grid_current_rgb;grid_current_rgb=NULL;
    float original[8];xqgrid_stats stats;
    if(!rgb || !xqn_board_corners(model,original))return 0;
    uint64_t start=now_ms();
    int okay=xqgrid_recover(rgb,1280u*720u*3u,original,output,cancelled,NULL,&stats);
    uint64_t end=now_ms();
#if XQ_GRID_MODEL_GUARD
    if(okay && stats.used){
        for(unsigned i=0;i<4;i++){
            grid_original_corners[i][0]=(double)original[2*i]*1280-.5;
            grid_original_corners[i][1]=(double)original[2*i+1]*720-.5;
        }
        grid_original_rgb=rgb;
    }
#endif
    printf("XQ_NATIVE_GRID_RECOVERY okay=%u attempted=%u used=%u edges=%u elapsed_ms=%llu\n",
        okay!=0,stats.attempted,stats.used,stats.edges,(unsigned long long)(end>=start?end-start:0));
    return okay;
}
#if XQ_GRID_MODEL_GUARD || (defined(XQ_GEOMETRY_CANCEL) && XQ_GEOMETRY_CANCEL)
static int grid_refine(const uint8_t *rgb,const double coarse[4][2],const xqr_box *boxes,
    unsigned n,const uint8_t rng[91][240][4],double refined[4][2],xnp_refinement *stats)
{
#if XQ_GRID_MODEL_GUARD
    const double (*original)[2]=rgb==grid_original_rgb?grid_original_corners:NULL;
    grid_original_rgb=NULL; /* Consume once; never reuse another frame's proposal. */
#else
    const double (*original)[2]=NULL;
#endif
    if(!original){
#if defined(XQ_GEOMETRY_CANCEL) && XQ_GEOMETRY_CANCEL
        return xqcoach_refine_cancellable(rgb,coarse,boxes,n,rng,refined,stats,cancelled,NULL);
#else
        return xnp_refine(rgb,coarse,boxes,n,rng,refined,stats);
#endif
    }
    unsigned used=0;
    int okay=xqcoach_refine_model_first(rgb,coarse,original,boxes,n,rng,
        &coach_partial.identity,refined,stats,cancelled,NULL,&used);
    printf("XQ_NATIVE_GRID_MODEL_GUARD okay=%u used_model=%u\n",okay!=0,used);
    return okay;
}
#endif
