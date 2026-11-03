#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include "accelerator_idle.h"
#include "pango_mac_uapi.h"
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

int xy_accelerator_words_idle(const volatile uint32_t *r)
{
    if(!r || r[0]!=PANGO_MAC_PIKAFISH_ID || r[1]!=PANGO_MAC_PIKAFISH_VERSION ||
       r[0x40/4]!=PANGO_VISION32_ID || r[0x100/4]!=PANGO_MAC_STAGEA_ID ||
       r[0x104/4]!=PANGO_MAC_STAGEA_VERSION || r[0x180/4]!=PANGO_MAC_NNUE_ID ||
       r[0x184/4]!=0x00020000u || r[0x1c0/4]!=1u ||
       r[PANGO_MAC_BATCH_BASE/4]!=PANGO_MAC_BATCH_ID ||
       (r[(PANGO_MAC_BATCH_BASE+4)/4]!=0x00010000u &&
        r[(PANGO_MAC_BATCH_BASE+4)/4]!=0x00010001u))return 0;
#ifdef __riscv
    __asm__ volatile("fence iorw,iorw":::"memory");
#else
    __sync_synchronize();
#endif
    return !((r[0x0c/4]|r[0x44/4]|r[0x10c/4]|r[0x18c/4]|
              r[(PANGO_MAC_BATCH_BASE+0x0c)/4])&1u);
}
int xy_accelerator_open(xy_accelerator *a)
{
    if(!a)return 0;
    a->fd=-1;a->regs=0;
    a->fd=open("/dev/mem",O_RDONLY|O_SYNC|O_CLOEXEC);
    if(a->fd<0)return 0;
    void *p=mmap(0,4096,PROT_READ,MAP_SHARED,a->fd,0x1fe10000);
    if(p==MAP_FAILED){xy_accelerator_close(a);return 0;}
    a->regs=p;
    if(!xy_accelerator_idle(a)){xy_accelerator_close(a);return 0;}
    return 1;
}
int xy_accelerator_idle(const xy_accelerator *a)
{return a && xy_accelerator_words_idle(a->regs);}
void xy_accelerator_close(xy_accelerator *a)
{
    if(!a)return;
    if(a->regs)munmap((void *)a->regs,4096);
    if(a->fd>=0)close(a->fd);
    a->regs=0;a->fd=-1;
}
