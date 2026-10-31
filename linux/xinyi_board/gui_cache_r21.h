/* Published CPU60 cache publication. The scratch area is outside scanout,
 * inside the existing 4 MiB GUI0 reservation; no camera/model bytes are used. */
#ifndef XINYI_GUI_CACHE_R21_H
#define XINYI_GUI_CACHE_R21_H
#include <stdint.h>
enum { XY21_SCRATCH_BASE=0x1bbf8000u, XY21_SCRATCH_BYTES=32768u };
static void xy21_cache_publish(void *unused)
{
    (void)unused;
#ifdef __riscv
    /* This source-bound CPU implements FENCE.I as a completed D-cache flush.
     * The encoding keeps the frozen rv32ima toolchain; never use fence alone. */
    __asm__ volatile("fence iorw,iorw\n.word 0x0000100f\nfence iorw,iorw":::"memory");
#else
    __sync_synchronize();
#endif
}
static int xy21_cache_check(volatile uint32_t *uncached,volatile uint32_t *cached,
    uint32_t *backup,void (*publish)(void *),void *context)
{
    const unsigned words=XY21_SCRATCH_BYTES/4u;
    int okay=1;
    publish(context);
    for(unsigned i=0;i<words;i++)backup[i]=uncached[i];
    for(unsigned turn=0;turn<2;turn++){
        for(unsigned i=0;i<words;i++)cached[i]=0x6b12d49fu^(i*0x9e3779b9u)^(turn*0x05030701u);
        publish(context);
        for(unsigned i=0;i<words;i++)
            if(uncached[i]!=(0x6b12d49fu^(i*0x9e3779b9u)^(turn*0x05030701u)))okay=0;
    }
    /* Restore both aliases even on failure. Any delayed dirty eviction then
     * contains the same original scratch data as the uncached fallback. */
    for(unsigned i=0;i<words;i++)cached[i]=backup[i];
    publish(context);
    for(unsigned i=0;i<words;i++)if(uncached[i]!=backup[i])okay=0;
    for(unsigned i=0;i<words;i++)uncached[i]=backup[i];
    return okay;
}
#endif
