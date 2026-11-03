/* Read-only cross-check. No timer programming or runtime calibration change. */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include "clock_contract.h"
static uint64_t ns(clockid_t clock)
{
    struct timespec t;
    if(clock_gettime(clock,&t))return 0;
    return (uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;
}
static uint64_t mtime(volatile const uint32_t *p)
{
    uint32_t hi,lo,again;
    do{hi=p[0xffc/4];lo=p[0xff8/4];again=p[0xffc/4];}while(hi!=again);
    return ((uint64_t)hi<<32)|lo;
}
static void number(uint64_t value)
{
    char digits[24];
    unsigned count=0;
    do{digits[count++]=(char)('0'+value%10);value/=10;}while(value);
    while(count){--count;if(write(1,digits+count,1)!=1)_exit(2);}
}
static void text(const char *value)
{
    unsigned size=0;
    while(value[size])++size;
    while(size){ssize_t count=write(1,value,size);if(count<=0)_exit(2);value+=count;size-=(unsigned)count;}
}
int main(void)
{
    int fd=open("/dev/mem",O_RDONLY|O_SYNC);
    if(fd<0)return 2;
    volatile const uint32_t *timer=mmap(0,4096,PROT_READ,MAP_SHARED,fd,0x0200b000);
    volatile const uint32_t *sys=mmap(0,4096,PROT_READ,MAP_SHARED,fd,0x1fe00000);
    if(timer==MAP_FAILED || sys==MAP_FAILED)return 2;
    uint32_t hz=sys[0x318/4],cpu=sys[0x314/4];
    if(hz!=49500000 || cpu!=XINYI_CPU_HZ)return 2;
    uint64_t c0=mtime(timer),r0=ns(CLOCK_MONOTONIC_RAW),m0=ns(CLOCK_MONOTONIC);
    struct timespec delay={0,200000000};
    while(nanosleep(&delay,&delay) && errno==EINTR){}
    uint64_t r1=ns(CLOCK_MONOTONIC_RAW),m1=ns(CLOCK_MONOTONIC),c1=mtime(timer);
    if(!r0 || !m0 || r1<=r0 || m1<=m0 || c1<=c0)return 2;
    text("XINYI_CLOCK_CROSSCHECK cpu_hz=");number(cpu);
    text(" clint_hz=");number(hz);
    text(" raw_ns=");number(r1-r0);
    text(" mono_ns=");number(m1-m0);
    text(" clint_ticks=");number(c1-c0);text("\n");
    munmap((void *)timer,4096);munmap((void *)sys,4096);close(fd);return 0;
}
