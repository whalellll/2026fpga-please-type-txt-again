#include "accelerator_idle.h"
#include "pango_mac_uapi.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
    uint32_t r[1024]={0},saved[1024];
    r[0]=PANGO_MAC_PIKAFISH_ID;r[1]=PANGO_MAC_PIKAFISH_VERSION;r[0x0c/4]=6;
    r[0x40/4]=PANGO_VISION32_ID;r[0x100/4]=PANGO_MAC_STAGEA_ID;
    r[0x104/4]=PANGO_MAC_STAGEA_VERSION;r[0x180/4]=PANGO_MAC_NNUE_ID;
    r[0x184/4]=0x00020000;r[0x1c0/4]=1;
    r[PANGO_MAC_BATCH_BASE/4]=PANGO_MAC_BATCH_ID;
    const unsigned busy[]={0x0c,0x44,0x10c,0x18c,PANGO_MAC_BATCH_BASE+0x0c};
    const unsigned ids[]={0,4,0x40,0x100,0x104,0x180,0x184,0x1c0,PANGO_MAC_BATCH_BASE};
    for(unsigned version=0x00010000u;version<=0x00010001u;version++){
        r[(PANGO_MAC_BATCH_BASE+4)/4]=version;
        memcpy(saved,r,sizeof(r));assert(xy_accelerator_words_idle(r));
        for(unsigned i=0;i<5;i++){
            r[busy[i]/4]|=1;assert(!xy_accelerator_words_idle(r));
            memcpy(r,saved,sizeof(r));
        }
        for(unsigned i=0;i<9;i++){
            r[ids[i]/4]^=1;assert(!xy_accelerator_words_idle(r));
            memcpy(r,saved,sizeof(r));
        }
    }
    const unsigned unknown[]={0,1,0x00010002u,0xffffffffu};
    for(unsigned i=0;i<4;i++){r[(PANGO_MAC_BATCH_BASE+4)/4]=unknown[i];assert(!xy_accelerator_words_idle(r));}
    memcpy(r,saved,sizeof(r));
    assert(!xy_accelerator_words_idle(NULL));
    assert(!memcmp(r,saved,sizeof(r)));
    puts("ACCELERATOR_FIXED_ID_AND_FIVE_BUSY_GATES_PASS_READ_ONLY_NOT_BOARD batch_versions=10000,10001 unknown_rejected=4");return 0;
}
