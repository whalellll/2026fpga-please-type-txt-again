#ifndef PF_FT_STAGE_A_CASES_H
#define PF_FT_STAGE_A_CASES_H

#include "pf_ft_stage_a.h"

#ifdef __cplusplus
extern "C" {
#endif

enum {
    PF_FT_CASE_ROWS = 8
};

typedef void (*pf_ft_expect_fn)(int ok, const char *name, void *ctx);

typedef struct {
    int8_t *weights;          /* CASE_ROWS * L1 */
    int32_t *acc_a;           /* L1 */
    int32_t *acc_b;           /* L1 */
    int32_t *tile;            /* MAC_MAX_CHANNELS */
    pf_ft_expect_fn expect;
    void *expect_ctx;
} pf_ft_case_env_t;

/* Host and board share these cases. Returns failure count. */
int pf_ft_run_stage_a_cases(pf_ft_case_env_t *env);

#ifdef __cplusplus
}
#endif

#endif
