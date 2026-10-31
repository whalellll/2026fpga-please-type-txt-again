#include "pf_ft_stage_a.h"

#include <string.h>

int pf_ft_pack_header_valid(const pf_ft_pack_header_t *h) {
    if (h == NULL)
        return 0;
    if (h->magic != PF_FT_PACK_MAGIC || h->version != PF_FT_PACK_VERSION)
        return 0;
    if (h->l1 != PF_FT_L1 || h->tile_width != PF_FT_MAC_MAX_CHANNELS)
        return 0;
    if (h->tile_count != PF_FT_TILE_COUNT)
        return 0;
    if (h->max_active == 0 || h->max_active > PF_FT_MAX_ACTIVE_THREAT)
        return 0;
    if (h->feature_rows == 0)
        return 0;
    if (h->weight_bytes != h->feature_rows * (uint32_t)PF_FT_L1)
        return 0;
    if ((h->flags & 1u) == 0u)
        return 0;
    return 1;
}

int pf_ft_model_bind(
    pf_ft_model_t *model,
    const pf_ft_pack_header_t *header,
    const int8_t *weights) {
    if (model == NULL || header == NULL || weights == NULL)
        return 0;
    if (!pf_ft_pack_header_valid(header))
        return 0;
    model->header = *header;
    model->weights = weights;
    return 1;
}

int pf_ft_build_tile_jobs(
    const uint16_t *feature_index,
    uint16_t feature_count,
    pf_ft_tile_job_t jobs[PF_FT_TILE_COUNT]) {
    uint16_t tile;
    uint16_t i;

    if (jobs == NULL)
        return 0;
    if (feature_count > PF_FT_MAX_ACTIVE)
        return 0;
    if (feature_count > 0 && feature_index == NULL)
        return 0;

    memset(jobs, 0, sizeof(pf_ft_tile_job_t) * PF_FT_TILE_COUNT);
    for (tile = 0; tile < PF_FT_TILE_COUNT; ++tile) {
        jobs[tile].tile_id = tile;
        jobs[tile].feature_count = feature_count;
        jobs[tile].cout = (uint16_t)PF_FT_MAC_MAX_CHANNELS;
        for (i = 0; i < feature_count; ++i)
            jobs[tile].feature_index[i] = feature_index[i];
    }
    return 1;
}

int pf_ft_ref_accumulate_tile(
    const pf_ft_model_t *model,
    const pf_ft_tile_job_t *job,
    int32_t *out_tile) {
    uint16_t lane;
    uint16_t fi;
    uint32_t base;
    uint32_t row;

    if (model == NULL || model->weights == NULL || job == NULL || out_tile == NULL)
        return 0;
    if (job->tile_id >= PF_FT_TILE_COUNT)
        return 0;
    if (job->cout != PF_FT_MAC_MAX_CHANNELS)
        return 0;
    if (job->feature_count > PF_FT_MAX_ACTIVE)
        return 0;

    base = (uint32_t)job->tile_id * PF_FT_MAC_MAX_CHANNELS;
    for (lane = 0; lane < job->cout; ++lane)
        out_tile[lane] = 0;

    for (fi = 0; fi < job->feature_count; ++fi) {
        row = job->feature_index[fi];
        if (row >= model->header.feature_rows)
            return 0;
        for (lane = 0; lane < job->cout; ++lane) {
            out_tile[lane] +=
                (int32_t)model->weights[row * PF_FT_L1 + base + lane];
        }
    }
    return 1;
}

int pf_ft_ref_accumulate(
    const pf_ft_model_t *model,
    const uint16_t *feature_index,
    uint16_t feature_count,
    int32_t *acc_l1) {
    uint16_t fi;
    uint32_t lane;
    uint32_t row;

    if (model == NULL || model->weights == NULL || acc_l1 == NULL)
        return 0;
    if (feature_count > PF_FT_MAX_ACTIVE)
        return 0;
    if (feature_count > 0 && feature_index == NULL)
        return 0;

    for (lane = 0; lane < PF_FT_L1; ++lane)
        acc_l1[lane] = 0;

    for (fi = 0; fi < feature_count; ++fi) {
        row = feature_index[fi];
        if (row >= model->header.feature_rows)
            return 0;
        for (lane = 0; lane < PF_FT_L1; ++lane)
            acc_l1[lane] += (int32_t)model->weights[row * PF_FT_L1 + lane];
    }
    return 1;
}

static int pf_ft_ref_tile_as_backend(
    void *ctx,
    const pf_ft_model_t *model,
    const pf_ft_tile_job_t *job,
    int32_t *out_tile) {
    (void)ctx;
    return pf_ft_ref_accumulate_tile(model, job, out_tile);
}

int pf_ft_tiled_accumulate(
    const pf_ft_model_t *model,
    const uint16_t *feature_index,
    uint16_t feature_count,
    pf_ft_tile_backend_fn backend,
    void *backend_ctx,
    int32_t *acc_l1) {
    pf_ft_tile_job_t jobs[PF_FT_TILE_COUNT];
    int32_t tile_out[PF_FT_MAC_MAX_CHANNELS];
    uint16_t tile;
    pf_ft_tile_backend_fn fn =
        backend != NULL ? backend : pf_ft_ref_tile_as_backend;

    if (acc_l1 == NULL)
        return 0;
    if (!pf_ft_build_tile_jobs(feature_index, feature_count, jobs))
        return 0;

    for (tile = 0; tile < PF_FT_TILE_COUNT; ++tile) {
        if (!fn(backend_ctx, model, &jobs[tile], tile_out))
            return 0;
        memcpy(acc_l1 + (size_t)tile * PF_FT_MAC_MAX_CHANNELS,
               tile_out,
               sizeof(tile_out));
    }
    return 1;
}
