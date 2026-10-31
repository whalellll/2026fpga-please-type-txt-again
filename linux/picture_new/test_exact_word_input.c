#define _POSIX_C_SOURCE 200809L
#ifndef EXACT_WORD_INPUT_HEADER
#define EXACT_WORD_INPUT_HEADER "exact_word_input.h"
#endif
#include EXACT_WORD_INPUT_HEADER
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static void reference(uint8_t *out,const int8_t *in,unsigned c,unsigned h,unsigned w)
{
    for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)for(unsigned ch=0;ch<c;ch++)
        out[((size_t)y*w+x)*c+ch]=(uint8_t)in[((size_t)ch*h+y)*w+x];
}
/* Compact no-halo scalar baseline with the driver's 8x8 loop nesting;
 * this subphase baseline excludes halo selection and dispatch overhead. */
static void original(uint8_t *out,const int8_t *input,unsigned cin,unsigned height,unsigned width)
{
    for(unsigned y=0;y<height;y++)for(unsigned xb=0;xb<width;xb+=8)for(unsigned cb=0;cb<cin;cb+=8)
        for(unsigned c=cb;c<cin && c<cb+8;c++)for(unsigned x=xb;x<width && x<xb+8;x++)
            out[((size_t)y*width+x)*cin+c]=(uint8_t)input[((size_t)c*height+y)*width+x];
}
static uint64_t cpu_ns(void){struct timespec t;assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t));return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;}
int main(int argc,char **argv)
{
    const unsigned shapes[][3]={{4,2,2},{8,3,4},{16,32,32},{32,16,16},{48,8,8},{64,4,4},{96,4,4},{144,24,24},{256,1,4},{16,96,96}};
    unsigned tests=0;uint32_t rng=0x19d780a3;
    for(unsigned k=0;k<sizeof(shapes)/sizeof(shapes[0]);k++){
        unsigned c=shapes[k][0],h=shapes[k][1],w=shapes[k][2];size_t n=(size_t)c*h*w;
        int8_t *src=malloc(n+32);uint8_t *dst=malloc(n+32),*want=malloc(n);assert(src&&dst&&want);
        for(size_t i=0;i<n+32;i++){rng=rng*1664525u+1013904223u;src[i]=(int8_t)(rng>>24);}
        reference(want,src,c,h,w);memset(dst,0xa5,n+32);
        assert(xqew_pack(dst+16,src,c,h,w));assert(!memcmp(dst+16,want,n));
        for(unsigned i=0;i<16;i++)assert(dst[i]==0xa5&&dst[n+16+i]==0xa5);
        original(dst+16,src,c,h,w);assert(!memcmp(dst+16,want,n));tests++;
        for(unsigned off=1;off<4;off++){
            memset(dst,0xa5,n+32);assert(!xqew_pack(dst+16+off,src,c,h,w));
            for(size_t i=0;i<n+32;i++)assert(dst[i]==0xa5);
            assert(!xqew_pack(dst+16,src+off,c,h,w));tests+=2;
        }
        if(argc==2 && !strcmp(argv[1],"--bench")){
            /* Warm both, then four alternating pairs. Assertions/IO excluded. */
            original(dst+16,src,c,h,w);assert(xqew_pack(dst+16,src,c,h,w));
            for(unsigned pair=0;pair<4;pair++)for(unsigned turn=0;turn<2;turn++){
                unsigned word=(turn+(pair&1u))&1u;uint64_t start=cpu_ns();
                for(unsigned repeat=0;repeat<64;repeat++){
                    if(word)(void)xqew_pack(dst+16,src,c,h,w);else original(dst+16,src,c,h,w);
                    __asm__ volatile("" : : "r"(dst) : "memory");
                }
                uint64_t elapsed=cpu_ns()-start;assert(!memcmp(dst+16,want,n));
                printf("WORD_PAIR shape=%u pair=%u word=%u cpu_ns=%llu\n",k,pair,word,(unsigned long long)elapsed);
            }
        }
        free(src);free(dst);free(want);
    }
    uint32_t src[16]={0},dst[16];memset(dst,0xa5,sizeof(dst));
    assert(!xqew_pack((void *)dst,(void *)src,3,4,4));
    assert(!xqew_pack((void *)dst,(void *)src,4,1,3));
    assert(!xqew_pack((void *)dst,(void *)src,0,4,4));
    assert(!xqew_pack((void *)dst,(void *)dst,4,4,4));
    assert(!xqew_pack((void *)dst+4,(void *)dst,4,2,4));
    assert(!xqew_pack((void *)dst,(void *)dst+4,4,2,4));
    assert(!xqew_pack((void *)dst,(void *)src,4,641,4));
    for(unsigned i=0;i<16;i++)assert(dst[i]==0xa5a5a5a5u);
    printf("EXACT_WORD_INPUT_BYTES_GUARDS_PASS cases=%u no_allocation_in_pack=1\n",tests+7);return 0;
}
