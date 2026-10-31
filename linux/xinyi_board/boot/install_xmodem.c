/* Bounded RAM-only XMODEM for 64 KiB slices. SD writes occur elsewhere only
 * after the exact per-slice and whole-payload CRC checks have passed. */
#include "soc.h"
static uint16_t packet_crc(const uint8_t *p,uint32_t n)
{
 uint16_t c=0;uint32_t i;unsigned bit;
 for(i=0;i<n;i++){c^=(uint16_t)p[i]<<8;for(bit=0;bit<8;bit++)c=(c&0x8000u)?(uint16_t)((c<<1)^0x1021u):(uint16_t)(c<<1);}
 return c;
}
static void quiet(void)
{
 unsigned n;for(n=0;n<4096;n++)if(console_getc_timeout(TIMEBASE_HZ/50u)<0)break;
}
uint32_t pn03_xmodem_receive(uint32_t address,uint32_t limit)
{
 uint8_t buffer[1024],block=1;uint32_t total=0,start=read_mtime_ticks32();unsigned errors=0;int started=0;
 if(!limit || limit>65536u || (limit&127u))return 0;
 console_puts("Start PN03 XMODEM-CRC slice...\n");console_putc('C');
 while(errors<8 && (uint32_t)(read_mtime_ticks32()-start)<TIMEBASE_HZ*60u){
  int lead=console_getc_timeout(TIMEBASE_HZ);uint32_t n,i;int number,inverse,high,low,valid=1;
  if(lead<0){errors++;console_putc(started?0x15:'C');continue;}
  if(lead==0x18){console_putc(0x18);return 0;}
  if(lead==0x04){if(total==limit){console_putc(0x06);return total;}break;}
  if(lead!=0x01 && lead!=0x02){quiet();errors++;console_putc(0x15);continue;}
  started=1;n=lead==0x01?128u:1024u;
  number=console_getc_timeout(TIMEBASE_HZ);inverse=console_getc_timeout(TIMEBASE_HZ);
  if(number<0 || inverse<0 || ((number^inverse)&255)!=255)valid=0;
  for(i=0;i<n;i++){int x=console_getc_timeout(TIMEBASE_HZ);if(x<0){valid=0;break;}buffer[i]=(uint8_t)x;}
  high=console_getc_timeout(TIMEBASE_HZ);low=console_getc_timeout(TIMEBASE_HZ);
  if(!valid || high<0 || low<0 || packet_crc(buffer,n)!=(uint16_t)((high<<8)|low)){
   quiet();errors++;console_putc(0x15);continue;
  }
  if((uint8_t)number==block){
   uint8_t *destination=(uint8_t *)(uintptr_t)address;
   if(total+n>limit)break;
   for(i=0;i<n;i++)destination[total+i]=buffer[i];
   total+=n;block++;console_putc(0x06);
  }else if((uint8_t)number==(uint8_t)(block-1))console_putc(0x06);
  else{errors++;console_putc(0x15);}
 }
 console_putc(0x18);console_putc(0x18);return 0;
}
