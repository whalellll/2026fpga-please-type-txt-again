/* Control-flow fixture only. Simulated time/CRC never supplies a score. */
#define _POSIX_C_SOURCE 200809L
#include "coremark.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
extern volatile ee_s32 seed1_volatile,seed4_volatile;
static uint64_t fake_ns=1000000000;
static unsigned validation_calls;
static unsigned measurement_calls;
int clock_gettime(clockid_t clock,struct timespec *out)
{
    (void)clock;
    out->tv_sec=(time_t)(fake_ns/1000000000);
    out->tv_nsec=(long)(fake_ns%1000000000);
    return 0;
}
int xy_cm_upstream_main(void)
{
    const char *scenario=getenv("XY_CALIBRATION_FIXTURE");
    unsigned n=(unsigned)seed4_volatile;
    int validation=seed1_volatile!=0;
    uint64_t per_iteration=50000000;
    int bad=scenario && !strcmp(scenario,"crc-fail");
    if(validation){
        ++validation_calls;
        /* Different seed cost plus warmup: the old second run is only 6s. */
        per_iteration=validation_calls==1?10000000:5000000;
    }
    if(scenario && !strcmp(scenario,"stable"))per_iteration=10000000;
    if(scenario && !strcmp(scenario,"retry-exhaustion") && validation && n>=100){
        ++measurement_calls;
        per_iteration=measurement_calls==1?1000000:measurement_calls==2?100000:1000;
    }
    if(scenario && !strcmp(scenario,"measurement-crc-fail") && validation && n>=100)
        bad=1;
    start_time();
    if(!scenario || strcmp(scenario,"stalled-clock"))fake_ns+=(uint64_t)n*per_iteration;
    stop_time();
    printf("XY_FAKE_SEGMENT simulated_only=1 validation=%d iterations=%u ticks=%llu\n",
           validation,n,(unsigned long long)get_time());
    xy_cm_printf("seedcrc : 0x%x\n",validation?0x18f2:0xe9f5);
    xy_cm_printf("[0]crclist : 0x%x\n",bad?0xffff:validation?0xe3c1:0xe714);
    xy_cm_printf("[0]crcmatrix : 0x%x\n",validation?0x0747:0x1fd7);
    xy_cm_printf("[0]crcstate : 0x%x\n",validation?0x8d84:0x8e3a);
    xy_cm_printf("Iterations : %u\n",n);
    if(get_time()>=10000000000ULL && !bad)
        xy_cm_printf("Correct operation validated.\n");
    else xy_cm_printf("ERROR! simulated invalid measurement\n");
    return 0;
}
