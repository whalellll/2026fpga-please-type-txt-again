#include "xiangqi_nnue_mac.h"

#include <string.h>

enum {
    XIANGQI_NNUE_MAX_FEATURES = 32,
    XIANGQI_NNUE_MAX_HIDDEN = 256,
    /* Worst-case staged DMA buffers: pixels(1..16) * ci(8) * 8 for input,
     * co(8) * ci(8) * 128 for weights and co(8) * 192 for the 48-bit bias
     * packing at MAX_FEATURES/MAX_HIDDEN. */
    XIANGQI_NNUE_INPUT_STAGE_BYTES = 16u * 8u * 8u,
    XIANGQI_NNUE_WEIGHT_STAGE_BYTES = 8u * 8u * 128u,
    XIANGQI_NNUE_BIAS_STAGE_BYTES = 8u * 192u
};

static int buffers_fit(
    const xiangqi_nnue_mac_t *mac,
    const mac_kernel_buffer_sizes_t *sizes) {
    return mac->input_buffer != NULL && mac->weight_buffer != NULL &&
           (sizes->bias_bytes == 0u || mac->bias_buffer != NULL) &&
           mac->output_buffer != NULL &&
           mac->input_capacity >= sizes->input_bytes &&
           mac->weight_capacity >= sizes->weight_bytes &&
           mac->bias_capacity >= sizes->bias_bytes &&
           mac->output_capacity >= sizes->output_bytes;
}

int xiangqi_nnue_mac_prepare(
    xiangqi_nnue_mac_t *mac,
    const int8_t *feature_weights,
    const size_t *feature_offsets,
    int feature_count,
    int hidden,
    mac_kernel_job_t *job) {
    mac_kernel_buffer_sizes_t sizes;
    int ci_tiles;
    int co_tiles;

    if (mac == NULL || feature_weights == NULL || feature_offsets == NULL ||
        job == NULL || feature_count <= 0 ||
        feature_count > XIANGQI_NNUE_MAX_FEATURES ||
        (hidden != 128 && hidden != XIANGQI_NNUE_MAX_HIDDEN)) {
        return MAC_KERNEL_ERR_ARGUMENT;
    }

    memset(job, 0, sizeof(*job));
    job->pixels = 1u;
    job->cin = (uint16_t)feature_count;
    job->cout = (uint16_t)hidden;
    job->compute_mode = MAC_KERNEL_MODE_U8_S8;
    job->activation = MAC_KERNEL_ACT_NONE;
    job->output_format = MAC_KERNEL_OUT_I32;
    job->zero_bias = 1u;
    job->input_addr = mac->input_addr;
    job->weight_addr = mac->weight_addr;
    job->bias_addr = mac->bias_addr;
    job->output_addr = mac->output_addr;

    if (mac_kernel_validate_job(job) != MAC_KERNEL_OK)
        return MAC_KERNEL_ERR_ARGUMENT;

    sizes = mac_kernel_buffer_sizes(job);
    if (!buffers_fit(mac, &sizes))
        return MAC_KERNEL_ERR_ARGUMENT;

    /* This platform stalls on sub-word stores through the uncached CPU
     * alias (verified on board: a single byte store to 0x9b00xxxx hangs
     * the CPU; 32-bit stores work). Stage the byte-addressed DMA buffers
     * in cached RAM first, then copy them to the alias with full-word
     * stores only. The MAC-visible byte layout is unchanged. */
    {
        static uint8_t input_stage[XIANGQI_NNUE_INPUT_STAGE_BYTES];
        static uint8_t weight_stage[XIANGQI_NNUE_WEIGHT_STAGE_BYTES];
        uint32_t cursor;

        memset(input_stage, 0, sizes.input_bytes);
        memset(weight_stage, 0, sizes.weight_bytes);
        if (sizes.bias_bytes != 0u)
            memset(mac->bias_buffer, 0, sizes.bias_bytes);

        ci_tiles = (feature_count + 3) / 4;
        co_tiles = (hidden + 31) / 32;

        for (int feature = 0; feature < feature_count; feature++) {
            size_t input_offset = (size_t)(feature / 4) * 8u +
                                  (size_t)(feature % 4) * 2u;
            input_stage[input_offset] = 1u;
        }

        for (int co_tile = 0; co_tile < co_tiles; co_tile++) {
            for (int ci_tile = 0; ci_tile < ci_tiles; ci_tile++) {
                size_t line = (size_t)(co_tile * ci_tiles + ci_tile) * 128u;
                for (int co = 0; co < 16; co++) {
                    int lane_low = co_tile * 32 + co * 2;
                    int lane_high = lane_low + 1;
                    for (int ci = 0; ci < 4; ci++) {
                        int feature = ci_tile * 4 + ci;
                        size_t slot = line + (size_t)(co * 4 + ci) * 2u;
                        if (feature < feature_count && lane_low < hidden) {
                            weight_stage[slot] = (uint8_t)
                                feature_weights[feature_offsets[feature] +
                                                (size_t)lane_low];
                        }
                        if (feature < feature_count && lane_high < hidden) {
                            weight_stage[slot + 1u] = (uint8_t)
                                feature_weights[feature_offsets[feature] +
                                                (size_t)lane_high];
                        }
                    }
                }
            }
        }

        for (cursor = 0; cursor + 3u < sizes.input_bytes; cursor += 4u) {
            uint32_t word = (uint32_t)input_stage[cursor] |
                ((uint32_t)input_stage[cursor + 1u] << 8) |
                ((uint32_t)input_stage[cursor + 2u] << 16) |
                ((uint32_t)input_stage[cursor + 3u] << 24);
            *(volatile uint32_t *)(void *)(mac->input_buffer + cursor) = word;
        }
        for (cursor = 0; cursor + 3u < sizes.weight_bytes; cursor += 4u) {
            uint32_t word = (uint32_t)weight_stage[cursor] |
                ((uint32_t)weight_stage[cursor + 1u] << 8) |
                ((uint32_t)weight_stage[cursor + 2u] << 16) |
                ((uint32_t)weight_stage[cursor + 3u] << 24);
            *(volatile uint32_t *)(void *)(mac->weight_buffer + cursor) = word;
        }
    }

    return MAC_KERNEL_OK;
}

int xiangqi_nnue_mac_accum(
    void *ctx,
    const int8_t *feature_weights,
    const size_t *feature_offsets,
    int feature_count,
    int hidden,
    int32_t *out) {
    xiangqi_nnue_mac_t *mac = (xiangqi_nnue_mac_t *)ctx;
    mac_kernel_buffer_sizes_t sizes;
    mac_kernel_job_t job;
    int result;

    if (out == NULL) {
        if (mac != NULL) {
            mac->failed_jobs++;
            mac->last_result = MAC_KERNEL_ERR_ARGUMENT;
        }
        return 0;
    }
    result = xiangqi_nnue_mac_prepare(
        mac, feature_weights, feature_offsets, feature_count, hidden, &job);
    if (result != MAC_KERNEL_OK) {
        if (mac != NULL) {
            mac->failed_jobs++;
            mac->last_result = result;
        }
        return 0;
    }

    sizes = mac_kernel_buffer_sizes(&job);
    if (mac->cache_clean != NULL) {
        mac->cache_clean(mac->cache_ctx, mac->input_buffer, sizes.input_bytes);
        mac->cache_clean(mac->cache_ctx, mac->weight_buffer, sizes.weight_bytes);
        if (sizes.bias_bytes != 0u)
            mac->cache_clean(
                mac->cache_ctx, mac->bias_buffer, sizes.bias_bytes);
    }

    result = mac_kernel_submit(mac->reg_base, &job);
    if (result == MAC_KERNEL_OK) {
        result = mac_kernel_wait(mac->reg_base,
            mac->timeout_polls == 0u ? 1000000u : mac->timeout_polls);
    }
    if (result != MAC_KERNEL_OK) {
        mac->failed_jobs++;
        mac->last_result = result;
        return 0;
    }

    if (mac->cache_invalidate != NULL) {
        mac->cache_invalidate(
            mac->cache_ctx, mac->output_buffer, sizes.output_bytes);
    }
    for (int lane = 0; lane < hidden; lane++) {
        /* Word-aligned alias read: sub-word uncached reads stall this
         * platform just like sub-word stores (verified on board). */
        const volatile uint32_t *src =
            (const volatile uint32_t *)(const void *)
                (mac->output_buffer + (size_t)lane * 4u);
        uint32_t raw = *src;
        out[lane] = (raw & 0x80000000u) != 0u
            ? -1 - (int32_t)(~raw)
            : (int32_t)raw;
    }
    mac->completed_jobs++;
    mac->last_cycles = mac_kernel_cycles(mac->reg_base);
    mac->last_result = MAC_KERNEL_OK;
    return 1;
}
int xiangqi_nnue_mac_prepare_batch_delta(
    xiangqi_nnue_mac_t *mac,
    const int8_t *feature_weights,
    const size_t *feature_offsets,
    const int8_t *deltas,
    int positions,
    int feature_count,
    int hidden,
    const int32_t *bias,
    mac_kernel_job_t *job) {
    mac_kernel_buffer_sizes_t sizes;
    int ci_tiles;
    int co_tiles;

    if (mac == NULL || feature_weights == NULL || feature_offsets == NULL ||
        deltas == NULL || bias == NULL || job == NULL ||
        positions <= 0 || positions > (int)MAC_KERNEL_MAX_PIXELS ||
        feature_count <= 0 ||
        feature_count > (int)MAC_KERNEL_MAX_CHANNELS ||
        (hidden != 128 && hidden != XIANGQI_NNUE_MAX_HIDDEN)) {
        return MAC_KERNEL_ERR_ARGUMENT;
    }

    memset(job, 0, sizeof(*job));
    job->pixels = (uint16_t)positions;
    job->cin = (uint16_t)feature_count;
    job->cout = (uint16_t)hidden;
    job->compute_mode = MAC_KERNEL_MODE_S8_S8;
    job->activation = MAC_KERNEL_ACT_NONE;
    job->output_format = MAC_KERNEL_OUT_I32;
    job->zero_bias = 0u;
    job->input_addr = mac->input_addr;
    job->weight_addr = mac->weight_addr;
    job->bias_addr = mac->bias_addr;
    job->output_addr = mac->output_addr;

    if (mac_kernel_validate_job(job) != MAC_KERNEL_OK)
        return MAC_KERNEL_ERR_ARGUMENT;
    sizes = mac_kernel_buffer_sizes(job);
    if (!buffers_fit(mac, &sizes))
        return MAC_KERNEL_ERR_ARGUMENT;

    /* Stage in cached RAM, then copy to the alias with word stores only
     * (sub-word uncached stores stall this platform; see accum). */
    {
        static uint8_t input_stage[XIANGQI_NNUE_INPUT_STAGE_BYTES];
        static uint8_t weight_stage[XIANGQI_NNUE_WEIGHT_STAGE_BYTES];
        static uint8_t bias_stage[XIANGQI_NNUE_BIAS_STAGE_BYTES];
        uint32_t cursor;

        memset(input_stage, 0, sizes.input_bytes);
        memset(weight_stage, 0, sizes.weight_bytes);
        memset(bias_stage, 0, sizes.bias_bytes);
        ci_tiles = (feature_count + 3) / 4;
        co_tiles = (hidden + 31) / 32;

        for (int position = 0; position < positions; ++position) {
            for (int feature = 0; feature < feature_count; ++feature) {
                size_t offset = (size_t)position * (size_t)ci_tiles * 8u +
                                (size_t)(feature / 4) * 8u +
                                (size_t)(feature % 4) * 2u;
                input_stage[offset] =
                    (uint8_t)deltas[position * feature_count + feature];
            }
        }

        for (int co_tile = 0; co_tile < co_tiles; co_tile++) {
            for (int ci_tile = 0; ci_tile < ci_tiles; ci_tile++) {
                size_t line = (size_t)(co_tile * ci_tiles + ci_tile) * 128u;
                for (int co = 0; co < 16; co++) {
                    int lane_low = co_tile * 32 + co * 2;
                    int lane_high = lane_low + 1;
                    for (int ci = 0; ci < 4; ci++) {
                        int feature = ci_tile * 4 + ci;
                        size_t slot = line + (size_t)(co * 4 + ci) * 2u;
                        if (feature < feature_count && lane_low < hidden) {
                            weight_stage[slot] = (uint8_t)
                                feature_weights[feature_offsets[feature] +
                                                (size_t)lane_low];
                        }
                        if (feature < feature_count && lane_high < hidden) {
                            weight_stage[slot + 1u] = (uint8_t)
                                feature_weights[feature_offsets[feature] +
                                                (size_t)lane_high];
                        }
                    }
                }
            }
        }

        for (int lane = 0; lane < hidden; ++lane) {
            int co_tile = lane / 32;
            int co = lane % 32;
            size_t offset = (size_t)co_tile * 192u + (size_t)co * 6u;
            uint64_t raw = (uint64_t)(int64_t)bias[lane];
            for (int byte = 0; byte < 6; ++byte)
                bias_stage[offset + (size_t)byte] =
                    (uint8_t)(raw >> (byte * 8));
        }

        for (cursor = 0; cursor + 3u < sizes.input_bytes; cursor += 4u) {
            uint32_t word = (uint32_t)input_stage[cursor] |
                ((uint32_t)input_stage[cursor + 1u] << 8) |
                ((uint32_t)input_stage[cursor + 2u] << 16) |
                ((uint32_t)input_stage[cursor + 3u] << 24);
            *(volatile uint32_t *)(void *)(mac->input_buffer + cursor) = word;
        }
        for (cursor = 0; cursor + 3u < sizes.weight_bytes; cursor += 4u) {
            uint32_t word = (uint32_t)weight_stage[cursor] |
                ((uint32_t)weight_stage[cursor + 1u] << 8) |
                ((uint32_t)weight_stage[cursor + 2u] << 16) |
                ((uint32_t)weight_stage[cursor + 3u] << 24);
            *(volatile uint32_t *)(void *)(mac->weight_buffer + cursor) = word;
        }
        for (cursor = 0; cursor + 3u < sizes.bias_bytes; cursor += 4u) {
            uint32_t word = (uint32_t)bias_stage[cursor] |
                ((uint32_t)bias_stage[cursor + 1u] << 8) |
                ((uint32_t)bias_stage[cursor + 2u] << 16) |
                ((uint32_t)bias_stage[cursor + 3u] << 24);
            *(volatile uint32_t *)(void *)(mac->bias_buffer + cursor) = word;
        }
    }
    return MAC_KERNEL_OK;
}

int xiangqi_nnue_mac_batch_delta(
    xiangqi_nnue_mac_t *mac,
    const int8_t *feature_weights,
    const size_t *feature_offsets,
    const int8_t *deltas,
    int positions,
    int feature_count,
    int hidden,
    const int32_t *bias,
    int32_t *out) {
    mac_kernel_buffer_sizes_t sizes;
    mac_kernel_job_t job;
    int result;

    if (out == NULL)
        return 0;
    result = xiangqi_nnue_mac_prepare_batch_delta(
        mac, feature_weights, feature_offsets, deltas, positions,
        feature_count, hidden, bias, &job);
    if (result != MAC_KERNEL_OK) {
        if (mac != NULL) {
            mac->failed_jobs++;
            mac->last_result = result;
        }
        return 0;
    }
    sizes = mac_kernel_buffer_sizes(&job);
    if (mac->cache_clean != NULL) {
        mac->cache_clean(mac->cache_ctx, mac->input_buffer, sizes.input_bytes);
        mac->cache_clean(mac->cache_ctx, mac->weight_buffer, sizes.weight_bytes);
        mac->cache_clean(mac->cache_ctx, mac->bias_buffer, sizes.bias_bytes);
    }
    result = mac_kernel_submit(mac->reg_base, &job);
    if (result == MAC_KERNEL_OK) {
        result = mac_kernel_wait(mac->reg_base,
            mac->timeout_polls == 0u ? 1000000u : mac->timeout_polls);
    }
    if (result != MAC_KERNEL_OK) {
        mac->failed_jobs++;
        mac->last_result = result;
        return 0;
    }
    if (mac->cache_invalidate != NULL)
        mac->cache_invalidate(mac->cache_ctx, mac->output_buffer,
                              sizes.output_bytes);
    for (int position = 0; position < positions; ++position) {
        for (int lane = 0; lane < hidden; ++lane) {
            /* Word-aligned alias read: sub-word uncached reads stall this
             * platform just like sub-word stores (board-verified). */
            const volatile uint32_t *src =
                (const volatile uint32_t *)(const void *)
                    (mac->output_buffer +
                     ((size_t)position * (size_t)hidden + (size_t)lane) * 4u);
            uint32_t raw = *src;
            out[position * hidden + lane] = (raw & 0x80000000u) != 0u
                ? -1 - (int32_t)(~raw)
                : (int32_t)raw;
        }
    }
    mac->completed_jobs++;
    mac->last_cycles = mac_kernel_cycles(mac->reg_base);
    mac->last_result = MAC_KERNEL_OK;
    return 1;
}
