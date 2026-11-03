#ifndef PF_MLP_MAC_PACK_H
#define PF_MLP_MAC_PACK_H

#include <stdint.h>

/*
 * Fixed DDR image for all 16 official Pikafish Stage-B layer stacks.
 * The fc0 weights are stored in the byte order consumed by the existing
 * 256-channel U8xS8 MAC, so inference only has to submit four DMA jobs.
 */
#define PF_STAGEB_PACK_MAGIC              0x42534650u /* 'PFSB' LE */
#define PF_STAGEB_PACK_VERSION            0x00020000u
#define PF_STAGEB_STACK_MAGIC             0x31534650u /* 'PFS1' LE */
#define PF_STAGEB_STACK_COUNT             16u

#define PF_STAGEB_DDR_BUS_BASE            0x1b000000u
#define PF_STAGEB_DDR_CPU_ALIAS           0x9b000000u
#define PF_STAGEB_DDR_BYTES               0x00100000u

#define PF_STAGEB_HEADER_BYTES            0x00001000u
#define PF_STAGEB_STACK_SLOT_BYTES        0x00009000u
#define PF_STAGEB_STACK_HEADER_BYTES      0x00000100u
#define PF_STAGEB_STACK_BASE              PF_STAGEB_HEADER_BYTES

#define PF_STAGEB_FC0_PACKED_OFFSET       0x00000100u
#define PF_STAGEB_FC0_TILE_BYTES          0x00002000u
#define PF_STAGEB_FC0_TILE_COUNT          4u
#define PF_STAGEB_FC0_PACKED_BYTES        0x00008000u
#define PF_STAGEB_FC0_BIAS_OFFSET         0x00008100u
#define PF_STAGEB_FC0_BIAS_BYTES          0x00000080u
#define PF_STAGEB_FC1_WEIGHT_OFFSET       0x00008180u
#define PF_STAGEB_FC1_WEIGHT_BYTES        0x00000800u
#define PF_STAGEB_FC1_BIAS_OFFSET         0x00008980u
#define PF_STAGEB_FC1_BIAS_BYTES          0x00000080u
#define PF_STAGEB_FC2_WEIGHT_OFFSET       0x00008a00u
#define PF_STAGEB_FC2_WEIGHT_BYTES        0x00000080u
#define PF_STAGEB_FC2_BIAS_OFFSET         0x00008a80u
#define PF_STAGEB_FC2_BIAS_BYTES          0x00000004u
#define PF_STAGEB_STACK_DATA_END          0x00008a84u

#define PF_STAGEB_PACK_USED_BYTES \
    (PF_STAGEB_STACK_BASE + \
     PF_STAGEB_STACK_COUNT * PF_STAGEB_STACK_SLOT_BYTES)

/* Scratch lives above the immutable 0x91000-byte model image. */
#define PF_STAGEB_INPUT_OFFSET            0x000f0000u
#define PF_STAGEB_INPUT_BYTES             0x00001000u
#define PF_STAGEB_OUTPUT_OFFSET           0x000f1000u
#define PF_STAGEB_OUTPUT_BYTES            0x00001000u

#define PF_STAGEB_FLAG_MAC_NATIVE_FC0     0x00000001u
#define PF_STAGEB_FLAG_ROW_MAJOR_TAIL     0x00000002u

/* PFSB v2 fixed header fields. The decoded-stream SHA and MLPS tuple bind the
 * accelerator image to the already-validated PFF1 used by the engine. */
#define PF_STAGEB_H_MAGIC                 0x00u
#define PF_STAGEB_H_VERSION               0x04u
#define PF_STAGEB_H_HEADER_BYTES          0x08u
#define PF_STAGEB_H_USED_BYTES            0x0cu
#define PF_STAGEB_H_STACK_COUNT           0x10u
#define PF_STAGEB_H_STACK_SLOT_BYTES      0x14u
#define PF_STAGEB_H_STACK_BASE            0x18u
#define PF_STAGEB_H_FC0_OFFSET            0x1cu
#define PF_STAGEB_H_FC0_TILE_BYTES        0x20u
#define PF_STAGEB_H_FC0_TILE_COUNT        0x24u
#define PF_STAGEB_H_FLAGS                 0x28u
#define PF_STAGEB_H_PAYLOAD_CRC32         0x2cu
#define PF_STAGEB_H_SOURCE_SHA256         0x30u
#define PF_STAGEB_H_DECODED_SHA256        0x50u
#define PF_STAGEB_H_MLPS_BYTES            0x70u
#define PF_STAGEB_H_MLPS_CRC32            0x74u
#define PF_STAGEB_H_HEADER_CRC32          0x78u

#define PF_STAGEB_S_DATA_CRC32            0x3cu
#define PF_STAGEB_S_FC0_CRC32             0x40u

static inline uint32_t pf_stageb_stack_offset(uint32_t stack) {
    return PF_STAGEB_STACK_BASE + stack * PF_STAGEB_STACK_SLOT_BYTES;
}

static inline uint32_t pf_stageb_fc0_tile_offset(
    uint32_t stack, uint32_t tile) {
    return pf_stageb_stack_offset(stack) + PF_STAGEB_FC0_PACKED_OFFSET +
           tile * PF_STAGEB_FC0_TILE_BYTES;
}

#endif
