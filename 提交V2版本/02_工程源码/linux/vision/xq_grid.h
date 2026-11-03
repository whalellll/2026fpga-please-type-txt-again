#ifndef XQ_GRID_H
#define XQ_GRID_H
#include "xq_vision.h"
/* Detector geometry is a sidecar; the frozen recognizer ABI 1 is unchanged.
 * Coordinates refer to the original 1280x720 frame, never a letterbox. */
typedef struct {
    double x, y;
    uint16_t x0, y0, x1, y1, confidence;
    uint8_t class_id;
} xqg_detection;
typedef struct { double h[8]; unsigned valid; } xqg_grid;
int xqg_corners(xqg_grid *, const double corners[4][2]); /* a0,i0,i9,a9 */
int xqg_project(const xqg_grid *, double file, double rank, double *x, double *y);
int xqg_map(const xqg_grid *, const xqg_detection *, unsigned count,
            uint32_t frame, xqv_result *);
/* Opening: use four rooks to seed, then fit all 32 centers and verify exact
 * reference occupancy. Current board: refit an existing grid; reject ambiguous
 * associations. A large displacement needs the four-corner fallback. */
int xqg_fit(xqg_grid *, const xqg_detection *, unsigned count,
            const xq_search_board_t *reference, uint32_t frame);
/* Explicit synthetic geometry for the file stub, never measured boxes. */
void xqg_stub_geometry(const xqv_result *, xqg_detection *);
#endif
