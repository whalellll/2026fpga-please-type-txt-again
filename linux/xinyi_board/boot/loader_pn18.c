/* PN18 read-only eight-payload loader with a separate reserved voice bank.
 * Independent successor; the PN15 loader and its source bytes remain intact.
 * Adapted from scripts/cpu80_sd/loader.c.
 * CPU60 sources/ROM and the immutable six payloads are bound by the builder.
 * No selector, FAT write, camera, Flash or on-card installation code is linked.
 */
#include "soc.h"
#include "sd.h"
#include "fat_ro.h"
#include "crc32_fast.h"
#include "payloads.h"
#include "target.h"
#include "xq_camera.h"
#ifndef XINYI_BOOT_PREFIX
#define XINYI_BOOT_PREFIX "PN03"
#endif

static fat_ro_volume_t volume;
struct boot_clock { uint32_t previous; uint64_t elapsed; int cancelled; };
static uint64_t camera_now(void *context)
{
    struct boot_clock *c=context;
    uint32_t now=read_mtime_ticks32();
    c->elapsed+=(uint32_t)(now-c->previous);c->previous=now;
    return c->elapsed/(TIMEBASE_HZ/1000u);
}
static int camera_poll(void *context,int waiting)
{
    struct boot_clock *c=context;
    if(waiting)delay_cycles(TIMEBASE_HZ/1000u);
    if(console_getc_timeout(1u)==27)c->cancelled=1;
    return c->cancelled;
}
static int camera_idle(void)
{
    uint32_t status=REG32(CAMERA_BASE+CAMERA_REG_STATUS);
    return !(REG32(CAMERA_BASE+CAMERA_REG_CONTROL)&CAMERA_CONTROL_ENABLE) &&
        !(status&(CAMERA_STATUS_ENABLED|CAMERA_STATUS_WRITER_BUSY|CAMERA_STATUS_STOPPING)) &&
        (status&CAMERA_STATUS_IDLE);
}
static int camera_quiesce(void)
{
    struct boot_clock clock={read_mtime_ticks32(),0,0};
    xqc_camera camera={0};
    unsigned polls;
    if(REG32(CAMERA_BASE)!=CAMERA_ID_VALUE || REG32(CAMERA_BASE+4u)!=CAMERA_VERSION_VALUE)return 0;
    camera.camera=(volatile uint32_t *)(uintptr_t)CAMERA_BASE;
    camera.fb=(volatile uint32_t *)(uintptr_t)FB_REG_BASE;
    camera.sys=(volatile uint32_t *)(uintptr_t)SYS_BASE;
    camera.now_ms=camera_now;camera.poll=camera_poll;camera.context=&clock;
    /* xqc_stop never returns ownership before accepted native DDR bursts drain.
     * It does not initialize or start a sensor that was already idle. */
    if(xqc_stop(&camera))return 0;
    for(polls=0;polls<2000u;polls++){
        if(camera_idle())return !clock.cancelled;
        (void)camera_poll(&clock,1);
    }
    return 0;
}
static int read_sectors(void *user,uint32_t lba,uint32_t count,uint8_t *out)
{ (void)user; return sd_read_sectors(lba,count,out); }
static int progress(void *user,uint32_t done,uint32_t total)
{
    (void)user;
    if(done==total || (done&0xfffffu)<16384u)console_putc('.');
    return console_getc_timeout(1u)==27;
}
/* The uncached alias accepts word stores only; CRC tails read a complete
 * word and fold the requested bytes in registers. Never issue alias byte IO.
 */
static uint32_t publish(uint32_t address,uint32_t bytes)
{
    volatile const uint32_t *cached=(const volatile uint32_t *)(uintptr_t)address;
    volatile uint32_t *alias=(volatile uint32_t *)(uintptr_t)(address|0x80000000u);
    uint32_t crc,i;
    for(i=0;i<(bytes+3u)/4u;i++)alias[i]=cached[i];
#ifdef __riscv
    __asm__ volatile("fence iorw,iorw":::"memory");
#endif
    crc=crc32_fast(0xffffffffu,(const void *)(uintptr_t)(address|0x80000000u),bytes&~3u);
    if(bytes&3u){
        uint32_t tail=alias[bytes>>2],remain=bytes&3u;
        while(remain--){
            uint32_t bit;
            crc^=tail&255u;
            for(bit=0;bit<8u;bit++)crc=(crc>>1)^(0xedb88320u&-(crc&1u));
            tail>>=8;
        }
    }
    return crc^0xffffffffu;
}
static int target_matches(void)
{
#ifdef XINYI_REQUIRE_EXACT_VERSION
    if(REG32(0x1fe1006cu)!=XINYI_REQUIRE_EXACT_VERSION ||
       ((REG32(0x1fe1000cu)|REG32(0x1fe10044u)|REG32(0x1fe1010cu)|
         REG32(0x1fe1018cu)|REG32(0x1fe1008cu))&1u))return 0;
#endif
    if(REG32(SYS_BASE)!=SYS_ID_VALUE || (REG32(SYS_BASE+12u)&31u)!=31u ||
       REG32(CPU_HZ_REG)!=60000000u || REG32(SYS_HZ_REG)!=49500000u ||
       REG32(TIMEBASE_HZ_REG)!=49500000u ||
       REG32(0x1fe10000u)!=0x50464e31u || REG32(0x1fe10004u)!=0x00010000u ||
       REG32(0x1fe10040u)!=0x56333231u ||
       REG32(0x1fe00800u)!=0x56434531u || REG32(0x1fe00804u)!=0x00010000u ||
       REG32(0x1fe00880u)!=0x56434e31u || REG32(0x1fe00884u)!=0x00010000u)return 0;
    /* BRAM .data/BSS/stack change while the ROM console runs. Check only its
     * exact immutable executable interval; full initial ROM SHA is bound by
     * the frozen source/bitstream snapshot, never inferred from this CRC.
     */
    return (crc32_fast(0xffffffffu,(const void *)(uintptr_t)XINYI_ROM_CODE_START,
                       XINYI_ROM_CODE_BYTES)^0xffffffffu)==XINYI_ROM_CODE_CRC;
}
/* The sidecar is never part of the16MiB initrd and never guesses a live
 * Linux allocation. All eight metadata records are rejected before SD reads
 * if the compile-time reservation/placement contract is inconsistent. */
static int sidecar_layout(void)
{
    static const uint32_t addresses[]={0x18000000u,0x03000000u,0x10000000u,
        0x15000000u,0x00400000u,0x1a000000u,0x03000000u+XINYI_ROOTFS_OVERLAY_OFFSET,
        XINYI_WHOLE_BANK_BASE};
    if(PAYLOAD_COUNT!=8 || XINYI_WHOLE_BANK_INDEX!=7u ||
       XINYI_WHOLE_BANK_BASE!=0x04000000u || !XINYI_WHOLE_BANK_BYTES ||
       XINYI_WHOLE_BANK_BYTES>0x0effffffu-XINYI_WHOLE_BANK_BASE ||
       XINYI_WHOLE_BANK_SPAN!=((XINYI_WHOLE_BANK_BYTES+4095u)&~4095u) ||
       XINYI_WHOLE_BANK_BASE+XINYI_WHOLE_BANK_SPAN>=0x0f000000u ||
       XINYI_ROOTFS_BASE_BYTES!=payloads[1].bytes ||
       XINYI_ROOTFS_BASE_BYTES>XINYI_ROOTFS_OVERLAY_OFFSET ||
       XINYI_ROOTFS_OVERLAY_OFFSET>0x01000000u ||
       payloads[6].bytes>0x01000000u-XINYI_ROOTFS_OVERLAY_OFFSET ||
       payloads[7].bytes!=XINYI_WHOLE_BANK_BYTES)return 0;
    for(uint32_t i=0;i<PAYLOAD_COUNT;i++){
        const payload_t *p=&payloads[i];
        if(!p->bytes || p->address!=addresses[i] || p->bytes>0x1bffffffu ||
           p->address>=0x1c000000u || p->bytes+3u>0x1c000000u-p->address)return 0;
        uint32_t end=p->address+((p->bytes+3u)&~3u);
        if(i!=XINYI_WHOLE_BANK_INDEX && p->address<XINYI_WHOLE_BANK_BASE+XINYI_WHOLE_BANK_SPAN &&
           XINYI_WHOLE_BANK_BASE<end)return 0;
        for(uint32_t j=0;j<i;j++){
            uint32_t previous_end=payloads[j].address+((payloads[j].bytes+3u)&~3u);
            if(p->address<previous_end && payloads[j].address<end)return 0;
        }
    }
    return 1;
}
int main(void)
{
    uint32_t i;
    int error;
    console_puts("XINYI_" XINYI_BOOT_PREFIX "_BOOT_BEGIN read_only_sd=1\n");
    if(!sidecar_layout()){
        console_puts("XINYI_PN18_BANK_LAYOUT_REJECTED no_sd_read=1\n");return 1;
    }
    if(!target_matches()){
        console_puts("XINYI_" XINYI_BOOT_PREFIX "_TARGET_OR_ROM_CODE_REJECTED\n");return 1;
    }
    console_puts("XINYI_" XINYI_BOOT_PREFIX "_TARGET_ROM_CODE_PASS cpu=60000000 sys=49500000 ratio=33/40\n");
    if(ddr_wait_ready())return 1;
    if(!camera_quiesce()){
        console_puts("XINYI_" XINYI_BOOT_PREFIX "_CAMERA_DRAIN_FAIL no_jump=1\n");return 1;
    }
    error=sd_init();
    if(error){console_puts("XINYI_" XINYI_BOOT_PREFIX "_SD_INIT_FAIL\n");sd_release();return 1;}
    error=fat_ro_mount(&volume,read_sectors,0,sd_card_info()->sector_count);
    if(error){console_puts("XINYI_" XINYI_BOOT_PREFIX "_FAT_FAIL\n");sd_release();return 1;}
    /* Validate every record before loading any Linux/model payload. */
    for(i=0;i<PAYLOAD_COUNT;i++){
        payload_t *p=&payloads[i];
        if(fat_ro_find(&volume,p->name,&p->file) || p->file.size!=p->bytes ||
           !ddr_range_valid(p->address,p->bytes+3u)){
            console_puts("XINYI_" XINYI_BOOT_PREFIX "_FILE_INVALID\n");sd_release();return 1;
        }
    }
    for(i=0;i<PAYLOAD_COUNT;i++){
        payload_t *p=&payloads[i];
        console_puts("Loading ");console_puts(p->name);console_putc('\n');
        error=fat_ro_load(&volume,&p->file,(void *)(uintptr_t)p->address,p->bytes,progress,0);
        if(error || publish(p->address,p->bytes)!=p->crc32){
            console_puts("XINYI_" XINYI_BOOT_PREFIX "_LOAD_OR_CRC_FAIL\n");sd_release();return 1;
        }
    }
    /* Clear the reserved page tail too. The complete file CRC has already
     * passed; ordinary Linux pages never include this no-map reservation. */
    for(i=(XINYI_WHOLE_BANK_BYTES+3u)&~3u;i<XINYI_WHOLE_BANK_SPAN;i+=4u){
        REG32(XINYI_WHOLE_BANK_BASE+i)=0;
        REG32((XINYI_WHOLE_BANK_BASE+i)|0x80000000u)=0;
    }
#ifdef __riscv
    __asm__ volatile("fence iorw,iorw":::"memory");
#endif
#ifdef XINYI_ROOTFS_OVERLAY
    /* The kernel accepts raw-newc followed by zero padding and gzip-newc.
     * Both archives have independently passed the descriptor CRC above.
     * Clear the page-alignment gap explicitly through word-safe publication. */
    for(i=XINYI_ROOTFS_BASE_BYTES;i<XINYI_ROOTFS_OVERLAY_OFFSET;i+=4u){
        REG32(0x03000000u+i)=0;REG32(0x83000000u+i)=0;
    }
#ifdef __riscv
    __asm__ volatile("fence iorw,iorw":::"memory");
#endif
#endif
    sd_release();
    if(!camera_idle()){
        console_puts("XINYI_" XINYI_BOOT_PREFIX "_CAMERA_HANDOFF_REJECTED no_jump=1\n");return 1;
    }
    console_puts("XINYI_" XINYI_BOOT_PREFIX "_CAMERA_HANDOFF_IDLE enable=0 writer_busy=0 stopping=0\n");
#ifdef XINYI_ROOTFS_OVERLAY
    console_puts("XINYI_" XINYI_BOOT_PREFIX "_EIGHT_CRC_PASS cpu=60000000 sys=49500000 ratio=33/40\n");
#else
    console_puts("XINYI_" XINYI_BOOT_PREFIX "_SIX_CRC_PASS cpu=60000000 sys=49500000 ratio=33/40\n");
#endif
    jump_to(0x18000000u,0u,0x1a000000u);
    return 1;
}
