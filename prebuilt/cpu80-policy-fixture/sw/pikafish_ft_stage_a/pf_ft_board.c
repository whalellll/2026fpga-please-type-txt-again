#include "pf_ft_stage_a.h"
#include "pf_ft_stage_a_cases.h"
#include "xiangqi_nnue_mac.h"

#include <stdint.h>
#include <stddef.h>

#define UART (*(volatile uint32_t *)0x1fe001e0u)
#define MAC_REG_BASE 0x1fe10000u
#define MAC_DDR_BASE 0x1b000000u
#define MAC_CPU_ALIAS 0x9b000000u

#define INPUT_BUS  (MAC_DDR_BASE + 0x0000u)
#define WEIGHT_BUS (MAC_DDR_BASE + 0x1000u)
#define BIAS_BUS   (MAC_DDR_BASE + 0x4000u)
#define OUTPUT_BUS (MAC_DDR_BASE + 0x5000u)

#define INPUT_CPU  ((uint8_t *)(MAC_CPU_ALIAS + 0x0000u))
#define WEIGHT_CPU ((uint8_t *)(MAC_CPU_ALIAS + 0x1000u))
#define OUTPUT_CPU ((uint8_t *)(MAC_CPU_ALIAS + 0x5000u))

static uint32_t g_failures;
static uint32_t g_passes;

/* Word-first copies: byte-granular stores through the uncached MAC DDR
 * alias stall this platform; 32-bit stores are safe (board-verified). */
void *memcpy(void *dst, const void *src, size_t n) {
    uint8_t *d = (uint8_t *)dst;
    const uint8_t *s = (const uint8_t *)src;
    while (n != 0u && (((uintptr_t)d & 3u) != 0u)) {
        *d++ = *s++;
        --n;
    }
    {
        uint32_t *dw = (uint32_t *)(void *)d;
        const uint32_t *sw = (const uint32_t *)(const void *)s;
        while (n >= 4u) {
            *dw++ = *sw++;
            n -= 4u;
        }
        d = (uint8_t *)dw;
        s = (const uint8_t *)sw;
    }
    while (n--)
        *d++ = *s++;
    return dst;
}

void *memset(void *dst, int c, size_t n) {
    uint8_t *d = (uint8_t *)dst;
    uint8_t v = (uint8_t)c;
    uint32_t word = (uint32_t)v * 0x01010101u;
    while (n != 0u && (((uintptr_t)d & 3u) != 0u)) {
        *d++ = v;
        --n;
    }
    {
        uint32_t *dw = (uint32_t *)(void *)d;
        while (n >= 4u) {
            *dw++ = word;
            n -= 4u;
        }
        d = (uint8_t *)dw;
    }
    while (n--)
        *d++ = v;
    return dst;
}

static void uart_putc(char c) {
    if (c == '\n')
        UART = '\r';
    UART = (uint8_t)c;
}

static void uart_puts(const char *s) {
    while (*s)
        uart_putc(*s++);
}

static void uart_put_uint(uint32_t value) {
    char digits[10];
    uint32_t count = 0;
    if (value == 0u) {
        uart_putc('0');
        return;
    }
    while (value != 0u) {
        digits[count++] = (char)('0' + (value % 10u));
        value /= 10u;
    }
    while (count != 0u)
        uart_putc(digits[--count]);
}

static void memory_fence(void) {
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
}

static void cache_fence(void *ctx, void *buffer, size_t bytes) {
    (void)ctx;
    (void)buffer;
    (void)bytes;
    memory_fence();
}

static void expect_cb(int ok, const char *name, void *ctx) {
    (void)ctx;
    if (ok) {
        uart_puts("PASS ");
        uart_puts(name);
        uart_putc('\n');
        g_passes++;
    } else {
        uart_puts("FAIL ");
        uart_puts(name);
        uart_putc('\n');
        g_failures++;
    }
}

static int mac_tile_backend(
    void *ctx,
    const pf_ft_model_t *model,
    const pf_ft_tile_job_t *job,
    int32_t *out_tile) {
    xiangqi_nnue_mac_t *mac = (xiangqi_nnue_mac_t *)ctx;
    size_t offsets[PF_FT_MAX_ACTIVE];
    uint16_t i;
    uint32_t base;

    if (mac == NULL || model == NULL || job == NULL || out_tile == NULL)
        return 0;
    if (job->feature_count == 0u) {
        for (i = 0; i < job->cout; ++i)
            out_tile[i] = 0;
        return 1;
    }
    base = (uint32_t)job->tile_id * PF_FT_MAC_MAX_CHANNELS;
    for (i = 0; i < job->feature_count; ++i)
        offsets[i] = (size_t)job->feature_index[i] * PF_FT_L1 + base;
    return xiangqi_nnue_mac_accum(
        mac,
        model->weights,
        offsets,
        (int)job->feature_count,
        (int)PF_FT_MAC_MAX_CHANNELS,
        out_tile);
}

static int vectors_equal(const int32_t *a, const int32_t *b, uint32_t n) {
    uint32_t i;
    for (i = 0; i < n; ++i) {
        if (a[i] != b[i])
            return 0;
    }
    return 1;
}

static void fill_ramp(int8_t *weights, uint32_t rows) {
    uint32_t row;
    uint32_t lane;
    for (row = 0; row < rows; ++row) {
        for (lane = 0; lane < PF_FT_L1; ++lane) {
            weights[row * PF_FT_L1 + lane] =
                (int8_t)((int)(row * 3u + lane * 5u) - 128);
        }
    }
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

static void run_mac_cases(
    pf_ft_model_t *model,
    xiangqi_nnue_mac_t *mac,
    int32_t *cpu,
    int32_t *hw) {
    uint16_t one[] = {0};
    uint16_t two[] = {1, 6};
    uint16_t four[] = {0, 2, 5, 7};
    uint16_t eight[] = {0, 1, 2, 3, 4, 5, 6, 7};
    const uint16_t *feat_ptr[4];
    uint16_t feat_n[4];
    uint32_t s;

    feat_ptr[0] = one;   feat_n[0] = 1;
    feat_ptr[1] = two;   feat_n[1] = 2;
    feat_ptr[2] = four;  feat_n[2] = 4;
    feat_ptr[3] = eight; feat_n[3] = 8;

    for (s = 0; s < 4u; ++s) {
        int cpu_ok;
        int hw_ok;
        cpu_ok = pf_ft_ref_accumulate(model, feat_ptr[s], feat_n[s], cpu);
        hw_ok = pf_ft_tiled_accumulate(
            model, feat_ptr[s], feat_n[s], mac_tile_backend, mac, hw);
        expect_cb(cpu_ok && hw_ok, s == 0 ? "mac.run_1feat" :
                                   s == 1 ? "mac.run_2feat" :
                                   s == 2 ? "mac.run_4feat" : "mac.run_8feat",
                  NULL);
        expect_cb(cpu_ok && hw_ok && vectors_equal(cpu, hw, PF_FT_L1),
                  s == 0 ? "mac.match_1feat" :
                  s == 1 ? "mac.match_2feat" :
                  s == 2 ? "mac.match_4feat" : "mac.match_8feat",
                  NULL);
        uart_puts("MAC_JOBS=");
        uart_put_uint(mac->completed_jobs);
        uart_puts(" CYCLES=");
        uart_put_uint(mac->last_cycles);
        uart_putc('\n');
        if (!(cpu_ok && hw_ok && vectors_equal(cpu, hw, PF_FT_L1))) {
            uart_puts("MAC_RESULT_FAIL set=");
            uart_put_uint(s);
            uart_puts(" failed_jobs=");
            uart_put_uint(mac->failed_jobs);
            uart_putc('\n');
        }
    }
}

int main(void) {
    static int8_t weights[PF_FT_CASE_ROWS * PF_FT_L1];
    static int32_t acc_a[PF_FT_L1];
    static int32_t acc_b[PF_FT_L1];
    static int32_t tile[PF_FT_MAC_MAX_CHANNELS];
    pf_ft_case_env_t env;
    pf_ft_pack_header_t header;
    pf_ft_model_t model;
    xiangqi_nnue_mac_t mac;

    g_passes = 0;
    g_failures = 0;
    uart_puts("PF_FT_STAGE_A_BOARD begin\n");

    memset(&env, 0, sizeof(env));
    env.weights = weights;
    env.acc_a = acc_a;
    env.acc_b = acc_b;
    env.tile = tile;
    env.expect = expect_cb;
    pf_ft_run_stage_a_cases(&env);

    if (mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_ID) != MAC_KERNEL_ID ||
        mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_VERSION) !=
            MAC_KERNEL_VERSION) {
        uart_puts("MAC_MMIO_FAIL\n");
        return 1;
    }
    uart_puts("MAC_MMIO_OK\n");

    memset(&mac, 0, sizeof(mac));
    mac.reg_base = MAC_REG_BASE;
    mac.input_addr = INPUT_BUS;
    mac.weight_addr = WEIGHT_BUS;
    mac.bias_addr = BIAS_BUS;
    mac.output_addr = OUTPUT_BUS;
    mac.input_buffer = INPUT_CPU;
    mac.weight_buffer = WEIGHT_CPU;
    mac.output_buffer = OUTPUT_CPU;
    mac.input_capacity = 0x1000u;
    mac.weight_capacity = 0x3000u;
    mac.bias_capacity = 0;
    mac.output_capacity = 0x1000u;
    mac.timeout_polls = 1000000u;
    mac.cache_clean = cache_fence;
    mac.cache_invalidate = cache_fence;

    fill_ramp(weights, PF_FT_CASE_ROWS);
    fill_header(&header, PF_FT_CASE_ROWS);
    if (!pf_ft_model_bind(&model, &header, weights)) {
        uart_puts("MAC_EXEC_FAIL bind\n");
        return 2;
    }
    run_mac_cases(&model, &mac, acc_a, acc_b);

    uart_puts("summary pass=");
    uart_put_uint(g_passes);
    uart_puts(" fail=");
    uart_put_uint(g_failures);
    uart_putc('\n');
    if (g_failures == 0) {
        uart_puts("PF_FT_STAGE_A_BOARD_PASS\n");
        return 0;
    }
    uart_puts("PF_FT_STAGE_A_BOARD_FAIL\n");
    return 3;
}
