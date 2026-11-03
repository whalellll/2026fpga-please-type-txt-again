#ifndef CORE_PORTME_H
#define CORE_PORTME_H
#include <stddef.h>
#include <stdint.h>
#define ITERATIONS 0
#define VALIDATION_RUN 0
#define PERFORMANCE_RUN 1
#define PROFILE_RUN 0
#define HAS_FLOAT 1
#define HAS_TIME_H 1
#define USE_CLOCK 0
#define HAS_STDIO 0
#define HAS_PRINTF 0
#define SEED_METHOD SEED_VOLATILE
#define MEM_METHOD MEM_STATIC
#define MEM_LOCATION "Linux user RAM (static)"
#define MULTITHREAD 1
#define default_num_contexts 1
#define USE_PTHREAD 0
#define USE_FORK 0
#define USE_SOCKET 0
#define MAIN_HAS_NOARGC 1
#define MAIN_HAS_NORETURN 0
#define COMPILER_VERSION "Linux GCC " __VERSION__
#ifndef COMPILER_FLAGS
#if defined(__riscv) && __riscv_xlen==32
#define COMPILER_FLAGS "-O2 -march=rv32ima -mabi=ilp32; single-context POSIX CLOCK_MONOTONIC_RAW"
#else
#define COMPILER_FLAGS "-O2; host functional validation; single-context POSIX CLOCK_MONOTONIC_RAW"
#endif
#endif
#define CORE_CLOCKS_PER_SEC 1000000000ULL
typedef uint8_t ee_u8;
typedef uint16_t ee_u16;
typedef uint32_t ee_u32;
typedef int16_t ee_s16;
typedef int32_t ee_s32;
typedef uintptr_t ee_ptr_int;
typedef size_t ee_size_t;
typedef uint64_t CORE_TICKS;
typedef struct core_portable_s { ee_u8 portable_id; } core_portable;
#define align_mem(x) (void *)(((ee_ptr_int)(x)+sizeof(ee_u32)-1)&~((ee_ptr_int)sizeof(ee_u32)-1))
int xy_cm_printf(const char *, ...);
#define ee_printf xy_cm_printf
void portable_init(core_portable *,int *,char *[]);
void portable_fini(core_portable *);
#endif
