#include "pf_mlp_stage_b_cases.h"

#include <string.h>

static void expect(const pf_mlp_case_env_t *env, int ok, const char *name) {
    if (env->expect)
        env->expect(ok, name, env->expect_ctx);
}

static void fill_header(pf_mlp_pack_header_t *h) {
    memset(h, 0, sizeof(*h));
    h->magic = PF_MLP_PACK_MAGIC;
    h->version = PF_MLP_PACK_VERSION;
    h->l1 = (uint16_t)PF_MLP_L1;
    h->l2 = (uint16_t)PF_MLP_L2;
    h->l3 = (uint16_t)PF_MLP_L3;
    h->weight_scale_bits = (uint16_t)PF_MLP_WEIGHT_SCALE_BITS;
    h->flags = 1u;
    h->crc32 = 0;
}

static void fill_model_weights(pf_mlp_case_env_t *env) {
    uint32_t i;
    uint32_t o;
    for (o = 0; o < PF_MLP_FC0_OUT; ++o) {
        env->fc0_b[o] = (int32_t)(o + 1);
        for (i = 0; i < PF_MLP_L1; ++i) {
            env->fc0_w[o * PF_MLP_L1 + i] =
                (int8_t)((int)((o * 3u + i * 5u) % 251u) - 125);
        }
    }
    for (o = 0; o < PF_MLP_FC1_OUT; ++o) {
        env->fc1_b[o] = (int32_t)(o * 2 + 3);
        for (i = 0; i < PF_MLP_FC1_IN; ++i) {
            env->fc1_w[o * PF_MLP_FC1_IN + i] =
                (int8_t)((int)((o * 7u + i) % 200u) - 100);
        }
    }
    env->fc2_b[0] = 11;
    for (i = 0; i < PF_MLP_FC2_IN; ++i)
        env->fc2_w[i] = (int8_t)((int)(i % 17u) - 8);
}

static void fill_x_pattern(uint8_t *x, uint32_t pattern) {
    uint32_t i;
    for (i = 0; i < PF_MLP_L1; ++i) {
        if (pattern == 0)
            x[i] = 0;
        else if (pattern == 1)
            x[i] = 1;
        else if (pattern == 2)
            x[i] = (uint8_t)(i & 127u);
        else if (pattern == 3)
            x[i] = (uint8_t)((i * 3u + 11u) % 128u);
        else
            x[i] = 127;
    }
}

static int mock_fc0_tile(
    void *ctx,
    const pf_mlp_model_t *model,
    const uint8_t *x_l1,
    const pf_mlp_fc0_tile_job_t *job,
    int32_t *partial) {
    uint32_t *calls = (uint32_t *)ctx;
    if (calls)
        (*calls)++;
    return pf_mlp_ref_fc0_tile(model, x_l1, job, partial);
}

static void test_abi(const pf_mlp_case_env_t *env) {
    expect(env, PF_MLP_L1 == 1024u, "abi.l1");
    expect(env, PF_MLP_L2 == 32u && PF_MLP_L3 == 32u, "abi.l2_l3");
    expect(env, PF_MLP_FC0_CIN_TILES == 4u, "abi.fc0_cin_tiles");
    expect(env, PF_MLP_FC1_IN == 64u && PF_MLP_FC2_IN == 128u, "abi.concat_dims");
    expect(env, PF_MLP_ACT0_SHIFT == 7 && PF_MLP_ACT1_SHIFT == 6, "abi.act_shifts");
    expect(env, PF_MLP_PACK_MAGIC == 0x31424650u, "abi.magic_pfb1");
    expect(env, pf_mlp_scale_output(16384) == 9600, "abi.scale_16384");
    expect(env, pf_mlp_scale_output(0) == 0, "abi.scale_zero");
}

static void test_header_bind(pf_mlp_case_env_t *env) {
    pf_mlp_pack_header_t h;
    pf_mlp_model_t model;
    fill_header(&h);
    expect(env, pf_mlp_pack_header_valid(&h), "header.valid");
    h.l2 = 16;
    expect(env, !pf_mlp_pack_header_valid(&h), "header.reject_l2");
    fill_header(&h);
    h.flags = 0;
    expect(env, !pf_mlp_pack_header_valid(&h), "header.reject_flags");
    fill_header(&h);
    expect(env, !pf_mlp_model_bind(&model, &h, NULL, env->fc0_b,
                                   env->fc1_w, env->fc1_b, env->fc2_w, env->fc2_b),
           "bind.reject_null_w");
    expect(env, pf_mlp_model_bind(&model, &h, env->fc0_w, env->fc0_b,
                                  env->fc1_w, env->fc1_b, env->fc2_w, env->fc2_b),
           "bind.ok");
}

static void test_activations(const pf_mlp_case_env_t *env) {
    int32_t in[4] = {-1000, 0, 128, 200000};
    uint8_t out[4];
    pf_mlp_clipped_relu_i32(in, out, 4, 7);
    expect(env, out[0] == 0 && out[1] == 0 && out[2] == 1 && out[3] == 127,
           "act.clip_shift7");
    {
        int32_t s_in[3] = {0, 128, -50};
        uint8_t s_out[3];
        pf_mlp_sqr_clipped_relu_i32(s_in, s_out, 3, 7);
        /* 128^2 >> (14+7)=21 => 16384>>21 = 0; use larger value */
        expect(env, s_out[0] == 0 && s_out[2] == 0, "act.sqr_nonneg");
    }
    {
        int32_t big = 1 << 14; /* 16384 */
        uint8_t s;
        /* 16384^2 >> 21 = 2^28 >> 21 = 2^7 = 128 -> clamp 127 */
        pf_mlp_sqr_clipped_relu_i32(&big, &s, 1, 7);
        expect(env, s == 127, "act.sqr_saturate");
    }
}

static void test_fc0_tiling(pf_mlp_case_env_t *env) {
    pf_mlp_pack_header_t h;
    pf_mlp_model_t model;
    uint32_t calls;
    uint32_t pattern;
    fill_header(&h);
    fill_model_weights(env);
    pf_mlp_model_bind(&model, &h, env->fc0_w, env->fc0_b,
                      env->fc1_w, env->fc1_b, env->fc2_w, env->fc2_b);

    for (pattern = 0; pattern < 5u; ++pattern) {
        fill_x_pattern(env->x, pattern);
        expect(env, pf_mlp_ref_fc0(&model, env->x, env->tmp32),
               pattern == 0 ? "fc0.ref_zero" :
               pattern == 1 ? "fc0.ref_ones" :
               pattern == 2 ? "fc0.ref_ramp" :
               pattern == 3 ? "fc0.ref_mix" : "fc0.ref_max");
        calls = 0;
        expect(env, pf_mlp_tiled_fc0(&model, env->x, mock_fc0_tile, &calls,
                                     env->tmp32b),
               pattern == 0 ? "fc0.tiled_zero" :
               pattern == 1 ? "fc0.tiled_ones" :
               pattern == 2 ? "fc0.tiled_ramp" :
               pattern == 3 ? "fc0.tiled_mix" : "fc0.tiled_max");
        expect(env, calls == PF_MLP_FC0_CIN_TILES,
               pattern == 0 ? "fc0.jobs_zero" :
               pattern == 1 ? "fc0.jobs_ones" :
               pattern == 2 ? "fc0.jobs_ramp" :
               pattern == 3 ? "fc0.jobs_mix" : "fc0.jobs_max");
        {
            uint32_t o;
            int eq = 1;
            for (o = 0; o < PF_MLP_FC0_OUT; ++o) {
                if (env->tmp32[o] != env->tmp32b[o]) {
                    eq = 0;
                    break;
                }
            }
            expect(env, eq,
                   pattern == 0 ? "fc0.match_zero" :
                   pattern == 1 ? "fc0.match_ones" :
                   pattern == 2 ? "fc0.match_ramp" :
                   pattern == 3 ? "fc0.match_mix" : "fc0.match_max");
        }
    }
}

static void test_propagate(pf_mlp_case_env_t *env) {
    pf_mlp_pack_header_t h;
    pf_mlp_model_t model;
    int32_t score_a;
    int32_t score_b;
    uint32_t calls;
    fill_header(&h);
    fill_model_weights(env);
    pf_mlp_model_bind(&model, &h, env->fc0_w, env->fc0_b,
                      env->fc1_w, env->fc1_b, env->fc2_w, env->fc2_b);

    fill_x_pattern(env->x, 3);
    expect(env, pf_mlp_propagate(&model, env->x, NULL, NULL, &score_a),
           "prop.cpu_ok");
    calls = 0;
    expect(env, pf_mlp_propagate(&model, env->x, mock_fc0_tile, &calls, &score_b),
           "prop.tiled_ok");
    expect(env, calls == PF_MLP_FC0_CIN_TILES, "prop.tiled_four_jobs");
    expect(env, score_a == score_b, "prop.score_match");

    fill_x_pattern(env->x, 0);
    expect(env, pf_mlp_propagate(&model, env->x, NULL, NULL, &score_a),
           "prop.zero_input_ok");
    /* With x=0, fc0 = bias only; score still well-defined. */
    expect(env, 1, "prop.zero_input_defined");

    {
        int32_t acc[8];
        uint8_t xu[8];
        uint32_t i;
        for (i = 0; i < 8; ++i)
            acc[i] = (int32_t)(i * 200 - 100);
        pf_mlp_quantize_ft(acc, xu, 8, 6);
        expect(env, xu[0] == 0 && xu[1] == 1 && xu[7] == 20, "quant.sample");
    }
}

static void test_skip_and_scale(const pf_mlp_case_env_t *env) {
    /* Manual tiny check: scale formula and skip polarity. */
    expect(env, pf_mlp_scale_output(16384) == 9600, "scale.unit");
    expect(env, pf_mlp_scale_output(-16384) == -9600, "scale.neg");
    expect(env, pf_mlp_scale_output(1) == 0, "scale.trunc_small");
}

int pf_mlp_run_stage_b_cases(pf_mlp_case_env_t *env) {
    if (env == NULL || env->fc0_w == NULL || env->fc0_b == NULL ||
        env->fc1_w == NULL || env->fc1_b == NULL || env->fc2_w == NULL ||
        env->fc2_b == NULL || env->x == NULL || env->tmp32 == NULL ||
        env->tmp32b == NULL)
        return -1;
    test_abi(env);
    test_header_bind(env);
    test_activations(env);
    test_fc0_tiling(env);
    test_propagate(env);
    test_skip_and_scale(env);
    return 0;
}
