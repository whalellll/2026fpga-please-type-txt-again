#ifndef XQ_NATIVE_GEOMETRY_H
#define XQ_NATIVE_GEOMETRY_H
#include "xq_roi.h"
/* Native FP64 sidecar. Keep the delivered binary64 producer output intact;
 * never round it into the older fixed-point Geometry preparation interface. */
typedef enum { XNG_NONE, XNG_BOARD_MODEL, XNG_PIECE_FIT, XNG_MANUAL, XNG_CACHED } xng_source;
typedef enum { XNG_OK, XNG_RETAKE, XNG_MANUAL_REQUIRED, XNG_BAD_REQUEST } xng_event;
typedef struct {
    double corners[4][2];
    uint64_t token;
    uint32_t frame,crc;
    xng_source source;
    unsigned kept;
    double p95;
} xng_geometry;
typedef struct {
    uint64_t token;
    uint32_t frame,crc;
    unsigned failures,active,resolved,has_cached;
    xng_geometry cached;
} xng_state;
int xng_begin(xng_state *,uint64_t token,uint32_t frame,uint32_t crc);
xng_event xng_resolve(xng_state *,const double board[4][2],int board_valid,
                     const xqr_box *,unsigned,const double current_seed[4][2],xng_geometry *);
/* Manual is explicit, for exactly the active frozen capture. Cached is only
 * diagnostic; neither cached coordinates nor tracked opening pieces seed fit. */
xng_event xng_manual(xng_state *,uint64_t,uint32_t,uint32_t,const double [4][2],xng_geometry *);
int xng_cached(const xng_state *,xng_geometry *);
int xng_read_manual(const char *,uint64_t,uint32_t,uint32_t,double [4][2]);
const char *xng_source_name(xng_source);
#endif
