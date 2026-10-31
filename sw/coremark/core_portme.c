#include "coremark.h"
#include <stdarg.h>

#define UART_THR          (*(volatile ee_u8 *)0x1fe001e0u)
#define CLINT_MTIME_LOW   (*(volatile ee_u32 *)0x0200bff8u)
#define CLINT_MTIME_HIGH  (*(volatile ee_u32 *)0x0200bffcu)
#define SYS_INFO_BASE     0x1fe00300u
#define SYS_CPU_HZ_REG    (*(volatile ee_u32 *)(SYS_INFO_BASE + 0x14u))
#define SYS_TIMEBASE_REG  (*(volatile ee_u32 *)(SYS_INFO_BASE + 0x18u))

volatile ee_s32 seed1_volatile = VALIDATION_RUN ? 0x3415 : 0;
volatile ee_s32 seed2_volatile = VALIDATION_RUN ? 0x3415 : 0;
volatile ee_s32 seed3_volatile = 0x66;
volatile ee_s32 seed4_volatile = ITERATIONS;
volatile ee_s32 seed5_volatile = 0;

static CORE_TICKS start_ticks;
static CORE_TICKS stop_ticks;
static int report_validated;
static int report_failed;
static ee_u32 coremark_iterations;

int coremark_benchmark_main(void);

static int starts_with(const char *text, const char *prefix)
{
    while (*prefix != '\0') {
        if (*text++ != *prefix++)
            return 0;
    }
    return 1;
}

/* The unmodified upstream main returns zero even on failure. Observe its
 * actual validation report and elapsed timer instead of trusting that value. */
int coremark_command(int validation)
{
    int passed;
    report_validated = 0;
    report_failed = 0;
    seed1_volatile = validation ? 0x3415 : 0;
    seed2_volatile = validation ? 0x3415 : 0;
    seed3_volatile = 0x66;
    seed4_volatile = ITERATIONS;
    seed5_volatile = 0;
    printf("COREMARK_MODE=%s\n", validation ? "validation" : "performance");
    (void)coremark_benchmark_main();
    passed = report_validated && !report_failed &&
             get_time() >= (CORE_TICKS)CORE_CLOCKS_PER_SEC * 10;
    printf("PORT_TICKS64 : %llu\n", (unsigned long long)get_time());
    printf(passed ? "COREMARK_PASS\n" : "COREMARK_FAIL\n");
    /* Print CoreMark/MHz from the same tick data the benchmark used. */
    {
        ee_u32 cpu_hz = SYS_CPU_HZ_REG;
        ee_u32 timebase_hz = SYS_TIMEBASE_REG;
        CORE_TICKS elapsed = get_time();
        if (cpu_hz > 0 && timebase_hz > 0 && elapsed > 0) {
            /* Two-step divide to avoid uint64 overflow:
             * step1: iter_per_sec_x1000 = iter * timebase * 1000 / elapsed
             * step2: per_mhz_x1000 = iter_per_sec_x1000 * 1000000 / cpu_hz */
            unsigned long long iter_per_sec_x1000 =
                (unsigned long long)coremark_iterations *
                (unsigned long long)timebase_hz * 1000ull /
                (unsigned long long)elapsed;
            unsigned long long per_mhz_x1000 =
                iter_per_sec_x1000 * 1000000ull /
                (unsigned long long)cpu_hz;
            printf("CoreMark/MHz: %llu.%03llu (CPU_HZ=%u)\n",
                   per_mhz_x1000 / 1000, per_mhz_x1000 % 1000, cpu_hz);
        }
    }
    printf("COREMARK_DONE\n");
    return passed ? 0 : 1;
}

/* CLINT mtime advances at TIMEBASE_HZ in the SYS domain. A coherent
 * high/low/high read handles a low-word rollover. CPU mcycle is separate. */
static CORE_TICKS read_mtime64(void)
{
    ee_u32 hi0;
    ee_u32 lo;
    ee_u32 hi1;

    do {
        hi0 = CLINT_MTIME_HIGH;
        lo = CLINT_MTIME_LOW;
        hi1 = CLINT_MTIME_HIGH;
    } while (hi0 != hi1);
    return ((CORE_TICKS)hi1 << 32) | lo;
}

void start_time(void)
{
    start_ticks = read_mtime64();
}

void stop_time(void)
{
    stop_ticks = read_mtime64();
}

CORE_TICKS get_time(void)
{
    return stop_ticks - start_ticks;
}

secs_ret time_in_secs(CORE_TICKS ticks)
{
    return (secs_ret)ticks / (secs_ret)CORE_CLOCKS_PER_SEC;
}

void *portable_malloc(ee_size_t size)
{
    (void)size;
    return NULL;
}

void portable_free(void *p)
{
    (void)p;
}

void portable_init(core_portable *p, int *argc, char *argv[])
{
    (void)argc;
    (void)argv;
    p->portable_id = 1;
}

void portable_fini(core_portable *p)
{
    p->portable_id = 0;
}

static void uart_putc(char c)
{
    if (c == '\n')
        UART_THR = '\r';
    UART_THR = (ee_u8)c;
}

static unsigned print_unsigned(unsigned long long value,
                               unsigned base,
                               unsigned width,
                               char pad,
                               int uppercase)
{
    char digits[24];
    const char *alphabet = uppercase ? "0123456789ABCDEF" : "0123456789abcdef";
    unsigned used = 0;
    unsigned total = 0;

    do {
        digits[used++] = alphabet[value % base];
        value /= base;
    } while (value != 0);

    while (width > used) {
        uart_putc(pad);
        width--;
        total++;
    }
    while (used != 0) {
        uart_putc(digits[--used]);
        total++;
    }
    return total;
}

static unsigned print_signed(long long value, unsigned width, char pad)
{
    unsigned total = 0;
    unsigned long long magnitude;

    if (value < 0) {
        uart_putc('-');
        total++;
        if (width != 0)
            width--;
        magnitude = (unsigned long long)(-(value + 1)) + 1;
    } else {
        magnitude = (unsigned long long)value;
    }
    return total + print_unsigned(magnitude, 10, width, pad, 0);
}

static unsigned print_double(double value, unsigned width, unsigned precision)
{
    unsigned total = 0;
    unsigned i;
    unsigned long long scale = 1;
    unsigned long long whole;
    unsigned long long fraction;

    if (value < 0.0) {
        uart_putc('-');
        total++;
        value = -value;
    }
    for (i = 0; i < precision; i++)
        scale *= 10;

    whole = (unsigned long long)value;
    fraction = (unsigned long long)(((value - (double)whole) *
                                     (double)scale) + 0.5);
    if (fraction >= scale) {
        whole++;
        fraction -= scale;
    }

    (void)width;
    total += print_unsigned(whole, 10, 0, ' ', 0);
    if (precision != 0) {
        uart_putc('.');
        total++;
        total += print_unsigned(fraction, 10, precision, '0', 0);
    }
    return total;
}

int printf(const char *format, ...)
{
    va_list ap;
    unsigned total = 0;

    if (starts_with(format, "Correct operation validated."))
        report_validated = 1;
    if (starts_with(format, "ERROR!") || starts_with(format, "Errors detected") ||
        starts_with(format, "Cannot validate operation") ||
        starts_with(format, "list_head structure too big"))
        report_failed = 1;
    /* Capture the actual iteration count printed by the benchmark
     * (seed4_volatile is 0 in auto-calibration mode). */
    if (starts_with(format, "Iterations       : ")) {
        va_start(ap, format);
        coremark_iterations = (ee_u32)va_arg(ap, unsigned long);
        va_end(ap);
    }
    va_start(ap, format);
    while (*format != '\0') {
        unsigned width = 0;
        unsigned precision = 6;
        int long_arg = 0;
        char pad = ' ';

        if (*format != '%') {
            uart_putc(*format++);
            total++;
            continue;
        }
        format++;
        if (*format == '%') {
            uart_putc(*format++);
            total++;
            continue;
        }
        if (*format == '0') {
            pad = '0';
            format++;
        }
        while (*format >= '0' && *format <= '9') {
            width = width * 10 + (unsigned)(*format - '0');
            format++;
        }
        if (*format == '.') {
            precision = 0;
            format++;
            while (*format >= '0' && *format <= '9') {
                precision = precision * 10 + (unsigned)(*format - '0');
                format++;
            }
        }
        if (*format == 'l') {
            long_arg = 1;
            format++;
            if (*format == 'l') {
                long_arg = 2;
                format++;
            }
        }

        switch (*format++) {
        case 'c':
            uart_putc((char)va_arg(ap, int));
            total++;
            break;
        case 's': {
            const char *s = va_arg(ap, const char *);
            if (s == NULL)
                s = "(null)";
            while (*s != '\0') {
                uart_putc(*s++);
                total++;
            }
            break;
        }
        case 'd':
        case 'i':
            if (long_arg == 2)
                total += print_signed(va_arg(ap, long long), width, pad);
            else if (long_arg == 1)
                total += print_signed(va_arg(ap, long), width, pad);
            else
                total += print_signed(va_arg(ap, int), width, pad);
            break;
        case 'u':
            if (long_arg == 2)
                total += print_unsigned(va_arg(ap, unsigned long long),
                                        10, width, pad, 0);
            else if (long_arg == 1)
                total += print_unsigned(va_arg(ap, unsigned long),
                                        10, width, pad, 0);
            else
                total += print_unsigned(va_arg(ap, unsigned int),
                                        10, width, pad, 0);
            break;
        case 'x':
        case 'X': {
            int upper = format[-1] == 'X';
            if (long_arg == 2)
                total += print_unsigned(va_arg(ap, unsigned long long),
                                        16, width, pad, upper);
            else if (long_arg == 1)
                total += print_unsigned(va_arg(ap, unsigned long),
                                        16, width, pad, upper);
            else
                total += print_unsigned(va_arg(ap, unsigned int),
                                        16, width, pad, upper);
            break;
        }
        case 'f':
            total += print_double(va_arg(ap, double), width, precision);
            break;
        default:
            uart_putc('?');
            total++;
            break;
        }
    }
    va_end(ap);
    return (int)total;
}
