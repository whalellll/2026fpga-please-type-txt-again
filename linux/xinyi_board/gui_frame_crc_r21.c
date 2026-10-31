/* Bounded read-only scanout check; never changes video/camera/control state. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include "platform.h"
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <sys/mman.h>
#include <unistd.h>
int main(void)
{
    alarm(60);
    if(!xy_platform_reservations_cover("/proc/device-tree"))return 2;
    int fd=open("/dev/mem",O_RDONLY|O_SYNC|O_CLOEXEC);if(fd<0)return 3;
    volatile uint32_t *video=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0x1fe11000u);
    volatile uint32_t *camera=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0x1fe12000u);
    if(video==MAP_FAILED || camera==MAP_FAILED)return 4;
    uint32_t status=video[3],control=video[2];
    if(video[0]!=0x58514642u || video[4]!=0x1b800000u || video[5]!=0x1bc00000u ||
       video[6]!=3840u || video[8]!=4147200u || !(status&2u) || (status&0x28u) ||
       (camera[2]&1u) || (camera[3]&0x71u)!=0x20u)return 5;
    uint32_t base=video[4+((status>>2)&1u)];
    volatile uint32_t *pixels=mmap(NULL,4147200,PROT_READ,MAP_SHARED,fd,(off_t)(base|0x80000000u));
    if(pixels==MAP_FAILED)return 6;
    uint32_t table[256];
    for(unsigned i=0;i<256;i++){
        uint32_t v=i;for(unsigned b=0;b<8;b++)v=(v>>1)^(0xedb88320u&-(v&1u));table[i]=v;
    }
    uint32_t crc=~0u;
    for(unsigned i=0;i<4147200/4;i++){
        uint32_t word=pixels[i];
        for(unsigned b=0;b<4;b++){crc=table[(crc^word)&255u]^(crc>>8);word>>=8;}
    }
    if(video[2]!=control || (video[3]&0x2fu)!=(status&0x2fu) || (camera[2]&1u))return 7;
    printf("R21_SCANOUT_CRC bytes=4147200 bank=%u crc32=%08x stable_source=1 uncached_read=1\n",(status>>2)&1u,~crc);
    munmap((void *)pixels,4147200);munmap((void *)camera,4096);munmap((void *)video,4096);close(fd);return 0;
}
