#include "soc.h"
#include "sd.h"
#include "fat_ro.h"
#include "xq_sha256.h"
#include "expected.h"
static fat_ro_volume_t volume;
static int reader(void *user,uint32_t lba,uint32_t count,uint8_t *out){(void)user;return sd_read_sectors(lba,count,out);}
static int progress(void *user,uint32_t done,uint32_t total){(void)user;(void)total;if(done==0||(done&0xffffffu)==0){console_puts("SD8_PROGRESS bytes=");console_dec(done);console_putc('\n');}return 0;}
static int same(const char *a,const char *b){while(*a&&*a==*b){a++;b++;}return *a==*b;}
static int fail(const char *why,int error){console_puts("SD8_READONLY_FAIL reason=");console_puts(why);console_puts(" code=");console_hex((uint32_t)error);console_putc('\n');return 1;}
int main(void){
 unsigned i;int rc;fat_ro_file_t file;char hex[65];const sd_card_info_t *card;void *buffer=(void *)(uintptr_t)0x03000000u;
 console_puts("SD8_READONLY_BEGIN cpu=");console_dec(REG32(CPU_HZ_REG));console_putc('\n');
 if(REG32(CPU_HZ_REG)!=120000000u||REG32(SYS_HZ_REG)!=49500000u||!ddr_range_valid(0x03000000u,0x08000000u))return fail("clock-or-ddr-range",0);
 rc=sd_init();if(rc)return fail("sd-init",rc);card=sd_card_info();
 console_puts("SD8_CID ");for(i=0;i<4;i++)console_hex(card->cid[i]);console_puts(" sectors=");console_dec(card->sector_count);console_putc('\n');
 rc=fat_ro_mount(&volume,reader,0,card->sector_count);if(rc)return fail("mount",rc);
 for(i=0;i<8;i++){
  rc=fat_ro_find(&volume,files[i].name,&file);if(rc)return fail("find",rc);
  if(file.size!=files[i].bytes)return fail("size",(int)i);
  console_puts("SD8_LOADING ");console_puts(files[i].name);console_putc('\n');
  rc=fat_ro_load(&volume,&file,buffer,0x08000000u,progress,0);if(rc)return fail("read",rc);
  xq_sha256_hex(buffer,file.size,hex);
  console_puts("SD8_FILE name=");console_puts(files[i].name);console_puts(" bytes=");console_dec(file.size);console_puts(" sha256=");console_puts(hex);console_putc('\n');
  if(!same(hex,files[i].digest))return fail("sha256",(int)i);
 }
 sd_release();console_puts("SD8_READONLY_SHA256_PASS files=8\n");return 0;
}
