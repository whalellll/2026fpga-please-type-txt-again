#ifndef PF_MLP_MAC_FC0_H
#define PF_MLP_MAC_FC0_H

#include "pf_mlp_stage_b.h"
#include "xiangqi_nnue_mac.h"

#ifdef __cplusplus
extern "C" {
#endif

/* xiangqi_nnue_mac_t* ctx — one dense fc0 cin-tile via MacAccel U8xS8. */
int pf_mlp_mac_fc0_tile(
    void *ctx,
    const pf_mlp_model_t *model,
    const uint8_t *x_l1,
    const pf_mlp_fc0_tile_job_t *job,
    int32_t *partial_out32);

typedef struct {
    xiangqi_nnue_mac_t *mac;
    const uint8_t *pack_cpu;
    uint32_t pack_bus_addr;
    uint32_t stack;
} pf_mlp_mac_prepacked_ctx_t;

/*
 * Same Stage-B callback, but the MAC reads an already packed tile directly
 * from the resident PFSB DDR image. No fc0 weight repacking or copying occurs.
 */
int pf_mlp_mac_prepacked_fc0_tile(
    void *ctx,
    const pf_mlp_model_t *model,
    const uint8_t *x_l1,
    const pf_mlp_fc0_tile_job_t *job,
    int32_t *partial_out32);

#ifdef __cplusplus
}
#endif

#endif
