#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#include "pango_mac_uapi.h"

#define TEST_CONTEXTS 8

static uint64_t now_us(void)
{
    struct timespec ts;

    if (clock_gettime(CLOCK_MONOTONIC, &ts))
        return 0;
    return (uint64_t)ts.tv_sec * 1000000u + (uint64_t)ts.tv_nsec / 1000u;
}

int main(void)
{
    int fds[TEST_CONTEXTS];
    uint8_t *maps[TEST_CONTEXTS];
    size_t bytes = 0;
    uint64_t open_us = 0;
    uint64_t start;
    unsigned i;
    int extra;
    int result = 1;

    for (i = 0; i < TEST_CONTEXTS; ++i) {
        fds[i] = -1;
        maps[i] = MAP_FAILED;
    }
    for (i = 0; i < TEST_CONTEXTS; ++i) {
        struct pango_mac_info info;

        start = now_us();
        fds[i] = open("/dev/pango-mac0", O_RDWR | O_CLOEXEC);
        open_us += now_us() - start;
        if (fds[i] < 0) {
            fprintf(stderr, "pool-test: open %u: %s\n", i, strerror(errno));
            goto out;
        }
        memset(&info, 0, sizeof(info));
        if (ioctl(fds[i], PANGO_MAC_IOC_GET_INFO, &info) ||
            info.abi_version != PANGO_MAC_ABI_VERSION ||
            info.device_id != PANGO_MAC_ID ||
            info.scratch_bytes != 0x00100000u ||
            (bytes && bytes != info.scratch_bytes)) {
            fputs("pool-test: invalid device info\n", stderr);
            goto out;
        }
        bytes = info.scratch_bytes;
        maps[i] = mmap(NULL, bytes, PROT_READ | PROT_WRITE,
                       MAP_SHARED, fds[i], 0);
        if (maps[i] == MAP_FAILED) {
            fprintf(stderr, "pool-test: mmap %u: %s\n", i, strerror(errno));
            goto out;
        }
        if (maps[i][0] || maps[i][bytes - 1]) {
            fputs("pool-test: new context is not zeroed\n", stderr);
            goto out;
        }
        maps[i][0] = (uint8_t)(i + 1u);
        maps[i][bytes - 1] = (uint8_t)(0x80u + i);
    }

    extra = open("/dev/pango-mac0", O_RDWR | O_CLOEXEC);
    if (extra >= 0) {
        close(extra);
        fputs("pool-test: ninth open unexpectedly succeeded\n", stderr);
        goto out;
    }
    if (errno != EBUSY) {
        fprintf(stderr, "pool-test: ninth open errno=%d\n", errno);
        goto out;
    }

    munmap(maps[0], bytes);
    maps[0] = MAP_FAILED;
    close(fds[0]);
    fds[0] = -1;
    start = now_us();
    fds[0] = open("/dev/pango-mac0", O_RDWR | O_CLOEXEC);
    open_us += now_us() - start;
    if (fds[0] < 0) {
        fputs("pool-test: released context cannot be reused\n", stderr);
        goto out;
    }
    maps[0] = mmap(NULL, bytes, PROT_READ | PROT_WRITE,
                   MAP_SHARED, fds[0], 0);
    if (maps[0] == MAP_FAILED || maps[0][0] || maps[0][bytes - 1]) {
        fputs("pool-test: reused context was not cleared\n", stderr);
        goto out;
    }
    for (i = 1; i < TEST_CONTEXTS; ++i) {
        if (maps[i][0] != i + 1u || maps[i][bytes - 1] != 0x80u + i) {
            fputs("pool-test: live contexts are not isolated\n", stderr);
            goto out;
        }
    }
    printf("PANGO_MAC_POOL_TEST_PASS contexts=%u bytes=%zu opens=9 open_us=%llu\n",
           TEST_CONTEXTS, bytes, (unsigned long long)open_us);
    result = 0;

out:
    for (i = 0; i < TEST_CONTEXTS; ++i) {
        if (maps[i] != MAP_FAILED)
            munmap(maps[i], bytes);
        if (fds[i] >= 0)
            close(fds[i]);
    }
    return result;
}
