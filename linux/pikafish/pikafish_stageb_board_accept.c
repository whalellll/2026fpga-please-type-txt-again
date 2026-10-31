#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include "mac_accel_kernel.h"
#include "pf_mlp_golden_pack.h"
#include "pf_mlp_mac_pack.h"
#include "pf_mlp_stage_b.h"

#define MAC_REGISTER_PHYSICAL 0x1fe10000u
#define SCRATCH_CANARY 0xa5u
#define OUTPUT_POISON 0x5au
#define MAC_POLL_LIMIT 5000000u

typedef struct {
    const uint8_t *data;
    size_t bytes;
    int fd;
} mapped_file_t;

typedef struct {
    volatile uint32_t *registers;
    volatile uint32_t *physical_ddr;
    uint8_t *ddr;
    uint32_t stack;
    uint32_t jobs;
    uint32_t failed_jobs;
    uint64_t cycles;
} board_context_t;

/* The V3.5 uncached DDR alias accepts aligned 32-bit transfers only. */
static int transfer_words(volatile uint32_t *physical, uint8_t *shadow,
                          size_t offset, size_t bytes, int publish) {
    size_t i;
    if (physical == NULL || shadow == NULL || ((offset | bytes) & 3u) != 0u ||
        offset > PF_STAGEB_DDR_BYTES || bytes > PF_STAGEB_DDR_BYTES - offset)
        return 0;
    for (i = 0; i < bytes; i += 4u) {
        uint32_t word;
        if (publish) {
            memcpy(&word, shadow + offset + i, sizeof(word));
            physical[(offset + i) / 4u] = word;
        } else {
            word = physical[(offset + i) / 4u];
            memcpy(shadow + offset + i, &word, sizeof(word));
        }
    }
    __sync_synchronize();
    return 1;
}

static uint32_t read_le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static int32_t read_le_i32(const uint8_t *p) {
    return (int32_t)read_le32(p);
}

static uint32_t crc32_bytes(const uint8_t *data, size_t bytes) {
    uint32_t crc = 0xffffffffu;
    size_t i;
    for (i = 0; i < bytes; ++i) {
        unsigned int bit;
        crc ^= data[i];
        for (bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return crc ^ 0xffffffffu;
}

static void fail_reason(const char *reason) {
    fprintf(stderr, "PIKAFISH_STAGEB_BOARD_GOLDEN_FAIL reason=%s\n", reason);
}

static int map_file_readonly(const char *path, mapped_file_t *mapped) {
    struct stat st;
    memset(mapped, 0, sizeof(*mapped));
    mapped->fd = -1;
    mapped->fd = open(path, O_RDONLY | O_CLOEXEC);
    if (mapped->fd < 0 || fstat(mapped->fd, &st) != 0 || st.st_size <= 0) {
        perror(path);
        if (mapped->fd >= 0)
            close(mapped->fd);
        mapped->fd = -1;
        return 0;
    }
    mapped->bytes = (size_t)st.st_size;
    mapped->data = mmap(NULL, mapped->bytes, PROT_READ, MAP_PRIVATE,
                        mapped->fd, 0);
    if (mapped->data == MAP_FAILED) {
        perror(path);
        close(mapped->fd);
        mapped->data = NULL;
        mapped->fd = -1;
        return 0;
    }
    return 1;
}

static void unmap_file(mapped_file_t *mapped) {
    if (mapped->data != NULL)
        munmap((void *)mapped->data, mapped->bytes);
    if (mapped->fd >= 0)
        close(mapped->fd);
    memset(mapped, 0, sizeof(*mapped));
    mapped->fd = -1;
}

static int validate_pfsb(const uint8_t *data, size_t bytes) {
    uint32_t stack;
    if (bytes != PF_STAGEB_PACK_USED_BYTES ||
        read_le32(data + 0) != PF_STAGEB_PACK_MAGIC ||
        read_le32(data + 4) != PF_STAGEB_PACK_VERSION ||
        read_le32(data + 8) != PF_STAGEB_HEADER_BYTES ||
        read_le32(data + 12) != PF_STAGEB_PACK_USED_BYTES ||
        read_le32(data + 16) != PF_STAGEB_STACK_COUNT ||
        read_le32(data + 20) != PF_STAGEB_STACK_SLOT_BYTES ||
        read_le32(data + 24) != PF_STAGEB_STACK_BASE ||
        read_le32(data + 28) != PF_STAGEB_FC0_PACKED_OFFSET ||
        read_le32(data + 32) != PF_STAGEB_FC0_TILE_BYTES ||
        read_le32(data + 36) != PF_STAGEB_FC0_TILE_COUNT ||
        read_le32(data + 40) != (PF_STAGEB_FLAG_MAC_NATIVE_FC0 |
                                 PF_STAGEB_FLAG_ROW_MAJOR_TAIL) ||
        read_le32(data + PF_STAGEB_H_PAYLOAD_CRC32) != PF_STAGEB_GOLDEN_PFSB_CRC32 ||
        crc32_bytes(data, PF_STAGEB_H_HEADER_CRC32) !=
            read_le32(data + PF_STAGEB_H_HEADER_CRC32) ||
        crc32_bytes(data + PF_STAGEB_HEADER_BYTES,
                    bytes - PF_STAGEB_HEADER_BYTES) !=
            read_le32(data + PF_STAGEB_H_PAYLOAD_CRC32)) {
        fprintf(stderr,
                "PFSB_HEADER_DIAG bytes=%u magic=%08x version=%08x "
                "used=%08x header_crc=%08x payload_crc=%08x expected=%08x\n",
                (unsigned)bytes, read_le32(data), read_le32(data + 4),
                read_le32(data + 12),
                crc32_bytes(data, PF_STAGEB_H_HEADER_CRC32),
                crc32_bytes(data + PF_STAGEB_HEADER_BYTES,
                            bytes - PF_STAGEB_HEADER_BYTES),
                PF_STAGEB_GOLDEN_PFSB_CRC32);
        return 0;
    }
    for (stack = 0; stack < PF_STAGEB_STACK_COUNT; ++stack) {
        const uint8_t *slot = data + pf_stageb_stack_offset(stack);
        if (read_le32(slot + 0) != PF_STAGEB_STACK_MAGIC ||
            read_le32(slot + 4) != stack ||
            read_le32(slot + 8) != PF_STAGEB_STACK_SLOT_BYTES ||
            read_le32(slot + 12) != PF_STAGEB_FC0_PACKED_OFFSET ||
            read_le32(slot + 16) != PF_STAGEB_FC0_PACKED_BYTES ||
            read_le32(slot + 20) != PF_STAGEB_FC0_BIAS_OFFSET ||
            read_le32(slot + 24) != PF_STAGEB_FC0_BIAS_BYTES ||
            read_le32(slot + 28) != PF_STAGEB_FC1_WEIGHT_OFFSET ||
            read_le32(slot + 32) != PF_STAGEB_FC1_WEIGHT_BYTES ||
            read_le32(slot + 36) != PF_STAGEB_FC1_BIAS_OFFSET ||
            read_le32(slot + 40) != PF_STAGEB_FC1_BIAS_BYTES ||
            read_le32(slot + 44) != PF_STAGEB_FC2_WEIGHT_OFFSET ||
            read_le32(slot + 48) != PF_STAGEB_FC2_WEIGHT_BYTES ||
            read_le32(slot + 52) != PF_STAGEB_FC2_BIAS_OFFSET ||
            read_le32(slot + 56) != PF_STAGEB_FC2_BIAS_BYTES ||
            crc32_bytes(slot + PF_STAGEB_STACK_HEADER_BYTES,
                        PF_STAGEB_STACK_DATA_END -
                            PF_STAGEB_STACK_HEADER_BYTES) !=
                    read_le32(slot + PF_STAGEB_S_DATA_CRC32) ||
            crc32_bytes(slot + PF_STAGEB_FC0_PACKED_OFFSET,
                        PF_STAGEB_FC0_PACKED_BYTES + PF_STAGEB_FC0_BIAS_BYTES) !=
                    read_le32(slot + PF_STAGEB_S_FC0_CRC32)) {
            fprintf(stderr,
                    "PFSB_STACK_DIAG index=%u magic=%08x slot=%08x "
                    "data_crc=%08x expected=%08x fc0_crc=%08x expected=%08x\n",
                    (unsigned)stack, read_le32(slot), read_le32(slot + 8),
                    crc32_bytes(slot + PF_STAGEB_STACK_HEADER_BYTES,
                                PF_STAGEB_STACK_DATA_END -
                                    PF_STAGEB_STACK_HEADER_BYTES),
                    read_le32(slot + PF_STAGEB_S_DATA_CRC32),
                    crc32_bytes(slot + PF_STAGEB_FC0_PACKED_OFFSET,
                                PF_STAGEB_FC0_PACKED_BYTES +
                                    PF_STAGEB_FC0_BIAS_BYTES),
                    read_le32(slot + PF_STAGEB_S_FC0_CRC32));
            return 0;
        }
    }
    return 1;
}

static int validate_golden(const uint8_t *data, size_t bytes,
                           const uint8_t *pfsb) {
    if (bytes != PF_STAGEB_GOLDEN_TOTAL_BYTES ||
        read_le32(data + 0) != PF_STAGEB_GOLDEN_MAGIC ||
        read_le32(data + 4) != PF_STAGEB_GOLDEN_VERSION ||
        read_le32(data + 8) != PF_STAGEB_GOLDEN_HEADER_BYTES ||
        read_le32(data + 12) != PF_STAGEB_GOLDEN_TOTAL_BYTES ||
        read_le32(data + 16) != PF_STAGEB_GOLDEN_STACK_COUNT ||
        read_le32(data + 20) != PF_STAGEB_GOLDEN_CASE_COUNT ||
        read_le32(data + 24) != PF_STAGEB_GOLDEN_LANE_COUNT ||
        read_le32(data + 28) != PF_STAGEB_GOLDEN_RECORD_BYTES ||
        read_le32(data + 32) != PF_STAGEB_GOLDEN_PFSB_CRC32 ||
        read_le32(data + 36) != PF_STAGEB_GOLDEN_MLPS_CRC32 ||
        read_le32(data + 44) != (PF_STAGEB_GOLDEN_FLAG_FC0 |
                                 PF_STAGEB_GOLDEN_FLAG_SCORE) ||
        memcmp(data + 48, pfsb + 48, 32) != 0 ||
        crc32_bytes(data + PF_STAGEB_GOLDEN_HEADER_BYTES,
                    PF_STAGEB_GOLDEN_PAYLOAD_BYTES) != read_le32(data + 40))
        return 0;
    return 1;
}

static void fill_input(uint8_t *input, uint32_t pattern, uint32_t stack) {
    uint32_t state = 0x9e3779b9u ^ (stack * 0x45d9f3bu) ^ pattern;
    uint32_t i;
    for (i = 0; i < PF_MLP_L1; ++i) {
        switch (pattern) {
        case 0:
            input[i] = 0;
            break;
        case 1:
            input[i] = 127;
            break;
        case 2:
            input[i] = (uint8_t)(i & 127u);
            break;
        case 3:
            input[i] = (uint8_t)((i * 37u + stack * 11u) & 127u);
            break;
        case 4:
            input[i] = i % 17u == 0u ? 127u : 0u;
            break;
        default:
            state ^= state << 13;
            state ^= state >> 17;
            state ^= state << 5;
            input[i] = (uint8_t)(state & 127u);
            break;
        }
    }
}

static int hardware_tile(void *opaque, const pf_mlp_model_t *model,
                         const uint8_t *input,
                         const pf_mlp_fc0_tile_job_t *tile,
                         int32_t *partial) {
    board_context_t *ctx = (board_context_t *)opaque;
    mac_kernel_job_t job;
    mac_kernel_buffer_sizes_t sizes;
    uint8_t *input_scratch;
    uint8_t *output_scratch;
    uint32_t feature;
    uint32_t lane;
    int result;
    (void)model;

    if (ctx == NULL || input == NULL || tile == NULL || partial == NULL ||
        ctx->stack >= PF_STAGEB_STACK_COUNT ||
        tile->tile_id >= PF_STAGEB_FC0_TILE_COUNT ||
        tile->cin != PF_MLP_MAC_MAX_CHANNELS ||
        tile->cout != PF_MLP_FC0_OUT)
        return 0;

    memset(&job, 0, sizeof(job));
    job.pixels = 1;
    job.cin = tile->cin;
    job.cout = tile->cout;
    job.compute_mode = MAC_KERNEL_MODE_U8_S8;
    job.activation = MAC_KERNEL_ACT_NONE;
    job.output_format = MAC_KERNEL_OUT_I32;
    job.zero_bias = 1;
    job.input_addr = PF_STAGEB_DDR_BUS_BASE + PF_STAGEB_INPUT_OFFSET;
    job.weight_addr = PF_STAGEB_DDR_BUS_BASE +
        pf_stageb_fc0_tile_offset(ctx->stack, tile->tile_id);
    job.bias_addr = job.input_addr;
    job.output_addr = PF_STAGEB_DDR_BUS_BASE + PF_STAGEB_OUTPUT_OFFSET;
    if (mac_kernel_validate_job(&job) != MAC_KERNEL_OK)
        return 0;
    sizes = mac_kernel_buffer_sizes(&job);
    if (sizes.input_bytes > PF_STAGEB_INPUT_BYTES ||
        sizes.output_bytes > PF_STAGEB_OUTPUT_BYTES)
        return 0;

    input_scratch = ctx->ddr + PF_STAGEB_INPUT_OFFSET;
    output_scratch = ctx->ddr + PF_STAGEB_OUTPUT_OFFSET;
    memset(input_scratch, 0, sizes.input_bytes);
    memset(output_scratch, OUTPUT_POISON, sizes.output_bytes);
    for (feature = 0; feature < tile->cin; ++feature) {
        size_t offset = (size_t)(feature / 4u) * 8u +
                        (size_t)(feature % 4u) * 2u;
        input_scratch[offset] =
            input[(uint32_t)tile->tile_id * PF_MLP_MAC_MAX_CHANNELS + feature];
    }

    if (!transfer_words(ctx->physical_ddr, ctx->ddr, PF_STAGEB_INPUT_OFFSET,
                        sizes.input_bytes, 1) ||
        !transfer_words(ctx->physical_ddr, ctx->ddr, PF_STAGEB_OUTPUT_OFFSET,
                        sizes.output_bytes, 1))
        return 0;

    __sync_synchronize();
    result = mac_kernel_submit((uintptr_t)ctx->registers, &job);
    if (result == MAC_KERNEL_OK)
        result = mac_kernel_wait((uintptr_t)ctx->registers, MAC_POLL_LIMIT);
    __sync_synchronize();
    if (result != MAC_KERNEL_OK) {
        fprintf(stderr,
                "PIKAFISH_STAGEB_BOARD_MAC_FAIL stack=%u case_tile=%u result=%d "
                "status=%08x error=%u\n",
                ctx->stack, (unsigned int)tile->tile_id, result,
                mac_kernel_read((uintptr_t)ctx->registers, MAC_KERNEL_REG_STATUS),
                mac_kernel_error_code((uintptr_t)ctx->registers));
        ctx->failed_jobs++;
        return 0;
    }
    if (!transfer_words(ctx->physical_ddr, ctx->ddr, PF_STAGEB_INPUT_OFFSET,
                        PF_STAGEB_INPUT_BYTES, 0) ||
        !transfer_words(ctx->physical_ddr, ctx->ddr, PF_STAGEB_OUTPUT_OFFSET,
                        PF_STAGEB_OUTPUT_BYTES, 0))
        return 0;
    for (lane = 0; lane < tile->cout; ++lane)
        partial[lane] = read_le_i32(output_scratch + lane * 4u);
    ctx->jobs++;
    ctx->cycles += mac_kernel_cycles((uintptr_t)ctx->registers);
    return 1;
}

static int score_from_fc0(const uint8_t *slot, const int32_t *fc0,
                          int32_t *score) {
    int32_t fc1[PF_MLP_FC1_OUT];
    int32_t fc2[PF_MLP_FC2_OUT];
    int32_t fc1_bias[PF_MLP_FC1_OUT];
    int32_t fc2_bias[PF_MLP_FC2_OUT];
    uint8_t act0_sqr[PF_MLP_FC0_OUT];
    uint8_t act0_clip[PF_MLP_FC0_OUT];
    uint8_t concat0[PF_MLP_FC1_IN];
    uint8_t act1_sqr[PF_MLP_FC1_OUT];
    uint8_t act1_clip[PF_MLP_FC1_OUT];
    uint8_t concat1[PF_MLP_FC2_IN];
    uint32_t i;
    int32_t fwd;

    for (i = 0; i < PF_MLP_FC1_OUT; ++i)
        fc1_bias[i] = read_le_i32(slot + PF_STAGEB_FC1_BIAS_OFFSET + i * 4u);
    fc2_bias[0] = read_le_i32(slot + PF_STAGEB_FC2_BIAS_OFFSET);
    pf_mlp_sqr_clipped_relu_i32(fc0, act0_sqr, PF_MLP_FC0_OUT,
                                PF_MLP_ACT0_SHIFT);
    pf_mlp_clipped_relu_i32(fc0, act0_clip, PF_MLP_FC0_OUT,
                            PF_MLP_ACT0_SHIFT);
    memcpy(concat0, act0_sqr, PF_MLP_FC0_OUT);
    memcpy(concat0 + PF_MLP_FC0_OUT, act0_clip, PF_MLP_FC0_OUT);
    pf_mlp_affine_u8_i8(
        concat0, PF_MLP_FC1_IN,
        (const int8_t *)(slot + PF_STAGEB_FC1_WEIGHT_OFFSET), fc1_bias,
        PF_MLP_FC1_OUT, fc1);
    pf_mlp_sqr_clipped_relu_i32(fc1, act1_sqr, PF_MLP_FC1_OUT,
                                PF_MLP_ACT1_SHIFT);
    pf_mlp_clipped_relu_i32(fc1, act1_clip, PF_MLP_FC1_OUT,
                            PF_MLP_ACT1_SHIFT);
    memcpy(concat1, act0_sqr, PF_MLP_FC0_OUT);
    memcpy(concat1 + PF_MLP_FC0_OUT, act0_clip, PF_MLP_FC0_OUT);
    memcpy(concat1 + PF_MLP_FC0_OUT * 2u, act1_sqr, PF_MLP_FC1_OUT);
    memcpy(concat1 + PF_MLP_FC0_OUT * 2u + PF_MLP_FC1_OUT,
           act1_clip, PF_MLP_FC1_OUT);
    pf_mlp_affine_u8_i8(
        concat1, PF_MLP_FC2_IN,
        (const int8_t *)(slot + PF_STAGEB_FC2_WEIGHT_OFFSET), fc2_bias,
        PF_MLP_FC2_OUT, fc2);
    fwd = fc2[0] + fc0[PF_MLP_FC0_OUT - 2u] -
          fc0[PF_MLP_FC0_OUT - 1u];
    *score = pf_mlp_scale_output(fwd);
    return 1;
}

static int scratch_canaries_ok(const uint8_t *ddr) {
    size_t i;
    for (i = 512u; i < PF_STAGEB_INPUT_BYTES; ++i)
        if (ddr[PF_STAGEB_INPUT_OFFSET + i] != SCRATCH_CANARY)
            return 0;
    for (i = PF_MLP_FC0_OUT * 4u; i < PF_STAGEB_OUTPUT_BYTES; ++i)
        if (ddr[PF_STAGEB_OUTPUT_OFFSET + i] != SCRATCH_CANARY)
            return 0;
    return 1;
}

int main(int argc, char **argv) {
    const char *pfsb_path = argc > 1 ? argv[1] :
        "/opt/pikafish/stageb-mac.bin";
    const char *golden_path = argc > 2 ? argv[2] :
        "/opt/pikafish/stageb-golden.bin";
    int verify_only = argc > 3 && strcmp(argv[3], "--verify-only") == 0;
    mapped_file_t pfsb;
    mapped_file_t golden;
    board_context_t ctx = {0};
    uint8_t input[PF_MLP_L1];
    int32_t actual[PF_MLP_FC0_OUT];
    int32_t bias[PF_MLP_FC0_OUT];
    pf_mlp_pack_header_t model_header;
    pf_mlp_model_t model;
    int mem_fd = -1;
    void *register_map = MAP_FAILED;
    void *ddr_map = MAP_FAILED;
    uint32_t stack;
    int exit_code = 1;

    memset(&pfsb, 0, sizeof(pfsb));
    memset(&golden, 0, sizeof(golden));
    pfsb.fd = -1;
    golden.fd = -1;
    if (!map_file_readonly(pfsb_path, &pfsb) ||
        !map_file_readonly(golden_path, &golden)) {
        fail_reason("input-open");
        goto cleanup;
    }
    if (!validate_pfsb(pfsb.data, pfsb.bytes)) {
        fail_reason("pfsb-contract");
        goto cleanup;
    }
    if (!validate_golden(golden.data, golden.bytes, pfsb.data)) {
        fail_reason("golden-contract");
        goto cleanup;
    }
    printf("PIKAFISH_STAGEB_BOARD_PACKS_VERIFIED pfsb_crc32=%08x "
           "mlps_crc32=%08x golden_crc32=%08x\n",
           read_le32(pfsb.data + 44), read_le32(golden.data + 36),
           read_le32(golden.data + 40));
    if (verify_only) {
        exit_code = 0;
        goto cleanup;
    }

    mem_fd = open("/dev/mem", O_RDWR | O_SYNC | O_CLOEXEC);
    if (mem_fd < 0) {
        perror("open /dev/mem");
        fail_reason("open-devmem");
        goto cleanup;
    }
    register_map = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED,
                        mem_fd, (off_t)MAC_REGISTER_PHYSICAL);
    ddr_map = mmap(NULL, PF_STAGEB_DDR_BYTES, PROT_READ | PROT_WRITE,
                   MAP_SHARED, mem_fd, (off_t)PF_STAGEB_DDR_CPU_ALIAS);
    if (register_map == MAP_FAILED || ddr_map == MAP_FAILED) {
        perror("mmap /dev/mem");
        fail_reason("mmap-devmem");
        goto cleanup;
    }
    memset(&ctx, 0, sizeof(ctx));
    ctx.registers = (volatile uint32_t *)register_map;
    ctx.physical_ddr = (volatile uint32_t *)ddr_map;
    ctx.ddr = (uint8_t *)calloc(PF_STAGEB_DDR_BYTES, 1u);
    if (ctx.ddr == NULL) {
        fail_reason("shadow-alloc");
        goto cleanup;
    }
    if (mac_kernel_read((uintptr_t)ctx.registers, MAC_KERNEL_REG_ID) !=
            MAC_KERNEL_ID ||
        mac_kernel_read((uintptr_t)ctx.registers, MAC_KERNEL_REG_VERSION) !=
            MAC_KERNEL_VERSION) {
        fail_reason("mac-id-version");
        goto cleanup;
    }
    memcpy(ctx.ddr, pfsb.data, pfsb.bytes);
    if (!transfer_words(ctx.physical_ddr, ctx.ddr, 0u, pfsb.bytes, 1) ||
        !transfer_words(ctx.physical_ddr, ctx.ddr, 0u, pfsb.bytes, 0)) {
        fail_reason("pfsb-ddr-transfer");
        goto cleanup;
    }
    if (memcmp(ctx.ddr, pfsb.data, pfsb.bytes) != 0) {
        fail_reason("pfsb-ddr-readback");
        goto cleanup;
    }
    memset(ctx.ddr + PF_STAGEB_INPUT_OFFSET, SCRATCH_CANARY,
           PF_STAGEB_INPUT_BYTES);
    memset(ctx.ddr + PF_STAGEB_OUTPUT_OFFSET, SCRATCH_CANARY,
           PF_STAGEB_OUTPUT_BYTES);
    if (!transfer_words(ctx.physical_ddr, ctx.ddr, PF_STAGEB_INPUT_OFFSET,
                        PF_STAGEB_INPUT_BYTES, 1) ||
        !transfer_words(ctx.physical_ddr, ctx.ddr, PF_STAGEB_OUTPUT_OFFSET,
                        PF_STAGEB_OUTPUT_BYTES, 1)) {
        fail_reason("scratch-ddr-transfer");
        goto cleanup;
    }
    printf("PIKAFISH_STAGEB_BOARD_DDR_READY bytes=%u crc32=%08x\n",
           (unsigned int)PF_STAGEB_PACK_USED_BYTES,
           read_le32(pfsb.data + 44));

    memset(&model_header, 0, sizeof(model_header));
    model_header.magic = PF_MLP_PACK_MAGIC;
    model_header.version = PF_MLP_PACK_VERSION;
    model_header.l1 = PF_MLP_L1;
    model_header.l2 = PF_MLP_L2;
    model_header.l3 = PF_MLP_L3;
    model_header.weight_scale_bits = PF_MLP_WEIGHT_SCALE_BITS;
    model_header.flags = 1u;

    for (stack = 0; stack < PF_STAGEB_STACK_COUNT; ++stack) {
        const uint8_t *slot = pfsb.data + pf_stageb_stack_offset(stack);
        uint32_t input_case;
        uint32_t jobs_before = ctx.jobs;
        uint32_t lane;
        for (lane = 0; lane < PF_MLP_FC0_OUT; ++lane)
            bias[lane] = read_le_i32(slot + PF_STAGEB_FC0_BIAS_OFFSET +
                                     lane * 4u);
        if (!pf_mlp_model_bind(
                &model, &model_header,
                (const int8_t *)(slot + PF_STAGEB_FC0_PACKED_OFFSET), bias,
                (const int8_t *)(slot + PF_STAGEB_FC1_WEIGHT_OFFSET),
                (const int32_t *)(slot + PF_STAGEB_FC1_BIAS_OFFSET),
                (const int8_t *)(slot + PF_STAGEB_FC2_WEIGHT_OFFSET),
                (const int32_t *)(slot + PF_STAGEB_FC2_BIAS_OFFSET))) {
            fail_reason("model-bind");
            goto cleanup;
        }
        ctx.stack = stack;
        for (input_case = 0; input_case < PF_STAGEB_GOLDEN_CASE_COUNT;
             ++input_case) {
            const uint8_t *record = golden.data +
                pf_stageb_golden_record_offset(stack, input_case);
            int32_t actual_score;
            fill_input(input, input_case, stack);
            if (!pf_mlp_tiled_fc0(&model, input, hardware_tile, &ctx, actual)) {
                fail_reason("hardware-fc0");
                goto cleanup;
            }
            for (lane = 0; lane < PF_MLP_FC0_OUT; ++lane) {
                int32_t expected = read_le_i32(record + lane * 4u);
                if (actual[lane] != expected) {
                    fprintf(stderr,
                            "PIKAFISH_STAGEB_BOARD_MISMATCH stack=%u case=%u "
                            "lane=%u expected=%d actual=%d\n",
                            stack, input_case, lane, expected, actual[lane]);
                    fail_reason("fc0-mismatch");
                    goto cleanup;
                }
            }
            score_from_fc0(slot, actual, &actual_score);
            if (actual_score != read_le_i32(
                    record + PF_STAGEB_GOLDEN_LANE_COUNT * 4u)) {
                fprintf(stderr,
                        "PIKAFISH_STAGEB_BOARD_SCORE_MISMATCH stack=%u case=%u "
                        "expected=%d actual=%d\n",
                        stack, input_case,
                        read_le_i32(record + PF_STAGEB_GOLDEN_LANE_COUNT * 4u),
                        actual_score);
                fail_reason("score-mismatch");
                goto cleanup;
            }
            if (!scratch_canaries_ok(ctx.ddr)) {
                fail_reason("scratch-canary");
                goto cleanup;
            }
        }
        printf("PIKAFISH_STAGEB_BOARD_BUCKET_PASS bucket=%u cases=%u jobs=%u\n",
               stack, PF_STAGEB_GOLDEN_CASE_COUNT, ctx.jobs - jobs_before);
    }
    if (!transfer_words(ctx.physical_ddr, ctx.ddr, 0u,
                        PF_STAGEB_PACK_USED_BYTES, 0)) {
        fail_reason("pfsb-ddr-final-readback");
        goto cleanup;
    }
    if (crc32_bytes(ctx.ddr + PF_STAGEB_HEADER_BYTES,
                    PF_STAGEB_PACK_USED_BYTES - PF_STAGEB_HEADER_BYTES) !=
            PF_STAGEB_GOLDEN_PFSB_CRC32) {
        fail_reason("pfsb-ddr-mutated");
        goto cleanup;
    }
    if (ctx.jobs != PF_STAGEB_GOLDEN_STACK_COUNT *
                    PF_STAGEB_GOLDEN_CASE_COUNT * PF_STAGEB_FC0_TILE_COUNT ||
        ctx.failed_jobs != 0u) {
        fail_reason("job-count");
        goto cleanup;
    }
    printf("PIKAFISH_STAGEB_BOARD_GOLDEN_PASS buckets=%u cases=%u jobs=%u "
           "fc0_lanes=%u pfsb_crc32=%08x cycles=%llu\n",
           PF_STAGEB_GOLDEN_STACK_COUNT,
           PF_STAGEB_GOLDEN_STACK_COUNT * PF_STAGEB_GOLDEN_CASE_COUNT,
           ctx.jobs,
           PF_STAGEB_GOLDEN_STACK_COUNT * PF_STAGEB_GOLDEN_CASE_COUNT *
               PF_STAGEB_GOLDEN_LANE_COUNT,
           PF_STAGEB_GOLDEN_PFSB_CRC32,
           (unsigned long long)ctx.cycles);
    exit_code = 0;

cleanup:
    free(ctx.ddr);
    if (ddr_map != MAP_FAILED)
        munmap(ddr_map, PF_STAGEB_DDR_BYTES);
    if (register_map != MAP_FAILED)
        munmap(register_map, 4096);
    if (mem_fd >= 0)
        close(mem_fd);
    unmap_file(&golden);
    unmap_file(&pfsb);
    return exit_code;
}
