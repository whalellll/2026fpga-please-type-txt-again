#ifndef PF_MLP_STAGE_B_CASES_H
#define PF_MLP_STAGE_B_CASES_H

#include "pf_mlp_stage_b.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*pf_mlp_expect_fn)(int ok, const char *name, void *ctx);

typedef struct {
    /* Working buffers owned by caller. */
    int8_t *fc0_w;   /* L2 * L1 */
    int32_t *fc0_b;  /* L2 */
    int8_t *fc1_w;   /* L3 * 64 */
    int32_t *fc1_b;  /* L3 */
    int8_t *fc2_w;   /* 128 */
    int32_t *fc2_b;  /* 1 */
    uint8_t *x;      /* L1 */
    int32_t *tmp32;  /* at least L2 */
    int32_t *tmp32b; /* at least L2 */
    pf_mlp_expect_fn expect;
    void *expect_ctx;
} pf_mlp_case_env_t;

int pf_mlp_run_stage_b_cases(pf_mlp_case_env_t *env);

#ifdef __cplusplus
}
#endif

#endif
