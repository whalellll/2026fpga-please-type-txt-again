#include <stdint.h>
#include "mac_accel_kernel.h"
#include "../../bootloader/release_version.h"

#define UART (*(volatile uint32_t *)0x1fe001e0u)
#define MAC_REG_BASE 0x1fe10000u
#define MAC_DDR_BASE 0x1b000000u
#define MAC_CPU_ALIAS 0x9b000000u

#define INPUT_BUS  (MAC_DDR_BASE + 0x0000u)
#define WEIGHT_BUS (MAC_DDR_BASE + 0x1000u)
#define BIAS_BUS   (MAC_DDR_BASE + 0x2000u)
#define OUTPUT_BUS (MAC_DDR_BASE + 0x3000u)

#define INPUT_CPU  ((volatile uint32_t *)(MAC_CPU_ALIAS + 0x0000u))
#define WEIGHT_CPU ((volatile uint32_t *)(MAC_CPU_ALIAS + 0x1000u))
#define OUTPUT_CPU ((volatile uint32_t *)(MAC_CPU_ALIAS + 0x3000u))

static void uart_putc(char c)
{
    if (c == '\n')
        UART = '\r';
    UART = (uint8_t)c;
}

static void uart_puts(const char *s)
{
    while (*s != '\0')
        uart_putc(*s++);
}

static void uart_put_uint(uint32_t value)
{
    char digits[10];
    uint32_t count = 0;
    if (value == 0u) {
        uart_putc('0');
        return;
    }
    while (value != 0u) {
        digits[count++] = (char)('0' + value % 10u);
        value /= 10u;
    }
    while (count != 0u)
        uart_putc(digits[--count]);
}

static void memory_fence(void)
{
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
}

int main(void)
{
    mac_kernel_job_t job;
    uint32_t i;
    int result;

    uart_puts("SOC_linux " SOC_RELEASE_VERSION " MAC DDR self-test\n");
    if (mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_ID) != MAC_KERNEL_ID ||
        mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_VERSION) !=
            MAC_KERNEL_VERSION) {
        uart_puts("MAC_MMIO_FAIL\n");
        return 1;
    }

    INPUT_CPU[0] = 0x00010001u;
    INPUT_CPU[1] = 0x00010001u;
    for (i = 0; i < 32u; ++i)
        WEIGHT_CPU[i] = 0x00010001u;
    for (i = 0; i < 16u; ++i)
        OUTPUT_CPU[i] = 0xdeadbeefu;
    memory_fence();

    job.pixels = 1;
    job.cin = 4;
    job.cout = 16;
    job.out_shift = 0;
    job.compute_mode = MAC_KERNEL_MODE_S16_S16;
    job.activation = MAC_KERNEL_ACT_NONE;
    job.output_format = MAC_KERNEL_OUT_I32;
    job.irq_enable = 0;
    job.zero_bias = 1;
    job.input_addr = INPUT_BUS;
    job.weight_addr = WEIGHT_BUS;
    job.bias_addr = BIAS_BUS;
    job.output_addr = OUTPUT_BUS;

    result = mac_kernel_submit(MAC_REG_BASE, &job);
    if (result == MAC_KERNEL_OK)
        result = mac_kernel_wait(MAC_REG_BASE, 1000000u);
    memory_fence();
    if (result != MAC_KERNEL_OK) {
        uart_puts("MAC_EXEC_FAIL error=");
        uart_put_uint(mac_kernel_error_code(MAC_REG_BASE));
        uart_putc('\n');
        return 2;
    }

    for (i = 0; i < 16u; ++i) {
        if (OUTPUT_CPU[i] != 4u) {
            uart_puts("MAC_RESULT_FAIL lane=");
            uart_put_uint(i);
            uart_puts(" value=");
            uart_put_uint(OUTPUT_CPU[i]);
            uart_putc('\n');
            return 3;
        }
    }

    uart_puts("MAC_CYCLES=");
    uart_put_uint(mac_kernel_cycles(MAC_REG_BASE));
    uart_puts("\nMAC_DDR_SOC_TEST_PASS\n");
    return 0;
}
