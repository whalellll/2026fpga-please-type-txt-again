#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../linux/mac_accel/kernel/pango_mac_copy_chunks.h"
static unsigned char source[1048576],destination[1048580];
struct probe { unsigned next,max,transfers,yields; };
static void copy(void *opaque,unsigned offset,unsigned bytes)
{
    struct probe *p=opaque;
    assert(offset==p->next && bytes && bytes<=4096 && offset+bytes<=sizeof(source));
    memcpy(destination+2+offset,source+offset,bytes);
    p->next+=bytes;if(bytes>p->max)p->max=bytes;p->transfers++;
}
static void yield(void *opaque)
{
    struct probe *p=opaque;
    /* Every reschedule point sees a complete prefix and untouched suffix. */
    assert(!memcmp(destination+2,source,p->next));
    assert(destination[2+p->next]==0xa5);
    p->yields++;
}
int main(void)
{
    const unsigned sizes[]={0,1,4095,4096,4097,8191,593920,1048576};
    unsigned i,n;
    for(i=0;i<sizeof(source);i++)source[i]=(unsigned char)(i*37u+19u);
    for(n=0;n<sizeof(sizes)/sizeof(sizes[0]);n++) {
        struct probe p={0};unsigned bytes=sizes[n];
        memset(destination,0xa5,sizeof(destination));
        pango_mac_copy_chunks(&p,bytes,copy,yield);
        assert(p.next==bytes && !memcmp(destination+2,source,bytes));
        assert(destination[0]==0xa5 && destination[1]==0xa5 && destination[2+bytes]==0xa5);
        assert(p.transfers==(bytes+4095u)/4096u);
        assert(p.yields==(p.transfers?p.transfers-1:0));
        if(bytes==593920)printf("MAC_MODEL_COPY_PASS bytes=%u max_chunk=%u transfers=%u schedule_points=%u\n",bytes,p.max,p.transfers,p.yields);
    }
    return 0;
}
