/* Real FAT32 library + production installer, sparse synthetic 32 GB card. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <windows.h>
#include "soc.h"
static uint32_t fake_mmio(uint32_t address){static uint32_t ticks;return address==CLINT_MTIME+4?0:++ticks;}
#undef REG32
#define REG32(address) fake_mmio(address)
#define main namespace_installer_entry
#include "xq_sd_namespace_install.c"
#undef main
#define TEST_DATA_LBA (32u+32u+16000u)
typedef struct {uint32_t lba;uint8_t bytes[512];} test_sector;
static test_sector sectors[8192];
static unsigned sector_count,write_count,fail_write,apply_failure,entry_writes;
static sd_card_info_t test_card;
static uint8_t original_entry[NS_OLD_BYTES];
static uint8_t *sector_at(uint32_t lba,int create)
{
    assert(lba<62333952u);
    for(unsigned i=0;i<sector_count;i++)if(sectors[i].lba==lba)return sectors[i].bytes;
    if(!create)return NULL;
    assert(sector_count<8192);test_sector *s=&sectors[sector_count++];s->lba=lba;memset(s->bytes,0,512);return s->bytes;
}
static void put16(uint8_t *p,uint32_t n){p[0]=(uint8_t)n;p[1]=(uint8_t)(n>>8);}
static void put32(uint8_t *p,uint32_t n){put16(p,n);put16(p+2,n>>16);}
int sd_read_sectors(uint32_t lba,uint32_t n,uint8_t *p)
{
    assert(n&&n<=32);
    for(unsigned i=0;i<n;i++){uint8_t *s=sector_at(lba+i,0);if(s)memcpy(p+i*512,s,512);else memset(p+i*512,0,512);}
    return 0;
}
int sd_write_sector(uint32_t lba,const uint8_t *p)
{
    ++write_count;
    if(lba>=TEST_DATA_LBA+7u*64u&&lba<TEST_DATA_LBA+7u*64u+(NS_OLD_BYTES+511u)/512u)++entry_writes;
    if(write_count==fail_write){if(apply_failure)memcpy(sector_at(lba,1),p,512);return SD_ERR_IO;}
    memcpy(sector_at(lba,1),p,512);return 0;
}
int sd_write_sectors(uint32_t lba,uint32_t n,const uint8_t *p,sd_write_poll_fn poll_fn,void *u)
{for(unsigned i=0;i<n;i++){if(poll_fn&&poll_fn(u))return SD_ERR_ABORTED;if(sd_write_sector(lba+i,p+i*512))return SD_ERR_IO;}return 0;}
int sd_init(void){return 0;}
int sd_card_raw_present(void){return 1;}
void sd_release(void){}
const sd_card_info_t *sd_card_info(void){return &test_card;}
int ddr_range_valid(uint32_t address,uint32_t bytes){return address>=0x04000000u&&address+bytes<=0x0a000000u;}
void console_puts(const char *s){(void)s;}
void console_putc(char c){(void)c;}
void console_hex(uint32_t n){(void)n;}
void console_dec(uint32_t n){(void)n;}
int console_getc_timeout(uint32_t n){(void)n;return -1;}
void console_readline(char *line,int capacity){(void)line;(void)capacity;abort();}
void jump_to(uint32_t entry,uint32_t a0,uint32_t a1){(void)entry;(void)a0;(void)a1;abort();}
static void fat_entry(unsigned cluster,uint32_t next)
{for(unsigned i=0;i<2;i++)put32(sector_at(64u+i*8000u+cluster/128u,1)+(cluster%128u)*4,next);}
static void seed_file(const char *name,unsigned slot,unsigned cluster,const uint8_t *bytes,unsigned n)
{
    uint8_t *e=sector_at(TEST_DATA_LBA,1)+slot*32;
    const char *dot=strchr(name,'.');assert(dot);
    memset(e,' ',11);memcpy(e,name,(size_t)(dot-name));memcpy(e+8,dot+1,strlen(dot+1));e[11]=0x20;
    put16(e+20,cluster>>16);put16(e+26,cluster);put32(e+28,n);fat_entry(cluster,0x0fffffff);
    for(unsigned i=0;i<(n+511)/512;i++){
        unsigned take=n-i*512;if(take>512)take=512;
        memcpy(sector_at(TEST_DATA_LBA+(cluster-2)*64+i,1),bytes+i*512,take);
    }
}
static void reset_card(void)
{
    sector_count=write_count=fail_write=apply_failure=entry_writes=0;memset(&card,0,sizeof(card));
    uint8_t *m=sector_at(0,1);m[446+4]=0x0c;put32(m+446+8,32);put32(m+446+12,62333920);m[510]=0x55;m[511]=0xaa;
    uint8_t *b=sector_at(32,1);b[0]=0xeb;b[2]=0x90;memcpy(b+3,"MSDOS5.0",8);
    put16(b+11,512);b[13]=64;put16(b+14,32);b[16]=2;b[21]=0xf8;
    put32(b+32,62333920);put32(b+36,8000);put32(b+44,2);put16(b+48,1);put16(b+50,6);
    b[66]=0x29;memcpy(b+71,"NAMESPACE  ",11);memcpy(b+82,"FAT32   ",8);b[510]=0x55;b[511]=0xaa;
    memcpy(sector_at(38,1),b,512);uint8_t *f=sector_at(33,1);
    put32(f,0x41615252);put32(f+484,0x61417272);put32(f+488,0xffffffff);put32(f+492,10);put32(f+508,0xaa550000);
    memcpy(sector_at(39,1),f,512);fat_entry(0,0x0ffffff8);fat_entry(1,0x0fffffff);fat_entry(2,0x0fffffff);
    for(unsigned i=0;i<6;i++)seed_file(copies[i].source,i,i+3,ns_test_data[i],copies[i].bytes);
    memcpy(original_entry,ns_test_old,NS_OLD_BYTES);seed_file("XIANGQI.BIN",6,9,original_entry,NS_OLD_BYTES);
    memset(&test_card,0,sizeof(test_card));test_card.sector_count=62333952u;test_card.high_capacity=1;test_card.bus_width=4;
    memcpy(test_card.cid,expected_cid,sizeof(expected_cid));
}
static void check_original_entry(int patched)
{
    fat_ro_file_t f;uint8_t out[NS_OLD_BYTES];assert(!fat_ro_find(&card.volume,"XIANGQI.BIN",&f));
    assert(f.first_cluster==9&&f.size==NS_OLD_BYTES&&!fat_ro_load(&card.volume,&f,out,sizeof(out),0,0));
    if(patched){assert(!memcmp(out,ns_menu,NS_MENU_BYTES));assert(!memcmp(out+NS_MENU_BYTES,original_entry+NS_MENU_BYTES,NS_OLD_BYTES-NS_MENU_BYTES));}
    else assert(!memcmp(out,original_entry,sizeof(out)));
}
int main(void)
{
    setbuf(stdout,NULL);
    void *ram=VirtualAlloc((void *)(uintptr_t)0x04000000u,0x06000000u,MEM_RESERVE|MEM_COMMIT,PAGE_READWRITE);assert(ram==(void *)(uintptr_t)0x04000000u);
    reset_card();assert(install("wrong-CID")==FC_CORRUPT&&write_count==0);
    test_card.cid[0]^=1;assert(install(NS_TEST_CID_TEXT)==FC_CORRUPT&&write_count==0);
    reset_card();sector_at(TEST_DATA_LBA+64,0)[0]^=1;
    assert(install(NS_TEST_CID_TEXT)==FC_CORRUPT&&write_count==0);
    reset_card();seed_file("PN01K.BIN",7,10,ns_test_data[1],copies[1].bytes);
    assert(install(NS_TEST_CID_TEXT)==FC_CORRUPT&&write_count==0);
    reset_card();int rc=install(NS_TEST_CID_TEXT);if(rc)printf("TEST_INSTALL_FAILURE rc=%d writes=%u dirty=%u staged=%u\n",rc,write_count,card.dirty,card.staged);
    assert(!rc);unsigned good_writes=write_count;assert(good_writes>10);
    check_original_entry(1);
    for(unsigned i=0;i<6;i++){
        assert(!load(copies[i].name,copies[i].bytes,copies[i].crc,0x04000000u));
        assert(!memcmp((void *)(uintptr_t)0x04000000u,ns_test_data[i],copies[i].bytes));
        assert(!load(copies[i].source,copies[i].bytes,copies[i].crc,0x04000000u));
    }
    assert(!load("PN00BOOT.BIN",NS_OLD_BYTES,NS_OLD_CRC,0x04000000u));
    assert(!memcmp((void *)(uintptr_t)0x04000000u,original_entry,NS_OLD_BYTES));
    assert(install(NS_TEST_CID_TEXT)==FC_CORRUPT&&write_count==good_writes);
    for(unsigned at=1;at<=good_writes;at++)for(unsigned applied=0;applied<2;applied++){
        reset_card();fail_write=at;apply_failure=applied;
        assert(install(NS_TEST_CID_TEXT)!=0&&write_count==at);
        if(!entry_writes)check_original_entry(0);
        else {
            assert(!load("PN00BOOT.BIN",NS_OLD_BYTES,NS_OLD_CRC,0x04000000u));
            assert(!memcmp((void *)(uintptr_t)0x04000000u,original_entry,NS_OLD_BYTES));
        }
    }
    assert(VirtualFree(ram,0,MEM_RELEASE));
    printf("SD_NAMESPACE_FAT32_INSTALL_PASS wrong_CID=2 corrupt_source=1 collisions=1 full_copy=1 preserve_tail_chain=1 write_fault_cases=%u no_write_retries=1\n",good_writes*2);return 0;
}
