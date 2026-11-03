#ifndef VISION32_ABI_H
#define VISION32_ABI_H
#include <stdint.h>
/* Relative to MAC+0x40. This ID rejects the old ABI3 conv driver. */
#define VISION32_ID UINT32_C(0x56333231)
#define VISION32_VERSION UINT32_C(0x00010000)
#define VISION32_REG_ID 0x00u
#define VISION32_REG_STATUS 0x04u
#define VISION32_REG_CONTROL 0x08u
#define VISION32_REG_INDEX 0x0cu
#define VISION32_REG_CONFIG 0x10u
#define VISION32_REG_CYCLES 0x14u
#define VISION32_REG_READ_BYTES 0x18u
#define VISION32_REG_WRITE_BYTES 0x1cu
#define VISION32_REG_MAC_CYCLES 0x20u
#define VISION32_REG_ERROR 0x24u
#define VISION32_START 1u
#define VISION32_ABORT 2u
#define VISION32_CLEAR 4u
#define VISION32_BUSY 1u
#define VISION32_DONE 2u
#define VISION32_ERROR 4u
#define VISION32_ABORT_DRAIN 16u
#define VISION32_LUT 1u
#define VISION32_RAW_I32 2u
/* All addresses physical, aligned4 and bounded by the hardware aperture.
 * Input NHWC with channels rounded to4; padding is signed INT8 zero.
 * Weights: [ceil(Cout/8)][KY][KX][Cin][OC8], signed bytes, tail OC zero.
 * Params: [ceil(Cout/8)][OC8] records below; padded records must be valid.
 * Output compact NHWC, one byte (or raw diagnostic signed32) per element.
 * Output may not overlap any input/model/parameter/table range.
 * Configuration writes during BUSY are ignored. A cancelled operation may
 * have partial output: publish only DONE with ERROR=0 for the matching frame.
 * No cache survives a layer; every START reloads its configured model data.
 */
struct vision32_descriptor {
 uint32_t input,weights,output,params,lut;
 uint32_t width,height,cin,cout,kernel,stride,padding;
 uint32_t flags,timeout_cycles,model_generation,frame_id;
};
struct vision32_quant {
 int32_t bias;
 uint32_t multiplier; /* 0..0x7fffffff */
 uint32_t shift;      /* 0..62; nearest, half away from zero */
};
/* q=saturate_s8(round_away((dot+bias)*multiplier / 2^shift)).
 * LUT mode returns table[(uint8_t)q]. Table has256 bytes. Calibrated SiLU
 * tables are supplied by the quantized model; no implicit ReLU/sigmoid.
 * RAW_I32 bypasses bias/quant/LUT and returns exact signed INT32 dot values.
 */
enum vision32_error {
 VISION32_OK=0, VISION32_BAD_GEOMETRY=1, VISION32_BAD_RANGE=2,
 VISION32_BUS_ERROR=3, VISION32_CANCELLED=4, VISION32_TIMEOUT=5,
 VISION32_BAD_QUANT=6
};
#endif
