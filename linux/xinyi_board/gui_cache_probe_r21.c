/* Finite GUI RAM alias probe. Requires exclusive ownership and video off.
 * No image/model/media access. Every tested word is restored before return. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include "platform.h"
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
static uint64_t us(void)
{struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))exit(9);return(uint64_t)t.tv_sec*1000000u+(unsigned)t.tv_nsec/1000u;}
static void io_fence(void){__asm__ volatile("fence iorw,iorw":::"memory");}
static void cache_publish(void)
{__asm__ volatile("fence iorw,iorw\n.word 0x0000100f\nfence iorw,iorw":::"memory");}
static uint32_t pattern(unsigned i,unsigned turn){return 0x6b12d49fu^(i*0x9e3779b9u)^(turn*0x05030701u);}
int main(void)
{
    alarm(90);setvbuf(stdout,NULL,_IOLBF,0);
    if(!xy_platform_reservations_cover("/proc/device-tree"))return 2;
    int lock=open("/run/xq-camera.lock",O_CREAT|O_RDWR|O_CLOEXEC,0600);
    if(lock<0 || flock(lock,LOCK_EX|LOCK_NB))return 3;
    int fd=open("/dev/mem",O_RDWR|O_SYNC|O_CLOEXEC);if(fd<0)return 4;
    volatile uint32_t *sys=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0x1fe00000u);
    volatile uint32_t *video=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0x1fe11000u);
    volatile uint32_t *camera=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0x1fe12000u);
    if(sys==MAP_FAILED || video==MAP_FAILED || camera==MAP_FAILED)return 4;
    if(sys[0x300/4]!=0x53563300u || sys[0x314/4]!=60000000u || sys[0x308/4]!=49500000u ||
       video[4]!=0x1b800000u || video[5]!=0x1bc00000u || video[6]!=3840u ||
       (video[2]&1u) || (video[3]&2u) || (camera[2]&1u) || (camera[3]&0x71u)!=0x20u)return 5;
    const unsigned bytes=1048576,words=bytes/4;
    volatile uint32_t *uncached=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,(off_t)0x9b800000u);
    volatile uint32_t *cached=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,(off_t)0x1b800000u);
    uint32_t *backup=malloc(bytes);if(uncached==MAP_FAILED || cached==MAP_FAILED || !backup)return 6;
    cache_publish();for(unsigned i=0;i<words;i++)backup[i]=uncached[i];
    unsigned failed=0;
    for(unsigned turn=0;turn<4;turn++){
        volatile uint32_t *out=turn&1?cached:uncached;uint64_t start=us();
        for(unsigned i=0;i<words;i++)out[i]=pattern(i,turn+1);
        if(turn&1)cache_publish();else io_fence();
        uint64_t elapsed=us()-start;
        for(unsigned i=0;i<words;i++)if(uncached[i]!=pattern(i,turn+1)){failed=1;break;}
        printf("R21_GUI_ALIAS turn=%u cached=%u bytes=%u write_and_publish_us=%llu coherent=%u\n",
            turn,turn&1,bytes,(unsigned long long)elapsed,!failed);
        if(failed)break;
    }
    for(unsigned i=0;i<words;i++)cached[i]=backup[i];cache_publish();
    for(unsigned i=0;i<words;i++)if(uncached[i]!=backup[i]){failed=1;break;}
    printf("R21_GUI_ALIAS_RESTORED pass=%u video_off=1 no_camera=1\n",!failed);
    munmap((void *)cached,bytes);munmap((void *)uncached,bytes);free(backup);
    munmap((void *)camera,4096);munmap((void *)video,4096);munmap((void *)sys,4096);close(fd);close(lock);
    return failed?7:0;
}
