#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

/* Benchmark-only read access. The kernel clocksource and accelerator owners
 * are unchanged. Link with --wrap=clock_gettime,--wrap=clock_getres. */
#define CLINT_PAGE 0x0200b000u
#define CLINT_HZ 49500000u
static pthread_once_t once = PTHREAD_ONCE_INIT;
static volatile const uint32_t *timer;
static int use_linux, clock_error;
int __real_clock_gettime(clockid_t id, struct timespec *t);
int __real_clock_getres(clockid_t id, struct timespec *t);

static uint64_t ticks(void)
{
    uint32_t high, low, check;
    do {
        high = timer[1];
        low = timer[0];
        check = timer[1];
    } while (high != check);
    return ((uint64_t)high << 32) | low;
}

static void init_clock(void)
{
    const char *mode = getenv("NNUE_CLOCKSOURCE");
    if (mode && !strcmp(mode, "linux")) { use_linux = 1; return; }
    if (mode && strcmp(mode, "clint")) { clock_error = EINVAL; return; }
    int fd = open("/dev/mem", O_RDONLY | O_SYNC);
    if (fd < 0) { clock_error = errno; return; }
    void *mapping = mmap(NULL, 4096, PROT_READ, MAP_SHARED, fd, CLINT_PAGE);
    int saved = errno;
    close(fd);
    if (mapping == MAP_FAILED) { clock_error = saved; return; }
    timer = (volatile const uint32_t *)((const char *)mapping + 0xff8);
    uint64_t first = ticks();
    unsigned retry;
    for (retry = 0; retry < 10000 && ticks() == first; ++retry) { }
    if (ticks() <= first) { clock_error = EIO; return; }
    fprintf(stderr, "NNUE_CLOCK_SOURCE source=clint hz=%u address=0200bff8 readonly=1\n", CLINT_HZ);
}

int __wrap_clock_gettime(clockid_t id, struct timespec *t)
{
    if (id != CLOCK_MONOTONIC) return __real_clock_gettime(id, t);
    pthread_once(&once, init_clock);
    if (use_linux) return __real_clock_gettime(id, t);
    if (clock_error) { errno = clock_error; return -1; }
    uint64_t value = ticks();
    t->tv_sec = (time_t)(value / CLINT_HZ);
    t->tv_nsec = (long)((value % CLINT_HZ) * 1000000000ull / CLINT_HZ);
    return 0;
}

int __wrap_clock_getres(clockid_t id, struct timespec *t)
{
    if (id != CLOCK_MONOTONIC) return __real_clock_getres(id, t);
    pthread_once(&once, init_clock);
    if (use_linux) return __real_clock_getres(id, t);
    if (clock_error) { errno = clock_error; return -1; }
    if (t) { t->tv_sec = 0; t->tv_nsec = (1000000000u + CLINT_HZ - 1) / CLINT_HZ; }
    return 0;
}
