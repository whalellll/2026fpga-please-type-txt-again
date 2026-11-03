#include "pf_mlp_stage_b.h"

#include <string.h>

static int32_t clamp_i32(int32_t v, int32_t lo, int32_t hi) {
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

int pf_mlp_pack_header_valid(const pf_mlp_pack_header_t *h) {
    if (h == NULL)
        return 0;
    if (h->magic != PF_MLP_PACK_MAGIC || h->version != PF_MLP_PACK_VERSION)
        return 0;
    if (h->l1 != PF_MLP_L1 || h->l2 != PF_MLP_L2 || h->l3 != PF_MLP_L3)
        return 0;
    if (h->weight_scale_bits != PF_MLP_WEIGHT_SCALE_BITS)
        return 0;
    if ((h->flags & 1u) == 0u)
        return 0;
    return 1;
}

int pf_mlp_model_bind(
    pf_mlp_model_t *model,
    const pf_mlp_pack_header_t *header,
    const int8_t *fc0_w, const int32_t *fc0_b,
    const int8_t *fc1_w, const int32_t *fc1_b,
    const int8_t *fc2_w, const int32_t *fc2_b) {
    if (model == NULL || header == NULL)
        return 0;
    if (!pf_mlp_pack_header_valid(header))
        return 0;
    if (fc0_w == NULL || fc0_b == NULL || fc1_w == NULL || fc1_b == NULL ||
        fc2_w == NULL || fc2_b == NULL)
        return 0;
    model->header = *header;
    model->fc0_w = fc0_w;
    model->fc0_b = fc0_b;
    model->fc1_w = fc1_w;
    model->fc1_b = fc1_b;
    model->fc2_w = fc2_w;
    model->fc2_b = fc2_b;
    return 1;
}

void pf_mlp_quantize_ft(
    const int32_t *acc_l1, uint8_t *x_u8, uint32_t n, int shift) {
    uint32_t i;
    for (i = 0; i < n; ++i) {
        int32_t v = acc_l1[i];
        if (shift > 0)
            v >>= shift;
        x_u8[i] = (uint8_t)clamp_i32(v, 0, 127);
    }
}

void pf_mlp_clipped_relu_i32(
    const int32_t *in, uint8_t *out, uint32_t n, int shift) {
    uint32_t i;
    for (i = 0; i < n; ++i)
        out[i] = (uint8_t)clamp_i32(in[i] >> shift, 0, 127);
}

void pf_mlp_sqr_clipped_relu_i32(
    const int32_t *in, uint8_t *out, uint32_t n, int shift) {
    uint32_t i;
    int shift_total = 2 * shift + 7;
    for (i = 0; i < n; ++i) {
        int64_t sq = (int64_t)in[i] * (int64_t)in[i];
        int64_t v = sq >> shift_total;
        if (v < 0)
            v = 0;
        if (v > 127)
            v = 127;
        out[i] = (uint8_t)v;
    }
}

void pf_mlp_affine_u8_i8(
    const uint8_t *x, uint32_t in_dim,
    const int8_t *w, const int32_t *bias,
    uint32_t out_dim, int32_t *out) {
    uint32_t o;
    uint32_t i;
    for (o = 0; o < out_dim; ++o) {
        int32_t sum = bias[o];
        const int8_t *row = w + (size_t)o * in_dim;
        for (i = 0; i < in_dim; ++i)
            sum += (int32_t)row[i] * (int32_t)x[i];
        out[o] = sum;
    }
}

int pf_mlp_ref_fc0_tile(
    const pf_mlp_model_t *model, const uint8_t *x_l1,
    const pf_mlp_fc0_tile_job_t *job, int32_t *partial_out32) {
    uint32_t o;
    uint32_t i;
    uint32_t base;

    if (model == NULL || model->fc0_w == NULL || x_l1 == NULL ||
        job == NULL || partial_out32 == NULL)
        return 0;
    if (job->tile_id >= PF_MLP_FC0_CIN_TILES)
        return 0;
    if (job->cin != PF_MLP_MAC_MAX_CHANNELS || job->cout != PF_MLP_FC0_OUT)
        return 0;

    base = (uint32_t)job->tile_id * PF_MLP_MAC_MAX_CHANNELS;
    for (o = 0; o < PF_MLP_FC0_OUT; ++o) {
        int32_t sum = 0;
        const int8_t *row = model->fc0_w + (size_t)o * PF_MLP_L1 + base;
        for (i = 0; i < PF_MLP_MAC_MAX_CHANNELS; ++i)
            sum += (int32_t)row[i] * (int32_t)x_l1[base + i];
        partial_out32[o] = sum;
    }
    return 1;
}

int pf_mlp_ref_fc0(
    const pf_mlp_model_t *model, const uint8_t *x_l1, int32_t *fc0_out) {
    if (model == NULL || x_l1 == NULL || fc0_out == NULL)
        return 0;
    pf_mlp_affine_u8_i8(
        x_l1, PF_MLP_L1, model->fc0_w, model->fc0_b, PF_MLP_FC0_OUT, fc0_out);
    return 1;
}

static int pf_mlp_ref_fc0_tile_as_backend(
    void *ctx,
    const pf_mlp_model_t *model,
    const uint8_t *x_l1,
    const pf_mlp_fc0_tile_job_t *job,
    int32_t *partial_out32) {
    (void)ctx;
    return pf_mlp_ref_fc0_tile(model, x_l1, job, partial_out32);
}

int pf_mlp_tiled_fc0(
    const pf_mlp_model_t *model, const uint8_t *x_l1,
    pf_mlp_fc0_tile_backend_fn backend, void *backend_ctx,
    int32_t *fc0_out) {
    pf_mlp_fc0_tile_job_t job;
    int32_t partial[PF_MLP_FC0_OUT];
    uint16_t tile;
    uint32_t o;
    pf_mlp_fc0_tile_backend_fn fn =
        backend != NULL ? backend : pf_mlp_ref_fc0_tile_as_backend;

    if (model == NULL || model->fc0_b == NULL || x_l1 == NULL || fc0_out == NULL)
        return 0;

    for (o = 0; o < PF_MLP_FC0_OUT; ++o)
        fc0_out[o] = 0;

    memset(&job, 0, sizeof(job));
    job.cin = (uint16_t)PF_MLP_MAC_MAX_CHANNELS;
    job.cout = (uint16_t)PF_MLP_FC0_OUT;
    for (tile = 0; tile < PF_MLP_FC0_CIN_TILES; ++tile) {
        job.tile_id = tile;
        if (!fn(backend_ctx, model, x_l1, &job, partial))
            return 0;
        for (o = 0; o < PF_MLP_FC0_OUT; ++o)
            fc0_out[o] += partial[o];
    }
    for (o = 0; o < PF_MLP_FC0_OUT; ++o)
        fc0_out[o] += model->fc0_b[o];
    return 1;
}

int32_t pf_mlp_scale_output(int32_t fwd_out) {
    const int64_t multiplier =
        (int64_t)600 * (int64_t)PF_MLP_OUTPUT_SCALE;
    const int64_t denominator =
        (int64_t)PF_MLP_HIDDEN_ONE_VAL *
        (int64_t)(1u << PF_MLP_WEIGHT_SCALE_BITS) * 2;
    return (int32_t)((fwd_out * multiplier) / denominator);
}

int pf_mlp_propagate(
    const pf_mlp_model_t *model,
    const uint8_t *x_l1,
    pf_mlp_fc0_tile_backend_fn fc0_backend,
    void *fc0_backend_ctx,
    int32_t *score_out) {
    int32_t fc0[PF_MLP_FC0_OUT];
    int32_t fc1[PF_MLP_FC1_OUT];
    int32_t fc2[1];
    uint8_t act0_sqr[PF_MLP_FC0_OUT];
    uint8_t act0_clip[PF_MLP_FC0_OUT];
    uint8_t concat0[PF_MLP_FC1_IN];
    uint8_t act1_sqr[PF_MLP_FC1_OUT];
    uint8_t act1_clip[PF_MLP_FC1_OUT];
    uint8_t concat1[PF_MLP_FC2_IN];
    int32_t fwd;
    int32_t skip;

    if (model == NULL || x_l1 == NULL || score_out == NULL)
        return 0;

    if (!pf_mlp_tiled_fc0(model, x_l1, fc0_backend, fc0_backend_ctx, fc0))
        return 0;

    pf_mlp_sqr_clipped_relu_i32(fc0, act0_sqr, PF_MLP_FC0_OUT, PF_MLP_ACT0_SHIFT);
    pf_mlp_clipped_relu_i32(fc0, act0_clip, PF_MLP_FC0_OUT, PF_MLP_ACT0_SHIFT);
    memcpy(concat0, act0_sqr, PF_MLP_FC0_OUT);
    memcpy(concat0 + PF_MLP_FC0_OUT, act0_clip, PF_MLP_FC0_OUT);

    pf_mlp_affine_u8_i8(
        concat0, PF_MLP_FC1_IN, model->fc1_w, model->fc1_b, PF_MLP_FC1_OUT, fc1);

    pf_mlp_sqr_clipped_relu_i32(fc1, act1_sqr, PF_MLP_FC1_OUT, PF_MLP_ACT1_SHIFT);
    pf_mlp_clipped_relu_i32(fc1, act1_clip, PF_MLP_FC1_OUT, PF_MLP_ACT1_SHIFT);
    memcpy(concat1, act0_sqr, PF_MLP_FC0_OUT);
    memcpy(concat1 + PF_MLP_FC0_OUT, act0_clip, PF_MLP_FC0_OUT);
    memcpy(concat1 + PF_MLP_FC0_OUT * 2u, act1_sqr, PF_MLP_FC1_OUT);
    memcpy(concat1 + PF_MLP_FC0_OUT * 2u + PF_MLP_FC1_OUT, act1_clip, PF_MLP_FC1_OUT);

    pf_mlp_affine_u8_i8(
        concat1, PF_MLP_FC2_IN, model->fc2_w, model->fc2_b, PF_MLP_FC2_OUT, fc2);

    /* Official skip: last two fc0 pre-activation lanes. */
    skip = fc0[PF_MLP_FC0_OUT - 2u] - fc0[PF_MLP_FC0_OUT - 1u];
    fwd = fc2[0] + skip;
    *score_out = pf_mlp_scale_output(fwd);
    return 1;
}
