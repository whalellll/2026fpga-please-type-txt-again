#ifndef PICTURE_GRAPH_BILINEAR_S16_H
#define PICTURE_GRAPH_BILINEAR_S16_H
#include "graph_tensor.h"
/* Exact equivalent of frozen FP32 half-pixel bilinear2x for a normal finite
 * S16/power-of-two parent. No S16 rounding of the result: outputs remain F32.
 * Ineligible input returns0 before touching output, so caller uses frozen op. */
int xqg_bilinear_s16_eligible(const xqg_tensor *,unsigned,unsigned,unsigned,unsigned);
int xqg_bilinear_s16(const xqg_tensor *,unsigned,unsigned,unsigned,unsigned,float *);
#endif
