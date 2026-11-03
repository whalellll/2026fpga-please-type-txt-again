#ifndef XQ_BOARD_GRID_RECOVERY_H
#define XQ_BOARD_GRID_RECOVERY_H
#include <stddef.h>
#include <stdint.h>
typedef struct {
    unsigned attempted,used,corner,edges,normal0,normal1,cancelled;
    double score;
} xqgrid_stats;
/* Experimental current-frame corner proposal, before detector ROI selection.
 * RGB is exactly 1280x720 RGB8. Corners are normalized TL/TR/BR/BL, as emitted
 * by the immutable board model. At most one corner changes. No piece/position
 * input, previous frame, manual coordinate, weights or refinement gate.
 * 1 = valid output (possibly unchanged); 0 = invalid/OOM/cancel, output zero.
 * Input/output corners may alias. No device access. Caller owns RGB lifetime. */
int xqgrid_recover(const uint8_t *,size_t,const float [8],float [8],
                   int (*cancelled)(void *),void *,xqgrid_stats *);
#endif
