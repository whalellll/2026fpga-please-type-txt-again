#include "pf_mlp_stage_b.h"
#include "pf_mlp_stage_b_cases.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int g_failures;
static int g_passes;

static void expect_cb(int ok, const char *name, void *ctx) {
    (void)ctx;
    if (ok) {
        printf("PASS %s\n", name);
        g_passes++;
    } else {
        printf("FAIL %s\n", name);
        g_failures++;
    }
}

static int mock_tile(
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

static void host_extra(pf_mlp_case_env_t *env) {
    pf_mlp_pack_header_t h;
    pf_mlp_model_t model;
    int32_t score_ref;
    int32_t score_tiled;
    uint32_t calls;
    uint32_t i;

    memset(&h, 0, sizeof(h));
    h.magic = PF_MLP_PACK_MAGIC;
    h.version = PF_MLP_PACK_VERSION;
    h.l1 = (uint16_t)PF_MLP_L1;
    h.l2 = (uint16_t)PF_MLP_L2;
    h.l3 = (uint16_t)PF_MLP_L3;
    h.weight_scale_bits = (uint16_t)PF_MLP_WEIGHT_SCALE_BITS;
    h.flags = 1u;

    /* Sparse-ish input: only 32 nonzeros. */
    memset(env->x, 0, PF_MLP_L1);
    for (i = 0; i < 32; ++i)
        env->x[i * 31u] = (uint8_t)(20u + i);

    pf_mlp_model_bind(&model, &h, env->fc0_w, env->fc0_b,
                      env->fc1_w, env->fc1_b, env->fc2_w, env->fc2_b);
    expect_cb(pf_mlp_propagate(&model, env->x, NULL, NULL, &score_ref),
              "host.sparse_cpu", NULL);
    calls = 0;
    expect_cb(pf_mlp_propagate(&model, env->x, mock_tile, &calls, &score_tiled),
              "host.sparse_tiled", NULL);
    expect_cb(calls == 4, "host.sparse_four_jobs", NULL);
    expect_cb(score_ref == score_tiled, "host.sparse_score_match", NULL);

    /* FT quant path into propagate. */
    {
        int32_t *acc = env->tmp32; /* reuse L2 buffer is too small; use x as scratch via tmp */
        static int32_t ft_acc[PF_MLP_L1];
        for (i = 0; i < PF_MLP_L1; ++i)
            ft_acc[i] = (int32_t)((i % 200) - 20) * 8;
        pf_mlp_quantize_ft(ft_acc, env->x, PF_MLP_L1, 3);
        expect_cb(pf_mlp_propagate(&model, env->x, NULL, NULL, &score_ref),
                  "host.from_ft_quant", NULL);
        (void)acc;
    }
}

int main(void) {
    static int8_t fc0_w[PF_MLP_FC0_OUT * PF_MLP_L1];
    static int32_t fc0_b[PF_MLP_FC0_OUT];
    static int8_t fc1_w[PF_MLP_FC1_OUT * PF_MLP_FC1_IN];
    static int32_t fc1_b[PF_MLP_FC1_OUT];
    static int8_t fc2_w[PF_MLP_FC2_IN];
    static int32_t fc2_b[1];
    static uint8_t x[PF_MLP_L1];
    static int32_t tmp32[PF_MLP_FC0_OUT];
    static int32_t tmp32b[PF_MLP_FC0_OUT];
    pf_mlp_case_env_t env;

    printf("PF_MLP_STAGE_B_ACCEPT begin\n");
    printf("contract: L1=%u L2=%u L3=%u fc0_cin_tiles=%u\n",
           (unsigned)PF_MLP_L1, (unsigned)PF_MLP_L2, (unsigned)PF_MLP_L3,
           (unsigned)PF_MLP_FC0_CIN_TILES);

    memset(&env, 0, sizeof(env));
    env.fc0_w = fc0_w;
    env.fc0_b = fc0_b;
    env.fc1_w = fc1_w;
    env.fc1_b = fc1_b;
    env.fc2_w = fc2_w;
    env.fc2_b = fc2_b;
    env.x = x;
    env.tmp32 = tmp32;
    env.tmp32b = tmp32b;
    env.expect = expect_cb;

    pf_mlp_run_stage_b_cases(&env);
    host_extra(&env);

    printf("summary pass=%d fail=%d\n", g_passes, g_failures);
    if (g_failures == 0) {
        printf("PF_MLP_STAGE_B_ACCEPT_PASS\n");
        return 0;
    }
    printf("PF_MLP_STAGE_B_ACCEPT_FAIL count=%d\n", g_failures);
    return 1;
}
