#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include "pango_mac_uapi.h"

/* Bounded mapping-only diagnostic: never submits an accelerator job. */
#define CONTEXTS 4
static int fds[CONTEXTS];
static volatile uint32_t *maps[CONTEXTS];
static size_t bytes;
static unsigned mismatches;

static void check(unsigned live, const char *phase)
{
    unsigned i;
    for (i=0;i<live;i++) {
        uint32_t first=maps[i][0], last=maps[i][bytes/4-1];
        uint32_t expected_first=0x12345600u+i, expected_last=0xabcd0080u+i;
        if (first!=expected_first || last!=expected_last) {
            printf("MAP_MISMATCH phase=%s slot=%u first=%08x/%08x last=%08x/%08x\n",
                   phase,i,first,expected_first,last,expected_last);
            ++mismatches;
        }
    }
}

static int map_slot(unsigned i)
{
    struct pango_mac_info info;
    int pm;
    uint64_t entry=0;
    fds[i]=open("/dev/pango-mac0",O_RDWR|O_CLOEXEC);
    if(fds[i]<0) return -1;
    memset(&info,0,sizeof(info));
    if(ioctl(fds[i],PANGO_MAC_IOC_GET_INFO,&info)) return -1;
    if(!info.scratch_bytes || (bytes && bytes!=info.scratch_bytes)) return -1;
    bytes=info.scratch_bytes;
    maps[i]=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fds[i],0);
    if(maps[i]==MAP_FAILED) return -1;
    printf("MAP_SLOT slot=%u va=%p bytes=%u first=%08x last=%08x\n",
           i,(void *)maps[i],(unsigned)bytes,maps[i][0],maps[i][bytes/4-1]);
    pm=open("/proc/self/pagemap",O_RDONLY|O_CLOEXEC);
    if(pm>=0) {
        off_t offset=(off_t)((uintptr_t)maps[i]/4096)*8;
        if(pread(pm,&entry,sizeof(entry),offset)==sizeof(entry))
            printf("MAP_PAGEMAP slot=%u flags=%08x pfn=%08x\n",i,
                   (unsigned)(entry>>32),(unsigned)(entry&0xffffffffu));
        close(pm);
    }
    return 0;
}

int main(void)
{
    unsigned i;
    int result=1;
    setvbuf(stdout,NULL,_IONBF,0);
    for(i=0;i<CONTEXTS;i++){fds[i]=-1;maps[i]=MAP_FAILED;}
    for(i=0;i<CONTEXTS;i++) {
        if(map_slot(i)){perror("map-slot");goto out;}
        check(i,"after-open");
        maps[i][0]=0x12345600u+i;
        maps[i][bytes/4-1]=0xabcd0080u+i;
        check(i+1,"after-word-store");
        ((volatile uint8_t *)maps[i])[0]=(uint8_t)i;
        ((volatile uint8_t *)maps[i])[bytes-4]=(uint8_t)(0x80u+i);
        check(i+1,"after-byte-store");
    }
    munmap((void *)maps[0],bytes);maps[0]=MAP_FAILED;
    close(fds[0]);fds[0]=-1;
    if(map_slot(0)){perror("remap-slot");goto out;}
    maps[0][0]=0x12345600u;maps[0][bytes/4-1]=0xabcd0080u;
    check(CONTEXTS,"after-slot-reuse");
    printf("MAC_MAPPING_DIAG_%s mismatches=%u contexts=%u no_mac_run=1\n",
           mismatches?"FAIL":"PASS",mismatches,CONTEXTS);
    result=mismatches?1:0;
out:
    for(i=0;i<CONTEXTS;i++) {
        if(maps[i]!=MAP_FAILED)munmap((void *)maps[i],bytes);
        if(fds[i]>=0)close(fds[i]);
    }
    return result;
}
