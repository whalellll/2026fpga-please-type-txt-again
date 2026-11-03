#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

#include "pango_mac_uapi.h"

#define TEST_THREADS 2u
#define TEST_PROCESSES 3u
#define TEST_LOOPS 64u
#define INPUT_OFFSET 0x0000u
#define WEIGHT_OFFSET 0x1000u
#define BIAS_OFFSET 0x2000u
#define OUTPUT_OFFSET 0x3000u

struct worker_args {
    unsigned value;
    int result;
};

static unsigned test_loops = TEST_LOOPS;
static int diag_mode;
static unsigned test_processes = TEST_PROCESSES;
static unsigned test_threads = TEST_THREADS;

static void* run_worker(void* opaque) {
    struct worker_args* args = (struct worker_args*)opaque;
    struct pango_mac_info info;
    struct pango_mac_job job;
    uint8_t* shadow;
    uint16_t* input;
    uint16_t* weights;
    uint32_t* output;
    unsigned loop;
    unsigned lane;
    int fd;

    args->result = 1;
    if (diag_mode == -1) {
        args->result = 0;
        return NULL;
    }
    fd = open("/dev/pango-mac0", O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        fprintf(stderr, "scheduler-test: open failed: %s\n", strerror(errno));
        return NULL;
    }
    if (diag_mode == -2) {
        args->result = 0;
        close(fd);
        return NULL;
    }
    memset(&info, 0, sizeof(info));
    if (ioctl(fd, PANGO_MAC_IOC_GET_INFO, &info) != 0 ||
        info.abi_version != PANGO_MAC_ABI_VERSION ||
        info.device_id != PANGO_MAC_ID || info.device_version != PANGO_MAC_VERSION ||
        info.scratch_bytes < OUTPUT_OFFSET + 16u * sizeof(uint32_t)) {
        fprintf(stderr, "scheduler-test: invalid device info\n");
        close(fd);
        return NULL;
    }
    if (diag_mode == -3) {
        args->result = 0;
        close(fd);
        return NULL;
    }
    shadow = mmap(NULL, info.scratch_bytes, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (shadow == MAP_FAILED) {
        fprintf(stderr, "scheduler-test: mmap failed: %s\n", strerror(errno));
        close(fd);
        return NULL;
    }
    if (diag_mode == -4) {
        args->result = 0;
        munmap(shadow, info.scratch_bytes);
        close(fd);
        return NULL;
    }

    input = (uint16_t*)(void*)(shadow + INPUT_OFFSET);
    weights = (uint16_t*)(void*)(shadow + WEIGHT_OFFSET);
    output = (uint32_t*)(void*)(shadow + OUTPUT_OFFSET);
    for (lane = 0; lane < 64u; ++lane)
        weights[lane] = 1u;

    memset(&job, 0, sizeof(job));
    job.abi_version = PANGO_MAC_ABI_VERSION;
    job.pixels = 1;
    job.cin = 4;
    job.cout = 16;
    job.compute_mode = 0; /* S16 x S16 */
    job.output_format = 3; /* I32 */
    job.zero_bias = 1;
    job.input_offset = INPUT_OFFSET;
    job.weight_offset = WEIGHT_OFFSET;
    job.bias_offset = BIAS_OFFSET;
    job.output_offset = OUTPUT_OFFSET;
    job.timeout_us = 100000u;

    for (loop = 0; loop < test_loops; ++loop) {
        for (lane = 0; lane < 4u; ++lane)
            input[lane] = (uint16_t)args->value;
        for (lane = 0; lane < 16u; ++lane)
            output[lane] = 0xdeadbeefu;
        if (ioctl(fd, PANGO_MAC_IOC_RUN, &job) != 0) {
            fprintf(stderr,
                    "scheduler-test: RUN failed value=%u loop=%u errno=%d status=%08x error=%u\n",
                    args->value, loop, errno, job.status, job.error_code);
            goto out;
        }
        for (lane = 0; lane < 16u; ++lane) {
            if (output[lane] != 4u * args->value) {
                fprintf(stderr,
                        "scheduler-test: mismatch value=%u loop=%u lane=%u got=%u expected=%u\n",
                        args->value, loop, lane, output[lane], 4u * args->value);
                goto out;
            }
        }
    }
    args->result = 0;

out:
    munmap(shadow, info.scratch_bytes);
    close(fd);
    return NULL;
}

static int run_thread_group(unsigned process_index) {
    pthread_t threads[TEST_THREADS];
    struct worker_args args[TEST_THREADS];
    unsigned index;
    int failed = 0;

    for (index = 0; index < test_threads; ++index) {
        args[index].value = 1u + process_index * test_threads + index;
        args[index].result = 1;
        if (pthread_create(&threads[index], NULL, run_worker, &args[index]) != 0) {
            fprintf(stderr, "scheduler-test: pthread_create failed\n");
            return 1;
        }
    }
    for (index = 0; index < test_threads; ++index) {
        if (pthread_join(threads[index], NULL) != 0 || args[index].result != 0)
            failed = 1;
    }
    return failed;
}

int main(int argc, char **argv) {
    pid_t children[TEST_PROCESSES - 1u];
    unsigned index;
    int failed = 0;

    if (argc == 2 && (strcmp(argv[1], "-5") == 0 ||
                      strcmp(argv[1], "-6") == 0 ||
                      strcmp(argv[1], "-7") == 0)) {
        const char *path = strcmp(argv[1], "-7") == 0 ?
            "/dev/null" : "/dev/pango-mac0";
        int flags = O_RDWR | (strcmp(argv[1], "-6") == 0 ? 0 : O_CLOEXEC);
        int fd = open(path, flags);

        if (fd < 0 || close(fd) != 0) {
            fprintf(stderr, "scheduler-test: main-thread open/close failed\n");
            return 1;
        }
        puts("PANGO_MAC_SCHEDULER_TEST_PASS processes=1 threads_per_process=0 jobs=0");
        return 0;
    }

    if (argc > 2) {
        fprintf(stderr, "usage: %s [loops-per-thread]\n", argv[0]);
        return 2;
    }
    if (argc == 2 && argv[1][0] == '-') {
        char *end;
        long parsed = strtol(argv[1], &end, 10);

        if (!*end && parsed <= -11 && parsed >= -32 &&
            (-parsed / 10) >= 1 && (-parsed / 10) <= (long)TEST_PROCESSES &&
            (-parsed % 10) >= 1 && (-parsed % 10) <= (long)TEST_THREADS) {
            test_processes = (unsigned)(-parsed / 10);
            test_threads = (unsigned)(-parsed % 10);
            diag_mode = -2;
            test_loops = 0;
        } else if (!*end && parsed >= -4 && parsed <= -1) {
            diag_mode = (int)parsed;
            test_loops = 0;
        } else {
            fprintf(stderr, "scheduler-test: invalid diagnostic mode\n");
            return 2;
        }
    } else if (argc == 2) {
        char *end;
        unsigned long parsed = strtoul(argv[1], &end, 10);

        if (!argv[1][0] || *end || parsed > TEST_LOOPS) {
            fprintf(stderr, "scheduler-test: loops must be 0..%u or -1..-4\n", TEST_LOOPS);
            return 2;
        }
        test_loops = (unsigned)parsed;
    }

    for (index = 1; index < test_processes; ++index) {
        pid_t pid = fork();
        if (pid < 0) {
            fprintf(stderr, "scheduler-test: fork failed: %s\n", strerror(errno));
            return 1;
        }
        if (pid == 0)
            _exit(run_thread_group(index));
        children[index - 1u] = pid;
    }

    failed |= run_thread_group(0);
    for (index = 0; index < test_processes - 1u; ++index) {
        int status = 0;
        if (waitpid(children[index], &status, 0) < 0 || !WIFEXITED(status) ||
            WEXITSTATUS(status) != 0)
            failed = 1;
    }
    if (failed) {
        puts("PANGO_MAC_SCHEDULER_TEST_FAIL");
        return 1;
    }
    printf("PANGO_MAC_SCHEDULER_TEST_PASS processes=%u threads_per_process=%u jobs=%u\n",
           test_processes, test_threads,
           test_processes * test_threads * test_loops);
    return 0;
}
