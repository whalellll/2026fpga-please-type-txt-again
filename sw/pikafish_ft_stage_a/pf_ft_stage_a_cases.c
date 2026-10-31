#include "pf_ft_stage_a_cases.h"

#include <string.h>

typedef struct {
    uint32_t calls;
    int fail_tile;
} fail_backend_ctx_t;

static void expect(const pf_ft_case_env_t *env, int ok, const char *name) {
    if (env->expect)
        env->expect(ok, name, env->expect_ctx);
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

static void fill_ramp_weights(int8_t *weights, uint32_t rows) {
    uint32_t row;
    uint32_t lane;
    for (row = 0; row < rows; ++row) {
        for (lane = 0; lane < PF_FT_L1; ++lane) {
            weights[row * PF_FT_L1 + lane] =
                (int8_t)((int)(row * 3u + lane * 5u) - 128);
        }
    }
}

static void fill_tile_markers(int8_t *weights, uint32_t rows) {
    static const int8_t marker[PF_FT_TILE_COUNT] = {1, 2, -3, 4};
    uint32_t row;
    uint32_t tile;
    uint32_t lane;
    for (row = 0; row < rows; ++row) {
        for (tile = 0; tile < PF_FT_TILE_COUNT; ++tile) {
            for (lane = 0; lane < PF_FT_MAC_MAX_CHANNELS; ++lane) {
                weights[row * PF_FT_L1 + tile * PF_FT_MAC_MAX_CHANNELS + lane] =
                    marker[tile];
            }
        }
    }
}

static void fill_const_weights(int8_t *weights, uint32_t rows, int8_t value) {
    uint32_t i;
    uint32_t n = rows * PF_FT_L1;
    for (i = 0; i < n; ++i)
        weights[i] = value;
}

static int vectors_equal(const int32_t *a, const int32_t *b, uint32_t n) {
    uint32_t i;
    for (i = 0; i < n; ++i) {
        if (a[i] != b[i])
            return 0;
    }
    return 1;
}

static int all_equal(const int32_t *a, uint32_t n, int32_t value) {
    uint32_t i;
    for (i = 0; i < n; ++i) {
        if (a[i] != value)
            return 0;
    }
    return 1;
}

static int mock_mac_tile(
    void *ctx,
    const pf_ft_model_t *model,
    const pf_ft_tile_job_t *job,
    int32_t *out_tile) {
    uint32_t *calls = (uint32_t *)ctx;
    if (calls != NULL)
        (*calls)++;
    return pf_ft_ref_accumulate_tile(model, job, out_tile);
}

static int fail_on_tile(
    void *ctx,
    const pf_ft_model_t *model,
    const pf_ft_tile_job_t *job,
    int32_t *out_tile) {
    fail_backend_ctx_t *state = (fail_backend_ctx_t *)ctx;
    state->calls++;
    if ((int)job->tile_id == state->fail_tile)
        return 0;
    return pf_ft_ref_accumulate_tile(model, job, out_tile);
}

static void test_abi(const pf_ft_case_env_t *env) {
    expect(env, PF_FT_L1 == 1024u, "abi.l1_1024");
    expect(env, PF_FT_MAC_MAX_CHANNELS == 256u, "abi.mac_max_channels_256");
    expect(env, PF_FT_TILE_COUNT == 4u, "abi.tile_count_4");
    expect(env, PF_FT_L1 == PF_FT_MAC_MAX_CHANNELS * PF_FT_TILE_COUNT,
           "abi.l1_equals_tiles");
    expect(env, PF_FT_PACK_MAGIC == 0x31414650u, "abi.pack_magic_pfa1");
    expect(env, PF_FT_MAX_ACTIVE == 32u, "abi.max_active_halfka_32");
    expect(env, PF_FT_MAX_ACTIVE_THREAT == 64u, "abi.max_active_threat_64");
}

static void test_header(const pf_ft_case_env_t *env) {
    pf_ft_pack_header_t h;
    fill_header(&h, PF_FT_CASE_ROWS);
    expect(env, pf_ft_pack_header_valid(&h), "header.valid_ok");

    h.magic = 0;
    expect(env, !pf_ft_pack_header_valid(&h), "header.reject_magic");
    fill_header(&h, PF_FT_CASE_ROWS);
    h.version = 0x00020000u;
    expect(env, !pf_ft_pack_header_valid(&h), "header.reject_version");
    fill_header(&h, PF_FT_CASE_ROWS);
    h.l1 = 512;
    expect(env, !pf_ft_pack_header_valid(&h), "header.reject_bad_l1");
    fill_header(&h, PF_FT_CASE_ROWS);
    h.tile_width = 128;
    expect(env, !pf_ft_pack_header_valid(&h), "header.reject_bad_tile");
    fill_header(&h, PF_FT_CASE_ROWS);
    h.tile_count = 8;
    expect(env, !pf_ft_pack_header_valid(&h), "header.reject_tile_count");
    fill_header(&h, PF_FT_CASE_ROWS);
    h.flags = 0;
    expect(env, !pf_ft_pack_header_valid(&h), "header.reject_flags");
    fill_header(&h, PF_FT_CASE_ROWS);
    h.weight_bytes = 1;
    expect(env, !pf_ft_pack_header_valid(&h), "header.reject_weight_bytes");
    fill_header(&h, PF_FT_CASE_ROWS);
    h.feature_rows = 0;
    expect(env, !pf_ft_pack_header_valid(&h), "header.reject_zero_rows");
    fill_header(&h, PF_FT_CASE_ROWS);
    h.max_active = 0;
    expect(env, !pf_ft_pack_header_valid(&h), "header.reject_zero_active");
    fill_header(&h, PF_FT_CASE_ROWS);
    h.max_active = 65;
    expect(env, !pf_ft_pack_header_valid(&h), "header.reject_active_over_threat");
    fill_header(&h, PF_FT_CASE_ROWS);
    h.max_active = 64;
    expect(env, pf_ft_pack_header_valid(&h), "header.allow_threat_max_active");
    expect(env, !pf_ft_pack_header_valid(NULL), "header.reject_null");
}

static void test_jobs_and_bind(const pf_ft_case_env_t *env) {
    uint16_t feats[3] = {1, 7, 4};
    pf_ft_tile_job_t jobs[PF_FT_TILE_COUNT];
    pf_ft_pack_header_t header;
    pf_ft_model_t model;

    expect(env, pf_ft_build_tile_jobs(feats, 3, jobs), "jobs.build_ok");
    expect(env, jobs[0].tile_id == 0 && jobs[3].tile_id == 3, "jobs.tile_ids");
    expect(env, jobs[0].feature_count == 3 && jobs[2].feature_index[1] == 7,
           "jobs.shared_features");
    expect(env, jobs[1].cout == PF_FT_MAC_MAX_CHANNELS, "jobs.cout_256");
    expect(env, !pf_ft_build_tile_jobs(feats, PF_FT_MAX_ACTIVE + 1, jobs),
           "jobs.reject_too_many_features");
    expect(env, !pf_ft_build_tile_jobs(NULL, 1, jobs), "jobs.reject_null_index");
    expect(env, pf_ft_build_tile_jobs(NULL, 0, jobs), "jobs.allow_empty");
    expect(env, !pf_ft_build_tile_jobs(feats, 1, NULL), "jobs.reject_null_out");

    fill_header(&header, PF_FT_CASE_ROWS);
    expect(env, !pf_ft_model_bind(NULL, &header, env->weights), "bind.reject_null_model");
    expect(env, !pf_ft_model_bind(&model, NULL, env->weights), "bind.reject_null_header");
    expect(env, !pf_ft_model_bind(&model, &header, NULL), "bind.reject_null_weights");
    expect(env, pf_ft_model_bind(&model, &header, env->weights), "bind.ok");
}

static int run_pair(
    const pf_ft_case_env_t *env,
    const pf_ft_model_t *model,
    const uint16_t *feats,
    uint16_t nfeat,
    uint32_t *calls) {
    if (!pf_ft_ref_accumulate(model, feats, nfeat, env->acc_a))
        return 0;
    if (!pf_ft_tiled_accumulate(
            model, feats, nfeat, mock_mac_tile, calls, env->acc_b))
        return 0;
    return vectors_equal(env->acc_a, env->acc_b, PF_FT_L1);
}

static void test_numeric(const pf_ft_case_env_t *env) {
    pf_ft_pack_header_t header;
    pf_ft_model_t model;
    uint32_t calls;
    uint16_t mixed[] = {0, 3, 7};
    uint16_t first[] = {0};
    uint16_t last[] = {PF_FT_CASE_ROWS - 1};
    uint16_t dup[] = {2, 2, 2};
    uint16_t all_rows[] = {0, 1, 2, 3, 4, 5, 6, 7};
    uint16_t shuffled[] = {7, 0, 5, 1};
    uint16_t bad = PF_FT_CASE_ROWS;
    fail_backend_ctx_t fail;
    pf_ft_tile_job_t job;
    uint16_t tile;
    uint16_t lane;

    fill_header(&header, PF_FT_CASE_ROWS);
    fill_ramp_weights(env->weights, PF_FT_CASE_ROWS);
    expect(env, pf_ft_model_bind(&model, &header, env->weights), "model.bind_ramp");

    calls = 0;
    expect(env, run_pair(env, &model, mixed, 3, &calls), "num.mixed_matches");
    expect(env, calls == PF_FT_TILE_COUNT, "num.mixed_four_jobs");

    calls = 0;
    expect(env, run_pair(env, &model, first, 1, &calls), "num.first_row");
    calls = 0;
    expect(env, run_pair(env, &model, last, 1, &calls), "num.last_row");
    calls = 0;
    expect(env, run_pair(env, &model, dup, 3, &calls), "num.duplicate_features");
    {
        uint16_t one = 2;
        pf_ft_ref_accumulate(&model, &one, 1, env->acc_b);
        expect(env,
               env->acc_a[0] == env->acc_b[0] * 3 &&
                   env->acc_a[256] == env->acc_b[256] * 3 &&
                   env->acc_a[1023] == env->acc_b[1023] * 3,
               "num.duplicate_triples_value");
    }
    calls = 0;
    expect(env, run_pair(env, &model, all_rows, 8, &calls), "num.all_rows");
    calls = 0;
    expect(env, run_pair(env, &model, shuffled, 4, &calls), "num.shuffled");

    expect(env, pf_ft_ref_accumulate(&model, NULL, 0, env->acc_a), "num.empty_ref");
    expect(env, pf_ft_tiled_accumulate(
                    &model, NULL, 0, NULL, NULL, env->acc_b),
           "num.empty_tiled");
    expect(env, vectors_equal(env->acc_a, env->acc_b, PF_FT_L1), "num.empty_match");
    expect(env, all_equal(env->acc_a, PF_FT_L1, 0), "num.empty_zero");

    expect(env, !pf_ft_ref_accumulate(&model, &bad, 1, env->acc_a),
           "num.ref_reject_oob");
    expect(env, !pf_ft_tiled_accumulate(
                    &model, &bad, 1, mock_mac_tile, &calls, env->acc_b),
           "num.tiled_reject_oob");
    expect(env, !pf_ft_ref_accumulate(&model, mixed, 1, NULL), "num.ref_reject_null_out");
    expect(env, !pf_ft_tiled_accumulate(
                    &model, mixed, 1, mock_mac_tile, &calls, NULL),
           "num.tiled_reject_null_out");

    fail.calls = 0;
    fail.fail_tile = 2;
    expect(env, !pf_ft_tiled_accumulate(
                    &model, mixed, 3, fail_on_tile, &fail, env->acc_b),
           "num.backend_fail_stops");
    expect(env, fail.calls == 3, "num.backend_fail_on_tile2");

    memset(&job, 0, sizeof(job));
    job.tile_id = 4;
    job.feature_count = 1;
    job.cout = (uint16_t)PF_FT_MAC_MAX_CHANNELS;
    job.feature_index[0] = 0;
    expect(env, !pf_ft_ref_accumulate_tile(&model, &job, env->tile),
           "num.reject_bad_tile_id");
    job.tile_id = 1;
    job.cout = 128;
    expect(env, !pf_ft_ref_accumulate_tile(&model, &job, env->tile),
           "num.reject_bad_cout");

    for (tile = 0; tile < PF_FT_TILE_COUNT; ++tile) {
        job.tile_id = tile;
        job.cout = (uint16_t)PF_FT_MAC_MAX_CHANNELS;
        job.feature_count = 2;
        job.feature_index[0] = 1;
        job.feature_index[1] = 6;
        pf_ft_ref_accumulate(&model, job.feature_index, 2, env->acc_a);
        expect(env, pf_ft_ref_accumulate_tile(&model, &job, env->tile),
               tile == 0 ? "slice.tile0" :
               tile == 1 ? "slice.tile1" :
               tile == 2 ? "slice.tile2" : "slice.tile3");
        {
            int ok = 1;
            for (lane = 0; lane < PF_FT_MAC_MAX_CHANNELS; ++lane) {
                if (env->tile[lane] !=
                    env->acc_a[tile * PF_FT_MAC_MAX_CHANNELS + lane]) {
                    ok = 0;
                    break;
                }
            }
            expect(env, ok,
                   tile == 0 ? "slice.tile0_window" :
                   tile == 1 ? "slice.tile1_window" :
                   tile == 2 ? "slice.tile2_window" : "slice.tile3_window");
        }
    }
}

static void test_markers_and_extremes(const pf_ft_case_env_t *env) {
    pf_ft_pack_header_t header;
    pf_ft_model_t model;
    uint32_t calls;
    uint16_t three[] = {0, 4, 7};
    uint16_t eight[] = {0, 1, 2, 3, 4, 5, 6, 7};

    fill_header(&header, PF_FT_CASE_ROWS);
    fill_tile_markers(env->weights, PF_FT_CASE_ROWS);
    pf_ft_model_bind(&model, &header, env->weights);
    calls = 0;
    expect(env, run_pair(env, &model, three, 3, &calls), "mark.tiled_matches");
    expect(env, all_equal(env->acc_a, PF_FT_MAC_MAX_CHANNELS, 3),
           "mark.tile0_times_3");
    expect(env, all_equal(env->acc_a + PF_FT_MAC_MAX_CHANNELS,
                          PF_FT_MAC_MAX_CHANNELS, 6),
           "mark.tile1_times_3");
    expect(env, all_equal(env->acc_a + 2u * PF_FT_MAC_MAX_CHANNELS,
                          PF_FT_MAC_MAX_CHANNELS, -9),
           "mark.tile2_times_3");
    expect(env, all_equal(env->acc_a + 3u * PF_FT_MAC_MAX_CHANNELS,
                          PF_FT_MAC_MAX_CHANNELS, 12),
           "mark.tile3_times_3");

    fill_const_weights(env->weights, PF_FT_CASE_ROWS, 127);
    pf_ft_model_bind(&model, &header, env->weights);
    calls = 0;
    expect(env, run_pair(env, &model, eight, 8, &calls), "sat.pos127_match");
    expect(env, all_equal(env->acc_a, PF_FT_L1, 8 * 127), "sat.pos127_value");

    fill_const_weights(env->weights, PF_FT_CASE_ROWS, -128);
    pf_ft_model_bind(&model, &header, env->weights);
    calls = 0;
    expect(env, run_pair(env, &model, eight, 8, &calls), "sat.neg128_match");
    expect(env, all_equal(env->acc_a, PF_FT_L1, 8 * -128), "sat.neg128_value");
}

int pf_ft_run_stage_a_cases(pf_ft_case_env_t *env) {
    if (env == NULL || env->weights == NULL || env->acc_a == NULL ||
        env->acc_b == NULL || env->tile == NULL)
        return -1;
    test_abi(env);
    test_header(env);
    test_jobs_and_bind(env);
    test_numeric(env);
    test_markers_and_extremes(env);
    return 0;
}
