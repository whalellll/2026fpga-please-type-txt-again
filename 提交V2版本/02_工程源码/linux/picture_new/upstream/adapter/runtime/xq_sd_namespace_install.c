/* Explicit user-authorized SD migration; no Flash/RTL access and no auto retry. */
#include "soc.h"
#include "sd.h"
#include "fat_camera.h"
#include "fat_boot_prefix.h"
#include "crc32_fast.h"
#include "console_line.h"
#include <string.h>
typedef struct {const char *source,*name,*short_name;uint32_t bytes,crc,address;} ns_item;
int xqns_begin_root_pair(fatcam_t *,const char *,uint32_t,const char *,uint32_t);
#include "sd_namespace_install.h"
static const ns_item copies[6]=NS_COPY_ITEMS;
static fatcam_t card;
static uint32_t workspace[FATCAM_MAX_CLUSTERS];
static uint8_t batch[4096] __attribute__((aligned(4)));
static const uint32_t expected_cid[4]=NS_EXPECTED_CID;
static uint64_t started;
static int io_failed;
static uint64_t clock64(void)
{
    uint32_t a,b,c;
    do {a=REG32(CLINT_MTIME+4);b=REG32(CLINT_MTIME);c=REG32(CLINT_MTIME+4);}while(a!=c);
    return ((uint64_t)c<<32)|b;
}
static uint32_t crc(const void *p,uint32_t n){return crc32_fast(0xffffffffu,p,n)^0xffffffffu;}
static int rd(void *u,uint32_t lba,uint32_t n,uint8_t *data)
{int r;(void)u;r=sd_read_sectors(lba,n,data);if(r)io_failed=1;return r;}
static int wr(void *u,uint32_t lba,const uint8_t *data)
{int r;(void)u;r=sd_write_sector(lba,data);if(r)io_failed=1;return r;}
static int poll(void *u,uint32_t done,uint32_t total,int cleanup)
{
    (void)u;(void)done;(void)total;
    if(!sd_card_raw_present())return FC_IO;
    if(!cleanup&&console_getc_timeout(1u)==27)return FC_CANCEL;
    return clock64()-started>(uint64_t)TIMEBASE_HZ*180u?FC_TIMEOUT:0;
}
static int batch_poll(void *u){return poll(u,0,0,0);}
static int batch_wr(void *u,uint32_t lba,uint32_t n,const uint8_t *data)
{int r;(void)u;r=sd_write_sectors(lba,n,data,batch_poll,0);if(r)io_failed=1;return r?FC_IO:0;}
static int same_card(void)
{
    int r=sd_init();if(r)return r;
    const sd_card_info_t *info=sd_card_info();
    if(info->sector_count!=62333952u||info->bus_width!=4||!info->high_capacity||
       memcmp(info->cid,expected_cid,sizeof(expected_cid)))return FC_CORRUPT;
    return 0;
}
static int mount(void)
{
    int r;
    started=clock64();io_failed=0;r=same_card();if(r)return r;
    r=fatcam_open(&card,rd,wr,0,sd_card_info()->sector_count,workspace,poll);if(r)return r;
    if(card.volume.partition_lba!=32u||card.volume.cluster_size_bytes!=32768u)return FC_CORRUPT;
    return fatcam_set_batch(&card,batch_wr,batch,8);
}
static void print_cid(void)
{
    console_puts("NS_CID=");
    for(unsigned i=0;i<4;i++)for(unsigned j=0;j<8;j++)
        console_putc("0123456789abcdef"[(expected_cid[i]>>(28u-j*4u))&15u]);
    console_puts(" sectors=");console_dec(sd_card_info()->sector_count);
    console_puts(" partition_lba=");console_dec(card.volume.partition_lba);console_putc('\n');
}
static int cid_text(const char *s)
{
    if(strlen(s)!=32)return 0;
    for(unsigned i=0;i<4;i++)for(unsigned j=0;j<8;j++)
        if(*s++!="0123456789abcdef"[(expected_cid[i]>>(28u-j*4u))&15u])return 0;
    return 1;
}
static int load(const char *name,uint32_t bytes,uint32_t expected,uint32_t address)
{
    fat_ro_file_t file;int r=fat_ro_find(&card.volume,name,&file);if(r)return r;
    if(file.size!=bytes||!ddr_range_valid(address,bytes))return FC_CORRUPT;
    r=fat_ro_load(&card.volume,&file,(void *)(uintptr_t)address,bytes,0,0);if(r)return r;
    if(crc((const void *)(uintptr_t)address,bytes)!=expected)return FC_CORRUPT;
    console_puts("NS_SOURCE_CRC_PASS name=");console_puts(name);console_puts(" bytes=");
    console_dec(bytes);console_puts(" crc=");console_hex(expected);console_putc('\n');return 0;
}
static int baseline(void)
{
    int r;
    for(unsigned i=0;i<6;i++){
        r=load(copies[i].source,copies[i].bytes,copies[i].crc,0x04000000u);if(r)return r;
    }
    return load("xiangqi.bin",NS_OLD_BYTES,NS_OLD_CRC,0x04000000u);
}
static int absent(void)
{
    const char *extra[]={"PN01BOOT.BIN","XQBOOT.CFG","PN00BOOT.BIN","XQMENU.BIN"};
    fat_ro_file_t file;
    for(unsigned i=0;i<6;i++)if(fat_ro_find(&card.volume,copies[i].name,&file)!=FAT_RO_ERR_NOT_FOUND)return FC_CORRUPT;
    for(unsigned i=0;i<4;i++)if(fat_ro_find(&card.volume,extra[i],&file)!=FAT_RO_ERR_NOT_FOUND)return FC_CORRUPT;
    return 0;
}
static int pair(const char *n0,const char *s0,const void *d0,uint32_t b0,uint32_t c0,
                const char *n1,const char *s1,const void *d1,uint32_t b1,uint32_t c1)
{
    const void *data[2]={d0,d1};const uint32_t bytes[2]={b0,b1},sums[2]={c0,c1};
    const char *names[2]={n0,n1};int r;
    /* A fresh exact CID immediately precedes each metadata transaction. */
    r=mount();if(r)return r;
    if(crc(d0,b0)!=c0||crc(d1,b1)!=c1)return FC_CORRUPT;
    started=clock64();r=xqns_begin_root_pair(&card,s0,b0,s1,b1);if(r)return r;
    for(unsigned f=0;f<2;f++){
        const uint8_t *p=data[f];
        for(uint32_t at=0;at<bytes[f];){
            uint32_t n=bytes[f]-at;if(n>32768u)n=32768u;
            r=fatcam_write(&card,f,p+at,n);if(r)return r;at+=n;
        }
        r=fatcam_finish(&card,f,sums[f]);if(r)return r;
        console_puts("NS_READBACK_CRC_PASS name=");console_puts(names[f]);
        console_puts(" bytes=");console_dec(bytes[f]);console_puts(" crc=");console_hex(sums[f]);console_putc('\n');
    }
    r=fatcam_commit_root_pair(&card);if(r)return r;
    console_puts("NS_PAIR_COMMITTED ");console_puts(n0);console_putc(' ');console_puts(n1);console_putc('\n');return 0;
}
static int activate(void)
{
    fat_ro_file_t file,again;int r=mount();if(r)return r;
    uint8_t *data=(uint8_t *)(uintptr_t)0x04000000u;
    r=load("xiangqi.bin",NS_OLD_BYTES,NS_OLD_CRC,0x04000000u);if(r)return r;
    if(NS_MENU_BYTES>NS_OLD_BYTES||NS_MENU_BYTES>card.volume.cluster_size_bytes)return FC_CORRUPT;
    memcpy(data,ns_menu,NS_MENU_BYTES);
    if(crc(data,NS_OLD_BYTES)!=NS_NEW_ENTRY_CRC)return FC_CORRUPT;
    r=fat_ro_find(&card.volume,"xiangqi.bin",&file);if(r)return r;
    started=clock64();r=same_card();if(r)return r;
    r=fat_boot_patch_prefix(&card.volume,&file,data,NS_MENU_BYTES,wr,0);if(r)return r;
    r=fat_ro_find(&card.volume,"xiangqi.bin",&again);if(r)return r;
    if(again.size!=file.size||again.first_cluster!=file.first_cluster)return FC_CORRUPT;
    r=fat_ro_load(&card.volume,&again,(void *)(uintptr_t)0x05000000u,again.size,0,0);if(r)return r;
    if(crc((const void *)(uintptr_t)0x05000000u,again.size)!=NS_NEW_ENTRY_CRC)return FC_CORRUPT;
    console_puts("NS_SHARED_MENU_ENTRY_PASS bytes=");console_dec(again.size);
    console_puts(" crc=");console_hex(NS_NEW_ENTRY_CRC);console_putc('\n');return 0;
}
static int install(const char *cid)
{
    int r;if(!cid_text(cid))return FC_CORRUPT;
    r=mount();if(r)return r;
    r=absent();if(r)return r;
    r=baseline();if(r)return r;
    for(unsigned i=0;i<6;i+=2){
        const ns_item *a=&copies[i],*b=&copies[i+1];
        r=load(a->source,a->bytes,a->crc,a->address);if(r)return r;
        r=load(b->source,b->bytes,b->crc,b->address);if(r)return r;
        r=pair(a->name,a->short_name,(void *)(uintptr_t)a->address,a->bytes,a->crc,
               b->name,b->short_name,(void *)(uintptr_t)b->address,b->bytes,b->crc);if(r)return r;
    }
    r=pair("PN01BOOT.BIN","PN01BOOTBIN",ns_loader,NS_LOADER_BYTES,NS_LOADER_CRC,
           "XQBOOT.CFG","XQBOOT  CFG",ns_config,NS_CONFIG_BYTES,NS_CONFIG_CRC);if(r)return r;
    r=load("xiangqi.bin",NS_OLD_BYTES,NS_OLD_CRC,0x04000000u);if(r)return r;
    r=pair("PN00BOOT.BIN","PN00BOOTBIN",(void *)(uintptr_t)0x04000000u,NS_OLD_BYTES,NS_OLD_CRC,
           "XQMENU.BIN","XQMENU  BIN",ns_menu,NS_MENU_BYTES,NS_MENU_CRC);if(r)return r;
    console_puts("NS_FILES_COMMITTED count=10 backup=PN00BOOT.BIN\n");
    r=activate();if(r)return r;
    console_puts("NS_INSTALL_PASS startup=SD_MENU uart_upload_each_boot=0 flash_written=0\n");return 0;
}
int main(void)
{
    char line[80];int r=mount();if(r){console_puts("NS_INSTALL_FAIL mount\n");return 1;}
    print_cid();console_puts("NS_INSTALL_READY inspect / install <CID> / console\n");
    for(;;){
        console_puts("nsinstall> ");console_readline(line,sizeof(line));r=0;
        if(!strcmp(line,"inspect")){r=baseline();if(!r)r=absent();if(!r)console_puts("NS_INSPECT_PASS no_writes=1\n");}
        else if(!strncmp(line,"install ",8))r=install(line+8);
        else if(!strcmp(line,"console")){sd_release();jump_to(0x1c000000u,0,0);return 0;}
        else if(!line[0])continue;
        else {console_puts("NS_UNKNOWN_COMMAND\n");continue;}
        if(r){
            console_puts("NS_INSTALL_FAIL code=");console_dec((uint32_t)-r);console_putc('\n');
            if(card.dirty||card.staged||card.allocated){
                if(io_failed&&same_card()){console_puts("NS_REPAIR_REQUIRED different/unavailable card\n");return 1;}
                started=clock64();if(fatcam_abort(&card))console_puts("NS_REPAIR_REQUIRED metadata rollback\n");
            }
            sd_release();return 1;
        }
        console_puts("NS_COMMAND_PASS\n");
    }
}
