#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include "soc.h"
#include "sd.h"
#include "fat_ro.h"
#include "crc32_fast.h"
#include "camera.h"
#include "install_payloads.h"
#include "target.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <setjmp.h>
#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif
int pn03_install_main(void);
static int disk,initializations,commands,jumped,received,failed,repair,fault;
static unsigned writes,after_fault,reads;
static uint32_t model_ticks;
static unsigned committed_pairs;
static const char *scenario,*directory;
static sd_card_info_t info;
static jmp_buf finish;
static void check(int ok,const char *s)
{if(!ok){fprintf(stderr,"INSTALL_TEST_FAIL %s\n",s);exit(2);}}
static uint32_t crc(const void *p,uint32_t n)
{return crc32_fast(0xffffffffu,p,n)^0xffffffffu;}
void console_puts(const char *s)
{fputs(s,stdout);if(strstr(s,"PN03_INSTALL_FAIL"))failed=1;if(strstr(s,"PN03_REPAIR_REQUIRED"))repair=1;if(strstr(s,"PN03_PAIR_COMMITTED"))committed_pairs++;}
void console_putc(char c){putchar(c);}
void console_dec(uint32_t n){printf("%u",n);}
int console_getc_timeout(uint32_t n){(void)n;return -1;}
uint32_t read_mtime_ticks32(void){model_ticks+=100;return model_ticks;}
int sd_init(void)
{
 initializations++;
 if((!strcmp(scenario,"cid-swap") && initializations==2) ||
    (!strcmp(scenario,"write-swap") && fault))info.cid[0]=1;
 return 0;
}
void sd_release(void){}
int sd_card_raw_present(void){return 1;}
const sd_card_info_t *sd_card_info(void){return &info;}
int sd_read_sectors(uint32_t lba,uint32_t n,uint8_t *p)
{
 reads++;check(n && n<=32 && lba<INSTALL_SECTORS && n<=INSTALL_SECTORS-lba,"read range");
 if(committed_pairs==2){
  if(!strcmp(scenario,"slow-big-pair"))model_ticks+=n*8000u;
  if(!strcmp(scenario,"stalled-big-file"))model_ticks+=n*32000u;
 }
 return pread(disk,p,(size_t)n*512,(off_t)lba*512)==(ssize_t)n*512?0:-1;
}
int sd_write_sector(uint32_t lba,const uint8_t *p)
{
 check(lba<INSTALL_SECTORS,"write range");writes++;if(fault)after_fault++;
 if(committed_pairs==2){
  if(!strcmp(scenario,"slow-big-pair"))model_ticks+=8000u;
  if(!strcmp(scenario,"stalled-big-file"))model_ticks+=32000u;
 }
 check(pwrite(disk,p,512,(off_t)lba*512)==512,"fixture write");
 if((!strcmp(scenario,"write-fail") || !strcmp(scenario,"write-swap")) && writes==20){fault=1;return -1;}
 return 0;
}
int sd_write_sectors(uint32_t lba,uint32_t n,const uint8_t *p,sd_write_poll_fn poll,void *user)
{for(uint32_t i=0;i<n;i++){if(poll && poll(user))return -1;if(sd_write_sector(lba+i,p+512u*i))return -1;}return 0;}
static void payload(const item_t *p)
{
 char path[4096];snprintf(path,sizeof(path),"%s/%s",directory,p->name);
 int f=open(path,O_RDONLY);check(f>=0,"payload file");
 check(read(f,(void *)(uintptr_t)p->address,p->bytes)==(ssize_t)p->bytes,"payload read");close(f);
}
uint32_t pn03_xmodem_receive(uint32_t address,uint32_t limit)
{
 for(unsigned i=0;i<INSTALL_COUNT;i++)if(address>=items[i].address && address-items[i].address<items[i].bytes){
  uint32_t offset=address-items[i].address,n=items[i].bytes-offset;if(n>65536u)n=65536u;
  check(limit==((n+1023u)&~1023u),"XMODEM exact slice limit");
  char path[4096];snprintf(path,sizeof(path),"%s/%s",directory,items[i].name);int f=open(path,O_RDONLY);check(f>=0,"slice source");
  check(pread(f,(void *)(uintptr_t)address,n,offset)==(ssize_t)n,"slice read");close(f);received++;
  if(!strcmp(scenario,"uart-corrupt"))((uint8_t *)(uintptr_t)address)[0]^=1;
  return limit;
 }
 check(0,"unknown XMODEM target");return 0;
}
void console_readline(char *line,int capacity)
{
 check(capacity>=80,"line capacity");
 if(commands==0)strcpy(line,"receive");
 else if(commands==1){
  if(!strcmp(scenario,"ram-corrupt"))((uint8_t *)(uintptr_t)items[0].address)[0]^=1;
  strcpy(line,!strcmp(scenario,"wrong-cid")?"install 10000000000000000000000000000000":"install 00000000000000000000000000000000");
 }else if(commands==2)strcpy(line,"boot");
 else check(0,"command bound");
 commands++;
}
void jump_to(uint32_t entry,uint32_t a,uint32_t b)
{
 check(entry==0x01000000u && !a && !b,"installed loader entry");
 check(crc((const void *)(uintptr_t)0x81000000u,items[INSTALL_BOOT_INDEX].bytes)==items[INSTALL_BOOT_INDEX].crc,"published loader bytes");
 jumped=1;longjmp(finish,1);
}
static int rd(void *u,uint32_t lba,uint32_t n,uint8_t *p)
{(void)u;return sd_read_sectors(lba,n,p);}
static void preservation(void)
{
 const char *names[]={"xiangqi.bin","xqmodel.bin","XQBOOT.CFG","PN00BOOT.BIN","PN01BOOT.BIN","PN02BOOT.BIN"};
 fat_ro_volume_t volume;fat_ro_file_t f;uint8_t expected[1024],actual[1024];
 check(!fat_ro_mount(&volume,rd,0,INSTALL_SECTORS),"final mount");
 for(unsigned i=0;i<6;i++){
  int n=snprintf((char *)expected,sizeof(expected),"KEEP %s\n",names[i]);check(n>0,"old file literal");
  check(!fat_ro_find(&volume,names[i],&f) && f.size==(uint32_t)n,"old metadata preserved");
  check(!fat_ro_load(&volume,&f,actual,sizeof(actual),0,0) && !memcmp(actual,expected,(size_t)n),"old bytes preserved");
 }
#ifdef XINYI_REQUIRE_EXACT_VERSION
 const char *prefixes[]={"PN03","PN04","PN05"
#ifdef XINYI_TEST_KEEP_PN06
 ,"PN06"
#endif
#ifdef XINYI_TEST_KEEP_PN07
 ,"PN07"
#endif
#ifdef XINYI_TEST_KEEP_PN08
 ,"PN08"
#endif
#ifdef XINYI_TEST_KEEP_PN09
 ,"PN09"
#endif
 };
 const char *suffixes[9]={"BOOT.BIN","SBI.BIN","K.BIN","FS.BIN","NN.PFF","ATK.BIN",".DTB","UPD.GZ",".JSN"};
 for(unsigned p=0;p<sizeof(prefixes)/sizeof(prefixes[0]);p++)for(unsigned s=0;s<9;s++){
  char name[32];snprintf(name,sizeof(name),"%s%s",prefixes[p],suffixes[s]);
  int n=snprintf((char *)expected,sizeof(expected),"KEEP %s\n",name);
  check(!fat_ro_find(&volume,name,&f) && f.size==(uint32_t)n,"PN03/04/05 metadata preserved");
  check(!fat_ro_load(&volume,&f,actual,sizeof(actual),0,0) && !memcmp(actual,expected,(size_t)n),"PN03/04/05 bytes preserved");
 }
#ifdef XINYI_TEST_KEEP_PN06
 check(!fat_ro_find(&volume,"PN06.SHA",&f) && f.size==14,"PN06 SHA metadata preserved");
 check(!fat_ro_load(&volume,&f,actual,sizeof(actual),0,0) && !memcmp(actual,"KEEP PN06.SHA\n",14),"PN06 SHA bytes preserved");
#endif
#ifdef XINYI_TEST_KEEP_PN07
 check(!fat_ro_find(&volume,"PN07.SHA",&f) && f.size==14,"PN07 SHA metadata preserved");
 check(!fat_ro_load(&volume,&f,actual,sizeof(actual),0,0) && !memcmp(actual,"KEEP PN07.SHA\n",14),"PN07 SHA bytes preserved");
#endif
#ifdef XINYI_TEST_KEEP_PN08
 check(!fat_ro_find(&volume,"PN08.SHA",&f) && f.size==14,"PN08 SHA metadata preserved");
 check(!fat_ro_load(&volume,&f,actual,sizeof(actual),0,0) && !memcmp(actual,"KEEP PN08.SHA\n",14),"PN08 SHA bytes preserved");
#endif
#ifdef XINYI_TEST_KEEP_PN09
 check(!fat_ro_find(&volume,"PN09.SHA",&f) && f.size==14,"PN09 SHA metadata preserved");
 check(!fat_ro_load(&volume,&f,actual,sizeof(actual),0,0) && !memcmp(actual,"KEEP PN09.SHA\n",14),"PN09 SHA bytes preserved");
#endif
#endif
 if(jumped)for(unsigned i=0;i<INSTALL_COUNT;i++){
  check(!fat_ro_find(&volume,items[i].name,&f) && f.size==items[i].bytes,"new metadata");
  check(!fat_ro_load(&volume,&f,(void *)(uintptr_t)items[i].address,items[i].bytes,0,0),"new readback");
  check(crc((const void *)(uintptr_t)items[i].address,items[i].bytes)==items[i].crc,"all new CRCs");
 }
}
static void map(uint32_t address,uint32_t bytes)
{check(mmap((void *)(uintptr_t)address,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0)==(void *)(uintptr_t)address,"mapping");}
int main(int argc,char **argv)
{
 check(argc==5,"arguments");scenario=argv[1];directory=argv[3];disk=open(argv[2],O_RDWR);check(disk>=0,"fixture disk");
 map(0x1fe00000u,0x20000u);map(0x1c000000u,0x20000u);map(0x04000000u,0x200000u);
 map(0x01000000u,0x100000u);map(0x81000000u,0x100000u);
 for(unsigned i=0;i<INSTALL_COUNT;i++)map(items[i].address,(items[i].bytes+4095u)&~4095u);
 int rom=open(argv[4],O_RDONLY);check(rom>=0,"ROM input");check(read(rom,(void *)(uintptr_t)0x1c000000u,0x20000)==0x20000,"ROM read");close(rom);
 REG32(SYS_BASE)=SYS_ID_VALUE;REG32(CPU_HZ_REG)=60000000u;REG32(SYS_HZ_REG)=REG32(TIMEBASE_HZ_REG)=49500000u;
 REG32(0x1fe10000u)=0x50464e31u;REG32(0x1fe10040u)=0x56333231u;
#ifdef XINYI_REQUIRE_EXACT_VERSION
 REG32(0x1fe1006cu)=XINYI_REQUIRE_EXACT_VERSION;
 if(!strcmp(scenario,"old-exact"))REG32(0x1fe1006cu)=0x00010000u;
 if(!strcmp(scenario,"wrong-exact"))REG32(0x1fe1006cu)=0x00010002u;
 const uint32_t busy_regs[5]={0x1fe1000cu,0x1fe10044u,0x1fe1010cu,0x1fe1018cu,0x1fe1008cu};
 if(!strncmp(scenario,"engine-busy-",12) && scenario[12]>='0' && scenario[12]<='4')
  REG32(busy_regs[scenario[12]-'0'])=1;
#endif
 REG32(CAMERA_BASE+CAMERA_REG_STATUS)=CAMERA_STATUS_IDLE;
 info.sector_count=INSTALL_SECTORS;info.high_capacity=1;info.bus_width=4;
 if(!strcmp(scenario,"clock"))REG32(CPU_HZ_REG)=80000000u;
 if(!strcmp(scenario,"camera-busy"))REG32(CAMERA_BASE+CAMERA_REG_STATUS)|=CAMERA_STATUS_WRITER_BUSY;
 if(!strcmp(scenario,"rom"))REG32(0x1c000000u)^=1;
 if(!strcmp(scenario,"ram-reuse"))for(unsigned i=0;i<INSTALL_COUNT;i++)payload(&items[i]);
 if(!setjmp(finish))check(pn03_install_main()!=0,"failure return");
 int success=!strcmp(scenario,"pass") || !strcmp(scenario,"existing") || !strcmp(scenario,"ram-reuse") || !strcmp(scenario,"slow-big-pair");
 check(jumped==success,"jump disposition");
 if(success)check(!failed && (!strcmp(scenario,"existing")?!writes:writes>100),"successful write disposition");
 else if(strcmp(scenario,"clock") && strcmp(scenario,"rom") && strcmp(scenario,"camera-busy") &&
         strcmp(scenario,"old-exact") && strcmp(scenario,"wrong-exact") && strncmp(scenario,"engine-busy-",12))check(failed,"explicit failure marker");
 if(!strcmp(scenario,"ram-reuse"))check(!received,"full RAM CRC reuse avoids retransmission");
 if(!strcmp(scenario,"clock") || !strcmp(scenario,"rom") || !strcmp(scenario,"camera-busy") ||
    !strcmp(scenario,"old-exact") || !strcmp(scenario,"wrong-exact") || !strncmp(scenario,"engine-busy-",12))check(!writes && !reads && !initializations,"reject before SD");
 else if(strcmp(scenario,"write-fail") && strcmp(scenario,"write-swap") && strcmp(scenario,"stalled-big-file"))check(success || !writes,"preflight before writes");
 if(!strcmp(scenario,"stalled-big-file"))check(failed && !repair && committed_pairs==2,"file timeout keeps earlier pairs and cleans incomplete pair");
 if(!strcmp(scenario,"write-swap"))check(repair && fault && !after_fault,"no rollback on swapped CID");
 if(strcmp(scenario,"write-swap"))preservation();
 printf("INSTALL_TEST_PASS %s writes=%u received=%d reads=%u\n",scenario,writes,received,reads);close(disk);return 0;
}
