#ifndef XQ_GEOMETRY_H
#define XQ_GEOMETRY_H
#include "xq_vision.h"

/* Geometry sidecar; recognizer ABI 1 and P19 xq_grid remain unchanged.
 * No projection, rounding, QC thresholds or fitting algorithm lives here.
 * Delivered C references must populate coordinates losslessly and perform QC.
 * Coordinate = raw / 2^fraction_bits in original 1280x720 pixels.
 * A delivery requiring another representation needs an explicit adaptation. */
typedef struct { int32_t x, y; } xqgeo_point;
typedef enum { XQGEO_NONE, XQGEO_BOARD_MODEL, XQGEO_PIECE_FIT,
               XQGEO_CACHED, XQGEO_MANUAL } xqgeo_source;
typedef struct {
    xqgeo_point corners[4];       /* a0, i0, i9, a9 */
    xqgeo_point intersections[90]; /* rank*9+file, a0 is red's bottom left */
    uint64_t capture_id;          /* process-local strictly increasing token */
    uint32_t frame_id;            /* hardware counter may reset per session */
    xqgeo_source source;
    uint16_t confidence;          /* permille [0,1000], from producer */
    uint8_t fraction_bits;        /* [0,20], preserves delivered fixed point */
} Geometry;
typedef struct {
    const xqv_frame *frame;        /* immutable ordinary RAM snapshot */
    const xq_search_board_t *reference; /* current tracked board, never opening-only */
    uint64_t capture_id;
} xqgeo_request;
/* 1 = produced/QC passed; every other return value is failure. There are no
 * production providers until Round2 references and bit-exact tests arrive. */
typedef int (*xqgeo_produce_fn)(void *, const xqgeo_request *, Geometry *);
typedef int (*xqgeo_qc_fn)(void *, const xqgeo_request *, const Geometry *);
typedef struct {
    xqgeo_produce_fn board_model, piece_fit, manual;
    xqgeo_qc_fn qc;               /* shared delivered convexity/aspect/area QC */
    void *context;
} xqgeo_providers;
typedef enum { XQGEO_OK, XQGEO_RETAKE, XQGEO_MANUAL_REQUIRED,
               XQGEO_BAD_REQUEST } xqgeo_event;
typedef struct {
    xqgeo_providers providers;
    Geometry cached;
    uint64_t last_capture_id;
    uint32_t last_frame_id;
    uint16_t threshold;
    unsigned board_failures, has_cached;
} xqgeo_state;

int xqgeo_init(xqgeo_state *, const xqgeo_providers *, uint16_t threshold);
/* One call per new Space capture; no internal retry, sleep or auto-capture.
 * Each frame tries board_model first. Failures 1/2 -> RETAKE; 3+ -> piece_fit
 * using the supplied current reference; unavailable/failing fit -> manual.
 * Failure always clears out, so stale geometry cannot advance the game. */
xqgeo_event xqgeo_capture(xqgeo_state *, const xqgeo_request *, Geometry *out);
xqgeo_event xqgeo_use_manual(xqgeo_state *, const xqgeo_request *, Geometry *out);
/* Cached is diagnostic-only, retains original frame/token. It is never an
 * automatic capture fallback: a moved board must not reuse yesterday's grid. */
int xqgeo_cached(const xqgeo_state *, Geometry *out);
const char *xqgeo_source_name(xqgeo_source);
#endif
