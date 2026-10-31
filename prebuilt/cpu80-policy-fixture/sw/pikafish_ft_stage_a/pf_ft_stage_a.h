#ifndef PF_FT_STAGE_A_H
#define PF_FT_STAGE_A_H

/*
 * Stage A: Pikafish feature-transformer acceleration contract.
 *
 * Goal: accelerate official-style FT accumulation
 *   acc[L1] += sum_i weight[feature_i][0..L1)
 * by tiling L1 across MAC jobs with cout <= MAC_MAX_CHANNELS (256).
 *
 * MLP / PSQT / threats-full decode remain out of scope for Stage A.
 * This header is the model-side + accelerator-side shared ABI.
 */

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Official Pikafish L1 width (nnue_architecture.h). */
#define PF_FT_L1                 1024u
/* Current MacAccel DDR-kernel single-job channel cap. */
#define PF_FT_MAC_MAX_CHANNELS   256u
#define PF_FT_TILE_COUNT         (PF_FT_L1 / PF_FT_MAC_MAX_CHANNELS) /* 4 */
#define PF_FT_MAX_ACTIVE_HALFKA  32u
#define PF_FT_MAX_ACTIVE_THREAT  64u
/* Stage A acceptance uses HalfKA-sized active lists; threats may pad later. */
#define PF_FT_MAX_ACTIVE         PF_FT_MAX_ACTIVE_HALFKA

#define PF_FT_PACK_MAGIC         0x31414650u /* 'PFA1' little-endian */
#define PF_FT_PACK_VERSION       0x00010000u

/* One tile job fed to a MAC-like backend (or the CPU reference). */
typedef struct {
    uint16_t tile_id;       /* 0 .. TILE_COUNT-1 */
    uint16_t feature_count; /* 0 .. MAX_ACTIVE */
    uint16_t cout;          /* must be MAC_MAX_CHANNELS for full tiles */
    uint16_t reserved;
    uint16_t feature_index[PF_FT_MAX_ACTIVE];
} pf_ft_tile_job_t;

typedef struct {
    uint32_t magic;
    uint32_t version;
    uint16_t l1;
    uint16_t tile_width;
    uint16_t tile_count;
    uint16_t max_active;
    uint32_t feature_rows; /* number of addressable feature rows */
    uint32_t flags;        /* bit0: weights are int8 row-major [row][L1] */
    uint32_t weight_bytes; /* feature_rows * L1 * sizeof(int8) */
    uint32_t crc32;        /* CRC of weight blob; 0 = skip in host tests */
} pf_ft_pack_header_t;

typedef struct {
    pf_ft_pack_header_t header;
    const int8_t *weights; /* row-major: weights[row * L1 + lane] */
} pf_ft_model_t;

/* Backend: compute one tile into out[0..cout). Returns 1 on success. */
typedef int (*pf_ft_tile_backend_fn)(
    void *ctx,
    const pf_ft_model_t *model,
    const pf_ft_tile_job_t *job,
    int32_t *out_tile);

int pf_ft_pack_header_valid(const pf_ft_pack_header_t *h);
int pf_ft_model_bind(
    pf_ft_model_t *model,
    const pf_ft_pack_header_t *header,
    const int8_t *weights);

/* Split a full L1 request into TILE_COUNT tile jobs (feature list shared). */
int pf_ft_build_tile_jobs(
    const uint16_t *feature_index,
    uint16_t feature_count,
    pf_ft_tile_job_t jobs[PF_FT_TILE_COUNT]);

/* CPU reference: full-width accumulation into acc_l1[L1]. */
int pf_ft_ref_accumulate(
    const pf_ft_model_t *model,
    const uint16_t *feature_index,
    uint16_t feature_count,
    int32_t *acc_l1);

/* CPU reference for one tile; used as golden and as software backend. */
int pf_ft_ref_accumulate_tile(
    const pf_ft_model_t *model,
    const pf_ft_tile_job_t *job,
    int32_t *out_tile);

/*
 * Run Stage A tiled path through backend, stitch tiles into acc_l1[L1].
 * When backend == NULL, uses pf_ft_ref_accumulate_tile.
 */
int pf_ft_tiled_accumulate(
    const pf_ft_model_t *model,
    const uint16_t *feature_index,
    uint16_t feature_count,
    pf_ft_tile_backend_fn backend,
    void *backend_ctx,
    int32_t *acc_l1);

#ifdef __cplusplus
}
#endif

#endif
