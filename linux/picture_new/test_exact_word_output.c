#define _POSIX_C_SOURCE 200809L
#ifndef EXACT_WORD_OUTPUT_HEADER
#define EXACT_WORD_OUTPUT_HEADER "exact_word_output.h"
#endif
#include EXACT_WORD_OUTPUT_HEADER
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static void reference(int16_t *out,const uint8_t *in,unsigned channels,unsigned h,unsigned w)
{
    for(unsigned c=0;c<channels;c++)for(size_t p=0;p<(size_t)h*w;p++)
        memcpy(out+(size_t)c*h*w+p,in+2*(p*channels+c),2);
}
/* Original compact output loop, excluding rectangle offsets and dispatch.
 * The real exact caller remains covered by the frozen full-graph tests. */
static void original(int16_t *out,const uint8_t *in,unsigned channels,unsigned h,unsigned w)
{
    for(unsigned y=0;y<h;y++)for(unsigned xb=0;xb<w;xb+=8)for(unsigned cb=0;cb<channels;cb+=8)
        for(unsigned c=cb;c<channels && c<cb+8;c++)for(unsigned x=xb;x<w && x<xb+8;x++){
            int16_t value;memcpy(&value,in+2*((y*w+x)*channels+c),2);
            out[(size_t)c*h*w+y*w+x]=value;
        }
}
static uint64_t cpu_ns(void)
{
    struct timespec t;assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t));
    return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;
}
static void untouched(const uint8_t *p,size_t bytes)
{
    for(size_t i=0;i<bytes;i++)assert(p[i]==0xa5);
}
int main(int argc,char **argv)
{
    const unsigned shapes[][3]={{2,1,2},{4,2,2},{14,1,6},{16,96,96},{32,48,48},
        {64,24,24},{128,12,12},{256,6,6},{16,32,32},{32,16,16},{64,8,8},
        {128,4,4},{256,2,2},{254,2,9},{4,128,128},{8,2,3},{6,3,4}};
    unsigned tests=0;
    for(unsigned k=0;k<sizeof(shapes)/sizeof(shapes[0]);k++){
        unsigned c=shapes[k][0],h=shapes[k][1],w=shapes[k][2];size_t n=(size_t)c*h*w,bytes=2*n;
        uint8_t *src=malloc(bytes+64),*dst=malloc(bytes+64),*saved=malloc(bytes+64);
        int16_t *want=malloc(bytes);assert(src&&dst&&saved&&want);
        for(size_t i=0;i<(bytes+64)/2;i++){
            uint16_t value=(uint16_t)(i*40503u+20013u);memcpy(src+2*i,&value,2);
        }
        memcpy(saved,src,bytes+64);reference(want,src,c,h,w);memset(dst,0xa5,bytes+64);
        assert(xqewo_unpack((void *)(dst+16),src,c,h,w));assert(!memcmp(dst+16,want,bytes));
        untouched(dst,16);untouched(dst+16+bytes,48);tests++;
        original((void *)(dst+16),src,c,h,w);assert(!memcmp(dst+16,want,bytes));
        /* Also cover aligned addresses at a different word offset. */
        reference(want,src+4,c,h,w);memset(dst,0xa5,bytes+64);
        assert(xqewo_unpack((void *)(dst+20),src+4,c,h,w));assert(!memcmp(dst+20,want,bytes));
        untouched(dst,20);untouched(dst+20+bytes,44);tests++;
        for(unsigned off=1;off<4;off++){
            memset(dst,0xa5,bytes+64);assert(!xqewo_unpack((void *)(dst+16+off),src,c,h,w));
            untouched(dst,bytes+64);assert(!xqewo_unpack((void *)(dst+16),src+off,c,h,w));
            untouched(dst,bytes+64);tests+=2;
        }
        reference(want,src,c,h,w);
        if(argc==2 && !strcmp(argv[1],"--bench") && k>=3 && k<=12){
            original((void *)(dst+16),src,c,h,w);assert(xqewo_unpack((void *)(dst+16),src,c,h,w));
            for(unsigned pair=0;pair<4;pair++)for(unsigned turn=0;turn<2;turn++){
                unsigned word=(turn+(pair&1u))&1u;uint64_t start=cpu_ns();
                for(unsigned repeat=0;repeat<64;repeat++){
                    if(word)(void)xqewo_unpack((void *)(dst+16),src,c,h,w);
                    else original((void *)(dst+16),src,c,h,w);
                    __asm__ volatile("" : : "r"(dst) : "memory");
                }
                uint64_t elapsed=cpu_ns()-start;
                assert(!memcmp(dst+16,want,bytes));untouched(dst,16);untouched(dst+16+bytes,48);
                printf("OUTPUT_WORD_PAIR shape=%u pair=%u word=%u cpu_ns=%llu\n",k,pair,word,(unsigned long long)elapsed);
            }
        }
        assert(!memcmp(src,saved,bytes+64));free(src);free(dst);free(saved);free(want);
    }
    _Alignas(4) uint8_t storage[256];memset(storage,0xa5,sizeof(storage));
    const unsigned bad[][3]={{0,2,2},{1,2,2},{3,2,2},{257,2,2},{2,0,2},{2,2,0},
        {2,641,2},{2,2,641},{2,1,1},{4,1,3}};
    for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++){
        assert(!xqewo_unpack((void *)(storage+128),storage,bad[i][0],bad[i][1],bad[i][2]));
        untouched(storage,sizeof(storage));tests++;
    }
    assert(!xqewo_unpack(NULL,storage,2,2,2));tests++;
    assert(!xqewo_unpack((void *)storage,NULL,2,2,2));tests++;
    assert(!xqewo_unpack((void *)storage,storage,2,2,2));tests++;
    assert(!xqewo_unpack((void *)(storage+4),storage,2,2,2));tests++;
    assert(!xqewo_unpack((void *)storage,storage+4,2,2,2));tests++;
    /* Adjacent non-overlapping regions must remain eligible. */
    assert(xqewo_unpack((void *)(storage+16),storage,2,2,2));tests++;
    untouched(storage,sizeof(storage));
    printf("EXACT_WORD_OUTPUT_BYTES_GUARDS_PASS cases=%u no_allocation_in_unpack=1\n",tests);
    return 0;
}
