#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include "pango_mac_uapi.h"
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
/* Only immutable PFF1 model words are mapped read-only through /dev/mem.
 * All accelerator registers and scratch ownership stay with the driver. */
int main(void)
{
    static const uint32_t descriptors[]={0,5,0xc0000008u,0x8000b1eau,0x40004097u};
    const size_t pff_bytes=68122688u;
    struct pango_mac_info info;
    struct pango_mac_stagea_job job={0};
    volatile const uint32_t *model=MAP_FAILED;
    uint8_t *shadow=MAP_FAILED;
    uint16_t expected[1024];
    int fd=-1,mem=-1,result=1;
    unsigned lane,term;
    fd=open("/dev/pango-mac0",O_RDWR|O_CLOEXEC);
    if(fd<0 || ioctl(fd,PANGO_MAC_IOC_GET_INFO,&info) ||
       !(info.features&PANGO_MAC_FEATURE_STAGEA_GATHER) || info.scratch_bytes!=0x100000)goto done;
    shadow=mmap(NULL,info.scratch_bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    if(shadow==MAP_FAILED)goto done;
    mem=open("/dev/mem",O_RDONLY|O_SYNC|O_CLOEXEC);
    if(mem<0)goto done;
    model=mmap(NULL,pff_bytes,PROT_READ,MAP_SHARED,mem,(off_t)0x10000000u);
    if(model==MAP_FAILED)goto done;
    for(lane=0;lane<1024;lane++) {
        uint16_t base=(uint16_t)(lane*977u+31000u);
        memcpy(shadow+lane*2,&base,2);expected[lane]=base;
        for(term=0;term<sizeof(descriptors)/sizeof(descriptors[0]);term++) {
            uint32_t d=descriptors[term];
            size_t offset=((d&0x40000000u)?0x02f45000u:0x2000u)+(d&65535u)*1024u+lane;
            uint32_t word=model[offset/4];
            int delta=(int8_t)(word>>((offset%4)*8));
            expected[lane]=(uint16_t)(expected[lane]+((d&0x80000000u)?-delta:delta));
        }
    }
    memcpy(shadow+4096,descriptors,sizeof(descriptors));
    job.abi_version=PANGO_MAC_STAGEA_ABI_VERSION;job.terms=sizeof(descriptors)/sizeof(descriptors[0]);
    job.base_offset=0;job.descriptor_offset=4096;job.output_offset=8192;job.timeout_us=1000000;
    if(ioctl(fd,PANGO_MAC_IOC_RUN_STAGEA,&job) || !(job.status&2) || job.error_code)goto done;
    if(memcmp(shadow+8192,expected,sizeof(expected))){errno=EILSEQ;goto done;}
    printf("PANGO_MAC_STAGEA_VALUES_PASS terms=%u lanes=1024 cycles=%u tables=threat+psq signed=add+subtract\n",job.terms,job.cycles);
    memset(shadow+8192,0xa5,2048);
    ((uint32_t *)(void *)(shadow+4096))[0]=0x10000u;
    errno=0;
    if(ioctl(fd,PANGO_MAC_IOC_RUN_STAGEA,&job)!=-1 || errno!=EINVAL)goto done;
    for(lane=0;lane<2048;lane++)if(shadow[8192+lane]!=0xa5){errno=EILSEQ;goto done;}
    puts("PANGO_MAC_STAGEA_BOARD_PASS backend=driver exact=1024 invalid_descriptor=reject output_preserved=pass");result=0;
done:
    if(result)perror("PANGO_MAC_STAGEA_BOARD_FAIL");
    if(model!=MAP_FAILED)munmap((void *)model,pff_bytes);
    if(shadow!=MAP_FAILED)munmap(shadow,info.scratch_bytes);
    if(mem>=0)close(mem);
    if(fd>=0)close(fd);
    return result;
}
