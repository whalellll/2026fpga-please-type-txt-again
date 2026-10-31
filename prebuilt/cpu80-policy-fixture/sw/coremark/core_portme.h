#ifndef CORE_PORTME_H
#define CORE_PORTME_H

#include <stddef.h>
#include <stdint.h>

/* Let CoreMark calibrate the timed run against the SYS-domain CLINT timer. */
#ifndef ITERATIONS
#define ITERATIONS 0
#endif

#ifndef VALIDATION_RUN
#define VALIDATION_RUN  0
#endif
#ifndef PERFORMANCE_RUN
#define PERFORMANCE_RUN (!VALIDATION_RUN)
#endif
#define PROFILE_RUN     0

#define HAS_FLOAT   1
#define HAS_TIME_H  0
#define USE_CLOCK   0
#define HAS_STDIO   0
#define HAS_PRINTF  1

#define SEED_METHOD SEED_VOLATILE
#define MEM_METHOD  MEM_STATIC
#define MEM_LOCATION "boot BRAM (static)"
#define MULTITHREAD 1
#define default_num_contexts MULTITHREAD
#define USE_PTHREAD 0
#define USE_FORK    0
#define USE_SOCKET  0

#define MAIN_HAS_NOARGC 1
#define MAIN_HAS_NORETURN 0

#define COMPILER_VERSION "riscv32-unknown-elf-gcc " __VERSION__
#ifndef COMPILER_FLAGS
#define COMPILER_FLAGS "-O2 -march=rv32ima_zicsr_zifencei -mabi=ilp32"
#endif
#define CORE_CLOCKS_PER_SEC 49500000ULL

typedef uint8_t   ee_u8;
typedef uint16_t  ee_u16;
typedef uint32_t  ee_u32;
typedef int16_t   ee_s16;
typedef int32_t   ee_s32;
typedef uintptr_t ee_ptr_int;
typedef size_t    ee_size_t;
typedef uint64_t  CORE_TICKS;

typedef struct core_portable_s {
    ee_u8 portable_id;
} core_portable;

#define align_mem(x) \
    (void *)(((ee_ptr_int)(x) + sizeof(ee_u32) - 1) & \
             ~((ee_ptr_int)sizeof(ee_u32) - 1))

int printf(const char *format, ...);
void portable_init(core_portable *p, int *argc, char *argv[]);
void portable_fini(core_portable *p);

#endif
