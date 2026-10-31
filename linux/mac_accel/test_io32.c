/* A byte-accessing aperture would fail these instrumented word callbacks. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define __iomem
static _Alignas(4) unsigned char aperture[8200];
static unsigned reads, writes;
static u32 readl(const void *p)
{
    u32 value;
    assert((uintptr_t)p%4==0 && (const u8 *)p>=aperture && (const u8 *)p+4<=aperture+sizeof(aperture));
    ++reads; memcpy(&value,p,4); return value;
}
static void writel(u32 value, void *p)
{
    assert((uintptr_t)p%4==0 && (u8 *)p>=aperture && (u8 *)p+4<=aperture+sizeof(aperture));
    ++writes; memcpy(p,&value,4);
}
#include "kernel/pango_mac_io32.h"
int main(void)
{
    unsigned sizes[]={0,1,2,3,4,5,7,16,4095,4096,4097,8192};
    unsigned char input[8200],result[8200];
    unsigned i,n,j;
    for(i=0;i<sizeof(input);i++)input[i]=(u8)(i*71u+3u);
    for(n=0;n<sizeof(sizes)/sizeof(sizes[0]);n++) {
        unsigned bytes=sizes[n];
        memset(aperture,0xa5,sizeof(aperture)); memset(result,0x5a,sizeof(result));
        reads=writes=0;
        pango_mac_toio32(aperture+4,input+1,bytes);
        assert(writes==(bytes+3)/4 && reads==(bytes%4!=0));
        assert(!memcmp(aperture+4,input+1,bytes));
        for(j=0;j<4;j++)assert(aperture[j]==0xa5);
        for(j=bytes+4;j<sizeof(aperture);j++)assert(aperture[j]==0xa5);
        reads=writes=0;
        pango_mac_fromio32(result+1,aperture+4,bytes);
        assert(reads==(bytes+3)/4 && writes==0 && result[0]==0x5a && result[bytes+1]==0x5a);
        assert(!memcmp(result+1,input+1,bytes));
    }
    puts("PANGO_MAC_IO32_TEST_PASS sizes=12 aligned_transactions_and_tail_guards=pass");
    return 0;
}
