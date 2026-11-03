#define _GNU_SOURCE
#include "soc.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <setjmp.h>
#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif
uint32_t pn03_xmodem_receive(uint32_t,uint32_t);
uint32_t legacy_xmodem_receive(uint32_t,uint32_t);
static uint8_t packet[1029],expected[65536];
static uint32_t ticks,gap,limit;static unsigned position,block,blocks,calls,naks,cancels;
static int active,eot,duplicate_done,corrupt;
static const char *mode;
static jmp_buf legacy_watchdog;
static void check(int ok,const char *message)
{if(!ok){fprintf(stderr,"XMODEM_TEST_FAIL %s\n",message);exit(2);}}
static uint16_t crc(const uint8_t *p)
{uint16_t n=0;for(unsigned i=0;i<1024;i++){n^=(uint16_t)p[i]<<8;for(unsigned j=0;j<8;j++)n=n&32768?(uint16_t)((n<<1)^0x1021):(uint16_t)(n<<1);}return n;}
static void frame(void)
{
 uint16_t c;packet[0]=2;packet[1]=(uint8_t)block;packet[2]=(uint8_t)~block;
 memcpy(packet+3,expected+(block-1)*1024,1024);c=crc(packet+3);
 if(!strcmp(mode,"bad-crc") || (!strcmp(mode,"crc-once") && !corrupt))c^=1;
 packet[1027]=(uint8_t)(c>>8);packet[1028]=(uint8_t)c;position=0;active=1;
 gap=(!strcmp(mode,"gap300") || !strcmp(mode,"legacy-gap300"))?TIMEBASE_HZ*3u/10u:0;
}
void console_puts(const char *s){(void)s;}
void console_putc(char c)
{
 if(c=='C'){if(!active && !eot)frame();return;}
 if((uint8_t)c==0x15){naks++;corrupt=1;frame();return;}
 if((uint8_t)c==0x18){cancels++;active=0;return;}
 if((uint8_t)c==0x06){
  if(eot){eot=0;return;}
  if(!strcmp(mode,"duplicate") && block==1 && !duplicate_done){duplicate_done=1;frame();return;}
  block++;if(block>blocks){active=0;eot=1;}else frame();
 }
}
int console_getc_timeout(uint32_t n)
{
 if(++calls>=200000){
  if(!strcmp(mode,"legacy-gap300")){puts("LEGACY_RETRY_LOOP_WATCHDOG_DETECTED");longjmp(legacy_watchdog,1);}
  check(0,"bounded simulated receiver");
 }
 if(!strcmp(mode,"cancel")){ticks+=1;return 0x18;}
 if(!strcmp(mode,"timeout")){ticks+=n;return -1;}
 if(eot){ticks+=1;return 4;}
 if(active && position<sizeof(packet)){
  if(position==100 && gap){if(gap>n){gap-=n;ticks+=n;return -1;}ticks+=gap;gap=0;}
  ticks+=100;return packet[position++];
 }
 ticks+=n;return -1;
}
uint32_t read_mtime_ticks32(void){return ticks;}
int main(int argc,char **argv)
{
 check(argc==2,"arguments");mode=argv[1];limit=!strcmp(mode,"64k")?65536u:1024u;blocks=limit/1024u;block=1;
 check(mmap((void *)(uintptr_t)0x06000000u,0x20000u,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0)==(void *)(uintptr_t)0x06000000u,"destination mapping");
 for(unsigned i=0;i<sizeof(expected);i++)expected[i]=(uint8_t)(i*37u+i/17u);
 memset((void *)(uintptr_t)0x06000000u,0xa5,0x20000u);
 uint32_t got=0;
 if(!strcmp(mode,"legacy-gap300")){if(!setjmp(legacy_watchdog))got=legacy_xmodem_receive(0x06000000u,limit);}
 else got=pn03_xmodem_receive(0x06000000u,limit);
 int reject=!strcmp(mode,"legacy-gap300") || !strcmp(mode,"bad-crc") || !strcmp(mode,"cancel") || !strcmp(mode,"timeout");
 if(reject)check(got!=limit,"old timeout/fault must reject");
 else check(got==limit && !memcmp((void *)(uintptr_t)0x06000000u,expected,limit),"exact received bytes");
 check(*(uint32_t *)(uintptr_t)(0x06000000u+limit)==0xa5a5a5a5u,"destination guard");
 if(!strcmp(mode,"gap300"))check(!naks,"300ms scheduling gap must fit one-second byte deadline");
 if(!strcmp(mode,"crc-once"))check(naks==1,"one bad frame retried exactly once");
 printf("XMODEM_TEST_PASS %s received=%u naks=%u cancels=%u\n",mode,got,naks,cancels);return 0;
}
