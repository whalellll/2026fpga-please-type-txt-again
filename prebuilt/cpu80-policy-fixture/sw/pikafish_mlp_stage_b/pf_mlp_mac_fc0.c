#include "pf_mlp_mac_fc0.h"
#include "pf_mlp_mac_pack.h"

#include "mac_accel_kernel.h"
#include "xiangqi_nnue_mac.h"

#include <string.h>

/*
 * Pack one fc0 cin-tile into the existing MAC U8xS8 / I32 zero-bias path.
 * x_l1[tile*256 ..] are u8 activations; weights are row-major int8[out][L1].
 */
int pf_mlp_mac_fc0_tile(
    void *ctx,
    const pf_mlp_model_t *model,
    const uint8_t *x_l1,
    const pf_mlp_fc0_tile_job_t *job,
    int32_t *partial_out32) {
    xiangqi_nnue_mac_t *mac = (xiangqi_nnue_mac_t *)ctx;
    mac_kernel_job_t kjob;
    mac_kernel_buffer_sizes_t sizes;
    uint32_t base;
    uint32_t feature;
    int ci_tiles;
    int co_tiles;
    int result;
    int lane;

    if (mac == NULL || model == NULL || model->fc0_w == NULL ||
        x_l1 == NULL || job == NULL || partial_out32 == NULL)
        return 0;
    if (job->tile_id >= PF_MLP_FC0_CIN_TILES)
        return 0;
    if (job->cin != PF_MLP_MAC_MAX_CHANNELS || job->cout != PF_MLP_FC0_OUT)
        return 0;

    memset(&kjob, 0, sizeof(kjob));
    kjob.pixels = 1;
    kjob.cin = job->cin;
    kjob.cout = job->cout;
    kjob.compute_mode = MAC_KERNEL_MODE_U8_S8;
    kjob.activation = MAC_KERNEL_ACT_NONE;
    kjob.output_format = MAC_KERNEL_OUT_I32;
    kjob.zero_bias = 1;
    kjob.input_addr = mac->input_addr;
    kjob.weight_addr = mac->weight_addr;
    kjob.bias_addr = mac->bias_addr;
    kjob.output_addr = mac->output_addr;

    if (mac_kernel_validate_job(&kjob) != MAC_KERNEL_OK)
        return 0;
    sizes = mac_kernel_buffer_sizes(&kjob);
    if (mac->input_buffer == NULL || mac->weight_buffer == NULL ||
        mac->output_buffer == NULL ||
        mac->input_capacity < sizes.input_bytes ||
        mac->weight_capacity < sizes.weight_bytes ||
        mac->output_capacity < sizes.output_bytes)
        return 0;

    /* Stage in cached RAM, then copy to the alias with word stores only
     * (sub-word uncached stores stall this platform; board-verified). */
    {
        static uint8_t input_stage[64];
        static uint8_t weight_stage[8u * 8u * 128u];
        uint32_t cursor;
        memset(input_stage, 0, sizes.input_bytes);
        memset(weight_stage, 0, sizes.weight_bytes);

        base = (uint32_t)job->tile_id * PF_MLP_MAC_MAX_CHANNELS;
        for (feature = 0; feature < job->cin; ++feature) {
            size_t offset = (size_t)(feature / 4u) * 8u + (size_t)(feature % 4u) * 2u;
            input_stage[offset] = x_l1[base + feature];
        }

        ci_tiles = ((int)job->cin + 3) / 4;
        co_tiles = ((int)job->cout + 31) / 32;
        {
            int co_tile;
            int ci_tile;
            for (co_tile = 0; co_tile < co_tiles; ++co_tile) {
                for (ci_tile = 0; ci_tile < ci_tiles; ++ci_tile) {
                    size_t line = (size_t)(co_tile * ci_tiles + ci_tile) * 128u;
                    int co;
                    for (co = 0; co < 16; ++co) {
                        int lane_low = co_tile * 32 + co * 2;
                        int lane_high = lane_low + 1;
                        int ci;
                        for (ci = 0; ci < 4; ++ci) {
                            int feat = ci_tile * 4 + ci;
                            size_t slot = line + (size_t)(co * 4 + ci) * 2u;
                            if (feat < (int)job->cin && lane_low < (int)job->cout) {
                                weight_stage[slot] = (uint8_t)
                                    model->fc0_w[(size_t)lane_low * PF_MLP_L1 +
                                                 base + (uint32_t)feat];
                            }
                            if (feat < (int)job->cin && lane_high < (int)job->cout) {
                                weight_stage[slot + 1u] = (uint8_t)
                                    model->fc0_w[(size_t)lane_high * PF_MLP_L1 +
                                                 base + (uint32_t)feat];
                            }
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

    if (mac->cache_clean != NULL) {
        mac->cache_clean(mac->cache_ctx, mac->input_buffer, sizes.input_bytes);
        mac->cache_clean(mac->cache_ctx, mac->weight_buffer, sizes.weight_bytes);
    }

    result = mac_kernel_submit(mac->reg_base, &kjob);
    if (result == MAC_KERNEL_OK) {
        result = mac_kernel_wait(
            mac->reg_base,
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

    for (lane = 0; lane < (int)job->cout; ++lane) {
        /* Word-aligned alias read: sub-word uncached reads stall this
         * platform (board-verified). */
        const volatile uint32_t *src =
            (const volatile uint32_t *)(const void *)
                (mac->output_buffer + (size_t)lane * 4u);
        uint32_t raw = *src;
        partial_out32[lane] = (raw & 0x80000000u) != 0u
            ? -1 - (int32_t)(~raw)
            : (int32_t)raw;
    }
    mac->completed_jobs++;
    mac->last_cycles = mac_kernel_cycles(mac->reg_base);
    mac->last_result = MAC_KERNEL_OK;
    return 1;
}

static uint32_t read_le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

int pf_mlp_mac_prepacked_fc0_tile(
    void *ctx,
    const pf_mlp_model_t *model,
    const uint8_t *x_l1,
    const pf_mlp_fc0_tile_job_t *job,
    int32_t *partial_out32) {
    pf_mlp_mac_prepacked_ctx_t *packed =
        (pf_mlp_mac_prepacked_ctx_t *)ctx;
    xiangqi_nnue_mac_t *mac;
    mac_kernel_job_t kjob;
    mac_kernel_buffer_sizes_t sizes;
    uint32_t feature;
    int result;
    int lane;

    (void)model;
    if (packed == NULL || packed->mac == NULL || packed->pack_cpu == NULL ||
        x_l1 == NULL || job == NULL || partial_out32 == NULL ||
        packed->stack >= PF_STAGEB_STACK_COUNT ||
        job->tile_id >= PF_STAGEB_FC0_TILE_COUNT ||
        job->cin != PF_MLP_MAC_MAX_CHANNELS ||
        job->cout != PF_MLP_FC0_OUT)
        return 0;
    if (read_le32(packed->pack_cpu) != PF_STAGEB_PACK_MAGIC ||
        read_le32(packed->pack_cpu + 4u) != PF_STAGEB_PACK_VERSION ||
        read_le32(packed->pack_cpu + 12u) != PF_STAGEB_PACK_USED_BYTES)
        return 0;
    {
        const uint8_t *slot =
            packed->pack_cpu + pf_stageb_stack_offset(packed->stack);
        if (read_le32(slot) != PF_STAGEB_STACK_MAGIC ||
            read_le32(slot + 4u) != packed->stack)
            return 0;
    }

    mac = packed->mac;
    memset(&kjob, 0, sizeof(kjob));
    kjob.pixels = 1;
    kjob.cin = job->cin;
    kjob.cout = job->cout;
    kjob.compute_mode = MAC_KERNEL_MODE_U8_S8;
    kjob.activation = MAC_KERNEL_ACT_NONE;
    kjob.output_format = MAC_KERNEL_OUT_I32;
    kjob.zero_bias = 1;
    kjob.input_addr = mac->input_addr;
    kjob.weight_addr = packed->pack_bus_addr +
        pf_stageb_fc0_tile_offset(packed->stack, job->tile_id);
    kjob.bias_addr = mac->bias_addr;
    kjob.output_addr = mac->output_addr;
    if (mac_kernel_validate_job(&kjob) != MAC_KERNEL_OK)
        return 0;
    sizes = mac_kernel_buffer_sizes(&kjob);
    if (mac->input_buffer == NULL || mac->output_buffer == NULL ||
        mac->input_capacity < sizes.input_bytes ||
        mac->output_capacity < sizes.output_bytes)
        return 0;

    {
        /* Stage the input in cached RAM, then word-copy to the alias
         * (sub-word uncached stores stall this platform). */
        static uint8_t input_stage[64];
        uint32_t cursor;
        memset(input_stage, 0, sizes.input_bytes);
        for (feature = 0; feature < job->cin; ++feature) {
            size_t offset = (size_t)(feature / 4u) * 8u +
                            (size_t)(feature % 4u) * 2u;
            input_stage[offset] =
                x_l1[(uint32_t)job->tile_id * PF_MLP_MAC_MAX_CHANNELS + feature];
        }
        for (cursor = 0; cursor + 3u < sizes.input_bytes; cursor += 4u) {
            uint32_t word = (uint32_t)input_stage[cursor] |
                ((uint32_t)input_stage[cursor + 1u] << 8) |
                ((uint32_t)input_stage[cursor + 2u] << 16) |
                ((uint32_t)input_stage[cursor + 3u] << 24);
            *(volatile uint32_t *)(void *)(mac->input_buffer + cursor) = word;
        }
    }
    if (mac->cache_clean != NULL)
        mac->cache_clean(mac->cache_ctx, mac->input_buffer, sizes.input_bytes);

    result = mac_kernel_submit(mac->reg_base, &kjob);
    if (result == MAC_KERNEL_OK)
        result = mac_kernel_wait(
            mac->reg_base,
            mac->timeout_polls == 0u ? 1000000u : mac->timeout_polls);
    if (result != MAC_KERNEL_OK) {
        mac->failed_jobs++;
        mac->last_result = result;
        return 0;
    }
    if (mac->cache_invalidate != NULL)
        mac->cache_invalidate(
            mac->cache_ctx, mac->output_buffer, sizes.output_bytes);
    for (lane = 0; lane < (int)job->cout; ++lane) {
        const volatile uint32_t *src =
            (const volatile uint32_t *)(const void *)
                (mac->output_buffer + (size_t)lane * 4u);
        uint32_t raw = *src;
        partial_out32[lane] = (int32_t)raw;
    }
    mac->completed_jobs++;
    mac->last_cycles = mac_kernel_cycles(mac->reg_base);
    mac->last_result = MAC_KERNEL_OK;
    return 1;
}
