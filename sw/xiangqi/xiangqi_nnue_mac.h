#ifndef XIANGQI_NNUE_MAC_H
#define XIANGQI_NNUE_MAC_H

#include "mac_accel_kernel.h"

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
typedef void (*xiangqi_nnue_cache_sync_fn)(
    void *ctx, void *buffer, size_t bytes);

typedef struct {
    uintptr_t reg_base;

    uint32_t input_addr;
    uint32_t weight_addr;
    uint32_t bias_addr;
    uint32_t output_addr;

    uint8_t *input_buffer;
    uint8_t *weight_buffer;
    uint8_t *bias_buffer;
    uint8_t *output_buffer;
    size_t input_capacity;
    size_t weight_capacity;
    size_t bias_capacity;
    size_t output_capacity;

    uint32_t timeout_polls;
    xiangqi_nnue_cache_sync_fn cache_clean;
    xiangqi_nnue_cache_sync_fn cache_invalidate;
    void *cache_ctx;

    uint32_t completed_jobs;
    uint32_t failed_jobs;
    uint32_t last_cycles;
    int last_result;
} xiangqi_nnue_mac_t;

/* Pack one GUI feature-accumulation request into the kernel DDR layout. */
int xiangqi_nnue_mac_prepare(
    xiangqi_nnue_mac_t *mac,
    const int8_t *feature_weights,
    const size_t *feature_offsets,
    int feature_count,
    int hidden,
    mac_kernel_job_t *job);

/* NnueInt8AccumBackend-compatible callback. Returns 1 on hardware success. */
int xiangqi_nnue_mac_accum(
    void *ctx,
    const int8_t *feature_weights,
    const size_t *feature_offsets,
    int feature_count,
    int hidden,
    int32_t *out);

/* Pack a batch of sibling-position deltas. Delta rows are position-major. */
int xiangqi_nnue_mac_prepare_batch_delta(
    xiangqi_nnue_mac_t *mac,
    const int8_t *feature_weights,
    const size_t *feature_offsets,
    const int8_t *deltas,
    int positions,
    int feature_count,
    int hidden,
    const int32_t *bias,
    mac_kernel_job_t *job);

/* Compute out[position][lane] = bias[lane] + delta[position] * weights. */
int xiangqi_nnue_mac_batch_delta(
    xiangqi_nnue_mac_t *mac,
    const int8_t *feature_weights,
    const size_t *feature_offsets,
    const int8_t *deltas,
    int positions,
    int feature_count,
    int hidden,
    const int32_t *bias,
    int32_t *out);

#ifdef __cplusplus
}
#endif

#endif
