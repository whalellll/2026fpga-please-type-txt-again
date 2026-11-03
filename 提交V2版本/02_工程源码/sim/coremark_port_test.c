/* Host-only test of the production port. VirtualAlloc creates ordinary
 * process memory at the MMIO addresses; no FPGA or physical device is used.
 * The upstream entry stub deliberately returns zero for every outcome. */
#include <windows.h>
#include <stdio.h>
#include "coremark.h"

extern volatile ee_s32 seed1_volatile, seed2_volatile, seed3_volatile;
int coremark_command(int validation);
/* MinGW stdio may inline its own printf; explicitly bind the port symbol. */
extern int port_printf(const char *format, ...) __asm__("printf");

static unsigned scenario;
static int expected_validation;
static volatile ee_u32 *const mtime_low = (volatile ee_u32 *)0x0200bff8u;
static volatile ee_u32 *const mtime_high = (volatile ee_u32 *)0x0200bffcu;

int coremark_benchmark_main(void)
{
    CORE_TICKS duration = CORE_CLOCKS_PER_SEC * 10;
    if (seed1_volatile != (expected_validation ? 0x3415 : 0) ||
        seed2_volatile != seed1_volatile || seed3_volatile != 0x66) {
        fputs("CoreMark runtime seed mode is wrong\n", stderr);
        ExitProcess(2);
    }
    *mtime_low = 0;
    *mtime_high = 0;
    start_time();
    if (scenario == 1)
        duration--;
    if (scenario == 5)
        duration += 0x100000000ULL;
    *mtime_low = (ee_u32)duration;
    *mtime_high = (ee_u32)(duration >> 32);
    stop_time();
    if (scenario != 3)
        port_printf("Correct operation validated. See readme.txt for run and reporting rules.\n");
    if (scenario == 2)
        port_printf("Errors detected\n");
    if (scenario == 4)
        port_printf("Cannot validate operation for these seed values\n");
    return 0;
}

int main(void)
{
    unsigned i;
    void *clint = VirtualAlloc((void *)0x02000000u, 0x10000,
                              MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    void *uart = VirtualAlloc((void *)0x1fe00000u, 0x10000,
                             MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE);
    if (clint != (void *)0x02000000u || uart != (void *)0x1fe00000u) {
        fputs("Cannot reserve fake MMIO for the CoreMark port host test\n", stderr);
        return 2;
    }
    for (i = 0; i < 12; ++i) {
        int expected;
        int actual;
        scenario = i % 6;
        expected_validation = i >= 6;
        expected = scenario == 0 || scenario == 5 ? 0 : 1;
        actual = coremark_command(expected_validation);
        if (actual != expected) {
            fprintf(stderr, "CoreMark wrapper case %u returned %d, expected %d\n", i, actual, expected);
            return 1;
        }
    }
    VirtualFree(clint, 0, MEM_RELEASE);
    VirtualFree(uart, 0, MEM_RELEASE);
    fputs("COREMARK_PRODUCTION_PORT_HOST_PASS cases=12 seeds=2 timer64=1 main_zero_not_trusted=1\n", stdout);
    return 0;
}
