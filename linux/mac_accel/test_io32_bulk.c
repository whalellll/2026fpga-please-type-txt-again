/* Model posted word writes and DMA publication at the copy boundaries. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define __iomem
#define PANGO_MAC_IO32_BULK 1
static _Alignas(4) u8 aperture[8200],dma[8200];
static struct {void *address;u32 word;} posted[2050];
static unsigned queued,phase,reads,writes,dma_pending;
static void boundary(void)
{
    if(!phase) {
#ifdef PANGO_TEST_OMIT_BEGIN
        return;
#endif
        if(dma_pending){memcpy(aperture,dma,sizeof(aperture));dma_pending=0;}
        phase=1;
    } else {
        assert(phase==1);
#ifdef PANGO_TEST_OMIT_END
        return;
#endif
        for(unsigned i=0;i<queued;i++)memcpy(posted[i].address,&posted[i].word,4);
        queued=0;phase=2;
    }
}
#define mb() boundary()
static u32 readl_relaxed(const void *p)
{
    u32 word;assert(phase==1 && !((uintptr_t)p&3));
    assert((const u8 *)p>=aperture && (const u8 *)p+4<=aperture+sizeof(aperture));
    ++reads;memcpy(&word,p,4);return word;
}
static void writel_relaxed(u32 word,void *p)
{
    assert(phase==1 && !((uintptr_t)p&3) && queued<2050);
    assert((u8 *)p>=aperture && (u8 *)p+4<=aperture+sizeof(aperture));
    posted[queued].address=p;posted[queued++].word=word;++writes;
}
#include "kernel/pango_mac_io32.h"
int main(void)
{
    const unsigned sizes[]={0,1,2,3,4,5,7,16,4095,4096,4097,8192};
    _Alignas(4) u8 input[8200],result[8200];unsigned cases=0;
    for(unsigned i=0;i<sizeof(input);i++)input[i]=(u8)(i*71+3);
    for(unsigned k=0;k<sizeof(sizes)/sizeof(sizes[0]);k++)for(unsigned a=0;a<4;a++)for(unsigned b=0;b<4;b++) {
        unsigned bytes=sizes[k];phase=queued=reads=writes=dma_pending=0;
        memset(aperture,0xa5,sizeof(aperture));
        pango_mac_toio32(aperture+4,input+a,bytes);
        assert(phase==(bytes?2u:0u) && !queued);
        assert(writes==(bytes+3)/4 && reads==(bytes%4!=0));
        assert(!memcmp(aperture+4,input+a,bytes));
        for(unsigned i=0;i<4;i++)assert(aperture[i]==0xa5);
        for(unsigned i=4+bytes;i<sizeof(aperture);i++)assert(aperture[i]==0xa5);
        phase=queued=reads=writes=0;
        memset(aperture,0xcc,sizeof(aperture));memset(dma,0xa5,sizeof(dma));
        memcpy(dma+4,input+a,bytes);dma_pending=bytes!=0;memset(result,0x5a,sizeof(result));
        pango_mac_fromio32(result+b,aperture+4,bytes);
        assert(phase==(bytes?2u:0u) && !queued && !dma_pending);
        assert(reads==(bytes+3)/4 && !writes && !memcmp(result+b,input+a,bytes));
        for(unsigned i=0;i<b;i++)assert(result[i]==0x5a);
        for(unsigned i=b+bytes;i<sizeof(result);i++)assert(result[i]==0x5a);
        ++cases;
    }
    printf("PANGO_IO32_BULK_BOUNDARY_TAIL_ALIGNMENT_PASS cases=%u\n",cases);return 0;
}
