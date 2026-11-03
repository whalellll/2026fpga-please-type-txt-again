/* Correctness oracle only; host time/performance is never a target score.
 * The upstream list allocator fixes per_item=16+sizeof(list_data), explicitly
 * preserving the workload on hosts with 64-bit pointers. Algorithms and the
 * iterate routine below are compiled unchanged from the pinned upstream files.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define main unused_coremark_main
#include "core_main.c"
#undef main

volatile ee_s32 seed1_volatile, seed2_volatile, seed3_volatile, seed4_volatile, seed5_volatile;
/* The unused upstream console entry is linked on PE/COFF. These trap stubs
 * deliberately prevent it from generating a host performance report. */
void portable_init(core_portable *p, int *argc, char *argv[]) { abort(); }
void portable_fini(core_portable *p) { abort(); }
void start_time(void) { abort(); }
void stop_time(void) { abort(); }
CORE_TICKS get_time(void) { abort(); }
secs_ret time_in_secs(CORE_TICKS ticks) { abort(); }

int main(int argc, char **argv) {
    core_results result;
    union { void *align; ee_u8 bytes[2048]; } list, matrix, state;
    unsigned long iterations;
    if (argc != 3 || (strcmp(argv[1], "performance") && strcmp(argv[1], "validation"))) return 2;
    iterations = strtoul(argv[2], NULL, 10);
    if (iterations < 1 || iterations > 1000000) return 2;
    memset(&result, 0, sizeof(result));
    result.seed1 = result.seed2 = !strcmp(argv[1], "validation") ? 0x3415 : 0;
    result.seed3 = 0x66;
    result.size = 2000 / 3;
    result.iterations = (ee_u32)iterations;
    result.execs = ALL_ALGORITHMS_MASK;
    result.memblock[1] = list.bytes;
    result.memblock[2] = matrix.bytes;
    result.memblock[3] = state.bytes;
    result.list = core_list_init(result.size, (list_head *)list.bytes, result.seed1);
    core_init_matrix(result.size, matrix.bytes,
        (ee_s32)result.seed1 | (((ee_s32)result.seed2) << 16), &result.mat);
    core_init_state(result.size, result.seed1, state.bytes);
    iterate(&result);
    printf("%04x %04x %04x %04x\n", result.crclist, result.crcmatrix, result.crcstate, result.crc);
    return 0;
}
