#include "soc.h"
#include "sd.h"
#include "crc32_fast.h"
#include "fat_ro.h"

/* NOMMU M-mode Linux: PAGE_OFFSET=0 for RV32 !MMU, kernel linked at 0. */
#define MMODE_KERNEL_ADDR 0x00000000u
#define MMODE_KERNEL_LIMIT 0x01c00000u
#define MMODE_DTB_ADDR    0x1a000000u
#define MMODE_DTB_LIMIT   0x00100000u
#define SDBENCH_ADDR     0x02000000u
#define SDBENCH_BYTES    (16u*1024u)
#define SDBENCH_SECTORS  (8u*1024u*1024u/512u)
#define SD_BATCH_SECTORS 32u

/* Bare-metal Xiangqi GUI (H128 sparse NNUE through the FPGA MAC engine).
 * Loaded one payload at a time so no static fat_ro_file_t array is needed;
 * the ROM budget leaves no room for embedded file records. */
#define XQ_APP_ADDR    0x01000000u
#define XQ_APP_LIMIT   0x00100000u
#define XQ_MODEL_ADDR  0x0f000000u
#define XQ_MODEL_BYTES 0x00032bb0u
#define XQ_MODEL_CRC32 0x51f2d900u

/* Payload definitions stay static (12 bytes each); the larger FAT file
 * records live on the stack of the boot entry points so the ROM budget
 * does not pay for embedded fat_ro_file_t arrays. */
typedef struct {
 const char *name;
 uint32_t address;
 uint32_t limit;
} boot_payload_t;

static fat_ro_volume_t volume;
static int last_sd_error;
static uint32_t progress_mark;

static int read_sectors(void *user,uint32_t lba,uint32_t count,
                        uint8_t *destination)
{
 int r;
 (void)user;
 r=sd_read_sectors(lba,count,destination);
 if(r)last_sd_error=r;
 return r;
}

static int load_progress(void *user,uint32_t done,uint32_t total)
{
 int c;
 (void)user;
 c=console_getc_timeout(1u);
 if(c==0x1b)return 1;
 if(done>=progress_mark&&done<total){
  console_putc('.');
  progress_mark+=1024u*1024u;
 }
 return 0;
}

static uint32_t elapsed_ms(uint32_t cycles)
{
 uint64_t value=((uint64_t)cycles*1000u+TIMEBASE_HZ-1u)/TIMEBASE_HZ;
 if(value>0xffffffffu)return 0xffffffffu;
 return (uint32_t)value;
}

static uint32_t kib_per_second(uint32_t bytes,uint32_t cycles)
{
 uint64_t value;
 if(!cycles)return 0u;
 value=(uint64_t)bytes*TIMEBASE_HZ/((uint64_t)cycles*1024u);
 if(value>0xffffffffu)return 0xffffffffu;
 return (uint32_t)value;
}

static void print_timing(uint32_t bytes,uint32_t cycles)
{
 console_dec(elapsed_ms(cycles));console_puts(" ms, ");
 console_dec(kib_per_second(bytes,cycles));console_puts(" KiB/s");
}

static void print_sd_error(int error)
{
 if(last_sd_error){
  console_puts("MicroSD protocol error ");console_dec((uint32_t)-last_sd_error);
 }else{
  console_puts("MicroSD filesystem error: ");console_puts(fat_ro_error_string(error));
  console_puts(" (");console_dec((uint32_t)-error);console_putc(')');
 }
 console_putc('\n');
}

static int mount_card(void)
{
 const sd_card_info_t *card;
 int r;
 last_sd_error=0;
 r=sd_init();
 if(r){last_sd_error=r;return FAT_RO_ERR_IO;}
 card=sd_card_info();
 r=fat_ro_mount(&volume,read_sectors,0,card->sector_count);
 return r;
}

static int check_file_record(const char *name,uint32_t address,uint32_t limit,
                             const fat_ro_file_t *file)
{
 if(!file->size||file->size>limit||
    !ddr_range_valid(address,file->size)){
  console_puts("SD file size is unsafe: ");console_puts(name);
  console_puts(" bytes=");console_dec(file->size);console_putc('\n');
  return FAT_RO_ERR_RANGE;
 }
 return FAT_RO_OK;
}

static int find_boot_files(const boot_payload_t *payloads,uint32_t count,
                           fat_ro_file_t *files)
{
 uint32_t i;
 int r;
 for(i=0;i<count;i++){
  r=fat_ro_find(&volume,payloads[i].name,&files[i]);
  if(r){
   console_puts("Missing or invalid SD file: ");console_puts(payloads[i].name);
   console_puts(" (");console_puts(fat_ro_error_string(r));console_puts(")\n");
   return r;
  }
  r=check_file_record(payloads[i].name,payloads[i].address,
                      payloads[i].limit,&files[i]);
  if(r)return r;
 }
 return FAT_RO_OK;
}

static int load_boot_file(const char *name,uint32_t address,uint32_t limit,
                          const fat_ro_file_t *file,uint32_t *cycles)
{
 uint32_t start;
 int r;
 console_puts("Loading ");console_puts(name);console_puts(" to ");
 console_hex(address);console_puts(", bytes=");console_dec(file->size);
 console_putc('\n');
 progress_mark=1024u*1024u;
 last_sd_error=0;
 start=read_mtime_ticks32();
 r=fat_ro_load(&volume,file,(void *)(uintptr_t)address,
               limit,load_progress,0);
 *cycles=(uint32_t)(read_mtime_ticks32()-start);
 if(r){
  console_putc('\n');
  if(r==FAT_RO_ERR_ABORTED)console_puts("SD load cancelled by Esc.\n");
  else print_sd_error(r);
  return r;
 }
 console_puts(" done, ");print_timing(file->size,*cycles);console_putc('\n');
 return FAT_RO_OK;
}

static uint32_t read_le32(const uint8_t *bytes){
 return (uint32_t)bytes[0]|((uint32_t)bytes[1]<<8)|
        ((uint32_t)bytes[2]<<16)|((uint32_t)bytes[3]<<24);
}

/* Find, size-check and load one named payload; the file record lives on
 * the caller stack so repeated payloads cost no static storage. */
static int load_sd_payload(const char *name,uint32_t address,uint32_t limit)
{
 fat_ro_file_t file;
 uint32_t cycles;
 int r;
 r=fat_ro_find(&volume,name,&file);
 if(r){
  console_puts("Missing or invalid SD file: ");console_puts(name);
  console_puts(" (");console_puts(fat_ro_error_string(r));console_puts(")\n");
  return r;
 }
 r=check_file_record(name,address,limit,&file);
 if(r)return r;
 return load_boot_file(name,address,limit,&file,&cycles);
}

static int validate_xiangqi_model(void){
 const uint8_t *model=(const uint8_t *)(uintptr_t)XQ_MODEL_ADDR;
 uint32_t crc;
 if(model[0]!='X'||model[1]!='Q'||model[2]!='8'){
  console_puts("Invalid Xiangqi model header.\n");
  return FAT_RO_ERR_CORRUPT;
 }
 if(read_le32(model+4u)!=128u||read_le32(model+8u)!=2u||
    read_le32(model+12u)!=9u||read_le32(model+16u)!=90u){
  console_puts("Invalid Xiangqi H128 model layout.\n");
  return FAT_RO_ERR_CORRUPT;
 }
 crc=crc32_fast(0xffffffffu,model,XQ_MODEL_BYTES)^0xffffffffu;
 if(crc!=XQ_MODEL_CRC32){
  console_puts("Xiangqi model CRC mismatch: actual=");console_hex(crc);
  console_puts(" expected=");console_hex(XQ_MODEL_CRC32);console_putc('\n');
  return FAT_RO_ERR_CORRUPT;
 }
 console_puts("Xiangqi model verified, CRC32=");console_hex(crc);console_putc('\n');
 return FAT_RO_OK;
}

void sd_print_info(void)
{
 static const char *const names[8]={"Image.mmode","mmode.dtb","mboot.bin",
                                    "fw_jump.bin","Image",
                                    "pikafish.pff","pikafish.atk",
                                    "xiangqi.bin"};
 const sd_card_info_t *card;
 fat_ro_file_t file;
 uint32_t i;
 int r;
 console_puts("MicroSD detect: stable=");console_puts(sd_card_present()?"present":"absent");
 console_puts(" raw=");console_puts(sd_card_raw_present()?"present":"absent");console_putc('\n');
 if(!sd_card_present())return;
 r=mount_card();
 if(r){print_sd_error(r);sd_release();return;}
 card=sd_card_info();
 console_puts("Card: ");console_puts(card->high_capacity?"SDHC/SDXC":"SDSC");
 console_puts(" OCR=");console_hex(card->ocr);
 console_puts(" RCA=");console_hex(card->rca);
 console_puts(" sectors=");console_dec(card->sector_count);
 console_puts(" capacity_MiB=");console_dec(card->sector_count/2048u);
 console_puts(" bus_width=");console_dec(card->bus_width);
 console_puts(" clock_Hz=");console_dec(card->transfer_hz);console_putc('\n');
 console_puts("Filesystem: FAT");console_dec(volume.fat_type);
 console_puts(" partition_lba=");console_dec(volume.partition_lba);
 console_puts(" cluster_bytes=");console_dec(volume.cluster_size_bytes);console_putc('\n');
 for(i=0;i<8;i++){
  r=fat_ro_find(&volume,names[i],&file);
  console_puts("  ");console_puts(names[i]);console_puts(": ");
  if(r)console_puts(fat_ro_error_string(r));
  else{console_dec(file.size);console_puts(" bytes");}
  console_putc('\n');
 }
 sd_release();
}

int sd_benchmark(void)
{
 const sd_card_info_t *card;
 uint8_t *scratch=(uint8_t *)(uintptr_t)SDBENCH_ADDR;
 uint32_t sectors;
 uint32_t lba=0;
 uint32_t start;
 uint32_t cycles;
 uint32_t bytes;
 int r;
 if(!ddr_range_valid(SDBENCH_ADDR,SDBENCH_BYTES)){
  console_puts("sdbench scratch DDR range is unsafe\n");
  return SD_ERR_IO;
 }
 r=sd_init();
 if(r){
  console_puts("sdbench initialization failed, error ");
  console_dec((uint32_t)-r);console_putc('\n');
  sd_release();
  return r;
 }
 card=sd_card_info();
 sectors=card->sector_count;
 if(sectors>SDBENCH_SECTORS)sectors=SDBENCH_SECTORS;
 bytes=sectors*512u;
 ddr_wait_ready();
 console_puts("sdbench read-only bytes=");console_dec(bytes);
 console_puts(" batch_sectors=");console_dec(SD_BATCH_SECTORS);console_putc('\n');
 start=read_mtime_ticks32();
 while(lba<sectors){
  uint32_t count=sectors-lba;
  if(count>SD_BATCH_SECTORS)count=SD_BATCH_SECTORS;
  r=sd_read_sectors(lba,count,scratch);
  if(r)break;
  lba+=count;
  if(console_getc_timeout(1u)==0x1b){r=SD_ERR_ABORTED;break;}
 }
 cycles=(uint32_t)(read_mtime_ticks32()-start);
 sd_release();
 if(r){
  if(r==SD_ERR_ABORTED)console_puts("sdbench cancelled by Esc\n");
  else{
   console_puts("sdbench failed at LBA ");console_dec(lba);
   console_puts(", error ");console_dec((uint32_t)-r);console_putc('\n');
  }
  return r;
 }
 console_puts("sdbench complete: bytes=");console_dec(bytes);console_puts(", ");
 print_timing(bytes,cycles);console_putc('\n');
 return SD_OK;
}

/* NOMMU M-mode Linux: load Image.mmode + mmode.dtb from SD and jump
 * directly to the kernel (no OpenSBI; the V3.5 CPU is M-mode only).
 * Address defines are at the top of this file. */

static const boot_payload_t mmode_files[2]={
 {"Image.mmode",MMODE_KERNEL_ADDR,MMODE_KERNEL_LIMIT},
 {"mmode.dtb",MMODE_DTB_ADDR,MMODE_DTB_LIMIT}
};

int sd_boot_linux(void)
{
 fat_ro_file_t mfiles[2];
 uint32_t total_cycles=0;
 uint32_t file_cycles;
 uint32_t total_bytes=0;
 uint32_t i;
 int r;
 console_puts("MicroSD Linux (M-mode NOMMU) boot\n");
 r=mount_card();
 if(r){print_sd_error(r);sd_release();return r;}
 console_puts("Mounted FAT");console_dec(volume.fat_type);
 console_puts(" volume, cluster bytes=");console_dec(volume.cluster_size_bytes);console_putc('\n');
 r=find_boot_files(mmode_files,2,mfiles);
 if(r){sd_release();return r;}
 ddr_wait_ready();
 for(i=0;i<2;i++){
  r=load_boot_file(mmode_files[i].name,mmode_files[i].address,
                   mmode_files[i].limit,&mfiles[i],&file_cycles);
  if(r){sd_release();return r==FAT_RO_ERR_ABORTED?SD_ERR_ABORTED:r;}
  total_bytes+=mfiles[i].size;
  total_cycles+=file_cycles;
 }
 sd_release();
 console_puts("MicroSD total: bytes=");console_dec(total_bytes);console_puts(", ");
 print_timing(total_bytes,total_cycles);console_putc('\n');
 console_puts("Starting kernel at 0x00000000\n");
 jump_to(MMODE_KERNEL_ADDR,0,MMODE_DTB_ADDR);
 return FAT_RO_OK;
}

/* The NNUE line also preloads pikafish.pff/.atk here for S-mode Linux; this
 * CPU cannot run that payload set, so v2 loads only the bare-metal chess
 * GUI and its H128 model. */
int sd_boot_xiangqi(void){
 int r;
 console_puts("MicroSD Xiangqi GUI boot\n");
 r=mount_card();
 if(r){print_sd_error(r);sd_release();return r;}
 console_puts("Mounted FAT");console_dec(volume.fat_type);
 console_puts(" volume, cluster bytes=");console_dec(volume.cluster_size_bytes);console_putc('\n');
 ddr_wait_ready();
 r=load_sd_payload("xqmodel.bin",XQ_MODEL_ADDR,XQ_MODEL_BYTES);
 if(r){sd_release();return r==FAT_RO_ERR_ABORTED?SD_ERR_ABORTED:r;}
 r=load_sd_payload("xiangqi.bin",XQ_APP_ADDR,XQ_APP_LIMIT);
 if(r){sd_release();return r==FAT_RO_ERR_ABORTED?SD_ERR_ABORTED:r;}
 sd_release();
 r=validate_xiangqi_model();
 if(r)return r;
 console_puts("Starting Xiangqi GUI at 0x01000000\n");
 jump_to(XQ_APP_ADDR,0,0);
 return FAT_RO_OK;
}

int sd_verify_boot_files(void)
{
 fat_ro_file_t files[2];
 uint32_t i,off,crc,cycles,n;int r=mount_card();
 if(r){print_sd_error(r);sd_release();return r;}
 console_puts("SD verify CID=");
 for(i=0;i<4;i++)console_hex(sd_card_info()->cid[i]);
 console_putc('\n');r=find_boot_files(mmode_files,2,files);
 if(r){sd_release();return r;}
 ddr_wait_ready();
 for(i=0;i<2;i++){
  r=load_boot_file(mmode_files[i].name,mmode_files[i].address,
                   mmode_files[i].limit,&files[i],&cycles);if(r)break;
  crc=0xffffffffu;
  for(off=0;off<files[i].size;off+=4096u){
   n=files[i].size-off;if(n>4096)n=4096;
   crc=crc32_fast(crc,(const void *)(uintptr_t)(mmode_files[i].address+off),n);
   if(console_getc_timeout(1u)==0x1b){r=SD_ERR_ABORTED;break;}
  }
  if(r)break;
  console_puts("SD_VERIFY ");console_puts(mmode_files[i].name);console_puts(" bytes=");console_dec(files[i].size);
  console_puts(" CRC32=");console_hex(crc^0xffffffffu);console_putc('\n');
 }
 sd_release();if(!r)console_puts("SD_VERIFY_READ_ONLY_PASS files=2\n");return r;
}
