#define _POSIX_C_SOURCE 200809L
#include "coremark.h"
#include <errno.h>
#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* EEMBC algorithm files and their main are compiled byte-for-byte from
 * sw/coremark; only this POSIX timer/stdio/seed port is new. */
volatile ee_s32 seed1_volatile,seed2_volatile,seed3_volatile=0x66;
volatile ee_s32 seed4_volatile,seed5_volatile;
static CORE_TICKS started,stopped;
static uint64_t cpu_started,cpu_stopped;
static int quiet,clock_failed;
static struct {
    unsigned seed,list,matrix,state,final,iterations;
    int validated,errors;
    uint64_t ticks;
} report;
int xy_cm_upstream_main(void);
static uint64_t monotonic_ns(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC_RAW,&t)) {clock_failed=1;return 0;}
    return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;
}
static uint64_t process_ns(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t))return 0;
    return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;
}
void start_time(void) {started=monotonic_ns();cpu_started=process_ns();}
void stop_time(void) {cpu_stopped=process_ns();stopped=monotonic_ns();}
CORE_TICKS get_time(void) {return stopped>=started?stopped-started:0;}
secs_ret time_in_secs(CORE_TICKS ticks) {return (double)ticks/1000000000.0;}
void portable_init(core_portable *p,int *argc,char *argv[])
{(void)argc;(void)argv;p->portable_id=1;}
void portable_fini(core_portable *p) {p->portable_id=0;}
void *portable_malloc(ee_size_t bytes) {return malloc(bytes);}
void portable_free(void *p) {free(p);}
int xy_cm_printf(const char *format,...)
{
    char adjusted[256],text[1024];
    size_t i=0,j=0;
    int n;
    va_list args;
    /* This upstream version prints ee_u32 using %lu. ee_u32 is uint32_t on
     * both RV32 and x86_64; use its actual promoted type on the POSIX port. */
    while(format[i] && j+2<sizeof(adjusted)) {
        if(format[i]=='%' && format[i+1]=='l' &&
           (format[i+2]=='u' || format[i+2]=='d')) {
            adjusted[j++]='%';adjusted[j++]=format[i+2];i+=3;
        } else adjusted[j++]=format[i++];
    }
    adjusted[j]=0;
    va_start(args,format);n=vsnprintf(text,sizeof(text),adjusted,args);va_end(args);
    if(n<0 || (size_t)n>=sizeof(text)) {report.errors=1;return -1;}
    /* Upstream casts CORE_TICKS to ee_u32 for this informational line. Linux
     * uses 64-bit nanoseconds: print the same full count used for scoring. */
    if(!strncmp(text,"Total ticks",11))
        (void)snprintf(text,sizeof(text),"Total ticks      : %" PRIu64 "\n",get_time());
    if(strstr(text,"ERROR") || strstr(text,"Errors detected") ||
       strstr(text,"Cannot validate"))report.errors=1;
    if(strstr(text,"Correct operation validated."))report.validated=1;
    (void)sscanf(text,"seedcrc : 0x%x",&report.seed);
    (void)sscanf(text,"[0]crclist : 0x%x",&report.list);
    (void)sscanf(text,"[0]crcmatrix : 0x%x",&report.matrix);
    (void)sscanf(text,"[0]crcstate : 0x%x",&report.state);
    (void)sscanf(text,"[0]crcfinal : 0x%x",&report.final);
    (void)sscanf(text,"Iterations : %u",&report.iterations);
    if(!quiet)fputs(text,stdout);
    return n;
}
static int run_segment(unsigned iterations,int validation,int silent)
{
    memset(&report,0,sizeof(report));clock_failed=0;quiet=silent;
    seed1_volatile=seed2_volatile=validation?0x3415:0;
    seed3_volatile=0x66;seed4_volatile=(ee_s32)iterations;seed5_volatile=0;
    (void)xy_cm_upstream_main();
    report.ticks=get_time();
    return !clock_failed && report.iterations==iterations &&
        report.seed==(validation?0x18f2u:0xe9f5u) &&
        report.list==(validation?0xe3c1u:0xe714u) &&
        report.matrix==(validation?0x0747u:0x1fd7u) &&
        report.state==(validation?0x8d84u:0x8e3au);
}
static unsigned scaled_iterations(unsigned n,uint64_t ticks,unsigned target_ms)
{
    long double calculated;
    unsigned result;
    if(!ticks)return 0;
    calculated=(long double)n*(long double)target_ms*1000000.0L/(long double)ticks;
    if(calculated<1 || calculated>2147483647.0L)return 0;
    result=(unsigned)calculated;
    if((long double)result<calculated)++result;
    return result;
}
static unsigned calibrate(int validation,unsigned target_ms)
{
    unsigned n=1,i;
    for(i=0;i<31;++i) {
        if(!run_segment(n,validation,1))return 0;
        printf("XY_CM_CALIBRATION phase=%s iterations=%u ticks=%" PRIu64 " crc_ok=1\n",
               validation?"validation":"performance",n,report.ticks);
        if(report.ticks>=200000000)return scaled_iterations(n,report.ticks,target_ms);
        if(n>1073741823u)return 0;
        n*=2;
    }
    return 0;
}
static int measure(unsigned *iterations,int validation,uint64_t *ticks)
{
    unsigned attempt;
    for(attempt=0;attempt<3;++attempt) {
        int correct=run_segment(*iterations,validation,0);
        *ticks=report.ticks;
        printf("XY_CM_CLOCK phase=%s raw_ns=%" PRIu64 " process_cpu_ns=%" PRIu64 "\n",
            validation?"validation":"performance",report.ticks,
            cpu_stopped>=cpu_started?cpu_stopped-cpu_started:0);
        if(!correct)return 0;
        if(report.validated && !report.errors && *ticks>=10000000000ULL)return 1;
        if(!*ticks || *ticks>=10000000000ULL || attempt==2)return 0;
        unsigned next=scaled_iterations(*iterations,*ticks,12000);
        if(!next || next<=*iterations)return 0;
        *iterations=next;
    }
    return 0;
}
int main(int argc,char **argv)
{
    unsigned target=45000,perf_n,valid_n,cpu_hz=0,i;
    uint64_t perf_ticks=0,valid_ticks=0;
    int perf_ok=0,valid_ok=0;
    const char *identity="unbound",*kind="host";
#if defined(__riscv) && __riscv_xlen==32
    kind="riscv32-linux";
#endif
    for(i=1;i<(unsigned)argc;++i) {
        if(!strcmp(argv[i],"--target-ms") && i+1<(unsigned)argc)target=(unsigned)strtoul(argv[++i],NULL,10);
        else if(!strcmp(argv[i],"--cpu-hz") && i+1<(unsigned)argc)cpu_hz=(unsigned)strtoul(argv[++i],NULL,10);
        else if(!strcmp(argv[i],"--identity") && i+1<(unsigned)argc)identity=argv[++i];
        else return 2;
    }
    if(target<30000 || target>60000 || strlen(identity)>80 ||
       strspn(identity,"0123456789abcdefABCDEF-_.")!=strlen(identity)) {
        if(strcmp(identity,"unbound"))return 2;
        if(target<30000 || target>60000)return 2;
    }
    setvbuf(stdout,NULL,_IOLBF,0);
    printf("XY_CM_BEGIN kind=%s target_ms=%u cpu_hz=%u identity=%s\n",kind,target,cpu_hz,identity);
    /* Each seed has its own cost and warmup. Real iterate() samples, bounded
     * doublings/retries and unchanged >=10s/CRC acceptance for both segments. */
    perf_n=calibrate(0,target-13000);
    if(!perf_n)return 3;
    printf("XY_CM_PHASE phase=performance iterations=%u\n",perf_n);
    perf_ok=measure(&perf_n,0,&perf_ticks);
    valid_n=calibrate(1,11000);
    if(!valid_n)return 3;
    printf("XY_CM_PHASE phase=validation iterations=%u\n",valid_n);
    valid_ok=measure(&valid_n,1,&valid_ticks);
    printf("XY_CM_RESULT kind=%s valid=%d perf_iterations=%u perf_ticks=%" PRIu64
        " validation_iterations=%u validation_ticks=%" PRIu64
        " timer_hz=1000000000 cpu_hz=%u identity=%s\n",kind,perf_ok&&valid_ok,
        perf_n,perf_ticks,valid_n,valid_ticks,cpu_hz,identity);
    return perf_ok&&valid_ok?0:1;
}
