#ifndef XQ_INT8_LAYER_H
#define XQ_INT8_LAYER_H
#include "xq_mac.h"
/* Adapter-owned code. Frozen tensors are NCHW/OIHW. All channels use the
 * delivered input/pre/output exponents, right shifts and 65536-byte LUT.
 * NULL transport is rejected unless the caller explicitly selects CPU_REFERENCE.
 * Device errors never cause a CPU fallback. Buffers are ordinary RAM only. */
typedef struct {
    unsigned batch,cin,height,width,cout,kh,kw;
    unsigned stride_h,stride_w,pad_h,pad_w,dilation_h,dilation_w;
    unsigned linear,cpu_reference;
} xqi_shape;
/* Output buffers have batch*cout*oh*ow elements (NCHW), linear batch*cout.
 * A failed call publishes no usable result. output_q uses I16 storage for both
 * S8 LUT outputs and S16 Identity heads. Per-job sums/bias are checked for I32.
 * accumulator/preactivation can be NULL for the memory-bounded graph runner.
 */
int xqi_layer(const xqm_transport *,const xqi_shape *,const int8_t *input,
              const int8_t *weight,const int32_t *bias,const int64_t *shifts,
              const int8_t *lut,size_t lut_bytes,int32_t *accumulator,
              int16_t *preactivation,int16_t *output_q,xqm_stats *);
/* Finite float->S8, ties to even, saturation. No dependence on libc rounding
 * mode; scale is a delivered power of two, not newly calibrated. */
int xqi_quantize(const float *,size_t,int exponent,int8_t *);
int xqi_dequantize(const int16_t *,size_t,int exponent,float *);
#endif
