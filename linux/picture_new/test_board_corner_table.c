/* Synthetic-only board softargmax comparison; no model or camera is loaded. */
#define _POSIX_C_SOURCE 200809L
#include GRAPH_RUNTIME_SOURCE
#include FROZEN_CORNER_REFERENCE
#include <assert.h>
#include <float.h>
#include <stdint.h>
#include <time.h>

static float priors[8],maps[4*2304];
static unsigned compared,failed_guards,malloc_calls,monitor_malloc=1;
static int reject_malloc;
void *__real_malloc(size_t);
void *__wrap_malloc(size_t bytes)
{if(monitor_malloc)++malloc_calls;return reject_malloc?NULL:__real_malloc(bytes);}
static float from_bits(uint32_t bits)
{float value;memcpy(&value,&bits,sizeof(value));return value;}
static uint32_t random_word(uint32_t *state)
{*state=*state*1664525u+1013904223u;return *state;}
static void same(const xqn_model *model)
{
    float expected[8],actual[8];
    memset(expected,0xa5,sizeof(expected));memset(actual,0xa5,sizeof(actual));
    int reference=xqg_corner_frozen_reference(model,expected);
    int result=xqn_board_corners(model,actual);
    assert(result==reference);
    /* Also compares any untouched or partly written output prefix. */
    assert(!memcmp(expected,actual,sizeof(actual)));++compared;
}
static void fixture(unsigned mode)
{
    uint32_t state=mode+12345u;
    for(unsigned i=0;i<8;i++)priors[i]=.5f;
    for(unsigned i=0;i<4*2304;i++)maps[i]=0;
    if(mode==0)return; /* All maximum locations tie. */
    if(mode==1) {
        for(unsigned c=0;c<4;c++)maps[c*2304+c*47]=24.f;
        return;
    }
    if(mode==2) {
        for(unsigned i=0;i<8;i++)priors[i]=(i&1)?1.f:0.f;
        for(unsigned c=0;c<4;c++){maps[c*2304]=16.f;maps[c*2304+2303]=16.f;}
        return;
    }
    if(mode>=3 && mode<=12) {
        const uint32_t special[]={0x00000000u,0x80000000u,0x00000001u,0x807fffffu,
            0x7f7fffffu,0xff7fffffu,0x7f800000u,0xff800000u,0x7fc12345u,0x7f800001u};
        for(unsigned i=0;i<8;i++)priors[i]=from_bits(special[mode-3]);
        for(unsigned i=0;i<4*2304;i++)maps[i]=(i%239)?(float)((int)(i%29)-14):from_bits(special[mode-3]);
        return;
    }
    if(mode==13) {
        for(unsigned i=0;i<4*2304;i++)maps[i]=FLT_MAX;
        return;
    }
    if(mode==14) {
        for(unsigned i=0;i<4*2304;i++)maps[i]=-FLT_MAX;
        return;
    }
    if(mode==15) {
        maps[17]=from_bits(0x7fc00011u);maps[91]=from_bits(0xffc00022u);
        return;
    }
    if(mode==16) {
        for(unsigned i=0;i<8;i++)priors[i]=from_bits(0x7fc00011u+i*0x101u);
        return;
    }
    if(mode==17) {
        for(unsigned i=0;i<8;i++)priors[i]=from_bits((i&1?0xff800001u:0x7fc12345u)+i);
        maps[31]=from_bits(0x7fc54321u);return;
    }
    for(unsigned i=0;i<8;i++) {
        if(mode&1)priors[i]=((int)(random_word(&state)%65537u)-32768)*(1.f/8192.f);
        else {uint32_t bits=random_word(&state);if((bits&0x7f800000u)==0x7f800000u)bits^=0x00800000u;priors[i]=from_bits(bits);}
    }
    for(unsigned i=0;i<4*2304;i++) {
        if(mode&1)maps[i]=((int)(random_word(&state)%65537u)-32768)*(1.f/2048.f);
        else {uint32_t bits=random_word(&state);if((bits&0x7f800000u)==0x7f800000u)bits^=0x00800000u;maps[i]=from_bits(bits);}
    }
}
static void guard_checks(xqn_model model)
{
    same(NULL);++failed_guards;
    model.header[1]=1;same(&model);++failed_guards;model.header[1]=0;
    model.batch=0;same(&model);++failed_guards;
    model.batch=2;same(&model);++failed_guards;model.batch=1;
    model.outputs[0]=NULL;same(&model);++failed_guards;model.outputs[0]=priors;
    model.outputs[1]=NULL;same(&model);++failed_guards;model.outputs[1]=maps;
    model.header[3]=1;same(&model);++failed_guards;model.header[3]=2;
    assert(xqn_board_corners(&model,NULL)==xqg_corner_frozen_reference(&model,NULL));++failed_guards;
}
static uint64_t benchmark_clock(void)
{
    struct timespec stamp;assert(!clock_gettime(CLOCK_MONOTONIC,&stamp));
    return (uint64_t)stamp.tv_sec*UINT64_C(1000000000)+(unsigned)stamp.tv_nsec;
}
static int benchmark(void)
{
    xqn_model model={0};model.header[3]=2;model.batch=1;
    model.outputs[0]=priors;model.outputs[1]=maps;
    const float normal_priors[8]={.15f,.23f,.78f,.18f,.77f,.82f,.20f,.79f};
    memcpy(priors,normal_priors,sizeof(priors));
    for(unsigned c=0;c<4;c++)for(unsigned y=0;y<48;y++)for(unsigned x=0;x<48;x++)
        maps[c*2304+y*48+x]=((int)((x*17+y*31+c*13)%29)-14)*.125f;
    float expected[8],actual[8];
    assert(xqg_corner_frozen_reference(&model,expected));
    assert(xqn_board_corners(&model,actual));assert(!memcmp(expected,actual,sizeof(actual)));
    /* Warm both complete paths before the first timing. */
    assert(xqg_corner_frozen_reference(&model,actual));assert(!memcmp(expected,actual,sizeof(actual)));
    assert(xqn_board_corners(&model,actual));assert(!memcmp(expected,actual,sizeof(actual)));
    reject_malloc=0;monitor_malloc=0;
    typedef int (*corner_operation)(const xqn_model *,float [8]);
    for(unsigned repeat=0;repeat<3;repeat++)for(unsigned order=0;order<2;order++) {
        unsigned selected=order^(repeat&1u);
        corner_operation volatile operation=selected?xqn_board_corners:xqg_corner_frozen_reference;
        uint64_t start=benchmark_clock();
        int okay=operation(&model,actual);
        uint64_t end=benchmark_clock();
        assert(okay && end>=start);assert(!memcmp(expected,actual,sizeof(actual)));
        printf("BOARD_CORNER_BENCH path=%s iteration=%u elapsed_ns=%llu\n",selected?"table":"frozen",repeat,(unsigned long long)(end-start));
    }
    puts("BOARD_CORNER_BENCH_BIT_EQUAL_PREWARMED_NO_PROBES_NOT_BOARD");
    return 0;
}
int main(int argc,char **argv)
{
    if(argc==2 && !strcmp(argv[1],"--bench"))return benchmark();
    assert(argc==1);
    xqn_model model={0};model.header[3]=2;model.batch=1;
    model.outputs[0]=priors;model.outputs[1]=maps;
    for(unsigned mode=0;mode<40;mode++){fixture(mode);same(&model);}
    guard_checks(model);
    /* The candidate adds only automatic arrays. It still works when every
     * attempted heap allocation would fail; neither implementation allocates. */
    fixture(19);malloc_calls=0;reject_malloc=1;same(&model);reject_malloc=0;
    assert(malloc_calls==0);
    printf("BOARD_CORNER_COORD_TABLE_FROZEN_BITS_GUARDS_NO_ALLOC_PASS cases=%u guards=%u table_array_bytes=768\n",compared,failed_guards);
    return 0;
}
