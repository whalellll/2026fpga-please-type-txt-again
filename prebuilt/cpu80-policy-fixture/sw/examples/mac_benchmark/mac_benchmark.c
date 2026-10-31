#include <stddef.h>
#include <stdint.h>

#include "mac_accel_kernel.h"

#define REG32(address) (*(volatile uint32_t *)(uintptr_t)(address))

#define UART_DATA_ADDR 0x1fe001e0u
#define SYS_BASE_ADDR  0x1fe00300u
#define CLINT_MTIME    0x0200bff8u
#define MAC_REG_BASE   0x1fe10000u

#define MAC_DDR_BUS    0x1b000000u
#define MAC_DDR_CPU    0x9b000000u
#define INPUT_OFFSET   0x00000u
#define WEIGHT_OFFSET  0x10000u
#define BIAS_OFFSET    0x30000u
#define OUTPUT_OFFSET  0x40000u

/* The top half of the 1 MiB accelerator window is kept separate from all
 * descriptor buffers and is used to stress the CPU DDR path. */
#define MEM_SRC_OFFSET 0x80000u
#define MEM_DST_OFFSET 0xc0000u
#define MEM_TEST_BYTES 0x40000u
#define MEM_TEST_WORDS (MEM_TEST_BYTES / sizeof(uint32_t))

#define INPUT_BUS  (MAC_DDR_BUS + INPUT_OFFSET)
#define WEIGHT_BUS (MAC_DDR_BUS + WEIGHT_OFFSET)
#define BIAS_BUS   (MAC_DDR_BUS + BIAS_OFFSET)
#define OUTPUT_BUS (MAC_DDR_BUS + OUTPUT_OFFSET)

#define INPUT_CPU  ((volatile uint32_t *)(MAC_DDR_CPU + INPUT_OFFSET))
#define WEIGHT_CPU ((volatile uint32_t *)(MAC_DDR_CPU + WEIGHT_OFFSET))
#define BIAS_CPU   ((volatile uint32_t *)(MAC_DDR_CPU + BIAS_OFFSET))
#define OUTPUT_CPU ((volatile uint32_t *)(MAC_DDR_CPU + OUTPUT_OFFSET))
#define MEM_SRC_CPU ((volatile uint32_t *)(MAC_DDR_CPU + MEM_SRC_OFFSET))
#define MEM_DST_CPU ((volatile uint32_t *)(MAC_DDR_CPU + MEM_DST_OFFSET))

#define EXPECTED_SYS_ID  0x53563300u
#define SYS_CLOCK_HZ     49500000u
#define RUN_TIMEOUT      (SYS_CLOCK_HZ * 5u)
#define MAX_INPUT_BYTES  (16u * 64u * 8u)
#define MAX_WEIGHT_BYTES (16u * 64u * 128u)
#define MAX_BIAS_BYTES   (16u * 192u)
#define MAX_OUTPUT_WORDS (16u * 256u)

typedef struct {
    const char *name;
    uint16_t pixels;
    uint16_t cin;
    uint16_t cout;
    uint8_t compute_mode;
    uint8_t zero_bias;
    uint16_t repeats;
} benchmark_case_t;

typedef struct {
    uint32_t input_cycles;
    uint32_t weight_cycles;
    uint32_t bias_cycles;
    uint32_t compute_cycles;
    uint32_t output_cycles;
    uint32_t wall_cycles;
    uint32_t hardware_cycles;
} phase_trace_t;

typedef struct {
    uint32_t average_cycles;
    uint32_t minimum_cycles;
    uint32_t maximum_cycles;
} case_result_t;

static void uart_putc(char value)
{
    if (value == '\n')
        REG32(UART_DATA_ADDR) = '\r';
    REG32(UART_DATA_ADDR) = (uint8_t)value;
}

static void uart_puts(const char *text)
{
    while (*text != '\0')
        uart_putc(*text++);
}

static void uart_put_u64(uint64_t value)
{
    char digits[20];
    uint32_t count = 0u;

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

static void uart_put_fixed3(uint64_t scaled_value)
{
    uart_put_u64(scaled_value / 1000u);
    uart_putc('.');
    uart_putc((char)('0' + (scaled_value / 100u) % 10u));
    uart_putc((char)('0' + (scaled_value / 10u) % 10u));
    uart_putc((char)('0' + scaled_value % 10u));
}

static uint32_t timer_now(void)
{
    return REG32(CLINT_MTIME);
}

static void memory_fence(void)
{
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
}

static uint64_t ratio_x1000(uint64_t numerator, uint64_t denominator)
{
    if (denominator == 0u)
        return 0u;
    return numerator * 1000u / denominator;
}

static uint64_t mib_per_second_x1000(uint64_t bytes, uint64_t cycles)
{
    if (cycles == 0u)
        return 0u;
    return bytes * SYS_CLOCK_HZ * 1000u /
           (cycles * 1024u * 1024u);
}

static uint32_t pattern(uint32_t index)
{
    return (index * 0x9e3779b9u) ^ 0xa5a55a5au;
}

static int run_cpu_memory_benchmark(void)
{
    uint32_t begin;
    uint32_t write_cycles;
    uint32_t read_cycles;
    uint32_t copy_cycles;
    uint32_t i;
    uint32_t checksum = 0u;
    uint32_t expected = 0u;

    memory_fence();
    begin = timer_now();
    for (i = 0u; i < MEM_TEST_WORDS; ++i)
        MEM_SRC_CPU[i] = pattern(i);
    memory_fence();
    write_cycles = timer_now() - begin;

    begin = timer_now();
    for (i = 0u; i < MEM_TEST_WORDS; ++i)
        checksum ^= MEM_SRC_CPU[i];
    memory_fence();
    read_cycles = timer_now() - begin;

    begin = timer_now();
    for (i = 0u; i < MEM_TEST_WORDS; ++i)
        MEM_DST_CPU[i] = MEM_SRC_CPU[i];
    memory_fence();
    copy_cycles = timer_now() - begin;

    for (i = 0u; i < MEM_TEST_WORDS; ++i) {
        expected ^= pattern(i);
        if (MEM_DST_CPU[i] != pattern(i)) {
            uart_puts("MEM_VERIFY_FAIL index=");
            uart_put_u64(i);
            uart_putc('\n');
            return -1;
        }
    }
    if (checksum != expected) {
        uart_puts("MEM_CHECKSUM_FAIL\n");
        return -1;
    }

    uart_puts("CPU_MEM_WRITE bytes=");
    uart_put_u64(MEM_TEST_BYTES);
    uart_puts(" cycles=");
    uart_put_u64(write_cycles);
    uart_puts(" MiBps=");
    uart_put_fixed3(mib_per_second_x1000(MEM_TEST_BYTES, write_cycles));
    uart_putc('\n');

    uart_puts("CPU_MEM_READ bytes=");
    uart_put_u64(MEM_TEST_BYTES);
    uart_puts(" cycles=");
    uart_put_u64(read_cycles);
    uart_puts(" MiBps=");
    uart_put_fixed3(mib_per_second_x1000(MEM_TEST_BYTES, read_cycles));
    uart_puts(" checksum=");
    uart_put_u64(checksum);
    uart_putc('\n');

    uart_puts("CPU_MEM_COPY traffic_bytes=");
    uart_put_u64(2u * MEM_TEST_BYTES);
    uart_puts(" cycles=");
    uart_put_u64(copy_cycles);
    uart_puts(" MiBps=");
    uart_put_fixed3(mib_per_second_x1000(2u * MEM_TEST_BYTES,
                                                    copy_cycles));
    uart_putc('\n');
    return 0;
}

static uint32_t pack_dims(const mac_kernel_job_t *job)
{
    return ((uint32_t)job->cin << 16) | job->pixels;
}

static uint32_t pack_format(const mac_kernel_job_t *job)
{
    return (uint32_t)job->cout |
           ((uint32_t)job->out_shift << 16) |
           ((uint32_t)(job->output_format & 3u) << 24) |
           ((uint32_t)(job->activation & 3u) << 26) |
           ((uint32_t)(job->compute_mode & 3u) << 28) |
           (job->zero_bias != 0u ? MAC_KERNEL_FORMAT_ZERO_BIAS : 0u);
}

static int program_job(const mac_kernel_job_t *job)
{
    uint32_t status;

    if (mac_kernel_validate_job(job) != MAC_KERNEL_OK)
        return MAC_KERNEL_ERR_ARGUMENT;
    status = mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_STATUS);
    if ((status & MAC_KERNEL_STATUS_BUSY) != 0u)
        return MAC_KERNEL_ERR_BUSY;

    mac_kernel_clear(MAC_REG_BASE, 0);
    mac_kernel_write(MAC_REG_BASE, MAC_KERNEL_REG_CFG_DIMS,
                     pack_dims(job));
    mac_kernel_write(MAC_REG_BASE, MAC_KERNEL_REG_CFG_FORMAT,
                     pack_format(job));
    mac_kernel_write(MAC_REG_BASE, MAC_KERNEL_REG_INPUT_SRC,
                     job->input_addr);
    mac_kernel_write(MAC_REG_BASE, MAC_KERNEL_REG_WEIGHT_SRC,
                     job->weight_addr);
    mac_kernel_write(MAC_REG_BASE, MAC_KERNEL_REG_BIAS_SRC,
                     job->bias_addr);
    mac_kernel_write(MAC_REG_BASE, MAC_KERNEL_REG_OUTPUT_DST,
                     job->output_addr);
    memory_fence();
    return MAC_KERNEL_OK;
}

static int run_traced_job(const mac_kernel_job_t *job, phase_trace_t *trace)
{
    uint32_t start;
    uint32_t now;
    uint32_t status;
    uint32_t state;
    uint32_t input_end = 0u;
    uint32_t weight_end = 0u;
    uint32_t bias_end = 0u;
    uint32_t compute_end = 0u;
    uint32_t end;
    int result = program_job(job);

    if (result != MAC_KERNEL_OK)
        return result;

    start = timer_now();
    mac_kernel_write(MAC_REG_BASE, MAC_KERNEL_REG_CONTROL,
                     MAC_KERNEL_CONTROL_START);

    for (;;) {
        status = mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_STATUS);
        now = timer_now();
        if ((status & MAC_KERNEL_STATUS_ERROR) != 0u)
            return MAC_KERNEL_ERR_HARDWARE;
        if ((status & MAC_KERNEL_STATUS_DONE) != 0u)
            break;

        state = (status & MAC_KERNEL_STATUS_STATE_MASK) >>
                MAC_KERNEL_STATUS_STATE_SHIFT;
        if (input_end == 0u && state >= 3u)
            input_end = now;
        if (weight_end == 0u && state >= 5u)
            weight_end = now;
        if (bias_end == 0u && state >= 7u)
            bias_end = now;
        if (compute_end == 0u && state >= 10u)
            compute_end = now;
        if ((uint32_t)(now - start) > RUN_TIMEOUT)
            return MAC_KERNEL_ERR_TIMEOUT;
    }
    end = now;
    if (input_end == 0u)
        input_end = end;
    if (weight_end == 0u)
        weight_end = end;
    if (bias_end == 0u)
        bias_end = end;
    if (compute_end == 0u)
        compute_end = end;

    memory_fence();
    trace->input_cycles = input_end - start;
    trace->weight_cycles = weight_end - input_end;
    trace->bias_cycles = bias_end - weight_end;
    trace->compute_cycles = compute_end - bias_end;
    trace->output_cycles = end - compute_end;
    trace->wall_cycles = end - start;
    trace->hardware_cycles = mac_kernel_cycles(MAC_REG_BASE);
    return MAC_KERNEL_OK;
}

static int verify_output(const mac_kernel_job_t *job)
{
    uint32_t count = (uint32_t)job->pixels * job->cout;
    uint32_t expected = job->cin;
    uint32_t i;

    memory_fence();
    for (i = 0u; i < count; ++i) {
        if (OUTPUT_CPU[i] != expected) {
            uart_puts("MAC_RESULT_FAIL index=");
            uart_put_u64(i);
            uart_puts(" got=");
            uart_put_u64(OUTPUT_CPU[i]);
            uart_puts(" expected=");
            uart_put_u64(expected);
            uart_putc('\n');
            return -1;
        }
    }
    return 0;
}

static void initialize_weights(uint8_t compute_mode)
{
    uint32_t value = compute_mode == MAC_KERNEL_MODE_S16_S16 ?
                     0x00010001u : 0x01010101u;
    uint32_t i;

    for (i = 0u; i < MAX_WEIGHT_BYTES / sizeof(uint32_t); ++i)
        WEIGHT_CPU[i] = value;
    memory_fence();
}

static void print_phase_report(const benchmark_case_t *test,
                               const phase_trace_t *trace,
                               const mac_kernel_buffer_sizes_t *sizes,
                               uint64_t macs)
{
    uint64_t read_bytes = sizes->input_bytes + sizes->weight_bytes +
                          sizes->bias_bytes;
    uint32_t read_cycles = trace->input_cycles + trace->weight_cycles +
                           trace->bias_cycles;
    uint32_t largest = read_cycles;
    const char *bottleneck = "DMA_READ";

    if (trace->compute_cycles > largest) {
        largest = trace->compute_cycles;
        bottleneck = "COMPUTE";
    }
    if (trace->output_cycles > largest) {
        largest = trace->output_cycles;
        bottleneck = "DMA_WRITE";
    }

    uart_puts("MAC_PHASE name=");
    uart_puts(test->name);
    uart_puts(" hw_total=");
    uart_put_u64(trace->hardware_cycles);
    uart_puts(" wall=");
    uart_put_u64(trace->wall_cycles);
    uart_puts(" input=");
    uart_put_u64(trace->input_cycles);
    uart_puts(" weight=");
    uart_put_u64(trace->weight_cycles);
    uart_puts(" bias=");
    uart_put_u64(trace->bias_cycles);
    uart_puts(" compute=");
    uart_put_u64(trace->compute_cycles);
    uart_puts(" output=");
    uart_put_u64(trace->output_cycles);
    uart_putc('\n');

    uart_puts("MAC_RATES name=");
    uart_puts(test->name);
    uart_puts(" dma_read_MiBps=");
    uart_put_fixed3(mib_per_second_x1000(read_bytes, read_cycles));
    uart_puts(" dma_write_MiBps=");
    uart_put_fixed3(mib_per_second_x1000(sizes->output_bytes,
                                        trace->output_cycles));
    uart_puts(" core_MAC_per_cycle=");
    uart_put_fixed3(ratio_x1000(macs, trace->compute_cycles));
    uart_puts(" e2e_MAC_per_cycle=");
    uart_put_fixed3(ratio_x1000(macs, trace->hardware_cycles));
    uart_putc('\n');

    uart_puts("MAC_BOTTLENECK name=");
    uart_puts(test->name);
    uart_puts(" stage=");
    uart_puts(bottleneck);
    uart_puts(" share_pct=");
    uart_put_fixed3(ratio_x1000((uint64_t)largest * 100u,
                               trace->wall_cycles));
    uart_putc('\n');
}

static int run_mac_case(const benchmark_case_t *test,
                        case_result_t *case_result)
{
    mac_kernel_job_t job;
    mac_kernel_buffer_sizes_t sizes;
    phase_trace_t first_trace = {0u, 0u, 0u, 0u, 0u, 0u, 0u};
    phase_trace_t trace;
    uint64_t total_cycles = 0u;
    uint64_t macs;
    uint64_t traffic_bytes;
    uint32_t run;
    int result;

    job.pixels = test->pixels;
    job.cin = test->cin;
    job.cout = test->cout;
    job.out_shift = 0u;
    job.compute_mode = test->compute_mode;
    job.activation = MAC_KERNEL_ACT_NONE;
    job.output_format = MAC_KERNEL_OUT_I32;
    job.irq_enable = 0u;
    job.zero_bias = test->zero_bias;
    job.input_addr = INPUT_BUS;
    job.weight_addr = WEIGHT_BUS;
    job.bias_addr = BIAS_BUS;
    job.output_addr = OUTPUT_BUS;
    sizes = mac_kernel_buffer_sizes(&job);
    macs = (uint64_t)test->pixels * test->cin * test->cout;
    traffic_bytes = sizes.input_bytes + sizes.weight_bytes +
                    sizes.bias_bytes + sizes.output_bytes;

    initialize_weights(test->compute_mode);

    case_result->minimum_cycles = 0xffffffffu;
    case_result->maximum_cycles = 0u;
    for (run = 0u; run < test->repeats; ++run) {
        result = run_traced_job(&job, &trace);
        if (result != MAC_KERNEL_OK) {
            uart_puts("MAC_EXEC_FAIL name=");
            uart_puts(test->name);
            uart_puts(" result=");
            uart_put_u64((uint32_t)(-result));
            uart_puts(" hw_error=");
            uart_put_u64(mac_kernel_error_code(MAC_REG_BASE));
            uart_putc('\n');
            return -1;
        }
        if (verify_output(&job) != 0)
            return -1;
        if (run == 0u)
            first_trace = trace;
        total_cycles += trace.hardware_cycles;
        if (trace.hardware_cycles < case_result->minimum_cycles)
            case_result->minimum_cycles = trace.hardware_cycles;
        if (trace.hardware_cycles > case_result->maximum_cycles)
            case_result->maximum_cycles = trace.hardware_cycles;
    }
    case_result->average_cycles =
        (uint32_t)(total_cycles / test->repeats);

    uart_puts("MAC_CASE name=");
    uart_puts(test->name);
    uart_puts(" dims=");
    uart_put_u64(test->pixels);
    uart_putc('x');
    uart_put_u64(test->cin);
    uart_putc('x');
    uart_put_u64(test->cout);
    uart_puts(" mode=");
    uart_puts(test->compute_mode == MAC_KERNEL_MODE_S16_S16 ?
              "s16s16" : "u8s8");
    uart_puts(" reps=");
    uart_put_u64(test->repeats);
    uart_puts(" MACs=");
    uart_put_u64(macs);
    uart_puts(" traffic_bytes=");
    uart_put_u64(traffic_bytes);
    uart_puts(" input_lines=");
    uart_put_u64(mac_kernel_read(MAC_REG_BASE,
        MAC_KERNEL_REG_LINE_COUNTS) & 0xffffu);
    uart_puts(" weight_lines=");
    uart_put_u64(mac_kernel_read(MAC_REG_BASE,
        MAC_KERNEL_REG_LINE_COUNTS) >> 16);
    uart_puts(" bias_lines=");
    uart_put_u64(mac_kernel_read(MAC_REG_BASE,
        MAC_KERNEL_REG_IO_COUNTS) & 0xffffu);
    uart_puts(" output_words=");
    uart_put_u64(mac_kernel_read(MAC_REG_BASE,
        MAC_KERNEL_REG_IO_COUNTS) >> 16);
    uart_puts(" arithmetic_intensity_MAC_per_byte=");
    uart_put_fixed3(ratio_x1000(macs, traffic_bytes));
    uart_putc('\n');

    print_phase_report(test, &first_trace, &sizes, macs);
    uart_puts("MAC_REPEAT name=");
    uart_puts(test->name);
    uart_puts(" avg_cycles=");
    uart_put_u64(case_result->average_cycles);
    uart_puts(" min_cycles=");
    uart_put_u64(case_result->minimum_cycles);
    uart_puts(" max_cycles=");
    uart_put_u64(case_result->maximum_cycles);
    uart_puts(" effective_MMACps=");
    uart_put_fixed3(macs * SYS_CLOCK_HZ * 1000u /
                    ((uint64_t)case_result->average_cycles * 1000000u));
    uart_putc('\n');
    return 0;
}

static int run_contention_test(const benchmark_case_t *test,
                               uint32_t baseline_cycles)
{
    mac_kernel_job_t job;
    uint64_t total_hardware_cycles = 0u;
    uint64_t total_wall_cycles = 0u;
    uint64_t pressure_bytes = 0u;
    uint32_t run;

    job.pixels = test->pixels;
    job.cin = test->cin;
    job.cout = test->cout;
    job.out_shift = 0u;
    job.compute_mode = test->compute_mode;
    job.activation = MAC_KERNEL_ACT_NONE;
    job.output_format = MAC_KERNEL_OUT_I32;
    job.irq_enable = 0u;
    job.zero_bias = test->zero_bias;
    job.input_addr = INPUT_BUS;
    job.weight_addr = WEIGHT_BUS;
    job.bias_addr = BIAS_BUS;
    job.output_addr = OUTPUT_BUS;

    initialize_weights(test->compute_mode);

    for (run = 0u; run < 4u; ++run) {
        uint32_t cursor = run * 997u;
        uint32_t start;
        uint32_t now;
        uint32_t status;
        uint64_t run_bytes = 0u;
        uint32_t index;
        uint32_t k;

        if (program_job(&job) != MAC_KERNEL_OK)
            return -1;
        start = timer_now();
        mac_kernel_write(MAC_REG_BASE, MAC_KERNEL_REG_CONTROL,
                         MAC_KERNEL_CONTROL_START);
        for (;;) {
            for (k = 0u; k < 32u; ++k) {
                index = (cursor + k) & (MEM_TEST_WORDS - 1u);
                MEM_DST_CPU[index] = MEM_SRC_CPU[index] ^ run;
            }
            cursor += 32u;
            run_bytes += 32u * 2u * sizeof(uint32_t);
            status = mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_STATUS);
            now = timer_now();
            if ((status & MAC_KERNEL_STATUS_ERROR) != 0u) {
                uart_puts("MAC_CONTENTION_EXEC_FAIL\n");
                return -1;
            }
            if ((status & MAC_KERNEL_STATUS_DONE) != 0u)
                break;
            if ((uint32_t)(now - start) > RUN_TIMEOUT) {
                uart_puts("MAC_CONTENTION_TIMEOUT\n");
                return -1;
            }
        }
        memory_fence();
        if (verify_output(&job) != 0)
            return -1;
        total_hardware_cycles += mac_kernel_cycles(MAC_REG_BASE);
        total_wall_cycles += now - start;
        pressure_bytes += run_bytes;
    }

    uart_puts("DDR_CONTENTION reps=4 baseline_avg_cycles=");
    uart_put_u64(baseline_cycles);
    uart_puts(" contended_avg_cycles=");
    uart_put_u64(total_hardware_cycles / 4u);
    uart_puts(" slowdown=");
    uart_put_fixed3(ratio_x1000(total_hardware_cycles,
                               (uint64_t)baseline_cycles * 4u));
    uart_puts(" cpu_traffic_bytes=");
    uart_put_u64(pressure_bytes);
    uart_puts(" cpu_MiBps=");
    uart_put_fixed3(mib_per_second_x1000(pressure_bytes,
                                        total_wall_cycles));
    uart_putc('\n');
    return 0;
}

static void initialize_mac_buffers(void)
{
    uint32_t i;

    for (i = 0u; i < MAX_INPUT_BYTES / sizeof(uint32_t); ++i)
        INPUT_CPU[i] = 0x00010001u;
    for (i = 0u; i < MAX_BIAS_BYTES / sizeof(uint32_t); ++i)
        BIAS_CPU[i] = 0u;
    for (i = 0u; i < MAX_OUTPUT_WORDS; ++i)
        OUTPUT_CPU[i] = 0xdeadbeefu;
    memory_fence();
}

int main(void)
{
    static const benchmark_case_t cases[] = {
        {"tiny_s16",       1u,   4u,  16u, MAC_KERNEL_MODE_S16_S16,
         1u, 16u},
        {"xiangqi_h256",   1u,  32u, 256u, MAC_KERNEL_MODE_U8_S8,
         1u, 16u},
        {"input_heavy",   16u, 256u,  32u, MAC_KERNEL_MODE_U8_S8,
         1u,  8u},
        {"weight_heavy",   1u, 256u, 256u, MAC_KERNEL_MODE_U8_S8,
         1u,  8u},
        {"output_heavy",  16u,   4u, 256u, MAC_KERNEL_MODE_U8_S8,
         1u,  8u},
        {"max_compute",   16u, 256u, 256u, MAC_KERNEL_MODE_U8_S8,
         1u, 32u},
        {"max_bias_dma",  16u, 256u, 256u, MAC_KERNEL_MODE_U8_S8,
         0u,  8u},
        {"max_s16",       16u, 256u, 256u, MAC_KERNEL_MODE_S16_S16,
         1u,  8u}
    };
    case_result_t result;
    case_result_t max_result = {0u, 0u, 0u};
    uint32_t i;
    uint32_t sys_clock;
    uint32_t completed_before;
    uint32_t completed_after;
    uint32_t expected_runs = 4u;

    uart_puts("MAC bottleneck stress benchmark v1\n");
    if (REG32(SYS_BASE_ADDR) != EXPECTED_SYS_ID) {
        uart_puts("SOC_ID_FAIL\n");
        return 1;
    }
    if ((REG32(SYS_BASE_ADDR + 4u) & 1u) == 0u) {
        uart_puts("DDR_NOT_READY\n");
        return 2;
    }
    if (mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_ID) != MAC_KERNEL_ID ||
        mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_VERSION) !=
            MAC_KERNEL_VERSION ||
        mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_CAP2) !=
            MAC_KERNEL_MAX_BURST_BEATS) {
        uart_puts("MAC_ABI_FAIL\n");
        return 3;
    }
    sys_clock = REG32(SYS_BASE_ADDR + 8u);
    uart_puts("BENCH_CONFIG sys_hz=");
    uart_put_u64(sys_clock);
    uart_puts(" mac_version=");
    uart_put_u64(mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_VERSION));
    uart_puts(" max_burst_beats=");
    uart_put_u64(mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_CAP2));
    uart_puts(" mem_test_bytes=");
    uart_put_u64(MEM_TEST_BYTES);
    uart_putc('\n');

    if (sys_clock != SYS_CLOCK_HZ) {
        uart_puts("SYS_CLOCK_FAIL\n");
        return 4;
    }
    if (run_cpu_memory_benchmark() != 0)
        return 5;

    initialize_mac_buffers();
    completed_before = mac_kernel_read(MAC_REG_BASE,
                                       MAC_KERNEL_REG_COMPLETED);
    for (i = 0u; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        expected_runs += cases[i].repeats;
        if (run_mac_case(&cases[i], &result) != 0)
            return 6;
        if (i == 5u)
            max_result = result;
    }
    if (run_contention_test(&cases[5], max_result.average_cycles) != 0)
        return 7;
    completed_after = mac_kernel_read(MAC_REG_BASE,
                                      MAC_KERNEL_REG_COMPLETED);
    if ((uint32_t)(completed_after - completed_before) != expected_runs) {
        uart_puts("MAC_COMPLETED_COUNT_FAIL expected=");
        uart_put_u64(expected_runs);
        uart_puts(" got=");
        uart_put_u64((uint32_t)(completed_after - completed_before));
        uart_putc('\n');
        return 8;
    }

    uart_puts("MAC_STRESS_SUMMARY max_compute_avg_cycles=");
    uart_put_u64(max_result.average_cycles);
    uart_puts(" runs_delta=");
    uart_put_u64((uint32_t)(completed_after - completed_before));
    uart_putc('\n');
    uart_puts("MAC_STRESS_PASS\n");
    return 0;
}
