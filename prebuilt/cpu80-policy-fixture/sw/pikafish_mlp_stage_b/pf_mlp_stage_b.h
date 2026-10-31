#ifndef PF_MLP_STAGE_B_H
#define PF_MLP_STAGE_B_H

/*
 * Stage B: Pikafish-style post-FT MLP contract.
 *
 * After Stage A produces a dense L1 accumulator (or u8 transformed features),
 * Stage B runs the Stockfish/Pikafish network tail:
 *
 *   x[u8,1024]
 *     -> fc0 dense 1024x32 (MAC-friendly; cin tiled by 256)
 *     -> dual SqrClippedReLU || ClippedReLU  (shift = WeightScaleBits+1)
 *     -> concat 64
 *     -> fc1 64x32
 *     -> dual activations (shift = WeightScaleBits)
 *     -> concat 128
 *     -> fc2 128x1 + skip(fc0[30]-fc0[31])
 *     -> scale to centipawn-like score
 *
 * PSQT / layer-stacks remain out of scope. Weights use simple row-major
 * layout for board bring-up (not the SIMD-scrambled official file order).
 */

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PF_MLP_L1                 1024u
#define PF_MLP_L2                 32u
#define PF_MLP_L3                 32u
#define PF_MLP_FC0_IN             PF_MLP_L1
#define PF_MLP_FC0_OUT            PF_MLP_L2
#define PF_MLP_FC1_IN             (PF_MLP_L2 * 2u)   /* 64 */
#define PF_MLP_FC1_OUT            PF_MLP_L3
#define PF_MLP_FC2_IN             (PF_MLP_L2 * 2u + PF_MLP_L3 * 2u) /* 128 */
#define PF_MLP_FC2_OUT            1u

#define PF_MLP_MAC_MAX_CHANNELS   256u
#define PF_MLP_FC0_CIN_TILES      (PF_MLP_L1 / PF_MLP_MAC_MAX_CHANNELS) /* 4 */

#define PF_MLP_WEIGHT_SCALE_BITS  6
#define PF_MLP_ACT0_SHIFT         (PF_MLP_WEIGHT_SCALE_BITS + 1) /* 7 */
#define PF_MLP_ACT1_SHIFT         PF_MLP_WEIGHT_SCALE_BITS       /* 6 */
#define PF_MLP_HIDDEN_ONE_VAL     128
#define PF_MLP_OUTPUT_SCALE       16

#define PF_MLP_PACK_MAGIC         0x31424650u /* 'PFB1' LE */
#define PF_MLP_PACK_VERSION       0x00010000u

typedef struct {
    uint32_t magic;
    uint32_t version;
    uint16_t l1;
    uint16_t l2;
    uint16_t l3;
    uint16_t weight_scale_bits;
    uint32_t flags; /* bit0: row-major int8 weights */
    uint32_t crc32;
} pf_mlp_pack_header_t;

/*
 * Weight blobs are contiguous and owned by the caller:
 *   fc0_w: int8[out][in]  = L2 * L1
 *   fc0_b: int32[L2]
 *   fc1_w: int8[out][in]  = L3 * 64
 *   fc1_b: int32[L3]
 *   fc2_w: int8[1][128]
 *   fc2_b: int32[1]
 */
typedef struct {
    pf_mlp_pack_header_t header;
    const int8_t *fc0_w;
    const int32_t *fc0_b;
    const int8_t *fc1_w;
    const int32_t *fc1_b;
    const int8_t *fc2_w;
    const int32_t *fc2_b;
} pf_mlp_model_t;

/* One cin-tile of dense fc0: inputs[base .. base+255] -> partial[32]. */
typedef struct {
    uint16_t tile_id; /* 0..3 */
    uint16_t cin;     /* 256 */
    uint16_t cout;    /* 32 */
    uint16_t reserved;
} pf_mlp_fc0_tile_job_t;

typedef int (*pf_mlp_fc0_tile_backend_fn)(
    void *ctx,
    const pf_mlp_model_t *model,
    const uint8_t *x_l1,
    const pf_mlp_fc0_tile_job_t *job,
    int32_t *partial_out32);

int pf_mlp_pack_header_valid(const pf_mlp_pack_header_t *h);
int pf_mlp_model_bind(
    pf_mlp_model_t *model,
    const pf_mlp_pack_header_t *header,
    const int8_t *fc0_w, const int32_t *fc0_b,
    const int8_t *fc1_w, const int32_t *fc1_b,
    const int8_t *fc2_w, const int32_t *fc2_b);

/* Quantize Stage-A style int32 FT lanes into official-like u8 features. */
void pf_mlp_quantize_ft(
    const int32_t *acc_l1, uint8_t *x_u8, uint32_t n, int shift);

void pf_mlp_clipped_relu_i32(
    const int32_t *in, uint8_t *out, uint32_t n, int shift);
void pf_mlp_sqr_clipped_relu_i32(
    const int32_t *in, uint8_t *out, uint32_t n, int shift);

/* Dense affine: out[j] = bias[j] + sum_i w[j*in_dim + i] * x[i]. */
void pf_mlp_affine_u8_i8(
    const uint8_t *x, uint32_t in_dim,
    const int8_t *w, const int32_t *bias,
    uint32_t out_dim, int32_t *out);

/* CPU fc0 over full 1024 inputs. */
int pf_mlp_ref_fc0(
    const pf_mlp_model_t *model, const uint8_t *x_l1, int32_t *fc0_out);

/* One cin tile reference (no bias). */
int pf_mlp_ref_fc0_tile(
    const pf_mlp_model_t *model, const uint8_t *x_l1,
    const pf_mlp_fc0_tile_job_t *job, int32_t *partial_out32);

/* Tiled fc0 via backend; adds bias after summing tiles. backend=NULL => ref. */
int pf_mlp_tiled_fc0(
    const pf_mlp_model_t *model, const uint8_t *x_l1,
    pf_mlp_fc0_tile_backend_fn backend, void *backend_ctx,
    int32_t *fc0_out);

/* Full Stage-B propagate from u8[L1] to score. fc0_backend may be NULL. */
int pf_mlp_propagate(
    const pf_mlp_model_t *model,
    const uint8_t *x_l1,
    pf_mlp_fc0_tile_backend_fn fc0_backend,
    void *fc0_backend_ctx,
    int32_t *score_out);

/* Same scale as Pikafish NetworkArchitecture::propagate. */
int32_t pf_mlp_scale_output(int32_t fwd_out);

#ifdef __cplusplus
}
#endif

#endif
