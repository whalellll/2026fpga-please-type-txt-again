/* Explicit PN03 create-only deployment. Original CPU60 SD transport and the
 * private, tested root-pair writer. No selector update or Flash code. */
#include "soc.h"
#include "sd.h"
#include "fat_camera.h"
#include "crc32_fast.h"
#include "console_line.h"
#include "install_payloads.h"
#include "target.h"
#include "camera.h"
#include <string.h>
#if (INSTALL_COUNT % 2u) != 0u
#error "Create-only root-pair installation requires an even payload count"
#endif
int xqns_begin_root_pair(fatcam_t *,const char *,uint32_t,const char *,uint32_t);
uint32_t pn03_xmodem_receive(uint32_t,uint32_t);
#define UART_RETRYABLE 10

static fatcam_t card;
static uint32_t clusters[FATCAM_MAX_CLUSTERS],owner[4],start;
static uint8_t batch[4096] __attribute__((aligned(4)));
static int io_failed;
static int timeout_reported;
static const char *old_names[]={"xiangqi.bin","xqmodel.bin","XQBOOT.CFG","PN00BOOT.BIN","PN01BOOT.BIN","PN02BOOT.BIN"};
static struct {uint32_t bytes,crc;int exists;} old_files[6];
static int equal(const char *a,const char *b)
{while(*a && *a==*b){a++;b++;}return *a==*b;}
static int prefix(const char *a,const char *b)
{while(*b)if(*a++!=*b++)return 0;return 1;}

static uint32_t crc(const void *p,uint32_t n)
{return crc32_fast(0xffffffffu,p,n)^0xffffffffu;}
static int rd(void *u,uint32_t lba,uint32_t n,uint8_t *p)
{int r;(void)u;r=sd_read_sectors(lba,n,p);if(r)io_failed=1;return r;}
static int wr(void *u,uint32_t lba,const uint8_t *p)
{int r;(void)u;r=sd_write_sector(lba,p);if(r)io_failed=1;return r;}
static int poll(void *u,uint32_t done,uint32_t total,int cleanup)
{
 (void)u;(void)done;(void)total;
 if(!sd_card_raw_present())return FC_IO;
 if(!cleanup && console_getc_timeout(1u)==27)return FC_CANCEL;
 if((uint32_t)(read_mtime_ticks32()-start)>TIMEBASE_HZ*60u){
  if(!timeout_reported){console_puts("PN03_OPERATION_TIMEOUT limit_seconds=60\n");timeout_reported=1;}
  return FC_TIMEOUT;
 }
 return 0;
}
static int batch_poll(void *u){return poll(u,0,0,0);}
static int batch_wr(void *u,uint32_t lba,uint32_t n,const uint8_t *p)
{int r;(void)u;r=sd_write_sectors(lba,n,p,batch_poll,0);if(r)io_failed=1;return r?FC_IO:0;}
static int load_poll(void *u,uint32_t done,uint32_t total)
{return poll(u,done,total,0);}
static int same_cid(const char *s)
{
 unsigned i,j;if(!s)return 0;
 for(i=0;i<4;i++)for(j=0;j<8;j++)if(*s++!="0123456789abcdef"[(owner[i]>>(28-4*j))&15u])return 0;
 return *s==0;
}
static int target(void)
{
#ifdef XINYI_REQUIRE_EXACT_VERSION
 if(REG32(0x1fe1006cu)!=XINYI_REQUIRE_EXACT_VERSION ||
    ((REG32(0x1fe1000cu)|REG32(0x1fe10044u)|REG32(0x1fe1010cu)|
      REG32(0x1fe1018cu)|REG32(0x1fe1008cu))&1u))return 0;
#endif
 return REG32(SYS_BASE)==SYS_ID_VALUE && REG32(CPU_HZ_REG)==60000000u &&
  REG32(SYS_HZ_REG)==49500000u && REG32(TIMEBASE_HZ_REG)==49500000u &&
  REG32(0x1fe10000u)==0x50464e31u && REG32(0x1fe10040u)==0x56333231u &&
  !(REG32(CAMERA_BASE+CAMERA_REG_CONTROL)&CAMERA_CONTROL_ENABLE) &&
  !(REG32(CAMERA_BASE+CAMERA_REG_STATUS)&(CAMERA_STATUS_ENABLED|CAMERA_STATUS_WRITER_BUSY|CAMERA_STATUS_STOPPING)) &&
  (REG32(CAMERA_BASE+CAMERA_REG_STATUS)&CAMERA_STATUS_IDLE) &&
  crc((const void *)(uintptr_t)XINYI_ROM_CODE_START,XINYI_ROM_CODE_BYTES)==XINYI_ROM_CODE_CRC;
}
static int mount(int preserve)
{
 uint32_t previous[4];const sd_card_info_t *info;int r;
 memcpy(previous,owner,sizeof(owner));start=read_mtime_ticks32();io_failed=0;
 r=sd_init();if(r)return r;info=sd_card_info();
 if(info->sector_count!=INSTALL_SECTORS || !info->high_capacity || info->bus_width!=4)return FC_FS;
 if(preserve && memcmp(previous,info->cid,sizeof(owner)))return FC_CORRUPT;
 memcpy(owner,info->cid,sizeof(owner));
 r=fatcam_open(&card,rd,wr,0,info->sector_count,clusters,poll);if(r)return r;
 if(card.volume.partition_lba!=INSTALL_PARTITION || card.volume.cluster_size_bytes!=32768u)return FC_FS;
 return fatcam_set_batch(&card,batch_wr,batch,8);
}
static void print_card(void)
{
 unsigned i,j;console_puts("PN03_INSTALL_CID=");
 for(i=0;i<4;i++)for(j=0;j<8;j++)console_putc("0123456789abcdef"[(owner[i]>>(28-4*j))&15u]);
 console_puts(" sectors=");console_dec(sd_card_info()->sector_count);
 console_puts(" partition_lba=");console_dec(card.volume.partition_lba);console_putc('\n');
}
static int baseline(int compare)
{
 unsigned i;int r;fat_ro_file_t file;
 for(i=0;i<6;i++){
  uint32_t actual=0;start=read_mtime_ticks32();
  r=fat_ro_find(&card.volume,old_names[i],&file);
  if(r && r!=FAT_RO_ERR_NOT_FOUND)return r;
  if(r==FAT_RO_ERR_NOT_FOUND){if(compare && old_files[i].exists)return FC_CORRUPT;continue;}
  if(!file.size || file.size>0x200000u)return FC_CORRUPT;
  r=fat_ro_load(&card.volume,&file,(void *)(uintptr_t)0x04000000u,file.size,load_poll,0);if(r)return r;
  actual=crc((const void *)(uintptr_t)0x04000000u,file.size);
  if(compare){if(!old_files[i].exists || old_files[i].bytes!=file.size || old_files[i].crc!=actual)return FC_CORRUPT;}
  else{old_files[i].exists=1;old_files[i].bytes=file.size;old_files[i].crc=actual;}
 }
 return old_files[0].exists && old_files[1].exists && old_files[2].exists?0:FC_CORRUPT;
}
static int read_item(item_t *p,const char *name,int required)
{
 fat_ro_file_t f;int r=fat_ro_find(&card.volume,name,&f);
 if(r==FAT_RO_ERR_NOT_FOUND)return required?FC_CORRUPT:2;
 if(r)return r;
 if(f.size!=p->bytes)return required?FC_CORRUPT:2;
 start=read_mtime_ticks32();r=fat_ro_load(&card.volume,&f,(void *)(uintptr_t)p->address,p->bytes,load_poll,0);if(r)return r;
 if(crc((const void *)(uintptr_t)p->address,p->bytes)!=p->crc)return required?FC_CORRUPT:2;
 return 0;
}
static int probe(void)
{
 unsigned i,j;int r;fat_ro_file_t f;
 r=baseline(0);if(r)return r;
 for(i=0;i<INSTALL_COUNT;i++){
  item_t *p=&items[i];r=fat_ro_find(&card.volume,p->name,&f);
  if(!r){r=read_item(p,p->name,1);if(r)return r;p->ready=p->exists=1;console_puts("PN03_EXISTING_MATCH ");console_puts(p->name);console_putc('\n');}
  else if(r!=FAT_RO_ERR_NOT_FOUND)return r;
  else if(crc((const void *)(uintptr_t)p->address,p->bytes)==p->crc){
   /* Recover completed, fully checked RAM reception across installer reloads.
    * No dirty/partial range is accepted, and install checks every CRC again. */
   p->ready=1;console_puts("PN03_RAM_REUSE_MATCH ");console_puts(p->name);console_putc('\n');
  }
  else{
   /* Salvage a verified prefix after a host/receiver interruption. Every
    * accepted slice is checked against its generated immutable checksum. */
   while(p->offset<p->bytes){
    uint32_t n=p->bytes-p->offset;if(n>65536u)n=65536u;
    if(crc((const void *)(uintptr_t)(p->address+p->offset),n)!=p->slice_crc[p->offset/65536u])break;
    p->offset+=n;
   }
   if(p->offset){console_puts("PN03_RAM_PREFIX_MATCH ");console_puts(p->name);console_puts(" bytes=");console_dec(p->offset);console_putc('\n');}
   else for(j=0;j<4 && p->aliases[j];j++){
   r=read_item(p,p->aliases[j],0);if(r && r!=2)return r;
   if(!r){p->ready=1;console_puts("PN03_REUSE_MATCH ");console_puts(p->name);console_puts(" source=");console_puts(p->aliases[j]);console_putc('\n');break;}
   }
  }
  if(!p->ready){console_puts("PN03_NEED_UART ");console_puts(p->name);console_putc('\n');}
 }
 /* Root-pair transactions are all-or-nothing. Never overwrite a partial or
  * conflicting namespace; preserve it for an explicit recovery plan. */
 for(i=0;i<INSTALL_COUNT;i+=2)if(items[i].exists!=items[i+1].exists)return FC_CORRUPT;
 return 0;
}
static int receive(void)
{
 unsigned i;for(i=0;i<INSTALL_COUNT;i++){
  item_t *p=&items[i];if(p->ready)continue;
  while(p->offset<p->bytes){
   uint32_t n=p->bytes-p->offset,received;if(n>65536u)n=65536u;
   console_puts("PN03_RECEIVE_CHUNK ");console_puts(p->name);console_puts(" offset=");console_dec(p->offset);console_puts(" bytes=");console_dec(n);console_putc('\n');
   received=pn03_xmodem_receive(p->address+p->offset,(n+1023u)&~1023u);
   if(received!=((n+1023u)&~1023u) || crc((const void *)(uintptr_t)(p->address+p->offset),n)!=p->slice_crc[p->offset/65536u])return UART_RETRYABLE;
   p->offset+=n;
  }
  if(crc((const void *)(uintptr_t)p->address,p->bytes)!=p->crc)return FC_CORRUPT;
  p->ready=1;console_puts("PN03_RAM_CRC_PASS ");console_puts(p->name);console_putc('\n');
 }
 return 0;
}
static int install(const char *cid)
{
 unsigned i,j;int r;fat_ro_file_t file;
 if(!same_cid(cid))return FC_CORRUPT;
 r=mount(1);if(r || !same_cid(cid))return r?r:FC_CORRUPT;
 r=baseline(1);if(r)return r;
 /* Validate every RAM CRC and every target's state before the first write. */
 for(i=0;i<INSTALL_COUNT;i++){
  item_t *p=&items[i];if(!p->ready || crc((const void *)(uintptr_t)p->address,p->bytes)!=p->crc)return FC_CORRUPT;
  r=fat_ro_find(&card.volume,p->name,&file);
  if(p->exists){if(r || file.size!=p->bytes)return FC_CORRUPT;}
  else if(r!=FAT_RO_ERR_NOT_FOUND)return FC_CORRUPT;
 }
 for(i=0;i<INSTALL_COUNT;i+=2){
  if(items[i].exists)continue;
  r=mount(1);if(r || !same_cid(cid))return r?r:FC_CORRUPT;
  start=read_mtime_ticks32();
  r=xqns_begin_root_pair(&card,items[i].short_name,items[i].bytes,items[i+1].short_name,items[i+1].bytes);if(r)return r;
  for(j=0;j<2;j++){
   /* Each bounded file operation has its own deadline. A verified 68 MB
    * file must not consume the 34 MB partner's entire write/readback budget. */
   item_t *p=&items[i+j];start=read_mtime_ticks32();
   r=fatcam_write(&card,j,(const uint8_t *)(uintptr_t)p->address,p->bytes);if(r)return r;
   r=fatcam_finish(&card,j,p->crc);if(r)return r;
   console_puts("PN03_READBACK_CRC_PASS ");console_puts(p->name);console_putc('\n');
  }
  start=read_mtime_ticks32();r=fatcam_commit_root_pair(&card);if(r)return r;
  items[i].exists=items[i+1].exists=1;console_puts("PN03_PAIR_COMMITTED\n");
 }
 r=baseline(1);if(r)return r;
 console_puts("PN03_OLD_BOOT_FILES_AND_SELECTOR_PRESERVED\n");return 0;
}
static int boot(void)
{
 item_t *p=&items[INSTALL_BOOT_INDEX];uint32_t i;int r=read_item(p,p->name,1);if(r)return r;
 volatile uint32_t *uncached=(volatile uint32_t *)(uintptr_t)0x81000000u;
 const uint32_t *cached=(const uint32_t *)(uintptr_t)0x01000000u;
 memcpy((void *)(uintptr_t)0x01000000u,(const void *)(uintptr_t)p->address,p->bytes);
 for(i=0;i<p->bytes/4u;i++)uncached[i]=cached[i];
#ifdef __riscv
 __asm__ volatile("fence iorw,iorw":::"memory");
#endif
 if(crc((const void *)uncached,p->bytes)!=p->crc)return FC_CORRUPT;
 sd_release();console_puts("PN03_INSTALLED_LOADER_CRC_PASS\n");jump_to(0x01000000u,0,0);return FC_CORRUPT;
}
static int stop(int result)
{
 int rollback=0;console_puts("PN03_INSTALL_FAIL code=");console_dec((uint32_t)-result);console_putc('\n');
 if(card.dirty || card.staged || card.allocated){
  if(io_failed && (sd_init() || memcmp(owner,sd_card_info()->cid,sizeof(owner)))){
   console_puts("PN03_REPAIR_REQUIRED\n");sd_release();return 1;
  }
  start=read_mtime_ticks32();rollback=fatcam_abort(&card);
 }
 if(rollback)console_puts("PN03_REPAIR_REQUIRED\n");
 else console_puts("PN03_FAILURE_CLEANUP_COMPLETE\n");
 sd_release();return 1;
}
int main(void)
{
 char line[80];int r;
 console_puts("PN03_INSTALL_BEGIN create_only=1 flash=0\n");
 if(!target()){console_puts("PN03_INSTALL_TARGET_REJECTED\n");return 1;}
 r=mount(0);if(r)return stop(r);print_card();
 r=probe();if(r)return stop(r);
 console_puts("PN03_PROBE_PASS\n");
 for(;;){
  console_puts("pn03> ");console_readline(line,sizeof(line));
  if(equal(line,"receive"))r=receive();
  else if(prefix(line,"install "))r=install(line+8);
  else if(equal(line,"boot"))r=boot();
  else if(equal(line,"console")){sd_release();jump_to(0x1c000000u,0,0);return 1;}
  else if(!line[0])continue;
  else{console_puts("PN03_UNKNOWN_COMMAND\n");continue;}
  if(r==UART_RETRYABLE){console_puts("PN03_UART_RETRYABLE no_sd_write=1\n");continue;}
  if(r)return stop(r);
  console_puts("PN03_COMMAND_PASS\n");
 }
}
