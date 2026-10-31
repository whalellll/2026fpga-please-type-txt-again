#include "soc.h"
#include "sd.h"
#include "fat_ro.h"
#include "crc32_fast.h"
#include "payloads.h"

static fat_ro_volume_t volume;
static int read_sectors(void *user, uint32_t lba, uint32_t count, uint8_t *out)
{
    (void)user;
    return sd_read_sectors(lba, count, out);
}
static int progress(void *user, uint32_t done, uint32_t total)
{
    (void)user;
    if (done == total || (done & 0xfffffu) < 16384u) console_putc('.');
    return console_getc_timeout(1u) == 0x1b;
}
/* Preserve the accepted loader's word stores to both DDR aliases. */
static uint32_t publish(uint32_t address, uint32_t bytes)
{
    volatile const uint32_t *cached = (const volatile uint32_t *)(uintptr_t)address;
    volatile uint32_t *alias = (volatile uint32_t *)(uintptr_t)(address | 0x80000000u);
    uint32_t i, crc;
    for (i = 0; i < (bytes + 3u) / 4u; ++i) alias[i] = cached[i];
#ifdef __riscv
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
#endif
    crc = crc32_fast(0xffffffffu, (const void *)(uintptr_t)(address | 0x80000000u), bytes & ~3u);
    if (bytes & 3u) {
        uint32_t tail = alias[bytes >> 2], remain = bytes & 3u;
        while (remain--) {
            uint32_t bit;
            crc ^= tail & 255u;
            for (bit = 0; bit < 8u; ++bit) crc = (crc >> 1) ^ (0xedb88320u & -(crc & 1u));
            tail >>= 8;
        }
    }
    return crc ^ 0xffffffffu;
}
int main(void)
{
    uint32_t i;
    int error;
    console_puts("MAIN75_SD_BOOT_BEGIN\n");
    if (REG32(CPU_HZ_REG) != 75000000u || REG32(SYS_HZ_REG) != 49500000u ||
        REG32(TIMEBASE_HZ_REG) != 49500000u) {
        console_puts("MAIN75_SD_CLOCK_MISMATCH\n");
        return 1;
    }
    ddr_wait_ready();
    error = sd_init();
    if (error) { console_puts("MAIN75_SD_INIT_FAIL\n"); sd_release(); return 1; }
    error = fat_ro_mount(&volume, read_sectors, 0, sd_card_info()->sector_count);
    if (error) { console_puts("MAIN75_SD_FAT_FAIL\n"); sd_release(); return 1; }
    /* Find and validate every file before writing any Linux/model payload. */
    for (i = 0; i < PAYLOAD_COUNT; ++i) {
        payload_t *p = &payloads[i];
        if (fat_ro_find(&volume, p->name, &p->file) || p->file.size != p->bytes ||
            !ddr_range_valid(p->address, p->bytes + 3u)) {
            console_puts("MAIN75_SD_FILE_INVALID "); console_puts(p->name); console_putc('\n');
            sd_release(); return 1;
        }
    }
    for (i = 0; i < PAYLOAD_COUNT; ++i) {
        payload_t *p = &payloads[i];
        console_puts("Loading "); console_puts(p->name); console_putc('\n');
        error = fat_ro_load(&volume, &p->file, (void *)(uintptr_t)p->address, p->bytes, progress, 0);
        if (error || publish(p->address, p->bytes) != p->crc32) {
            console_puts("MAIN75_SD_LOAD_OR_CRC_FAIL "); console_puts(p->name); console_putc('\n');
            sd_release(); return 1;
        }
    }
    sd_release();
    console_puts("MAIN75_SD_PAYLOADS_CRC_PASS cpu=75000000 sys=49500000 ratio=33/50\n");
    delay_cycles(TIMEBASE_HZ * 5u);
    jump_to(0x18000000u, 0u, 0x1a000000u);
    return 1;
}
