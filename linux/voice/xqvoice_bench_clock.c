#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

/* Initialize the benchmark-only readonly CLINT wrapper before either timed
 * path. A failed or coarse clock must not produce an acceleration ratio. */
__attribute__((constructor)) static void prepare_benchmark_clock(void)
{
    struct timespec resolution;
    if (clock_getres(CLOCK_MONOTONIC, &resolution) || resolution.tv_sec ||
        resolution.tv_nsec <= 0 || resolution.tv_nsec > 1000) {
        fputs("VOICE_BENCH_CLOCK_FAIL\n", stderr);
        exit(90);
    }
    fprintf(stderr, "VOICE_BENCH_CLOCK resolution_ns=%ld initialized_before_timing=1\n",
            resolution.tv_nsec);
}
