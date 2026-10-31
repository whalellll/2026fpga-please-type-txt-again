#define _POSIX_C_SOURCE 200809L
#include "xqvoice_profile.h"
#ifdef XQVOICE_PROFILE_ENABLED
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#if defined(__linux__) && defined(__riscv) && __riscv_xlen == 32
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#endif
static int enabled,csr_clock;
static uint32_t tick_hz=1000000000u;
static uint64_t started,capture_end,stage_ticks[XQVP_COUNT],mac_jobs,mac_cycles;
static const char *const names[XQVP_COUNT]={
 "model_read","input_read","model_check","capture","feature",
 "window","fft","power","mel_quant","mac_open","cnn",
 "layer0","layer1","layer2","layer3","layer4",
 "pack","mac_wait","requant","trace","decode"
};
uint64_t xqvp_now(void) {
 struct timespec t;
 if(!enabled)return 0;
#if defined(__riscv) && __riscv_xlen == 32
 if(csr_clock){
  uint32_t hi,lo,again;
  do {__asm__ volatile("rdtimeh %0":"=r"(hi));__asm__ volatile("rdtime %0":"=r"(lo));__asm__ volatile("rdtimeh %0":"=r"(again));}while(hi!=again);
  return ((uint64_t)hi<<32)|lo;
 }
#endif
 if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
 return (uint64_t)t.tv_sec*1000000000u+(uint32_t)t.tv_nsec;
}
void xqvp_init(void) {
 const char *value=getenv("XQVOICE_PROFILE");
 enabled=value && !strcmp(value,"1");
 memset(stage_ticks,0,sizeof(stage_ticks));capture_end=mac_jobs=mac_cycles=0;
#if defined(__linux__) && defined(__riscv) && __riscv_xlen == 32
 if(enabled){
  int fd=open("/dev/mem",O_RDONLY|O_SYNC|O_CLOEXEC);
  if(fd>=0){
   volatile uint32_t *sys=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,(off_t)0x1fe00000u);
   if(sys!=MAP_FAILED){
    uint32_t hz=sys[0x314/4];
    if(sys[0x300/4]==0x53563300u && hz>=1000000u && hz<=100000000u && sys[0x318/4]==49500000u){csr_clock=1;tick_hz=hz;}
    munmap((void *)sys,4096);
   }
   close(fd);
  }
 }
#endif
 started=xqvp_now();
}
void xqvp_reset(void) {
 memset(stage_ticks,0,sizeof(stage_ticks));capture_end=mac_jobs=mac_cycles=0;started=xqvp_now();
}
void xqvp_add(unsigned stage,uint64_t ticks) {if(enabled && stage<XQVP_COUNT)stage_ticks[stage]+=ticks;}
void xqvp_capture_ended(void) {capture_end=xqvp_now();}
void xqvp_mac(uint64_t jobs,uint64_t cycles) {mac_jobs=jobs;mac_cycles=cycles;}
static uint64_t us(uint64_t ticks) {return (ticks/tick_hz)*1000000u+(ticks%tick_hz)*1000000u/tick_hz;}
void xqvp_emit(int status) {
 uint64_t ended=xqvp_now();
 if(!enabled)return;
 printf("XQVOICE_PROFILE_V1 rc=%d clock=%s hz=%u total_us=%llu after_capture_us=%llu mac_jobs=%llu mac_cycles=%llu",
  status,csr_clock?"cpu-time-csr":"monotonic",tick_hz,
  (unsigned long long)us(ended-started),(unsigned long long)(capture_end?us(ended-capture_end):0),
  (unsigned long long)mac_jobs,(unsigned long long)mac_cycles);
 for(unsigned i=0;i<XQVP_COUNT;i++)printf(" %s_us=%llu",names[i],(unsigned long long)us(stage_ticks[i]));
 putchar('\n');
}
#endif
