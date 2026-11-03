#include "soc.h"
int memcmp(const void *a,const void *b,size_t n){const uint8_t *x=a,*y=b;while(n--){if(*x!=*y)return (int)*x-(int)*y;++x;++y;}return 0;}

void *memcpy(void *d,const void *s,size_t n){uint8_t*dd=d;const uint8_t*ss=s;while(n--)*dd++=*ss++;return d;}
void *memset(void *d,int c,size_t n){uint8_t*dd=d;while(n--)*dd++=(uint8_t)c;return d;}

/* CLINT mtime is in the SYS domain. This reads its low 32 bits for bounded
 * intervals; CSR mcycle instead counts CPU clocks. */
uint32_t read_mtime_ticks32(void){return REG32(CLINT_MTIME);}
void delay_cycles(uint32_t n){uint32_t s=read_mtime_ticks32();while((uint32_t)(read_mtime_ticks32()-s)<n);}
void console_putc(char c){if(c=='\n')REG32(UART_BASE)='\r';REG32(UART_BASE)=(uint8_t)c;}
int console_getc_timeout(uint32_t n){uint32_t s=read_mtime_ticks32();do{if(REG32(UART_BASE+4)&(1u<<8))return REG32(UART_BASE)&255;}while((uint32_t)(read_mtime_ticks32()-s)<n);return -1;}
void console_puts(const char*s){while(*s)console_putc(*s++);}
void console_hex(uint32_t v){static const char h[]="0123456789abcdef";int i;console_puts("0x");for(i=7;i>=0;i--)console_putc(h[(v>>(i*4))&15]);}
void console_dec(uint32_t v){char b[11];int n=0;if(!v){console_putc('0');return;}while(v){b[n++]=(char)('0'+v%10);v/=10;}while(n)console_putc(b[--n]);}
uint32_t parse_u32(const char*s,int*ok){uint32_t v=0,b=10;*ok=0;if(!s||!*s)return 0;if(s[0]=='0'&&(s[1]=='x'||s[1]=='X')){b=16;s+=2;}while(*s){uint32_t d;if(*s>='0'&&*s<='9')d=*s-'0';else if(*s>='a'&&*s<='f')d=*s-'a'+10;else if(*s>='A'&&*s<='F')d=*s-'A'+10;else return 0;if(d>=b)return 0;v=v*b+d;s++;}*ok=1;return v;}
uint32_t crc32_update(uint32_t crc,const void*data,uint32_t len){const uint8_t*p=data;uint32_t i,j;for(i=0;i<len;i++){crc^=p[i];for(j=0;j<8;j++)crc=(crc>>1)^(0xedb88320u&-(crc&1));}return crc;}
int ddr_range_valid(uint32_t address,uint32_t len)
{
 uint32_t end;
 if(!len||address>=DDR_SAFE_LIMIT||len>DDR_SAFE_LIMIT-address)return 0;
 end=address+len;
 if(address<CLINT_END&&end>CLINT_BASE)return 0;
 return end<=DDR_DMA_RESERVED_BASE||address>=DDR_DMA_RESERVED_END;
}
int ddr_entry_valid(uint32_t address)
{
 /* RV32IMA has IALIGN=32; download data itself may be byte aligned. */
 return !(address&3u)&&ddr_range_valid(address,4);
}
uint32_t ddr_contiguous_limit(uint32_t address)
{
 if(address<CLINT_BASE)return CLINT_BASE;
 if(address<CLINT_END)return address;
 if(address<DDR_DMA_RESERVED_BASE)return DDR_DMA_RESERVED_BASE;
 if(address>=DDR_DMA_RESERVED_END&&address<DDR_SAFE_LIMIT)return DDR_SAFE_LIMIT;
 return address;
}

/* The DDR AXI bridge holds transactions until calibration completes.  The
 * status bit on this board revision is diagnostic only, so all autonomous
 * loaders share one conservative delay before their first DDR access. */
int ddr_wait_ready(void){static int waited;if(!waited){console_puts("Waiting for DDR training...\n");delay_cycles(TIMEBASE_HZ*5u);waited=1;console_puts("DDR startup delay complete\n");}return 0;}

static uint16_t crc16(const uint8_t*p,uint32_t n){uint16_t c=0;uint32_t i;int b;for(i=0;i<n;i++){c^=(uint16_t)p[i]<<8;for(b=0;b<8;b++)c=(c&0x8000)?(uint16_t)((c<<1)^0x1021):(uint16_t)(c<<1);}return c;}
uint32_t xmodem_receive(uint32_t address,uint32_t limit){uint8_t*p=(uint8_t*)(uintptr_t)address;uint8_t block=1;uint32_t total=0;int tries=0;console_puts("Start XMODEM-CRC transfer now...\n");while(tries++<60){int c;console_putc('C');c=console_getc_timeout(TIMEBASE_HZ);if(c==0x01||c==0x02){for(;;){uint32_t n=(c==0x01)?128:1024,i;int bn=console_getc_timeout(TIMEBASE_HZ/10u),inv=console_getc_timeout(TIMEBASE_HZ/10u);uint8_t buf[1024];if(bn<0||inv<0||(((bn^inv)&255)!=255)){console_putc(0x15);break;}for(i=0;i<n;i++){int x=console_getc_timeout(TIMEBASE_HZ/10u);if(x<0)break;buf[i]=(uint8_t)x;}int ch=console_getc_timeout(TIMEBASE_HZ/10u),cl=console_getc_timeout(TIMEBASE_HZ/10u);if(i!=n||ch<0||cl<0||crc16(buf,n)!=(uint16_t)((ch<<8)|cl)){console_putc(0x15);c=console_getc_timeout(TIMEBASE_HZ);if(c<0)break;continue;}if((uint8_t)bn==block){if(total+n>limit){console_putc(0x18);return 0;}for(i=0;i<n;i++)p[total+i]=buf[i];total+=n;block++;}else if((uint8_t)bn!=(uint8_t)(block-1)){console_putc(0x18);return 0;}console_putc(0x06);c=console_getc_timeout(TIMEBASE_HZ);if(c==0x04){console_putc(0x06);return total;}if(c!=0x01&&c!=0x02)break;}}else if(c==0x04){console_putc(0x06);return total;}else if(c==0x18)return 0;}return 0;}
