#ifndef PICTURE_HWC_INPUT_QUANT_H
#define PICTURE_HWC_INPUT_QUANT_H
#include <stddef.h>
#include <stdint.h>
typedef struct {uint32_t keys[512];int8_t values[512];int exponent;} xqih_input_table;
/* Per-inference, reentrant cache of the exact frozen byte/255.f quantizer.
 * Unknown binary32 values use the original quantizer, including NaN/error.
 * Failure leaves the same output prefix as xqi_quantize; caller owns discard. */
int xqih_input_table_init(xqih_input_table *,int);
int xqih_input_quantize(const xqih_input_table *,const float *,size_t,int8_t *);
#endif
