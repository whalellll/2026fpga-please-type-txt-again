#ifndef PF_MLP_GOLDEN_PACK_H
#define PF_MLP_GOLDEN_PACK_H

#include <stdint.h>

/*
 * Host-generated, official-Pikafish Stage-B acceptance vectors.
 * Each record contains fc0[32] followed by the final positional score.
 */
#define PF_STAGEB_GOLDEN_MAGIC          0x31474650u /* 'PFG1' LE */
#define PF_STAGEB_GOLDEN_VERSION        0x00010000u
#define PF_STAGEB_GOLDEN_HEADER_BYTES   0x00000100u
#define PF_STAGEB_GOLDEN_STACK_COUNT    16u
#define PF_STAGEB_GOLDEN_CASE_COUNT     6u
#define PF_STAGEB_GOLDEN_LANE_COUNT     32u
#define PF_STAGEB_GOLDEN_RECORD_BYTES   \
    ((PF_STAGEB_GOLDEN_LANE_COUNT + 1u) * 4u)
#define PF_STAGEB_GOLDEN_PAYLOAD_BYTES  \
    (PF_STAGEB_GOLDEN_STACK_COUNT * PF_STAGEB_GOLDEN_CASE_COUNT * \
     PF_STAGEB_GOLDEN_RECORD_BYTES)
#define PF_STAGEB_GOLDEN_TOTAL_BYTES    \
    (PF_STAGEB_GOLDEN_HEADER_BYTES + PF_STAGEB_GOLDEN_PAYLOAD_BYTES)

#define PF_STAGEB_GOLDEN_FLAG_FC0       (1u << 0)
#define PF_STAGEB_GOLDEN_FLAG_SCORE     (1u << 1)

/* Current pinned official MLPS section and derived PFSB payload. */
#define PF_STAGEB_GOLDEN_MLPS_CRC32     0x8c4b6711u
#define PF_STAGEB_GOLDEN_PFSB_CRC32     0x7261d3e8u

static inline uint32_t pf_stageb_golden_record_offset(
    uint32_t stack, uint32_t input_case) {
    return PF_STAGEB_GOLDEN_HEADER_BYTES +
           (stack * PF_STAGEB_GOLDEN_CASE_COUNT + input_case) *
               PF_STAGEB_GOLDEN_RECORD_BYTES;
}

#endif
