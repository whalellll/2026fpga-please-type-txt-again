#include "pf_ft_stage_a.h"
#include "pf_ft_stage_a_cases.h"

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

static void fill_header(pf_ft_pack_header_t *h, uint32_t rows) {
    memset(h, 0, sizeof(*h));
    h->magic = PF_FT_PACK_MAGIC;
    h->version = PF_FT_PACK_VERSION;
    h->l1 = (uint16_t)PF_FT_L1;
    h->tile_width = (uint16_t)PF_FT_MAC_MAX_CHANNELS;
    h->tile_count = (uint16_t)PF_FT_TILE_COUNT;
    h->max_active = (uint16_t)PF_FT_MAX_ACTIVE;
    h->feature_rows = rows;
    h->flags = 1u;
    h->weight_bytes = rows * PF_FT_L1;
    h->crc32 = 0;
}

static void fill_ramp(int8_t *weights, uint32_t rows) {
    uint32_t row;
    uint32_t lane;
    for (row = 0; row < rows; ++row) {
        for (lane = 0; lane < PF_FT_L1; ++lane) {
            weights[row * PF_FT_L1 + lane] =
                (int8_t)((int)(row * 7u + lane) - 128);
        }
    }
}

static int mock_mac(
    void *ctx,
    const pf_ft_model_t *model,
    const pf_ft_tile_job_t *job,
    int32_t *out_tile) {
    uint32_t *calls = (uint32_t *)ctx;
    if (calls)
        (*calls)++;
    return pf_ft_ref_accumulate_tile(model, job, out_tile);
}

static void host_extra_cases(void) {
    enum { ROWS = 64 };
    pf_ft_pack_header_t header;
    pf_ft_model_t model;
    int8_t *weights;
    int32_t *full;
    int32_t *tiled;
    uint16_t feats32[32];
    uint32_t calls;
    uint16_t i;

    weights = (int8_t *)malloc((size_t)ROWS * PF_FT_L1);
    full = (int32_t *)malloc(sizeof(int32_t) * PF_FT_L1);
    tiled = (int32_t *)malloc(sizeof(int32_t) * PF_FT_L1);
    expect_cb(weights && full && tiled, "host.alloc_64rows", NULL);
    if (!weights || !full || !tiled) {
        free(weights);
        free(full);
        free(tiled);
        return;
    }

    fill_header(&header, ROWS);
    fill_ramp(weights, ROWS);
    expect_cb(pf_ft_model_bind(&model, &header, weights), "host.bind_64", NULL);

    for (i = 0; i < 32; ++i)
        feats32[i] = (uint16_t)((i * 2u) % ROWS);

    calls = 0;
    expect_cb(pf_ft_ref_accumulate(&model, feats32, 32, full), "host.full_32feat", NULL);
    expect_cb(pf_ft_tiled_accumulate(
                  &model, feats32, 32, mock_mac, &calls, tiled),
              "host.tiled_32feat", NULL);
    expect_cb(calls == PF_FT_TILE_COUNT, "host.32feat_four_jobs", NULL);
    {
        int eq = 1;
        uint32_t lane;
        for (lane = 0; lane < PF_FT_L1; ++lane) {
            if (full[lane] != tiled[lane]) {
                eq = 0;
                break;
            }
        }
        expect_cb(eq, "host.32feat_matches", NULL);
    }

    {
        uint16_t wrap = 63;
        calls = 0;
        expect_cb(pf_ft_ref_accumulate(&model, &wrap, 1, full), "host.last64_ref", NULL);
        expect_cb(pf_ft_tiled_accumulate(
                      &model, &wrap, 1, mock_mac, &calls, tiled),
                  "host.last64_tiled", NULL);
        expect_cb(full[0] == tiled[0] && full[1023] == tiled[1023],
                  "host.last64_edges", NULL);
    }

    {
        uint16_t oob = 64;
        expect_cb(!pf_ft_ref_accumulate(&model, &oob, 1, full),
                  "host.reject_row64", NULL);
    }

    free(weights);
    free(full);
    free(tiled);
}

int main(void) {
    static int8_t weights[PF_FT_CASE_ROWS * PF_FT_L1];
    static int32_t acc_a[PF_FT_L1];
    static int32_t acc_b[PF_FT_L1];
    static int32_t tile[PF_FT_MAC_MAX_CHANNELS];
    pf_ft_case_env_t env;

    printf("PF_FT_STAGE_A_ACCEPT begin\n");
    printf("contract: L1=%u tile=%u jobs=%u max_active=%u case_rows=%u\n",
           (unsigned)PF_FT_L1,
           (unsigned)PF_FT_MAC_MAX_CHANNELS,
           (unsigned)PF_FT_TILE_COUNT,
           (unsigned)PF_FT_MAX_ACTIVE,
           (unsigned)PF_FT_CASE_ROWS);

    memset(&env, 0, sizeof(env));
    env.weights = weights;
    env.acc_a = acc_a;
    env.acc_b = acc_b;
    env.tile = tile;
    env.expect = expect_cb;
    pf_ft_run_stage_a_cases(&env);
    host_extra_cases();

    printf("summary pass=%d fail=%d\n", g_passes, g_failures);
    if (g_failures == 0) {
        printf("PF_FT_STAGE_A_ACCEPT_PASS\n");
        return 0;
    }
    printf("PF_FT_STAGE_A_ACCEPT_FAIL count=%d\n", g_failures);
    return 1;
}
