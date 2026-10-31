#include "pf_mlp_stage_b.h"
#include "pf_mlp_stage_b_cases.h"
#include "pf_mlp_mac_fc0.h"
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

static void uart_put_int(int32_t value) {
    if (value < 0) {
        uart_putc('-');
        uart_put_uint((uint32_t)(-(int64_t)value));
    } else {
        uart_put_uint((uint32_t)value);
    }
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

static void fill_x(uint8_t *x, uint32_t pattern) {
    uint32_t i;
    for (i = 0; i < PF_MLP_L1; ++i) {
        if (pattern == 0)
            x[i] = 0;
        else if (pattern == 1)
            x[i] = 1;
        else if (pattern == 2)
            x[i] = (uint8_t)(i & 127u);
        else
            x[i] = (uint8_t)((i * 3u + 11u) % 128u);
    }
}

static void run_mac_fc0_cases(
    pf_mlp_model_t *model,
    xiangqi_nnue_mac_t *mac,
    uint8_t *x,
    int32_t *cpu,
    int32_t *hw) {
    uint32_t pattern;
    for (pattern = 0; pattern < 4u; ++pattern) {
        uint32_t o;
        int eq = 1;
        fill_x(x, pattern);
        expect_cb(pf_mlp_ref_fc0(model, x, cpu),
                  pattern == 0 ? "mac.fc0_ref_0" :
                  pattern == 1 ? "mac.fc0_ref_1" :
                  pattern == 2 ? "mac.fc0_ref_2" : "mac.fc0_ref_3",
                  NULL);
        expect_cb(pf_mlp_tiled_fc0(model, x, pf_mlp_mac_fc0_tile, mac, hw),
                  pattern == 0 ? "mac.fc0_hw_0" :
                  pattern == 1 ? "mac.fc0_hw_1" :
                  pattern == 2 ? "mac.fc0_hw_2" : "mac.fc0_hw_3",
                  NULL);
        for (o = 0; o < PF_MLP_FC0_OUT; ++o) {
            if (cpu[o] != hw[o]) {
                eq = 0;
                break;
            }
        }
        expect_cb(eq,
                  pattern == 0 ? "mac.fc0_match_0" :
                  pattern == 1 ? "mac.fc0_match_1" :
                  pattern == 2 ? "mac.fc0_match_2" : "mac.fc0_match_3",
                  NULL);
        uart_puts("MAC_JOBS=");
        uart_put_uint(mac->completed_jobs);
        uart_puts(" CYCLES=");
        uart_put_uint(mac->last_cycles);
        uart_putc('\n');
        if (!eq) {
            uart_puts("MAC_RESULT_FAIL lane=");
            uart_put_uint(o);
            uart_puts(" cpu=");
            uart_put_int(cpu[o]);
            uart_puts(" hw=");
            uart_put_int(hw[o]);
            uart_putc('\n');
        }
    }
}

static void run_mac_full_score(
    pf_mlp_model_t *model,
    xiangqi_nnue_mac_t *mac,
    uint8_t *x) {
    int32_t score_cpu;
    int32_t score_hw;
    fill_x(x, 3);
    expect_cb(pf_mlp_propagate(model, x, NULL, NULL, &score_cpu),
              "mac.score_cpu", NULL);
    expect_cb(pf_mlp_propagate(model, x, pf_mlp_mac_fc0_tile, mac, &score_hw),
              "mac.score_hw", NULL);
    expect_cb(score_cpu == score_hw, "mac.score_match", NULL);
    uart_puts("SCORE_CPU=");
    uart_put_int(score_cpu);
    uart_puts(" SCORE_HW=");
    uart_put_int(score_hw);
    uart_putc('\n');
}

int main(void) {
    static int8_t fc0_w[PF_MLP_FC0_OUT * PF_MLP_L1];
    static int32_t fc0_b[PF_MLP_FC0_OUT];
    static int8_t fc1_w[PF_MLP_FC1_OUT * PF_MLP_FC1_IN];
    static int32_t fc1_b[PF_MLP_FC1_OUT];
    static int8_t fc2_w[PF_MLP_FC2_IN];
    static int32_t fc2_b[1];
    static uint8_t x[PF_MLP_L1];
    static int32_t tmp32[PF_MLP_FC0_OUT];
    static int32_t tmp32b[PF_MLP_FC0_OUT];
    pf_mlp_case_env_t env;
    pf_mlp_pack_header_t header;
    pf_mlp_model_t model;
    xiangqi_nnue_mac_t mac;

    g_passes = 0;
    g_failures = 0;
    uart_puts("PF_MLP_STAGE_B_BOARD begin\n");

    memset(&env, 0, sizeof(env));
    env.fc0_w = fc0_w;
    env.fc0_b = fc0_b;
    env.fc1_w = fc1_w;
    env.fc1_b = fc1_b;
    env.fc2_w = fc2_w;
    env.fc2_b = fc2_b;
    env.x = x;
    env.tmp32 = tmp32;
    env.tmp32b = tmp32b;
    env.expect = expect_cb;
    pf_mlp_run_stage_b_cases(&env);

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

    memset(&header, 0, sizeof(header));
    header.magic = PF_MLP_PACK_MAGIC;
    header.version = PF_MLP_PACK_VERSION;
    header.l1 = (uint16_t)PF_MLP_L1;
    header.l2 = (uint16_t)PF_MLP_L2;
    header.l3 = (uint16_t)PF_MLP_L3;
    header.weight_scale_bits = (uint16_t)PF_MLP_WEIGHT_SCALE_BITS;
    header.flags = 1u;
    if (!pf_mlp_model_bind(&model, &header, fc0_w, fc0_b, fc1_w, fc1_b,
                           fc2_w, fc2_b)) {
        uart_puts("MAC_EXEC_FAIL bind\n");
        return 2;
    }

    run_mac_fc0_cases(&model, &mac, x, tmp32, tmp32b);
    run_mac_full_score(&model, &mac, x);

    uart_puts("summary pass=");
    uart_put_uint(g_passes);
    uart_puts(" fail=");
    uart_put_uint(g_failures);
    uart_putc('\n');
    if (g_failures == 0) {
        uart_puts("PF_MLP_STAGE_B_BOARD_PASS\n");
        return 0;
    }
    uart_puts("PF_MLP_STAGE_B_BOARD_FAIL\n");
    return 3;
}
