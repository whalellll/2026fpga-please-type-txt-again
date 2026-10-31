#include "soc.h"
#include "camera.h"
#include "sd.h"
#include "fat_camera.h"
#include "png_rgb565.h"
#include "crc32_fast.h"
#include <string.h>

static fatcam_t card;
/* CPU-private data staging stays in boot BRAM; the driver copies it to MMIO.
 * The encoder and file verifier continue reading the independent snapshot. */
static uint8_t write_batch[8u*512u] __attribute__((aligned(4)));
typedef struct {uint32_t start,cleanup_start,percent,last_hud,write_bytes,cid[4];uint64_t write_cycles;int cleanup_started,verify,cancelled,io_failed,removed;} save_state_t;
static save_state_t state;
uint64_t camera_sd_time_ms(void)
{
 uint32_t hi,lo,again;
 do{hi=REG32(CLINT_MTIME+4u);lo=REG32(CLINT_MTIME);again=REG32(CLINT_MTIME+4u);}while(hi!=again);
 return (((uint64_t)hi<<32)|lo)/(TIMEBASE_HZ/1000u);
}
static int disk_read(void *u,uint32_t lba,uint32_t count,uint8_t *b)
{int r;(void)u;r=sd_read_sectors(lba,count,b);if(r){state.io_failed=1;if(r==SD_ERR_REMOVED||r==SD_ERR_NO_CARD)state.removed=1;}return r;}
static int disk_write(void *u,uint32_t lba,const uint8_t *b)
{int r;uint32_t start=read_mtime_ticks32();(void)u;r=sd_write_sector(lba,b);state.write_cycles+=(uint32_t)(read_mtime_ticks32()-start);if(r){state.io_failed=1;if(r==SD_ERR_REMOVED||r==SD_ERR_NO_CARD)state.removed=1;}else state.write_bytes+=512u;return r;}
static char *decimal(char *p,uint64_t n)
{char b[20];unsigned i=0;do{b[i++]=(char)('0'+n%10);n/=10;}while(n);while(i)*p++=b[--i];return p;}
static char *hex(char *p,uint32_t n)
{unsigned i;for(i=0;i<8;i++){*p++="0123456789abcdef"[n>>28];n<<=4;}return p;}
static char *append(char *p,const char *s){while(*s)*p++=*s++;return p;}
static int save_poll(void *u,uint32_t done,uint32_t total,int cleanup)
{
 uint32_t now=read_mtime_ticks32(),pct;int key;char msg[32],*p; (void)u;
 if(cleanup){
  if(!state.cleanup_started){state.cleanup_started=1;state.cleanup_start=now;}
  return (uint32_t)(now-state.cleanup_start)>TIMEBASE_HZ*2u?FC_TIMEOUT:0;
 }
 key=console_getc_timeout(1u);
 if(key==0x1b)state.cancelled=1;
 if(key==' ')console_puts("Camera busy; one photo at a time.\n");
 if(state.cancelled)return FC_CANCEL;
 if((uint32_t)(now-state.start)>TIMEBASE_HZ*60u)return FC_TIMEOUT;
 /* Driver polling runs much more frequently than HDMI can acknowledge text.
  * Keep key/deadline checks fast; calculate the 64-bit percentage only when
  * a progress update can actually be displayed. */
 if(state.verify||!total||(done==total&&state.percent==100u))return 0;
 if(done!=total&&(uint32_t)(now-state.last_hud)<TIMEBASE_HZ/10u)return 0;
 pct=(uint32_t)(((uint64_t)done*100u)/total);
 if(pct!=state.percent){
  p=append(msg,"SAVING ");p=decimal(p,pct);*p++='%';*p=0;
  if(camera_hud_try(msg,1)){state.percent=pct;state.last_hud=now;}
 }
 return 0;
}
static int batch_poll(void *u)
{(void)u;return save_poll(0,card.file[0].done,PNG565_BYTES,0);}
static int disk_write_batch(void *u,uint32_t lba,uint32_t count,const uint8_t *b)
{
 int r;uint32_t start=read_mtime_ticks32();(void)u;
 r=sd_write_sectors(lba,count,b,batch_poll,0);
 state.write_cycles+=(uint32_t)(read_mtime_ticks32()-start);
 if(r==SD_ERR_ABORTED)return state.cancelled?FC_CANCEL:FC_TIMEOUT;
 if(r){state.io_failed=1;if(r==SD_ERR_REMOVED||r==SD_ERR_NO_CARD)state.removed=1;return FC_IO;}
 state.write_bytes+=count*512u;return 0;
}
static int png_write(void *u,const uint8_t *b,uint32_t n){(void)u;return fatcam_write(&card,0,b,n);}
static int row_poll(void *u,uint32_t row){(void)row;return save_poll(u,card.file[0].done,PNG565_BYTES,0);}
uint32_t camera_sd_metadata(char *b,uint32_t frame,uint32_t raw_crc,uint32_t png_crc,uint64_t ms)
{
 char *p=b;
 p=append(p,"{\n  \"captured_at\": null,\n  \"clock\": \"board uptime; no RTC\",\n  \"uptime_ms\": ");p=decimal(p,ms);
 p=append(p,",\n  \"frame\": ");p=decimal(p,frame);
 p=append(p,",\n  \"width\": 1280,\n  \"height\": 720,\n  \"source\": \"CMOS2\",\n  \"pixel_format\": \"RGB565LE\",\n  \"row_order\": \"top-to-bottom\",\n  \"raw_crc32\": \"");p=hex(p,raw_crc);
 p=append(p,"\",\n  \"png_crc32\": \"");p=hex(p,png_crc);p=append(p,"\"\n}\n");*p=0;return (uint32_t)(p-b);
}
int camera_sd_save(uint32_t frame,uint32_t raw_crc,uint64_t ms)
{
 char json[384],name[13],msg[32];uint32_t length,png_crc=0,init_done,prep_done,encode_done,verify_done,end;int r,abort_r;
 const sd_card_info_t *info;
 memset(&state,0,sizeof(state));state.start=read_mtime_ticks32();state.percent=0xffffffffu;state.last_hud=state.start-TIMEBASE_HZ/10u;
 camera_hud("SD INITIALIZING",1);r=sd_init();
 if(r){camera_hud("ERROR NO SD / SD INIT",5);console_puts("SD initialization failed.\n");sd_release();return state.cancelled?1:-1;}
 info=sd_card_info();
 init_done=read_mtime_ticks32();
 memcpy(state.cid,info->cid,sizeof(state.cid));
 if(!info->high_capacity||info->bus_width!=4){camera_hud("ERROR SDHC 4BIT REQUIRED",5);sd_release();return -1;}
 /* 24 KiB workspace fits above the 0x1c2000-byte immutable snapshot, inside
  * the existing 2 MiB DMA reservation. It does not extend Linux reservations. */
 r=fatcam_open(&card,disk_read,disk_write,0,info->sector_count,
               (uint32_t *)(uintptr_t)(CAMERA_SNAPSHOT_CPU_ALIAS+0x1d0000u),save_poll);
 if(r)goto fail;
 r=fatcam_set_batch(&card,disk_write_batch,write_batch,8u);if(r)goto fail;
 length=camera_sd_metadata(json,frame,raw_crc,0,ms);
 r=fatcam_begin(&card,PNG565_BYTES,length);if(r)goto rollback;
 prep_done=read_mtime_ticks32();
 console_puts("SD writing PNG; Esc cancels after current block.\n");
 r=png565_encode((const uint8_t *)(uintptr_t)CAMERA_SNAPSHOT_CPU_ALIAS,png_write,0,row_poll,0);if(r)goto rollback;
 png_crc=card.file[0].crc^0xffffffffu;encode_done=read_mtime_ticks32();
 (void)camera_sd_metadata(json,frame,raw_crc,png_crc,ms);
 r=fatcam_write(&card,1,(const uint8_t *)json,length);if(r)goto rollback;
 state.verify=1;camera_hud("VERIFYING SD CRC",1);
 r=fatcam_finish(&card,0,png_crc);if(r)goto rollback;
 r=fatcam_finish(&card,1,crc32_fast(0xffffffffu,json,length)^0xffffffffu);if(r)goto rollback;
 verify_done=read_mtime_ticks32();
 r=fatcam_commit(&card);if(r)goto rollback;
 end=read_mtime_ticks32();
 fatcam_name(card.id,name);append(append(msg,"SAVED "),name)[0]=0;camera_hud(msg,3);
 console_puts("SD saved: /CAMERA/");console_puts(name);console_puts(" + same-name JSON; PNG CRC32=");console_hex(png_crc);console_putc('\n');
 console_puts("SD_TIMING init_ms=");console_dec((uint32_t)((uint64_t)(uint32_t)(init_done-state.start)*1000u/TIMEBASE_HZ));
 console_puts(" prep_ms=");console_dec((uint32_t)((uint64_t)(uint32_t)(prep_done-init_done)*1000u/TIMEBASE_HZ));
 console_puts(" encode_write_ms=");console_dec((uint32_t)((uint64_t)(uint32_t)(encode_done-prep_done)*1000u/TIMEBASE_HZ));
 console_puts(" verify_ms=");console_dec((uint32_t)((uint64_t)(uint32_t)(verify_done-encode_done)*1000u/TIMEBASE_HZ));
 console_puts(" commit_ms=");console_dec((uint32_t)((uint64_t)(uint32_t)(end-verify_done)*1000u/TIMEBASE_HZ));
 console_puts(" write_io_ms=");console_dec((uint32_t)(state.write_cycles*1000u/TIMEBASE_HZ));
 console_puts(" write_io_bytes=");console_dec(state.write_bytes);
 console_puts(" total_ms=");console_dec((uint32_t)((uint64_t)(uint32_t)(end-state.start)*1000u/TIMEBASE_HZ));console_putc('\n');
 sd_release();return 0;
rollback:
 /* The driver releases a failed session. Reinitialize only for cleanup of the
  * same still-present card, never continue writing a replacement card. */
 if(state.io_failed){
  if(state.removed||!sd_card_raw_present()||sd_init()||
     memcmp(state.cid,sd_card_info()->cid,sizeof(state.cid))){r=FC_REPAIR;goto fail;}
 }
 camera_hud("CANCELLING / CLEANUP",1);abort_r=fatcam_abort(&card);
 if(abort_r)r=FC_REPAIR;
fail:
 append(append(msg,"ERROR "),fatcam_error(r))[0]=0;camera_hud(msg,5);
 console_puts("SD photo failed: ");console_puts(fatcam_error(r));console_putc('\n');sd_release();
 return state.cancelled?1:-1;
}
