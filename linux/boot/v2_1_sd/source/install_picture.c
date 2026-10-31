/* One-shot, explicitly invoked SD deployment in M mode. No Flash access. */
#include "soc.h"
#include "sd.h"
#include "fat_camera.h"
#include "crc32_fast.h"
#include "console_line.h"
#include "picture_install_payloads.h"
#include <string.h>

typedef struct {const char *name,*short_name;uint32_t address,bytes,crc;} item_t;
static const item_t items[4]=INSTALL_PAYLOADS;
static fatcam_t card;
static uint32_t work[FATCAM_MAX_CLUSTERS],owner_cid[4],start;
static uint8_t batch[4096] __attribute__((aligned(4)));
static int io_failed;
static int equal(const char *a,const char *b)
{while(*a&&*a==*b){a++;b++;}return *a==*b;}

static int rd(void *u,uint32_t lba,uint32_t count,uint8_t *b)
{int r;(void)u;r=sd_read_sectors(lba,count,b);if(r)io_failed=1;return r;}
static int wr(void *u,uint32_t lba,const uint8_t *b)
{int r;(void)u;r=sd_write_sector(lba,b);if(r)io_failed=1;return r;}
static int poll(void *u,uint32_t done,uint32_t total,int cleanup)
{
 (void)u;(void)done;(void)total;
 if(!sd_card_raw_present())return FC_IO;
 if(!cleanup&&console_getc_timeout(1u)==27)return FC_CANCEL;
 return (uint32_t)(read_mtime_ticks32()-start)>TIMEBASE_HZ*60u?FC_TIMEOUT:0;
}
static int batch_poll(void *u){return poll(u,0,0,0);}
static int batch_wr(void *u,uint32_t lba,uint32_t count,const uint8_t *b)
{int r;(void)u;r=sd_write_sectors(lba,count,b,batch_poll,0);if(r)io_failed=1;return r?FC_IO:0;}
static void print_cid(void)
{
 unsigned i,j;console_puts("SD_INSTALL_CID=");
 for(i=0;i<4;i++)for(j=0;j<8;j++)console_putc("0123456789abcdef"[(owner_cid[i]>>(28-4*j))&15u]);
 console_puts(" sectors=");console_dec(sd_card_info()->sector_count);
 console_puts(" partition_lba=");console_dec(card.volume.partition_lba);console_putc('\n');
}
static int same_cid(const char *s)
{
 unsigned i,j;
 if(!s)return 0;
 for(i=0;i<4;i++)for(j=0;j<8;j++)
  if(*s++!="0123456789abcdef"[(owner_cid[i]>>(28-4*j))&15u])return 0;
 return *s==0;
}
static int mount(void)
{
 const sd_card_info_t *info;int r;
 start=read_mtime_ticks32();io_failed=0;r=sd_init();if(r)return r;
 info=sd_card_info();
 if(info->sector_count!=INSTALL_MEDIA_SECTORS||!info->high_capacity||info->bus_width!=4)return FC_FS;
 memcpy(owner_cid,info->cid,sizeof(owner_cid));
 r=fatcam_open(&card,rd,wr,0,info->sector_count,work,poll);if(r)return r;
 if(card.volume.partition_lba!=INSTALL_PARTITION_LBA)return FC_FS;
 return fatcam_set_batch(&card,batch_wr,batch,8);
}
static int receive(void)
{
 unsigned i;
 for(i=0;i<4;i++){
  uint32_t got,actual;const item_t *p=&items[i];
  console_puts("SD_INSTALL_RECEIVE ");console_puts(p->name);console_putc('\n');
  got=xmodem_receive(p->address,(p->bytes+1023u)&~1023u);
  actual=crc32_fast(0xffffffffu,(const void *)(uintptr_t)p->address,p->bytes)^0xffffffffu;
  if(got!=((p->bytes+1023u)&~1023u)||actual!=p->crc)return FC_CORRUPT;
  console_puts("SD_INSTALL_RAM_CRC_PASS ");console_puts(p->name);console_putc('\n');
 }
 return 0;
}
static int baseline(void)
{
 static const item_t old[2]={{"brfs2.bin",0,0x04000000u,8227328u,0xb6f3cce0u},
                            {"br.dtb",0,0x04000000u,2335u,0xcf189f13u}};
 unsigned i;int r;
 for(i=0;i<2;i++){
  fat_ro_file_t file;const item_t *p=&old[i];
  r=fat_ro_find(&card.volume,p->name,&file);if(r||file.size!=p->bytes)return FC_CORRUPT;
  r=fat_ro_load(&card.volume,&file,(void *)(uintptr_t)p->address,p->bytes,0,0);if(r)return r;
  if((crc32_fast(0xffffffffu,(const void *)(uintptr_t)p->address,p->bytes)^0xffffffffu)!=p->crc)return FC_CORRUPT;
  console_puts("SD_BASELINE_CRC_PASS ");console_puts(p->name);console_putc('\n');
 }
 return 0;
}
static int install(const char *cid)
{
 unsigned i,f;int r;uint32_t expected_cid[4];
 if(!same_cid(cid))return FC_CORRUPT;
 /* Reception can take minutes. Re-read CID and geometry after the transfer,
  * before touching FAT, so a card swapped during reception is rejected. */
 memcpy(expected_cid,owner_cid,sizeof(expected_cid));r=mount();if(r)return r;
 if(memcmp(expected_cid,owner_cid,sizeof(expected_cid))||!same_cid(cid))return FC_CORRUPT;
 r=baseline();if(r)return r;
 /* Verify every staged input and every destination's absence before the first
  * write. A partial previous deployment is reported; it is never overwritten. */
 for(i=0;i<4;i++){
  fat_ro_file_t existing;const item_t *p=&items[i];
  if((crc32_fast(0xffffffffu,(const void *)(uintptr_t)p->address,p->bytes)^0xffffffffu)!=p->crc)return FC_CORRUPT;
  r=fat_ro_find(&card.volume,p->name,&existing);
  if(r!=FAT_RO_ERR_NOT_FOUND)return FC_CORRUPT;
 }
 for(i=0;i<4;i+=2){
  start=read_mtime_ticks32();
  r=fatcam_begin_root_pair(&card,items[i].short_name,items[i].bytes,
                           items[i+1].short_name,items[i+1].bytes);
  if(r)return r;
  for(f=0;f<2;f++){
   const item_t *p=&items[i+f];
   r=fatcam_write(&card,f,(const uint8_t *)(uintptr_t)p->address,p->bytes);if(r)return r;
   r=fatcam_finish(&card,f,p->crc);if(r)return r;
   console_puts("SD_INSTALL_READBACK_CRC_PASS ");console_puts(p->name);
   console_puts(" bytes=");console_dec(p->bytes);console_puts(" crc=");console_hex(p->crc);console_putc('\n');
  }
  r=fatcam_commit_root_pair(&card);if(r)return r;
  console_puts("SD_INSTALL_PAIR_COMMITTED\n");
 }
 return baseline();
}
static int bootlinux(void)
{
 const item_t *p=&items[2];fat_ro_file_t file;int r;
 r=fat_ro_find(&card.volume,p->name,&file);if(r||file.size!=p->bytes)return FC_CORRUPT;
 r=fat_ro_load(&card.volume,&file,(void *)(uintptr_t)0x01000000u,p->bytes,0,0);if(r)return r;
 if((crc32_fast(0xffffffffu,(const void *)(uintptr_t)0x01000000u,p->bytes)^0xffffffffu)!=p->crc)return FC_CORRUPT;
 sd_release();console_puts("SD_INSTALL_BOOT_LOADER_CRC_PASS\n");jump_to(0x01000000u,0,0);return 0;
}
int main(void)
{
 char line[80];int r=mount();
 if(r){console_puts("SD_INSTALL_FAIL mount\n");return 1;}
 print_cid();console_puts("SD_INSTALL_READY create-only; commands: receive, install <CID>, bootlinux\n");
 for(;;){
  console_puts("install> ");console_readline(line,sizeof(line));r=0;
  if(equal(line,"receive"))r=receive();
  else if(!memcmp(line,"install ",8))r=install(line+8);
  else if(equal(line,"bootlinux"))r=bootlinux();
  else if(equal(line,"console")){sd_release();jump_to(0x1c000000u,0,0);return 0;}
  else if(line[0]){console_puts("SD_INSTALL_UNKNOWN_COMMAND\n");continue;}
  else continue;
  if(r){
   int rollback=0;console_puts("SD_INSTALL_FAIL code=");console_dec((uint32_t)-r);console_putc('\n');
   if(card.dirty||card.staged||card.allocated){
    if(io_failed){
     uint32_t old[4];memcpy(old,owner_cid,sizeof(old));
     if(sd_init()||memcmp(old,sd_card_info()->cid,sizeof(old))){console_puts("SD_INSTALL_REPAIR_REQUIRED\n");return 1;}
    }
    start=read_mtime_ticks32();rollback=fatcam_abort(&card);
   }
   if(rollback)console_puts("SD_INSTALL_REPAIR_REQUIRED\n");
   /* Stop after any failure. A second command must never retry an uncertain
    * write or accidentally continue a partially installed pair. */
   sd_release();return 1;
  }
  console_puts("SD_INSTALL_COMMAND_PASS\n");
 }
}
