#ifndef XQ_GRAPH_RGB8_H
#define XQ_GRAPH_RGB8_H
#include "xq_native_graph.h"
#include <stddef.h>
#include <stdint.h>

#define XQ_RGB8_DETECTOR_INPUT_BYTES (3u*640u*640u)
/* Explicit candidate entry, available only with XQ_HWC_RGB8_DIRECT=1.
 * Input is the current detector preprocessing's RGB uint8 NCHW tensor, not
 * an arbitrary F32 tensor or an interleaved camera image. No CPU fallback.
 * General argument rejection matches xqn_run before output invalidation;
 * an accepted HWC request invalidates old heads even if its byte length fails. */
int xqn_run_rgb8(xqn_model *,const xqm_transport *,unsigned batch,const uint8_t *,
                 size_t bytes,int cpu_reference,xqm_stats *);
#endif
