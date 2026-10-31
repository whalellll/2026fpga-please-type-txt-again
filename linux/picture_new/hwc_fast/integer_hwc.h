#ifndef INTEGER_HWC_H
#define INTEGER_HWC_H
#include "xq_mac.h"
#include <stddef.h>
#include <stdint.h>
typedef struct {void *data;unsigned c,h,w,pitch,bits;int exponent;} xi8_tensor;
typedef struct xi8_model xi8_model;
typedef struct {
 uint64_t jobs,cycles,pack_ticks,output_ticks,weight_ticks,ioctl_ticks,ops_ticks,allocate_ticks;
 uint64_t converted_input_values,copied_input_bytes,output_bytes;
 uint64_t input_zero_bytes,output_word_values,reused_tensor_bytes,allocated_tensor_bytes,peak_tensor_bytes;
} xi8_stats;
void xi8_clock_init(void);
uint64_t xi8_now(void);
uint64_t xi8_us(uint64_t);
xi8_model *xi8_load(const char *);
void xi8_free(xi8_model *);
int xi8_input_load(xi8_model *,const char *,xi8_tensor *);
void xi8_tensor_free(xi8_tensor *);
int xi8_run(xi8_model *,const xqm_transport *,const xi8_tensor *,xi8_stats *);
/* Explicit graph OUTPUT boundary, not called by the integer graph itself.
 * Encode the original S16 heads as NCHW IEEE-F32 for oracle/decoder use. */
int xi8_export_f32(const xi8_model *,unsigned,void *,size_t,unsigned dims[4]);
size_t xi8_output_elements(const xi8_model *,unsigned);
#endif
