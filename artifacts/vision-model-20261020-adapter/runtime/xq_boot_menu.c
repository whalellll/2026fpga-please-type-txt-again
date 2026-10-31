/* Stable SD selector: ROM loads at 0x01000000; start relocates to 0x01400000. */
#include "soc.h"
#include "sd.h"
#include "fat_ro.h"
#include "crc32_fast.h"
#include "console_line.h"
#include "xq_boot_menu.h"
#include <string.h>
static fat_ro_volume_t volume;
static char config[XQBM_CONFIG_MAX+4] __attribute__((aligned(4)));
static xqbm_menu menu;
static int rd(void *u,uint32_t lba,uint32_t n,uint8_t *data)
{(void)u;return sd_read_sectors(lba,n,data);}
static int progress(void *u,uint32_t done,uint32_t total)
{(void)u;(void)done;(void)total;return console_getc_timeout(1u)==27;}
static int boot(const xqbm_entry *e)
{
    fat_ro_file_t f;
    if(fat_ro_find(&volume,e->name,&f)||f.size!=e->bytes||
       fat_ro_load(&volume,&f,(void *)(uintptr_t)0x01000000u,e->bytes,progress,0))return 0;
    volatile const uint32_t *src=(volatile const uint32_t *)(uintptr_t)0x01000000u;
    volatile uint32_t *dst=(volatile uint32_t *)(uintptr_t)0x81000000u;
    for(uint32_t i=0;i<e->bytes/4u;i++)dst[i]=src[i];
    __asm__ volatile("fence iorw,iorw" ::: "memory");
    uint32_t crc=crc32_fast(0xffffffffu,(const void *)(uintptr_t)0x81000000u,e->bytes)^0xffffffffu;
    if(crc!=e->crc)return 0;
    console_puts("XQ_BOOT_MENU_PAYLOAD_PASS name=");console_puts(e->name);
    console_puts(" bytes=");console_dec(e->bytes);console_puts(" crc=");console_hex(crc);console_putc('\n');
    sd_release();jump_to(0x01000000u,0,0);return 1;
}
int main(void)
{
    fat_ro_file_t f;char line[32];
    console_puts("XQ_BOOT_MENU_BEGIN sd_only=1\n");
    if(sd_init()||fat_ro_mount(&volume,rd,0,sd_card_info()->sector_count)||
       fat_ro_find(&volume,"XQBOOT.CFG",&f)||!f.size||f.size>XQBM_CONFIG_MAX||
       fat_ro_load(&volume,&f,config,sizeof(config)-1,0,0))goto fail;
    config[f.size]=0;if(!xqbm_parse(config,f.size,&menu))goto fail;
    for(unsigned i=0;i<menu.count;i++){
        console_dec(i+1);console_puts(" ");console_puts(menu.entry[i].label);
        console_puts(" [");console_puts(menu.entry[i].name);console_puts("]\n");
    }
    for(;;){
        console_puts("bootmenu> ");console_readline(line,sizeof(line));
        if(!strcmp(line,"console")){sd_release();jump_to(0x1c000000u,0,0);return 0;}
        unsigned n=line[0]?(unsigned)(line[0]-'1'):0;
        if((line[0]&&line[1])||n>=menu.count){console_puts("Select 1..8 or console; Enter selects 1\n");continue;}
        if(!boot(&menu.entry[n]))console_puts("XQ_BOOT_MENU_REJECT size/CRC/read; no jump\n");
    }
fail:
    console_puts("XQ_BOOT_MENU_FAIL configuration; returning ROM\n");
    sd_release();jump_to(0x1c000000u,0,0);return 1;
}
