#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "fat_camera.h"
#include "png_rgb565.h"
#include "crc32_fast.h"
#include "camera.h"
#include "sd.h"
#include <windows.h>
#define SECTORS 70000u
#define RESERVED 32u
#define FATSIZE 550u
#define DATA (RESERVED+2*FATSIZE)
static uint8_t *disk,*baseline;
static uint32_t base,work[FATCAM_MAX_CLUSTERS],writes,fail_write,cancel_at,reads,fail_read;
static int applied,corrupt_read;
static uint32_t verify_offset,verify_reads,verify_blocks,verify_full_batches,verify_fragment_stops;
static int verify_track,verify_started,fail_multi_read,escape_after_multi_read;
static uint8_t batch_work[8u*512u] __attribute__((aligned(4)));
static uint32_t batch_next[2],batch_calls,batch_physical,batch_full,batch_fragments,batch_indices[6144];
static uint32_t batch_cancel_after,transaction_pattern;
static int use_batch;
static fatcam_t camera;
static sd_card_info_t info;
static uint32_t ticks,escape_after_write;static unsigned busy_messages,space_keys;static int last_style,init_error,escape_pending,png_started;
uint32_t read_mtime_ticks32(void){ticks+=100;return ticks;}
int console_getc_timeout(uint32_t cycles){(void)cycles;if(space_keys){space_keys--;return ' ';}if(escape_pending&&png_started&&writes>=escape_after_write){escape_pending=0;return 27;}return -1;}
void console_puts(const char *s){if(strstr(s,"Camera busy;"))busy_messages++;if(strstr(s,"SD writing PNG;"))png_started=1;}
void console_putc(char ch){(void)ch;}
void console_hex(uint32_t v){(void)v;}
void console_dec(uint32_t v){(void)v;}
void camera_hud(const char *s,uint32_t style){(void)s;last_style=(int)style;}
int camera_hud_try(const char *s,uint32_t style){camera_hud(s,style);return 1;}
int sd_init(void){return init_error;}
void sd_release(void){}
const sd_card_info_t *sd_card_info(void){return &info;}
int sd_card_raw_present(void){return 1;}
static void p16(uint8_t *p,uint16_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void p32(uint8_t *p,uint32_t v){p16(p,(uint16_t)v);p16(p+2,(uint16_t)(v>>16));}
static uint32_t g32(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static uint8_t *sector(uint32_t n){return disk+(base+n)*512;}
static void fatentry(uint32_t cluster,uint32_t v)
{p32(sector(RESERVED)+cluster*4,v);p32(sector(RESERVED+FATSIZE)+cluster*4,v);}
static uint32_t expected_file_lba(uint32_t offset)
{
 uint32_t cluster=camera.clusters[camera.file[0].first+offset/camera.volume.cluster_size_bytes];
 return camera.volume.data_lba+(cluster-2u)*camera.volume.sectors_per_cluster+
        (offset%camera.volume.cluster_size_bytes)/512u;
}
static int rd(void *u,uint32_t lba,uint32_t count,uint8_t *b)
{
 (void)u;assert(lba<base+SECTORS&&count<=32&&count<=base+SECTORS-lba);
 if(++reads==fail_read){fail_read=0;return -1;}
 if(count>1&&fail_multi_read){fail_multi_read=0;return -1;}
 /* Watch only the complete-file verification pass, after its optional last
  * partial-sector flush/readback. Metadata/FAT reads remain independent. */
 if(verify_track&&lba>=camera.volume.data_lba&&
    (verify_started||lba==expected_file_lba(0))){
  uint32_t block,n;
  verify_started=1;assert(verify_offset<camera.file[0].length&&count<=8);
  assert(lba==expected_file_lba(verify_offset));
  assert(count<=(camera.file[0].length-verify_offset+511u)/512u);
  for(block=0;block<count;block++)
   assert(expected_file_lba(verify_offset+block*512u)==lba+block);
  verify_reads++;verify_blocks+=count;if(count==8)verify_full_batches++;
  n=camera.file[0].length-verify_offset;if(n>count*512u)n=count*512u;
  verify_offset+=n;
  if(verify_offset<camera.file[0].length&&expected_file_lba(verify_offset)!=lba+count)
   verify_fragment_stops++;
 }
 memcpy(b,disk+lba*512,count*512);
 if(corrupt_read&&camera.staged&&lba>=base+DATA+16)b[0]^=1;
 if(count>1&&escape_after_multi_read){
  escape_after_multi_read=0;escape_pending=1;escape_after_write=0;
 }
 return 0;
}
static int wr(void *u,uint32_t lba,const uint8_t *b)
{
 (void)u;assert(lba>=base&&lba<base+SECTORS);
 if(++writes==fail_write){fail_write=0;if(applied)memcpy(disk+lba*512,b,512);return -1;}
 memcpy(disk+lba*512,b,512);return 0;
}
int sd_read_sectors(uint32_t lba,uint32_t count,uint8_t *b){return rd(0,lba,count,b)?SD_ERR_CRC:0;}
int sd_write_sector(uint32_t lba,const uint8_t *b){return wr(0,lba,b)?SD_ERR_CRC:0;}
int sd_write_sectors(uint32_t lba,uint32_t count,const uint8_t *b,int (*p)(void *),void *u)
{
 uint32_t block;assert(count&&count<=8&&lba<base+SECTORS&&count<=base+SECTORS-lba);
 for(block=0;block<count;block++){
  if(p&&p(u))return SD_ERR_ABORTED;
  if(wr(0,lba+block,b+block*512u))return SD_ERR_CRC;
 }
 return SD_OK;
}
static int poll(void *u,uint32_t done,uint32_t total,int cleanup)
{(void)u;(void)total;return !cleanup&&cancel_at&&done>=cancel_at?FC_CANCEL:0;}
static int batch_write(void *u,uint32_t lba,uint32_t count,const uint8_t *b)
{
 uint32_t block,index=camera.batch_file,start=batch_next[index],remaining;
 (void)u;assert(index<2&&count&&count<=8&&((uintptr_t)b&3u)==0);
 assert(start+count*512u<=camera.file[index].length);
 batch_calls++;if(count==8)batch_full++;
 for(block=0;block<count;block++){
  uint32_t offset=start+block*512u;
  uint32_t cluster=camera.clusters[camera.file[index].first+offset/camera.volume.cluster_size_bytes];
  uint32_t expected=camera.volume.data_lba+(cluster-2u)*camera.volume.sectors_per_cluster+
                    (offset%camera.volume.cluster_size_bytes)/512u;
  assert(lba+block==expected); /* Data batches cannot write foreign clusters. */
  if(batch_cancel_after&&batch_physical>=batch_cancel_after)return FC_CANCEL;
  assert(batch_physical<6144);batch_indices[batch_physical]=writes+1;
  if(wr(0,lba+block,b+block*512u))return FC_IO;
  batch_physical++;
 }
 batch_next[index]+=count*512u;remaining=camera.file[index].length-batch_next[index];
 if(remaining>=512u){
  uint32_t offset=batch_next[index],cluster=camera.clusters[camera.file[index].first+offset/camera.volume.cluster_size_bytes];
  uint32_t next_lba=camera.volume.data_lba+(cluster-2u)*camera.volume.sectors_per_cluster+
                    (offset%camera.volume.cluster_size_bytes)/512u;
  if(next_lba!=lba+count)batch_fragments++;
 }
 return 0;
}
static void init(unsigned mbr,int active)
{
 uint8_t *b,*e;unsigned i;base=mbr?2048:0;memset(disk,0,(SECTORS+2048)*512u);
 if(base){b=disk;b[446+4]=0x0c;p32(b+446+8,base);p32(b+446+12,SECTORS);b[510]=0x55;b[511]=0xaa;}
 b=sector(0);b[0]=0xeb;b[2]=0x90;memcpy(b+3,"MSDOS5.0",8);p16(b+11,512);b[13]=1;p16(b+14,RESERVED);b[16]=2;
 b[21]=0xf8;p32(b+32,SECTORS);p32(b+36,FATSIZE);p16(b+40,active?0x81:0);p32(b+44,2);p16(b+48,1);p16(b+50,6);
 b[66]=0x29;memcpy(b+71,"CAMERATEST ",11);memcpy(b+82,"FAT32   ",8);b[510]=0x55;b[511]=0xaa;
 memcpy(sector(6),b,512);b=sector(1);p32(b,0x41615252);p32(b+484,0x61417272);p32(b+488,1234);p32(b+492,8);p32(b+508,0xaa550000);memcpy(sector(7),b,512);
 fatentry(0,0x0ffffff8);fatentry(1,0x0fffffff);fatentry(2,0x0fffffff);
 for(i=0;i<4;i++){
  fatentry(3+i,0x0fffffff);e=sector(DATA)+i*32;memcpy(e,"BOOT0000BIN",11);e[7]=(uint8_t)('0'+i);e[11]=0x20;p16(e+26,(uint16_t)(3+i));p32(e+28,512);
  memset(sector(DATA+1+i),(int)(0x81+i),512);
 }
 /* Occupied islands force the PNG to span fragmented chains. */
 for(i=32;i<6200;i+=37){fatentry(i,0x0fffffff);memset(sector(DATA+i-2),0x6b,512);}
 if(active)memset(sector(RESERVED),0xa5,FATSIZE*512u); /* inactive FAT must stay untouched */
 memcpy(baseline,disk,(SECTORS+2048)*512u);
 writes=reads=fail_write=fail_read=cancel_at=0;corrupt_read=0;
 verify_track=verify_started=fail_multi_read=escape_after_multi_read=0;
 verify_offset=verify_reads=verify_blocks=verify_full_batches=verify_fragment_stops=0;
 batch_calls=batch_physical=batch_full=batch_fragments=batch_cancel_after=transaction_pattern=0;
 batch_next[0]=batch_next[1]=0;use_batch=0;
}
static void boot_intact(void)
{
 unsigned i;assert(!memcmp(disk,baseline,512));assert(!memcmp(sector(0),baseline+base*512,512));
 assert(!memcmp(sector(DATA),baseline+(base+DATA)*512,128));
 for(i=0;i<4;i++)assert(!memcmp(sector(DATA+1+i),baseline+(base+DATA+1+i)*512,512));
}
static int open_card(void)
{
 int r=fatcam_open(&camera,rd,wr,0,base+SECTORS,work,poll);
 batch_next[0]=batch_next[1]=0;
 batch_calls=batch_physical=batch_full=batch_fragments=0;
 return !r&&use_batch?fatcam_set_batch(&camera,batch_write,batch_work,8):r;
}
static int transaction(uint32_t n)
{
 uint8_t b[512];uint32_t off,crc=0xffffffffu,k;int r;
 r=open_card();if(r)return r;r=fatcam_begin(&camera,n,3);if(r)goto out;
 assert(fatcam_commit(&camera)==FC_CORRUPT);
 for(off=0;off<n;off+=k){k=n-off;if(k>512)k=512;memset(b,(int)(off/512+transaction_pattern),k);crc=crc32_fast(crc,b,k);r=fatcam_write(&camera,0,b,k);if(r)goto out;}
 r=fatcam_write(&camera,1,(const uint8_t *)"{}\n",3);if(r)goto out;
 r=fatcam_finish(&camera,0,crc^0xffffffffu);if(r)goto out;
 r=fatcam_finish(&camera,1,crc32_fast(0xffffffffu,"{}\n",3)^0xffffffffu);if(r)goto out;
 r=fatcam_commit(&camera);
out:if(r){int a=fatcam_abort(&camera);assert(a==0||a==FC_REPAIR);}boot_intact();return r;
}
static void check_directory(unsigned files)
{
 fat_ro_volume_t v;fat_ro_file_t f;uint8_t *b;unsigned i,seen=0;uint32_t cl=0;
 assert(!fat_ro_mount(&v,rd,0,base+SECTORS));
 b=sector(DATA);for(i=0;i<512;i+=32)if(!memcmp(b+i,"CAMERA     ",11))cl=(uint32_t)(b[i+26]|((uint32_t)b[i+27]<<8));
 if(!cl){assert(!files);return;}
 v.root_cluster=cl;
 assert(fat_ro_find(&v,"IMG00001.JSON",&f)==(files?0:FAT_RO_ERR_NOT_FOUND));
 {unsigned skip=64,hops=0;
 while(cl<0x0ffffff8u){assert(++hops<10);b=sector(DATA+cl-2);
  for(i=skip;i<512;i+=32){if(!b[i])break;if(b[i]!=0xe5&&b[i+11]!=0x0f)assert(memcmp(b+i+8,"TMP",3));if(b[i]!=0xe5&&b[i+11]==0x20)seen++;}
  cl=g32(sector(RESERVED+v.active_fat*FATSIZE)+cl*4)&0x0fffffff;skip=0;
 }}
 assert(seen==files*2);
 assert((g32(sector(RESERVED+v.active_fat*FATSIZE)+4)&0x08000000)!=0);
}
static int sink(void *u,const uint8_t *b,uint32_t n){(void)u;return fatcam_write(&camera,0,b,n);}
typedef struct {const uint8_t *expected;uint32_t offset;} png_compare_t;
static int compare_png(void *u,const uint8_t *b,uint32_t n)
{
 png_compare_t *c=u;assert(n<=PNG565_BYTES-c->offset);
 assert(!memcmp(c->expected+c->offset,b,n));c->offset+=n;return 0;
}
int main(int argc,char **argv)
{
 uint32_t total,total_reads,i,pngcrc;uint8_t *raw;int r;FILE *out;unsigned mode;
 assert(argc==2);disk=malloc((SECTORS+2048)*512u);baseline=malloc((SECTORS+2048)*512u);raw=malloc(1280u*720*2);assert(disk&&baseline&&raw);
 assert((crc32_fast(0xffffffffu,"123456789",9)^0xffffffffu)==0xcbf43926u);
 for(mode=0;mode<3;mode++){
  init(mode!=0,mode==2);assert(!transaction(1539));check_directory(1);
  total=writes;total_reads=reads;assert(!transaction(1539));assert(camera.id==2);check_directory(2);
  if(mode==2)assert(!memcmp(sector(RESERVED),baseline+(base+RESERVED)*512,FATSIZE*512u));
  for(i=1;i<=total;i++){
   unsigned a;for(a=0;a<2;a++){init(mode!=0,mode==2);fail_write=i;applied=(int)a;r=transaction(1539);assert(r);check_directory(0);}
  }
  for(i=1;i<=total_reads;i++){
   init(mode!=0,mode==2);fail_read=i;r=transaction(1539);
   fail_read=0;
   /* A read fault after commit can only belong to the check, not transaction. */
   if(r)check_directory(0);else check_directory(1);
  }
  init(mode!=0,mode==2);cancel_at=512;assert(transaction(1539)==FC_CANCEL);check_directory(0);
  cancel_at=0;assert(!transaction(1539));check_directory(1);
  for(i=2;i<=6;i++){assert(!transaction(1539));if(camera.id!=i)fprintf(stderr,"mode=%u id=%u expected=%u dir=%u\n",mode,camera.id,i,camera.dir_cluster);assert(camera.id==i);check_directory(i);}
 }
 /* Every data sector of a fragmented 40-sector batch stream can fail before
  * or after being applied. None may publish a final file or overwrite boot. */
 for(mode=0;mode<3;mode++){
  uint32_t fault_indices[40],j;unsigned applied_mode;
  init(mode!=0,mode==2);use_batch=1;assert(!transaction(40u*512u+7u));check_directory(1);
  assert(batch_physical==40&&batch_full&&batch_fragments);
  memcpy(fault_indices,batch_indices,sizeof(fault_indices));
  for(j=0;j<40;j++)for(applied_mode=0;applied_mode<2;applied_mode++){
   init(mode!=0,mode==2);use_batch=1;fail_write=fault_indices[j];applied=(int)applied_mode;
   assert(transaction(40u*512u+7u)==FC_IO);check_directory(0);assert(!camera.batch_blocks);
  }
  init(mode!=0,mode==2);use_batch=1;batch_cancel_after=3;
  assert(transaction(40u*512u+7u)==FC_CANCEL);assert(batch_physical==3&&!camera.batch_blocks);check_directory(0);
  batch_cancel_after=0;batch_next[0]=batch_next[1]=0;assert(!transaction(40u*512u+7u));check_directory(1);
  /* Aborting queued bytes must discard them without submitting a data batch. */
  init(mode!=0,mode==2);use_batch=1;assert(!open_card());assert(!fatcam_begin(&camera,2048,3));
  {uint8_t b[1024];uint32_t before=writes;memset(b,0x5a,sizeof(b));
   assert(!fatcam_write(&camera,0,b,sizeof(b)));assert(writes==before&&camera.batch_blocks==2);
   assert(!fatcam_abort(&camera));assert(!batch_calls&&!camera.batch_blocks);check_directory(0);boot_intact();
  }
 }
 puts("CAMERA_SD_WRITE_BATCH_FRAGMENT_ALL_SECTOR_PARTIAL_FAULT_CANCEL_DISCARD_RETRY_PASS");
 init(1,0);use_batch=1;assert(!open_card());assert(!fatcam_begin(&camera,PNG565_BYTES,3));
 for(i=0;i<1280u*720;i++){uint16_t v=(uint16_t)(((i/1280)*97u)^((i%1280)*31u));raw[i*2]=(uint8_t)v;raw[i*2+1]=(uint8_t)(v>>8);}
 /* Explicit primary colours and differently coloured first/last rows. */
 raw[0]=0;raw[1]=0xf8;raw[2]=0xe0;raw[3]=7;raw[4]=0x1f;raw[5]=0;
 assert(!png565_encode(raw,sink,0,0,&pngcrc));assert(camera.file[0].done==PNG565_BYTES);
 assert(!fatcam_write(&camera,1,(const uint8_t *)"{}\n",3));verify_track=1;
 assert(!fatcam_finish(&camera,0,pngcrc));verify_track=0;
 assert(verify_offset==PNG565_BYTES&&verify_blocks==(PNG565_BYTES+511u)/512u);
 assert(verify_full_batches&&verify_fragment_stops&&verify_reads<verify_blocks/2u);
 puts("CAMERA_SD_VERIFY_BATCH_CONTIGUOUS_FRAGMENT_BOUNDARIES_FULL_CRC_PASS");
 assert(!fatcam_finish(&camera,1,crc32_fast(0xffffffffu,"{}\n",3)^0xffffffffu));assert(!fatcam_commit(&camera));boot_intact();
 /* Use the independent production FAT reader to retrieve and export the PNG. */
 {fat_ro_volume_t v;fat_ro_file_t f;uint8_t *png=malloc(PNG565_BYTES);assert(png);
 assert(!fat_ro_mount(&v,rd,0,base+SECTORS));v.root_cluster=camera.dir_cluster;
 assert(!fat_ro_find(&v,"IMG00001.PNG",&f));assert(f.size==PNG565_BYTES);
 assert(!fat_ro_load(&v,&f,png,PNG565_BYTES,0,0));
 /* Identical file bytes and CRC for the aligned word source and all three
  * byte-source alignments. Python checks every decoded pixel independently. */
 {uint8_t *unaligned=malloc(1280u*720u*2u+4u);uint32_t alignment,crc;
  png_compare_t cmp;assert(unaligned&&((uintptr_t)raw&3u)==0u);
  assert((crc32_fast(0xffffffffu,png,PNG565_BYTES)^0xffffffffu)==pngcrc);
  cmp.expected=png;cmp.offset=0;
  assert(!png565_encode(raw,compare_png,&cmp,0,0));assert(cmp.offset==PNG565_BYTES);
  for(alignment=1;alignment<=3;alignment++){
   memcpy(unaligned+alignment,raw,1280u*720u*2u);cmp.expected=png;cmp.offset=0;
   assert(!png565_encode(unaligned+alignment,compare_png,&cmp,0,&crc));
   assert(cmp.offset==PNG565_BYTES&&crc==pngcrc);
   cmp.offset=0;assert(!png565_encode(unaligned+alignment,compare_png,&cmp,0,0));
   assert(cmp.offset==PNG565_BYTES);
  }
  free(unaligned);puts("CAMERA_SD_PNG_ALIGNED_UNALIGNED_IDENTICAL_BYTES_CRC_PASS");
  puts("CAMERA_SD_PNG_SINK_FILE_CRC_IDENTICAL_BYTES_PASS");
 }
 out=fopen(argv[1],"wb");assert(out);assert(fwrite(png,1,PNG565_BYTES,out)==PNG565_BYTES);fclose(out);free(png);}
 {char name[1024],json[384];uint32_t len;
  assert(strlen(argv[1])<1000);strcpy(name,argv[1]);strcpy(name+strlen(name)-3,"JSON");
  len=camera_sd_metadata(json,321,crc32_fast(0xffffffffu,raw,1280u*720*2)^0xffffffffu,pngcrc,1234567890123ull);
  out=fopen(name,"wb");assert(out);assert(fwrite(json,1,len,out)==len);fclose(out);
 }
 assert(!open_card());assert(!fatcam_begin(&camera,PNG565_BYTES,3));
 assert(!png565_encode(raw,sink,0,0,&pngcrc));corrupt_read=1;
 assert(fatcam_finish(&camera,0,pngcrc)==FC_IO);corrupt_read=0;
 assert(!fatcam_abort(&camera));check_directory(1);boot_intact();
 /* Full and dirty volume rejection perform no mutation. */
 for(i=2;i<SECTORS-DATA+2;i++)fatentry(i,0x0fffffff);
 total=writes;assert(!open_card());assert(fatcam_begin(&camera,1025,3)==FC_FULL);assert(writes==total);
 fatentry(1,0x07ffffff);assert(open_card()==FC_REPAIR);assert(writes==total);
 /* Execute production camera_sd_save with an immutable DDR alias and mock
  * sector I/O. The separate RV32 test covers the real driver and native pins. */
 {void *snapshot=VirtualAlloc((void *)(uintptr_t)0x9b600000u,0x200000u,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);uint32_t crc;
  assert(snapshot==(void *)(uintptr_t)0x9b600000u);memcpy(snapshot,raw,1280u*720*2);crc=crc32_fast(0xffffffffu,raw,1280u*720*2)^0xffffffffu;
  init(1,0);memset(&info,0,sizeof(info));info.high_capacity=1;info.bus_width=4;info.sector_count=base+SECTORS;info.cid[0]=0x12345678;
  space_keys=2;assert(!camera_sd_save(321,crc,1234567890123ull));assert(last_style==3&&busy_messages==2);check_directory(1);
  png_started=0;escape_pending=1;escape_after_write=writes+50;assert(camera_sd_save(322,crc,1234567890124ull)==1);check_directory(1);
  assert(!camera_sd_save(323,crc,1234567890125ull));check_directory(2);
  init_error=SD_ERR_NO_CARD;total=writes;assert(camera_sd_save(324,crc,1234567890126ull)==-1);assert(writes==total&&last_style==5);init_error=0;
  fail_write=writes+1;applied=1;assert(camera_sd_save(325,crc,1234567890127ull)==-1);check_directory(2);
  assert(!camera_sd_save(326,crc,1234567890128ull));check_directory(3);
  /* A multi-block verification read fault and Esc received after a completed
   * batch must roll back both files, preserve boot data, and allow retry. */
  fail_multi_read=1;assert(camera_sd_save(327,crc,1234567890129ull)==-1);
  assert(!fail_multi_read&&last_style==5);check_directory(3);boot_intact();
  assert(!camera_sd_save(328,crc,1234567890130ull));check_directory(4);
  png_started=0;escape_pending=0;escape_after_multi_read=1;
  assert(camera_sd_save(329,crc,1234567890131ull)==1);
  assert(!escape_after_multi_read&&!escape_pending&&last_style==5);check_directory(4);boot_intact();
  assert(!camera_sd_save(330,crc,1234567890132ull));check_directory(5);
  puts("CAMERA_SD_VERIFY_BATCH_IO_FAULT_ESC_ROLLBACK_RETRY_PASS");
  assert(VirtualFree(snapshot,0,MEM_RELEASE));
 }
 free(raw);free(baseline);free(disk);puts("CAMERA_SD_FAT32_MIRROR_ACTIVE_FAULT_CANCEL_RETRY_PNG_PASS");
 puts("CAMERA_SD_PRODUCTION_SAVE_BUSY_ESC_NO_CARD_FAILURE_RECOVERY_PASS");return 0;
}
