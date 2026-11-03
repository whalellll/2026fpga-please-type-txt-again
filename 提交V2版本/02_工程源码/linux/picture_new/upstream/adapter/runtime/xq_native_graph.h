#ifndef XQ_NATIVE_GRAPH_H
#define XQ_NATIVE_GRAPH_H
#include "xq_int8_layer.h"
typedef struct xqn_model xqn_model;
typedef void (*xqn_observer)(void *,unsigned,const int8_t *,size_t,const int16_t *,size_t,const int32_t *,const int16_t *);
void xqn_observe(xqn_model *,xqn_observer,void *);
xqn_model *xqn_load(const char *path);
void xqn_free(xqn_model *);
/* Dynamic batch for classifier only. output pointers owned by the model until
 * next run/free, NCHW, F32. No CPU fallback from a driver error. */
int xqn_run(xqn_model *,const xqm_transport *,unsigned batch,const float *,
             int cpu_reference,xqm_stats *);
const float *xqn_output(const xqn_model *,unsigned index,unsigned dims[4]);
/* Board host decode preserves delivered spatial maps + broad prior, then
 * outputs normalized TL,TR,BR,BL coordinates. Non-MAC FP32 is explicit. */
int xqn_board_corners(const xqn_model *,float corners[8]);
#endif
