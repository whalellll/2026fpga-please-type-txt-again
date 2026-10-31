#ifndef XY_COREMARK_REFERENCE_H
#define XY_COREMARK_REFERENCE_H
/* Six measured CPU60 ROM BRAM samples, main e7288be9, bit6565ad37.
 * docs/validation/integrated-opt60-board-20261025/opt60-coremark-abab-04/result.json
 * comparisons.candidate.coremark_per_mhz.all_values. No Linux score claim. */
static const double xy_cm_reference_scores[6]={
    5.278868675096502,5.279519977596405,5.279587947167240,
    5.279183795951675,5.279670725943637,5.279516480762626
};
#define XY_CM_REFERENCE_MEAN 5.279391267086348
#endif
