/* Production loader/FAT reader, synthetic SD transport and mapped DDR/MMIO.
 * Adapted from scripts/cpu80_sd/host_test.c. No real hardware or image input.
 */
#define _GNU_SOURCE
#include "soc.h"
#include "sd.h"
#include "fat_ro.h"
#include "camera.h"
#include "payloads.h"
#include "target.h"
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
int xinyi_boot_main(void);
static int released,initialized,jumped;
static uint8_t *image_data;
static unsigned reads,camera_polls;
static const char *scenario,*directory;
static sd_card_info_t card;
static jmp_buf finish;
static void check(int ok,const char *message)
{if(!ok){fprintf(stderr,"HOST_TEST_FAIL %s\n",message);exit(2);}}
void console_putc(char c){(void)c;}
void console_puts(const char *s){fputs(s,stdout);}
int console_getc_timeout(uint32_t ticks)
{(void)ticks;return !strcmp(scenario,"abort")?27:-1;}
uint32_t read_mtime_ticks32(void)
{static uint32_t ticks;ticks+=TIMEBASE_HZ/1000u;return ticks;}
void delay_cycles(uint32_t ticks)
{
    (void)ticks;
    if((REG32(CAMERA_BASE+CAMERA_REG_CONTROL)&CAMERA_CONTROL_STOP_REQUEST) &&
       strcmp(scenario,"camera-stuck") && ++camera_polls>=3)
        REG32(CAMERA_BASE+CAMERA_REG_STATUS)=CAMERA_STATUS_IDLE;
}
int ddr_wait_ready(void){return 0;}
int ddr_range_valid(uint32_t address,uint32_t count)
{
    return count && address<0x1c000000u && count<=0x1c000000u-address &&
        !(address<0x02010000u && address+count>0x02000000u) &&
        !(address<0x1b800000u && address+count>0x1b000000u);
}
int sd_init(void){initialized++;return !strcmp(scenario,"init")?-1:0;}
void sd_release(void){released++;}
const sd_card_info_t *sd_card_info(void){return &card;}
int sd_read_sectors(uint32_t lba,uint32_t count,uint8_t *out)
{
    reads++;
    if(!strcmp(scenario,"io") || !count || count>32 ||
       lba>card.sector_count || count>card.sector_count-lba)return -1;
    memcpy(out,image_data+(size_t)lba*512,(size_t)count*512);return 0;
}
static void map(uint32_t address,uint32_t size)
{
    void *p=mmap((void *)(uintptr_t)address,size,PROT_READ|PROT_WRITE,
                MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED_NOREPLACE,-1,0);
    check(p==(void *)(uintptr_t)address,"DDR/MMIO mapping");
}
void jump_to(uint32_t entry,uint32_t hart,uint32_t dtb)
{
    check(entry==0x18000000u && !hart && dtb==0x1a000000u,"jump ABI");
    check(released==1,"SD released before jump");
    check(!REG32(CAMERA_BASE+CAMERA_REG_CONTROL) &&
          REG32(CAMERA_BASE+CAMERA_REG_STATUS)==CAMERA_STATUS_IDLE,"camera idle before jump");
    for(unsigned i=0;i<PAYLOAD_COUNT;i++){
        char path[4096];payload_t *p=&payloads[i];
        snprintf(path,sizeof(path),"%s/%s",directory,p->name);
        FILE *f=fopen(path,"rb");check(f!=NULL,"source file");
        uint8_t *data=malloc(p->bytes);check(data!=NULL,"allocation");
        check(fread(data,1,p->bytes,f)==p->bytes,"source read");fclose(f);
        check(!memcmp(data,(const void *)(uintptr_t)p->address,p->bytes),"cached payload bytes");
        check(!memcmp(data,(const void *)(uintptr_t)(p->address|0x80000000u),p->bytes),"uncached word publication bytes");
        free(data);
    }
#ifdef XINYI_ROOTFS_OVERLAY
    for(unsigned i=XINYI_ROOTFS_BASE_BYTES;i<XINYI_ROOTFS_OVERLAY_OFFSET;i++)
        check(!*(const uint8_t *)(uintptr_t)(0x03000000u+i) && !*(const uint8_t *)(uintptr_t)(0x83000000u+i),"overlay alignment zeros published");
#endif
    jumped=1;longjmp(finish,1);
}
int main(int argc,char **argv)
{
    struct stat st;check(argc==5,"arguments");scenario=argv[1];directory=argv[3];
    int image=open(argv[2],O_RDONLY);check(image>=0 && !fstat(image,&st),"FAT image");
    image_data=malloc((size_t)st.st_size);check(image_data!=NULL,"image allocation");
    check(pread(image,image_data,(size_t)st.st_size,0)==st.st_size,"image read");close(image);
    card.sector_count=(uint32_t)(st.st_size/512);
    map(0x1fe00000u,0x20000u);map(0x1c000000u,0x20000u);
    FILE *rom=fopen(argv[4],"rb");check(rom!=NULL,"ROM input");
    check(fread((void *)(uintptr_t)0x1c000000u,1,0x20000u,rom)==0x20000u,"ROM complete read");fclose(rom);
    REG32(SYS_BASE)=SYS_ID_VALUE;REG32(SYS_BASE+12u)=31u;
    REG32(CPU_HZ_REG)=60000000u;REG32(SYS_HZ_REG)=REG32(TIMEBASE_HZ_REG)=49500000u;
    REG32(0x1fe10000u)=0x50464e31u;REG32(0x1fe10004u)=0x00010000u;REG32(0x1fe10040u)=0x56333231u;
#ifdef XINYI_REQUIRE_EXACT_VERSION
    REG32(0x1fe1006cu)=XINYI_REQUIRE_EXACT_VERSION;
    if(!strcmp(scenario,"old-exact"))REG32(0x1fe1006cu)=0x00010000u;
    if(!strcmp(scenario,"wrong-exact"))REG32(0x1fe1006cu)=0x00010002u;
    const uint32_t busy_regs[5]={0x1fe1000cu,0x1fe10044u,0x1fe1010cu,0x1fe1018cu,0x1fe1008cu};
    if(!strncmp(scenario,"engine-busy-",12) && scenario[12]>='0' && scenario[12]<='4')
        REG32(busy_regs[scenario[12]-'0'])=1;
#endif
    REG32(0x1fe00800u)=0x56434531u;REG32(0x1fe00804u)=0x00010000u;
    REG32(0x1fe00880u)=0x56434e31u;REG32(0x1fe00884u)=0x00010000u;
    REG32(CAMERA_BASE)=CAMERA_ID_VALUE;REG32(CAMERA_BASE+4u)=CAMERA_VERSION_VALUE;
    REG32(CAMERA_BASE+CAMERA_REG_STATUS)=CAMERA_STATUS_IDLE;
    if(!strcmp(scenario,"clock"))REG32(CPU_HZ_REG)=80000000u;
    if(!strcmp(scenario,"sys"))REG32(SYS_HZ_REG)=50000000u;
    if(!strcmp(scenario,"timebase"))REG32(TIMEBASE_HZ_REG)=60000000u;
    if(!strcmp(scenario,"capability"))REG32(0x1fe10040u)=0;
    if(!strcmp(scenario,"rom"))REG32(0x1c000000u)^=1u;
    if(!strcmp(scenario,"rom-data"))REG32(XINYI_ROM_CODE_START+XINYI_ROM_CODE_BYTES+4u)^=1u;
    if(!strcmp(scenario,"camera-busy") || !strcmp(scenario,"camera-stuck")){
        REG32(CAMERA_BASE+CAMERA_REG_CONTROL)=CAMERA_CONTROL_ENABLE;
        REG32(CAMERA_BASE+CAMERA_REG_STATUS)=CAMERA_STATUS_ENABLED|CAMERA_STATUS_WRITER_BUSY;
    }
    for(unsigned i=0;i<PAYLOAD_COUNT;i++){
        uint32_t size=(payloads[i].bytes+4095u)&~4095u;
        map(payloads[i].address,size);map(payloads[i].address|0x80000000u,size);
    }
#ifdef XINYI_ROOTFS_OVERLAY
    memset((void *)(uintptr_t)(0x03000000u+XINYI_ROOTFS_BASE_BYTES),0xa5,XINYI_ROOTFS_OVERLAY_OFFSET-XINYI_ROOTFS_BASE_BYTES);
    memset((void *)(uintptr_t)(0x83000000u+XINYI_ROOTFS_BASE_BYTES),0xa5,XINYI_ROOTFS_OVERLAY_OFFSET-XINYI_ROOTFS_BASE_BYTES);
#endif
    if(!setjmp(finish))check(xinyi_boot_main()!=0,"failure returns nonzero");
    if(!strcmp(scenario,"pass") || !strcmp(scenario,"camera-busy") || !strcmp(scenario,"rom-data"))
        check(jumped && reads>100,"complete six-file load");
    else check(!jumped,"reject unsafe jump");
    if(!strcmp(scenario,"clock") || !strcmp(scenario,"sys") || !strcmp(scenario,"timebase") ||
       !strcmp(scenario,"capability") || !strcmp(scenario,"rom") || !strcmp(scenario,"camera-stuck"))
        check(!initialized && !reads && !released,"preflight rejected before SD");
    else if(!strcmp(scenario,"old-exact") || !strcmp(scenario,"wrong-exact") || !strncmp(scenario,"engine-busy-",12))
        check(!initialized && !reads && !released,"e42 preflight rejected before SD");
    else check(released==1,"SD released on success/failure");
    if(!strcmp(scenario,"metadata"))for(unsigned i=0;i<PAYLOAD_COUNT;i++)
        check(!REG32(payloads[i].address) && !REG32(payloads[i].address|0x80000000u),"all metadata before any payload");
    printf("HOST_TEST_PASS %s reads=%u camera_polls=%u\n",scenario,reads,camera_polls);return 0;
}
