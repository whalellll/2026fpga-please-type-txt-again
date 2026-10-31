/* Runs the production loader and frozen FAT reader on a real FAT32 image.
 * Only SD transport, MMIO, DDR mapping and the final hardware jump are mocked. */
#define _GNU_SOURCE
#include "soc.h"
#include "sd.h"
#include "fat_ro.h"
#include "payloads.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <setjmp.h>
#include <sys/mman.h>
#include <sys/stat.h>
#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif

int sd80_main(void);
static int image, released, initialized, jumped;
static uint8_t *image_data;
static unsigned reads;
static const char *scenario, *directory;
static sd_card_info_t card;
static jmp_buf finish;
static void check(int ok, const char *message)
{
    if (!ok) { fprintf(stderr, "HOST_TEST_FAIL %s\n", message); exit(2); }
}
void console_putc(char c) { (void)c; }
void console_puts(const char *s) { fputs(s, stdout); }
int console_getc_timeout(uint32_t ticks) { (void)ticks; return !strcmp(scenario,"abort") ? 27 : -1; }
void delay_cycles(uint32_t n) { (void)n; }
int ddr_wait_ready(void) { return 0; }
int ddr_range_valid(uint32_t a, uint32_t n)
{
    return n && a < 0x1c000000u && n <= 0x1c000000u-a &&
        !(a < 0x02010000u && a+n > 0x02000000u) &&
        !(a < 0x1b800000u && a+n > 0x1b000000u);
}
int sd_init(void) { initialized++; return !strcmp(scenario,"init") ? -1 : 0; }
void sd_release(void) { released++; }
const sd_card_info_t *sd_card_info(void) { return &card; }
int sd_read_sectors(uint32_t lba, uint32_t n, uint8_t *out)
{
    size_t bytes = (size_t)n * 512;
    reads++;
    if (!strcmp(scenario,"io") || !n || n>32 || lba>card.sector_count || n>card.sector_count-lba) return -1;
    memcpy(out,image_data+(size_t)lba*512,bytes);
    return 0;
}
static void map(uint32_t address, uint32_t size)
{
    void *p=mmap((void *)(uintptr_t)address,size,PROT_READ|PROT_WRITE,
                 MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    check(p==(void *)(uintptr_t)address,"DDR mapping");
}
void jump_to(uint32_t entry,uint32_t hart,uint32_t dtb)
{
    unsigned i;
    check(entry==0x18000000u && hart==0 && dtb==0x1a000000u,"jump ABI");
    check(released==1,"SD released before OpenSBI");
    for(i=0;i<PAYLOAD_COUNT;i++) {
        char path[4096]; uint8_t *data; FILE *f;
        payload_t *p=&payloads[i];
        snprintf(path,sizeof(path),"%s/%s",directory,p->name);
        f=fopen(path,"rb"); check(f!=NULL,"source file");
        data=malloc(p->bytes); check(data!=NULL,"allocation");
        check(fread(data,1,p->bytes,f)==p->bytes,"source read"); fclose(f);
        check(!memcmp(data,(const void *)(uintptr_t)p->address,p->bytes),"cached payload exact bytes");
        check(!memcmp(data,(const void *)(uintptr_t)(p->address|0x80000000u),p->bytes),"alias payload exact bytes");
        free(data);
    }
    jumped=1; longjmp(finish,1);
}
int main(int argc,char **argv)
{
    struct stat st; unsigned i;
    check(argc==4,"arguments"); scenario=argv[1]; directory=argv[3];
    image=open(argv[2],O_RDONLY); check(image>=0 && !fstat(image,&st),"open FAT image");
    image_data=malloc((size_t)st.st_size); check(image_data!=NULL,"image allocation");
    check(pread(image,image_data,(size_t)st.st_size,0)==st.st_size,"read complete image");
    card.sector_count=(uint32_t)(st.st_size/512);
    map(0x1fe00000u,0x10000);
    REG32(CPU_HZ_REG)=!strcmp(scenario,"clock")?69000000u:75000000u;
    REG32(SYS_HZ_REG)=49500000u; REG32(TIMEBASE_HZ_REG)=49500000u;
    for(i=0;i<PAYLOAD_COUNT;i++) {
        uint32_t size=(payloads[i].bytes+4095u)&~4095u;
        map(payloads[i].address,size); map(payloads[i].address|0x80000000u,size);
    }
    if(!setjmp(finish)) check(sd80_main()!=0,"failure returns nonzero");
    if(!strcmp(scenario,"pass")) check(jumped && reads>100,"complete FAT32 six-file boot");
    else check(!jumped,"refuse unsafe boot");
    if(!strcmp(scenario,"clock")) check(!initialized && !reads && !released,"clock checked before SD");
    else check(released==1,"release on success/failure");
    close(image); printf("HOST_TEST_PASS %s reads=%u\n",scenario,reads); return 0;
}
