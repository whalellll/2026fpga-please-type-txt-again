/* Independent PFF1 gather check using the deployed model's signed bytes. */
#include "pango_mac_uapi.h"
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

static void fail(const char *s) { perror(s); exit(1); }
int main(void) {
    int fd=open("/dev/pango-mac0",O_RDWR),mem;
    struct pango_mac_info info;
    unsigned char *shadow;
    const int8_t *threat,*psq;
    unsigned sizes[]={1,3,256},test,lane,term;
    if(fd<0) fail("open-mac");
    if(ioctl(fd,PANGO_MAC_IOC_GET_INFO,&info)) fail("get-info");
    printf("MAC_GATHER_INFO id=%08x version=%08x features=%08x\n",info.device_id,info.device_version,info.features);
    if(!(info.features&PANGO_MAC_FEATURE_STAGEA_GATHER)) fail("missing-gather-feature");
    shadow=mmap(NULL,info.scratch_bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    if(shadow==MAP_FAILED) fail("shadow-map");
    mem=open("/dev/mem",O_RDONLY|O_SYNC);
    if(mem<0) fail("open-model");
    threat=mmap(NULL,4096,PROT_READ,MAP_SHARED,mem,0x10002000);
    psq=mmap(NULL,4096,PROT_READ,MAP_SHARED,mem,0x12f45000);
    if(threat==MAP_FAILED||psq==MAP_FAILED) fail("model-map");
    for(test=0;test<3;test++) {
        uint16_t *base=(uint16_t *)(shadow+0x1000),*out=(uint16_t *)(shadow+0x3000);
        uint32_t *desc=(uint32_t *)(shadow+0x2000);
        struct pango_mac_stagea_job job={0};
        job.abi_version=PANGO_MAC_STAGEA_ABI_VERSION;job.terms=sizes[test];
        job.base_offset=0x1000;job.descriptor_offset=0x2000;job.output_offset=0x3000;job.timeout_us=1000000;
        for(lane=0;lane<1024;lane++)base[lane]=(uint16_t)(lane*997u+32700u);
        for(term=0;term<job.terms;term++)desc[term]=term%3==0?0u:term%3==1?0x80000001u:0x40000000u;
        if(ioctl(fd,PANGO_MAC_IOC_RUN_STAGEA,&job))fail("gather-run");
        for(lane=0;lane<1024;lane++) {
            uint16_t expected=base[lane];
            for(term=0;term<job.terms;term++) {
                int value=term%3==0?threat[lane]:term%3==1?-threat[1024+lane]:psq[lane];
                expected=(uint16_t)(expected+value);
            }
            if(out[lane]!=expected) {fprintf(stderr,"GATHER_MISMATCH terms=%u lane=%u expected=%u actual=%u\n",job.terms,lane,expected,out[lane]);return 1;}
        }
        printf("MAC_GATHER_CASE_PASS terms=%u lanes=1024 cycles=%u\n",job.terms,job.cycles);
    }
    {
        struct pango_mac_stagea_job job={0};
        job.abi_version=PANGO_MAC_STAGEA_ABI_VERSION;job.terms=1;
        job.base_offset=0x1000;job.descriptor_offset=0x2000;job.output_offset=0x3000;
        *(uint32_t *)(shadow+0x2000)=0x20000000u;memset(shadow+0x3000,0xa5,2048);
        errno=0;
        if(ioctl(fd,PANGO_MAC_IOC_RUN_STAGEA,&job)!=-1||errno!=EINVAL)fail("invalid-descriptor-accepted");
        for(lane=0;lane<2048;lane++)if(shadow[0x3000+lane]!=0xa5)fail("invalid-output-mutated");
    }
    munmap((void *)threat,4096);munmap((void *)psq,4096);close(mem);
    munmap(shadow,info.scratch_bytes);close(fd);
    puts("MAC_GATHER_BOARD_PASS cases=3 lanes=3072 modulo=pass invalid_descriptor=pass");
    return 0;
}
