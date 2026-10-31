/* Explicit, backed-up adaptation of the frozen ROM's xqboot entry. */
#include "soc.h"
#include "sd.h"
#include "fat_camera.h"
#include "fat_boot_prefix.h"
#include "crc32_fast.h"
#include "console_line.h"
#include "picture_console_boot.h"
#include <string.h>
static fatcam_t card;
static uint32_t work[FATCAM_MAX_CLUSTERS],start;
static uint8_t batch[4096] __attribute__((aligned(4)));
static const uint32_t expected_cid[4]=CONSOLE_CARD_CID;
/* Eleven FAT bytes plus the C literal terminator; reject padding mistakes. */
static const char backup_short[]=CONSOLE_BACKUP_SHORT;
static const char loader_short[]=CONSOLE_LOADER_SHORT;
typedef char backup_short_size_check[sizeof(backup_short)==12?1:-1];
typedef char loader_short_size_check[sizeof(loader_short)==12?1:-1];
static int rd(void *u,uint32_t lba,uint32_t count,uint8_t *b)
{(void)u;return sd_read_sectors(lba,count,b);}
static int wr(void *u,uint32_t lba,const uint8_t *b)
{(void)u;return sd_write_sector(lba,b);}
static int poll(void *u,uint32_t done,uint32_t total,int cleanup)
{(void)u;(void)done;(void)total;(void)cleanup;return (uint32_t)(read_mtime_ticks32()-start)>TIMEBASE_HZ*60u?FC_TIMEOUT:0;}
static int batch_wr(void *u,uint32_t lba,uint32_t count,const uint8_t *b)
{(void)u;return sd_write_sectors(lba,count,b,0,0);}
static int mount(void)
{
 const sd_card_info_t *info;int r;start=read_mtime_ticks32();r=sd_init();if(r)return r;
 info=sd_card_info();
 if(info->sector_count!=62333952u||info->bus_width!=4||!info->high_capacity||
    memcmp(info->cid,expected_cid,sizeof(expected_cid)))return FC_CORRUPT;
 r=fatcam_open(&card,rd,wr,0,info->sector_count,work,poll);if(r)return r;
 if(card.volume.partition_lba!=32u||card.volume.cluster_size_bytes!=32768u)return FC_CORRUPT;
 return fatcam_set_batch(&card,batch_wr,batch,8);
}
static uint32_t crc(const void *p,uint32_t n){return crc32_fast(0xffffffffu,p,n)^0xffffffffu;}
static int load(const char *name,fat_ro_file_t *file,uint32_t address,uint32_t size)
{
 int r=fat_ro_find(&card.volume,name,file);if(r)return r;
 if(file->size!=size)return FC_CORRUPT;
 return fat_ro_load(&card.volume,file,(void *)(uintptr_t)address,file->size,0,0);
}
static int replace(const char *name,fat_ro_file_t *file,const uint8_t *image,uint32_t expected)
{
 fat_ro_file_t again;int r;
 r=fat_boot_patch_prefix(&card.volume,file,image,CONSOLE_BOOT_BYTES,wr,0);if(r)return r;
 r=load(name,&again,0x05000000u,file->size);if(r)return r;
 if(again.first_cluster!=file->first_cluster||crc((const void *)(uintptr_t)0x05000000u,again.size)!=expected)return FC_IO;
 console_puts("SD_CONSOLE_IMAGE_READBACK_PASS name=");console_puts(name);
 console_puts(" bytes=");console_dec(again.size);
 console_puts(" crc=");console_hex(expected);console_putc('\n');return 0;
}
static int ensure_model(void)
{
 fat_ro_file_t file;int r=fat_ro_find(&card.volume,"xqmodel.bin",&file);
 if(sizeof(console_model)!=207792u||crc(console_model,207792u)!=0x51f2d900u)return FC_CORRUPT;
 if(r==FAT_RO_ERR_NOT_FOUND){
  r=fatcam_begin_root_pair(&card,"XQMODEL BIN",207792u,"P18XQ   JSN",2);if(r)return r;
  r=fatcam_write(&card,0,(const uint8_t *)console_model,207792u);if(r)return r;
  r=fatcam_write(&card,1,(const uint8_t *)"{}",2);if(r)return r;
  r=fatcam_finish(&card,0,0x51f2d900u);if(r)return r;
  r=fatcam_finish(&card,1,crc("{}",2));if(r)return r;
  r=fatcam_commit_root_pair(&card);if(r)return r;
 }else if(r)return r;
 r=load("xqmodel.bin",&file,0x0f000000u,207792u);if(r)return r;
 if(crc((const void *)(uintptr_t)0x0f000000u,file.size)!=0x51f2d900u)return FC_CORRUPT;
 console_puts("SD_CONSOLE_ROM_MODEL_PASS crc=0x51f2d900\n");return 0;
}
static int install(void)
{
 fat_ro_file_t file,found;uint8_t *image=(uint8_t *)(uintptr_t)0x04000000u;
 uint32_t original,boot_crc,new_crc;int r=mount();if(r)return r;
 r=ensure_model();if(r)return r;
 r=load("xiangqi.bin",&file,0x04000000u,42648u);if(r)return r;
 original=crc(image,file.size);boot_crc=crc(console_boot,CONSOLE_BOOT_BYTES);
 console_puts("SD_CONSOLE_ORIGINAL bytes=");console_dec(file.size);console_puts(" crc=");console_hex(original);console_putc('\n');
 if(fat_ro_find(&card.volume,CONSOLE_BACKUP_NAME,&found)!=FAT_RO_ERR_NOT_FOUND||
    fat_ro_find(&card.volume,CONSOLE_LOADER_NAME,&found)!=FAT_RO_ERR_NOT_FOUND)return FC_CORRUPT;
 r=fatcam_begin_root_pair(&card,backup_short,file.size,loader_short,CONSOLE_BOOT_BYTES);if(r)return r;
 r=fatcam_write(&card,0,image,file.size);if(r)return r;
 r=fatcam_write(&card,1,(const uint8_t *)console_boot,CONSOLE_BOOT_BYTES);if(r)return r;
 r=fatcam_finish(&card,0,original);if(r)return r;
 r=fatcam_finish(&card,1,boot_crc);if(r)return r;
 r=fatcam_commit_root_pair(&card);if(r)return r;
 console_puts("SD_CONSOLE_BACKUP_COMMITTED name=");console_puts(CONSOLE_BACKUP_NAME);
 console_puts(" crc=");console_hex(original);console_putc('\n');
 /* Both immutable backup and standalone Linux loader are on SD now.
  * Patch only the first cluster's prefix; preserve old file length, chain,
  * LFN/directory entry, final-sector tail and all later data. */
 memcpy(image,console_boot,CONSOLE_BOOT_BYTES);new_crc=crc(image,file.size);
 r=mount();if(r)return r; /* fresh CID immediately before changing boot data */
 r=replace("xiangqi.bin",&file,image,new_crc);if(r)return r;
 console_puts("SD_CONSOLE_INSTALL_PASS manual_command=xqboot flash_written=false\n");return 0;
}
static int restore(uint32_t expected,int mmode)
{
 fat_ro_file_t backup,file;int r=mount();if(r)return r;
 const char *name=mmode?"Image.mmode":"xiangqi.bin";
 r=load(mmode?"P17MOLD.BIN":CONSOLE_BACKUP_NAME,&backup,0x04000000u,mmode?2444544u:42648u);if(r)return r;
 if(crc((const void *)(uintptr_t)0x04000000u,backup.size)!=expected)return FC_CORRUPT;
 r=fat_ro_find(&card.volume,name,&file);if(r||file.size!=backup.size)return FC_CORRUPT;
 r=replace(name,&file,(const uint8_t *)(uintptr_t)0x04000000u,expected);if(r)return r;
 console_puts(mmode?"SD_CONSOLE_RESTORE_MMODE_PASS\n":"SD_CONSOLE_RESTORE_PASS\n");return 0;
}
static int equal(const char *a,const char *b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
int main(void)
{
 char line[80];int r=mount();if(r){console_puts("SD_CONSOLE_FAIL mount\n");return 1;}
 console_puts("SD_CONSOLE_READY exact-CID; install / restore[-mmode] <crc> / console\n");
 for(;;){
  console_puts("sdentry> ");console_readline(line,sizeof(line));
  if(equal(line,"install"))r=install();
  else if(!memcmp(line,"restore-mmode ",14)){int ok;uint32_t value=parse_u32(line+14,&ok);r=ok?restore(value,1):FC_CORRUPT;}
  else if(!memcmp(line,"restore ",8)){int ok;uint32_t value=parse_u32(line+8,&ok);r=ok?restore(value,0):FC_CORRUPT;}
  else if(equal(line,"console")){sd_release();console_puts("SD_CONSOLE_RETURN_ROM\n");jump_to(0x1c000000u,0,0);return 0;}
  else continue;
  if(r){console_puts("SD_CONSOLE_FAIL code=");console_dec((uint32_t)-r);console_putc('\n');
   if(card.dirty||card.staged){
    /* Reinitialize and match CID before bounded metadata rollback. A data
     * prefix fault leaves the committed backup available for restore. */
    if(sd_init()||memcmp(expected_cid,sd_card_info()->cid,sizeof(expected_cid))){console_puts("SD_CONSOLE_REPAIR_REQUIRED\n");return 1;}
    start=read_mtime_ticks32();if(fatcam_abort(&card))console_puts("SD_CONSOLE_REPAIR_REQUIRED\n");
   }
   return 1;
  }
 }
}
