#define _POSIX_C_SOURCE 200809L
/* Explicit experimental worker entry. Immutable upstream worker/math remain
 * unchanged; only RGB lifetime and the corner proposal seam are adapted. */
#include "xq_native_graph.h"
#include "xq_roi.h"
#include "board_grid_recovery.h"
#include <stdlib.h>
static const uint8_t *grid_current_rgb;
static int grid_rgb565(const xqv_frame *,uint8_t *,size_t);
static int grid_corners(const xqn_model *,float [8]);
static void grid_free(void *);
#define xqr_rgb565 grid_rgb565
#define xqn_board_corners grid_corners
#define free grid_free
#include "../../artifacts/vision-model-20261020-adapter/runtime/xq_native_worker.c"
#undef free
#undef xqn_board_corners
#undef xqr_rgb565
static int grid_rgb565(const xqv_frame *frame,uint8_t *rgb,size_t bytes)
{
    grid_current_rgb=NULL;
    int okay=xqr_rgb565(frame,rgb,bytes);
    if(okay)grid_current_rgb=rgb;
    return okay;
}
static void grid_free(void *p)
{
    if(p==grid_current_rgb)grid_current_rgb=NULL;
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
    printf("XQ_NATIVE_GRID_RECOVERY okay=%u attempted=%u used=%u edges=%u elapsed_ms=%llu\n",
        okay!=0,stats.attempted,stats.used,stats.edges,(unsigned long long)(end>=start?end-start:0));
    return okay;
}
