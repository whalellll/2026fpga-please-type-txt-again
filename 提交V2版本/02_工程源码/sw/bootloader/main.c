#include "soc.h"
#include "camera.h"
#include "sd.h"
#include "audio.h"
#include "console_line.h"

int coremark_command(int validation);

/* Never printed at boot; shown by `help` and embedded for the audit gate.
 * Keep in sync with VERSION and scripts/release_version.ps1. */
static const char release_marker[] = "SoC V2.1 bootloader";

static int split(char*s,char**v,int max){int n=0;while(*s){while(*s==' ')s++;if(!*s)break;if(n<max)v[n++]=s;while(*s&&*s!=' ')s++;if(*s)*s++=0;}return n;}
static int streq(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static void help(void){console_puts(release_marker);console_puts("\n");
 console_puts(
 "help | info | debug help\n"
 "loadx <ddr_addr> | netcfg <board_ip>\n"
 "tftp <server_ip> <file> <addr> | netboot [server_ip]\n"
 "sdinfo | sdboot | xqboot | sdbench | sdverify\n"
 "coremark [validate] | flashboot | reboot\n"
 "boot <entry> | linux <entry> <dtb_addr>\n");}
static void debug_help(void){console_puts(
 "debug mic                    - live microphone-to-speaker monitor\n"
 "debug speaker                - loop SD-root SONG.PCM through speaker\n"
 "debug speaker volume <1..100> - set shared output volume (default 10%)\n"
 "debug camera                 - CMOS2 HDMI; Space saves PNG, Esc exits\n"
 "debug camera_sd              - CMOS2 HDMI; Space saves SD PNG+JSON\n"
 "During audio: +/- changes volume by 5%; q or Esc stops.\n");}
static int do_flashboot(void){image_header_t h;int r=flash_load_image(&h);if(r){console_puts("Flash image invalid, error ");console_dec((uint32_t)-r);console_putc('\n');return r;}console_puts("CRC OK, jumping to ");console_hex(h.entry_addr);console_putc('\n');jump_to(h.entry_addr,0,0);return 0;}
/* Preserve bare-metal Flash autoboot; Linux is only started by a command. */
static void try_automatic_flashboot(void){image_header_t h;
 if(flash_read_header(&h)||(h.flags&1u)==0)return;
 console_puts("Flash autoboot in 3s; key cancels.\n");
 if(console_getc_timeout(TIMEBASE_HZ*3u)<0)do_flashboot();
 else console_puts("Autoboot stopped.\n");
}
static int do_netboot(uint32_t ip){uint32_t n;int r;
 console_puts("Linux netboot server ");console_hex(ip);console_putc('\n');
 ddr_wait_ready();
 r=tftp_get(ip,"fw_jump.bin",0x18000000u,0x00100000u,&n);if(r)return r;
 r=tftp_get(ip,"Image",0x00400000u,0x01c00000u,&n);if(r)return r;
 r=tftp_get(ip,"rootfs.cpio",0x03000000u,0x01000000u,&n);if(r)return r;
 r=tftp_get(ip,"soc.dtb",0x1a000000u,0x00100000u,&n);if(r)return r;
 console_puts("Starting OpenSBI at 0x18000000\n");jump_to(0x18000000u,0,0x1a000000u);return 0;
}
static uint32_t getnum(char*s,int*allok){int ok;uint32_t v=parse_u32(s,&ok);if(!ok)*allok=0;return v;}
int main(void){char line[160],*av[8];uint32_t last_addr=0x01000000,last_len=0;int n,ok,r;
 eth_init();try_automatic_flashboot();
 console_puts("Console ready. Type help.\n");
 for(;;){console_puts("soc> ");console_readline(line,sizeof(line));n=split(line,av,8);if(!n)continue;
   if(streq(av[0],"help")){help();continue;}
   if(streq(av[0],"debug")){
    if(n==2&&streq(av[1],"help")){debug_help();continue;}
    if(n==2&&streq(av[1],"camera")){camera_command();continue;}
    if(n==2&&streq(av[1],"camera_sd")){camera_sd_command();continue;}
    if(n==2&&streq(av[1],"speaker")){
     r=cmd_debug_speaker();
     if(r){console_puts("debug speaker returned, error ");console_dec((uint32_t)-r);console_putc('\n');}
     continue;
    }
    if(n==2&&streq(av[1],"mic")){
     r=cmd_debug_mic();
     if(r){console_puts("debug mic returned, error ");console_dec((uint32_t)-r);console_putc('\n');}
     continue;
    }
    if(n==4&&streq(av[1],"speaker")&&streq(av[2],"volume")){
     uint32_t volume;
     ok=1;volume=getnum(av[3],&ok);
     if(!ok||audio_set_volume(volume))console_puts("volume must be 1..100 percent\n");
     else{console_puts("Audio volume=");console_dec(audio_get_volume());console_puts("%.\n");}
     continue;
    }
    console_puts("unknown debug command; type debug help\n");continue;
   }
   if(streq(av[0],"maikefen")){console_puts("Use debug mic\n");continue;}
   if(streq(av[0],"yangshenqi")){console_puts("Use debug speaker; set volume with debug speaker volume <1..100>\n");continue;}
   if(streq(av[0],"shexiantou")){console_puts("Use debug camera\n");continue;}
   if(streq(av[0],"sdinfo")&&n==1){sd_print_info();continue;}
   if(streq(av[0],"sdboot")&&n==1){r=sd_boot_linux();console_puts("sdboot returned, error ");console_dec((uint32_t)-r);console_putc('\n');continue;}
   if(streq(av[0],"xqboot")&&n==1){r=sd_boot_xiangqi();console_puts("xqboot returned, error ");console_dec((uint32_t)-r);console_putc('\n');continue;}
    if(streq(av[0],"sdbench")&&n==1){r=sd_benchmark();if(r){console_puts("sdbench returned, error ");console_dec((uint32_t)-r);console_putc('\n');}continue;}
    if(streq(av[0],"sdverify")&&n==1){r=sd_verify_boot_files();if(r){console_puts("sdverify returned, error ");console_dec((uint32_t)-r);console_putc('\n');}continue;}
   if(streq(av[0],"coremark")&&(n==1||(n==2&&streq(av[1],"validate")))){console_puts("CoreMark v1.0: RV32IMA, boot BRAM, automatic >=10 s calibration\nCPU_HZ=");console_dec(REG32(CPU_HZ_REG));console_puts("\nSYS_HZ=");console_dec(REG32(SYS_HZ_REG));console_puts("\nTIMEBASE_HZ=");console_dec(REG32(TIMEBASE_HZ_REG));console_putc('\n');r=coremark_command(n==2);if(r)console_puts("CoreMark command failed validation.\n");continue;}
     if(streq(av[0],"info")){console_puts("SYS_ID=");console_hex(REG32(SYS_BASE));console_puts(" DDR=");console_puts((REG32(SYS_BASE+4)&1)?"ready":"not-ready");console_puts(" SYS_HZ=");console_dec(REG32(SYS_HZ_REG));console_puts(" CPU_HZ=");console_dec(REG32(CPU_HZ_REG));console_puts(" TIMEBASE_HZ=");console_dec(REG32(TIMEBASE_HZ_REG));console_puts(" CAPS=");console_hex(REG32(SYS_BASE+12));console_puts(" ETH_ID=");console_hex(REG32(ETH_BASE));console_puts(" SPI_ID=");console_hex(REG32(SPI_BASE));console_puts(" FLASH_JEDEC=");console_hex(flash_read_jedec_id());console_puts(" SD_ID=");console_hex(REG32(SD_BASE));console_puts(" SD=");console_puts(sd_card_present()?"present":"absent");console_puts(" AUDIO_ID=");console_hex(REG32(AUDIO_BASE+AUDIO_ID));console_puts(" MAC_ID=");console_hex(REG32(MAC_BASE));console_puts(" MAC_VER=");console_hex(REG32(MAC_BASE+4));console_putc('\n');continue;}
  if(streq(av[0],"loadx")&&n==2){uint32_t lim;ok=1;last_addr=getnum(av[1],&ok);if(!ok||!ddr_range_valid(last_addr,1)){console_puts("bad or DMA-reserved DDR address\n");continue;}lim=ddr_contiguous_limit(last_addr)-last_addr;last_len=xmodem_receive(last_addr,lim);console_puts("received ");console_dec(last_len);console_puts(" bytes\n");continue;}
  if(streq(av[0],"netcfg")&&n==2){uint32_t ip=parse_ip(av[1],&ok);if(!ok){console_puts("bad IP address\n");continue;}eth_set_ip(ip);console_puts("board IP set to ");console_hex(ip);console_putc('\n');continue;}
  if(streq(av[0],"netboot")&&(n==1||n==2)){uint32_t ip=0xc0a80102u;if(n==2)ip=parse_ip(av[1],&ok);else ok=1;if(!ok){console_puts("bad IP address\n");continue;}r=do_netboot(ip);console_puts("netboot failed, error ");console_dec((uint32_t)-r);console_putc('\n');continue;}
  if(streq(av[0],"tftp")&&n==4){uint32_t ip=parse_ip(av[1],&ok),lim;last_addr=getnum(av[3],&ok);if(!ok||!ddr_range_valid(last_addr,1)){console_puts("bad or DMA-reserved DDR address\n");continue;}lim=ddr_contiguous_limit(last_addr)-last_addr;r=tftp_get(ip,av[2],last_addr,lim,&last_len);console_puts(r?"TFTP failed ":"downloaded ");console_dec(r?(uint32_t)-r:last_len);console_putc('\n');continue;}
  if(streq(av[0],"flashwrite")&&n==5){uint32_t a,l,load,e;ok=1;a=getnum(av[1],&ok);l=getnum(av[2],&ok);load=getnum(av[3],&ok);e=getnum(av[4],&ok);if(!ok){console_puts("bad argument\n");continue;}r=flash_write_image(a,l,load,e,1);console_puts(r?"flash failed\n":"flash verified header written\n");continue;}
  if(streq(av[0],"tftpflash")&&n==5){uint32_t ip,load,e,lim;ok=1;ip=parse_ip(av[1],&ok);load=getnum(av[3],&ok);e=getnum(av[4],&ok);if(!ok||!ddr_range_valid(load,1)||!ddr_entry_valid(e)){console_puts("bad or DMA-reserved DDR address\n");continue;}last_addr=load;lim=ddr_contiguous_limit(load)-load;if(lim>FLASH_LIMIT_ADDR-FLASH_PAYLOAD_ADDR)lim=FLASH_LIMIT_ADDR-FLASH_PAYLOAD_ADDR;r=tftp_get(ip,av[2],last_addr,lim,&last_len);if(!r)r=flash_write_image(last_addr,last_len,load,e,1);console_puts(r?"tftpflash failed\n":"tftpflash complete\n");continue;}
  if(streq(av[0],"flashboot")){do_flashboot();continue;}
  if(streq(av[0],"boot")&&n==2){uint32_t e;ok=1;e=getnum(av[1],&ok);if(ok&&ddr_entry_valid(e))jump_to(e,0,0);else console_puts("bad or DMA-reserved DDR entry\n");continue;}
  if(streq(av[0],"linux")&&n==3){uint32_t e,d;ok=1;e=getnum(av[1],&ok);d=getnum(av[2],&ok);if(ok&&ddr_entry_valid(e)&&ddr_range_valid(d,4))jump_to(e,0,d);else console_puts("bad or DMA-reserved DDR address\n");continue;}
  if(streq(av[0],"reboot")){console_puts("Press the board reset key.\n");for(;;);}
  console_puts("unknown command; type help\n");
 }
}
