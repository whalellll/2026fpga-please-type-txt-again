#ifndef PICTURE_GRAPH_OPS_H
#define PICTURE_GRAPH_OPS_H
#include <stddef.h>
#include <stdint.h>
/* r24 first-batch operator library only. It is deliberately not an XQGRPH2
 * loader: whole-graph selection awaits the training-side second batch.
 * Concat follows spec section2; bilinear follows the authoritative Oct25
 * ruling (weight sum16, shift4). Invalid first-batch vectors are excluded
 * only under that ruling. Whole-graph product selection still awaits batch2.
 * All buffers are ordinary, disjoint RAM in contiguous NCHW order. */
typedef struct {
    const int16_t *data;
    size_t count;
    unsigned batch,channels,height,width;
    int exponent;
} xqg_s16_view;
typedef struct {
    const int16_t *data;
    size_t count;
    int input_exponent,output_exponent;
} xqg_s16_lut;
/* Types: 3 sigmoid, 4 maxpool5/s1/p2, 5 nearest2x, 6 bilinear2x,
 * 7 channel concat, 8 residual add, 9 GAP, 10 identity, 11 ReLU.
 * Output view is cleared on failure. No allocation, FP32, recalibration,
 * hidden fallback or inferred sigmoid table. Type12 is an FP32 boundary. */
int xqg_op_run(unsigned type,const xqg_s16_view *inputs,unsigned input_count,
               int16_t *output,size_t capacity,const xqg_s16_lut *lut,
               xqg_s16_view *result);
#endif
