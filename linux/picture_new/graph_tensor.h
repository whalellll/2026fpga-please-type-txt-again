#ifndef PICTURE_GRAPH_TENSOR_H
#define PICTURE_GRAPH_TENSOR_H
#include <stddef.h>
#include <stdint.h>
/* Owned NCHW carrier. q16 is exact delivered output_q at exponent, never a
 * recalibration. f32 is created only for an unchanged FP32 operator/output.
 * Both may coexist for fanout; clear exactly once after the final use. */
typedef struct {
    int16_t *q16;
    float *f32;
    size_t count;
    int exponent;
} xqg_tensor;
void xqg_tensor_clear(xqg_tensor *);
const float *xqg_tensor_float(xqg_tensor *);
int xqg_tensor_quantize(const xqg_tensor *,int exponent,int8_t *);
static inline int16_t xqg_pre_value(int32_t value,unsigned shift)
{
    /* I32 / 2^32 rounds to zero, including the INT32_MIN halfway tie. */
    if(shift>=32)return 0;
    if(!shift)return value>32767?32767:value< -32768?-32768:(int16_t)value;
    uint32_t mag=value<0?0u-(uint32_t)value:(uint32_t)value;
    uint32_t q=mag>>shift,half=1u<<(shift-1),rem=mag&((1u<<shift)-1u);
    if(rem>half || (rem==half && (q&1u)))++q;
    uint32_t limit=value<0?32768u:32767u;if(q>limit)q=limit;
    return (int16_t)(value<0?-(int32_t)q:(int32_t)q);
}
#endif
