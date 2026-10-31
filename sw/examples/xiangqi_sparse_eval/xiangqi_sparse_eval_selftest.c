#include <stdint.h>
#include "xiangqi_sparse_eval.h"

#define UART (*(volatile uint32_t *)0x1fe001e0u)
#define MAC_REG_BASE 0x1fe10000u

#define MAC_DDR_BUS 0x1b000000u
#define MAC_DDR_CPU 0x9b000000u
#define MODEL_OFFSET  0x00000u
#define PARENT_OFFSET 0x34000u
#define WEIGHT_OFFSET 0x34400u
#define DESC_OFFSET   0x34600u

#define MODEL_BUS   (MAC_DDR_BUS + MODEL_OFFSET)
#define PARENT_BUS  (MAC_DDR_BUS + PARENT_OFFSET)
#define WEIGHT_BUS  (MAC_DDR_BUS + WEIGHT_OFFSET)
#define DESC_BUS    (MAC_DDR_BUS + DESC_OFFSET)

#define MODEL_CPU  ((volatile uint32_t *)(MAC_DDR_CPU + MODEL_OFFSET))
#define PARENT_CPU ((volatile int32_t  *)(MAC_DDR_CPU + PARENT_OFFSET))
#define WEIGHT_CPU ((volatile uint32_t *)(MAC_DDR_CPU + WEIGHT_OFFSET))
#define DESC_CPU   ((volatile xq_sparse_descriptor_t *)(MAC_DDR_CPU + DESC_OFFSET))

#define TEST_MODEL_ROWS 16u
#define TEST_CHILDREN 16u
#define STRESS_RUNS 32u
#define SCORE_BIAS_NUMERATOR (-321987ll)

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

static void uart_put_int(int32_t value)
{
    uint32_t magnitude;
    if (value < 0) {
        uart_putc('-');
        magnitude = (uint32_t)(-(int64_t)value);
    } else {
        magnitude = (uint32_t)value;
    }
    uart_put_uint(magnitude);
}

static inline void memory_fence(void)
{
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
}

static inline uint32_t read_cycle(void)
{
    uint32_t value;
    __asm__ volatile ("rdcycle %0" : "=r"(value));
    return value;
}

static int32_t row_value(uint32_t row, uint32_t lane)
{
    return (int32_t)((row * 3u + lane * 5u + 2u) % 15u) - 7;
}

static int32_t weight_value(uint32_t bank, uint32_t lane)
{
    if (bank == 0u)
        return (int32_t)((lane * 2u + 1u) % 9u) - 4;
    return (int32_t)((lane * 3u + 2u) % 11u) - 5;
}

static int32_t parent_value(uint32_t bank, uint32_t lane)
{
    if (bank == 0u)
        return 4200 + ((int32_t)(lane % 13u) - 6) * 510;
    return 3600 + ((int32_t)(lane % 9u) - 4) * 630;
}

static uint32_t pack4(int32_t a, int32_t b, int32_t c, int32_t d)
{
    return ((uint32_t)a & 0xffu) |
           (((uint32_t)b & 0xffu) << 8) |
           (((uint32_t)c & 0xffu) << 16) |
           (((uint32_t)d & 0xffu) << 24);
}

static void prepare_data(void)
{
    uint32_t row;
    uint32_t word;
    uint32_t lane;
    uint32_t child;

    for (row = 0; row < TEST_MODEL_ROWS; ++row) {
        for (word = 0; word < 32u; ++word) {
            lane = word * 4u;
            MODEL_CPU[row * 32u + word] = pack4(
                row_value(row, lane), row_value(row, lane + 1u),
                row_value(row, lane + 2u), row_value(row, lane + 3u));
        }
    }
    for (lane = 0; lane < 128u; ++lane) {
        PARENT_CPU[lane] = parent_value(0u, lane);
        PARENT_CPU[128u + lane] = parent_value(1u, lane);
    }
    for (word = 0; word < 64u; ++word) {
        lane = word * 4u;
        WEIGHT_CPU[word] = pack4(
            weight_value(lane / 128u, lane % 128u),
            weight_value((lane + 1u) / 128u, (lane + 1u) % 128u),
            weight_value((lane + 2u) / 128u, (lane + 2u) % 128u),
            weight_value((lane + 3u) / 128u, (lane + 3u) % 128u));
    }
    for (child = 0; child < TEST_CHILDREN; ++child) {
        DESC_CPU[child].child_side = child & 1u;
        DESC_CPU[child].red_remove_from = child % 12u;
        DESC_CPU[child].red_add_to = (child + 1u) % 12u;
        DESC_CPU[child].red_remove_capture = (child % 3u == 0u) ?
            (child + 2u) % 12u : XQ_SPARSE_INVALID_ROW;
        DESC_CPU[child].black_remove_from = (child + 3u) % 12u;
        DESC_CPU[child].black_add_to = (child + 4u) % 12u;
        DESC_CPU[child].black_remove_capture = (child % 4u == 0u) ?
            (child + 5u) % 12u : XQ_SPARSE_INVALID_ROW;
        DESC_CPU[child].reserved = 0u;
    }
    memory_fence();
}

static int8_t staged_row_byte(uint32_t row, uint32_t lane)
{
    volatile uint8_t *bytes = (volatile uint8_t *)MODEL_CPU;
    return (int8_t)bytes[row * 128u + lane];
}

static int8_t staged_weight(uint32_t bank, uint32_t lane)
{
    volatile uint8_t *bytes = (volatile uint8_t *)WEIGHT_CPU;
    return (int8_t)bytes[bank * 128u + lane];
}

static int32_t reference_score(uint32_t child)
{
    const volatile xq_sparse_descriptor_t *d = &DESC_CPU[child];
    int64_t sum = 0;
    int32_t dr;
    int32_t db;
    int32_t red_hidden;
    int32_t black_hidden;
    uint32_t lane;
    uint32_t side = d->child_side & 1u;

    for (lane = 0; lane < 128u; ++lane) {
        dr = -staged_row_byte(d->red_remove_from, lane) +
              staged_row_byte(d->red_add_to, lane);
        if (d->red_remove_capture != XQ_SPARSE_INVALID_ROW)
            dr -= staged_row_byte(d->red_remove_capture, lane);
        db = -staged_row_byte(d->black_remove_from, lane) +
              staged_row_byte(d->black_add_to, lane);
        if (d->black_remove_capture != XQ_SPARSE_INVALID_ROW)
            db -= staged_row_byte(d->black_remove_capture, lane);
        red_hidden = PARENT_CPU[lane] + dr * 627;
        black_hidden = PARENT_CPU[128u + lane] + db * 627;
        if (red_hidden > 0)
            sum += (int64_t)red_hidden * staged_weight(side, lane);
        if (black_hidden > 0)
            sum += (int64_t)black_hidden * staged_weight(side ^ 1u, lane);
    }
    return (int32_t)((SCORE_BIAS_NUMERATOR + 1092ll * sum) /
                     (int64_t)XQ_SPARSE_SCORE_DIVISOR);
}

static uint32_t wait_for_hardware(uint32_t timeout)
{
    uint32_t status;
    do {
        status = xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_STATUS);
        if ((status & XQ_SPARSE_STATUS_DONE) != 0u)
            return status;
    } while (--timeout != 0u);
    return 0u;
}

static void program_job(void)
{
    uint64_t bias_bits = (uint64_t)SCORE_BIAS_NUMERATOR;
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_CHILD_COUNT,
                    TEST_CHILDREN);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_MODEL_BASE, MODEL_BUS);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_PARENT_BASE, PARENT_BUS);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_OUTPUT_WEIGHT, WEIGHT_BUS);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_DESCRIPTOR, DESC_BUS);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_BIAS_LO,
                    (uint32_t)bias_bits);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_BIAS_HI,
                    (uint32_t)(bias_bits >> 32));
}

int main(void)
{
    int32_t expected[XQ_SPARSE_MAX_CHILDREN];
    uint32_t status;
    uint32_t child;
    uint32_t run;
    uint32_t before_runs;
    uint32_t cpu_start;
    uint32_t cpu_cycles;
    uint32_t hw_cycles = 0;

    uart_puts("Xiangqi sparse fused evaluator self-test\n");
    if (xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_ID) != XQ_SPARSE_ID ||
        xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_VERSION) !=
            XQ_SPARSE_VERSION ||
        xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_MODEL_ROWS) != 1620u ||
        xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_DIVISOR) !=
            XQ_SPARSE_SCORE_DIVISOR) {
        uart_puts("XQ_SPARSE_MMIO_FAIL\n");
        return 1;
    }

    // A zero-child command must fail without touching DDR.
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_CHILD_COUNT, 0u);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_CONTROL,
                    XQ_SPARSE_CONTROL_START);
    status = wait_for_hardware(1000u);
    if ((status & XQ_SPARSE_STATUS_ERROR) == 0u ||
        xq_sparse_error_code(status) != XQ_SPARSE_ERR_CONFIG) {
        uart_puts("XQ_SPARSE_CONFIG_CHECK_FAIL\n");
        return 2;
    }
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_CONTROL,
                    XQ_SPARSE_CONTROL_CLEAR);

    prepare_data();
    cpu_start = read_cycle();
    for (child = 0; child < TEST_CHILDREN; ++child)
        expected[child] = reference_score(child);
    cpu_cycles = read_cycle() - cpu_start;

    program_job();
    before_runs = xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_COMPLETED);
    for (run = 0; run < STRESS_RUNS; ++run) {
        memory_fence();
        xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_CONTROL,
                        XQ_SPARSE_CONTROL_START);
        status = wait_for_hardware(1000000u);
        if ((status & XQ_SPARSE_STATUS_DONE) == 0u ||
            (status & XQ_SPARSE_STATUS_ERROR) != 0u) {
            uart_puts("XQ_SPARSE_EXEC_FAIL run=");
            uart_put_uint(run);
            uart_puts(" error=");
            uart_put_uint(xq_sparse_error_code(status));
            uart_putc('\n');
            return 3;
        }
        hw_cycles += xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_CYCLES);
        for (child = 0; child < TEST_CHILDREN; ++child) {
            int32_t actual = (int32_t)xq_sparse_read(
                MAC_REG_BASE, XQ_SPARSE_REG_RESULT(child));
            if (actual != expected[child]) {
                uart_puts("XQ_SPARSE_RESULT_FAIL run=");
                uart_put_uint(run);
                uart_puts(" child=");
                uart_put_uint(child);
                uart_puts(" actual=");
                uart_put_int(actual);
                uart_puts(" expected=");
                uart_put_int(expected[child]);
                uart_putc('\n');
                return 4;
            }
        }
    }
    if (xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_COMPLETED) -
        before_runs != STRESS_RUNS) {
        uart_puts("XQ_SPARSE_RUN_COUNT_FAIL\n");
        return 5;
    }

    uart_puts("CHILDREN=");
    uart_put_uint(TEST_CHILDREN);
    uart_puts(" RUNS=");
    uart_put_uint(STRESS_RUNS);
    uart_puts(" CPU_REF_CYCLES=");
    uart_put_uint(cpu_cycles);
    uart_puts(" HW_CYCLES_AVG=");
    uart_put_uint(hw_cycles / STRESS_RUNS);
    uart_puts(" SCORE0=");
    uart_put_int(expected[0]);
    uart_puts(" SCORE15=");
    uart_put_int(expected[15]);
    uart_puts("\nXIANGQI_SPARSE_BOARD_PASS\n");
    return 0;
}
