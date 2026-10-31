#include "soc.h"
#include "sd.h"
#include "fat_ro.h"
#include "crc32_fast.h"
#ifdef SD_LOADER_SMODE_TIMER_PROBE
#include "smode_timer_payload.inc"
#endif
#ifdef SD_LOADER_SBI_TIMER_BRIDGE
#include "opensbi_timer_bridge.inc"
#endif

#define SKIP_STAGEB_PROBE 0

typedef struct {
    const char *name;
    uint32_t address;
    uint32_t bytes;
    uint32_t crc32;
    fat_ro_file_t file;
} payload_t;

static fat_ro_volume_t volume;
#ifdef SD_LOADER_TIMER_HW_PROBE
static uint64_t read_mtime64(void)
{
    uint32_t hi0, lo, hi1;
    do {
        hi0 = REG32(CLINT_MTIME + 4u);
        lo = REG32(CLINT_MTIME);
        hi1 = REG32(CLINT_MTIME + 4u);
    } while (hi0 != hi1);
    return ((uint64_t)hi1 << 32) | lo;
}

static int probe_machine_timer(void)
{
    const uint64_t start = read_mtime64();
    const uint64_t target = start + (uint64_t)TIMEBASE_HZ * 2u;
    const uint64_t deadline = start + (uint64_t)TIMEBASE_HZ * 3u;
    uint64_t now;
    uint32_t mip;
    REG32(CLINT_BASE + 0x4004u) = 0xffffffffu;
    REG32(CLINT_BASE + 0x4000u) = (uint32_t)target;
    REG32(CLINT_BASE + 0x4004u) = (uint32_t)(target >> 32);
    do {
        // csrr a0,mip, encoded for the bundled GCC 9 assembler's rv32ima mode.
        __asm__ volatile (".word 0x34402573\n\tmv %0,a0" : "=r"(mip) :: "a0");
        now = read_mtime64();
        if (mip & (1u << 7)) {
            REG32(CLINT_BASE + 0x4004u) = 0xffffffffu;
            REG32(CLINT_BASE + 0x4000u) = 0xffffffffu;
            console_puts("M_TIMER_IRQ_PASS elapsed_ticks=");
            console_dec((uint32_t)(now - start));
            console_putc('\n');
            return 1;
        }
    } while (now < deadline);
    REG32(CLINT_BASE + 0x4004u) = 0xffffffffu;
    REG32(CLINT_BASE + 0x4000u) = 0xffffffffu;
    console_puts("M_TIMER_IRQ_FAIL mip=");
    console_hex(mip);
    console_putc('\n');
    return 0;
}
#endif
static payload_t payloads[] = {
#if defined(SD_LOADER_BRIDGE_RELEASE_BOOT) || defined(SD_LOADER_BRIDGE_NONBLOCK_BOOT)
    {"brfw.bin",     0x18000000u,   266448u, 0x8072b5c4u, {0}},
#else
    {"fw_jump.bin",  0x18000000u,   264680u, 0x4bd705f0u, {0}},
#endif
    {"vaimage.bin", 0x00400000u, 7480856u, 0x33cbdbd7u, {0}},
#ifdef SD_LOADER_BRIDGE_NONBLOCK_BOOT
    {"vafs.bin", 0x03000000u, 8445952u, 0xc845a459u, {0}},
    {"va.dtb", 0x1a000000u, 2443u, 0xbf63c3d0u, {0}},
#elif defined(SD_LOADER_BRIDGE_RELEASE_BOOT)
    {"brfs.bin",     0x03000000u,  8227328u, 0x5472e903u, {0}},
    {"va.dtb", 0x1a000000u, 2443u, 0xbf63c3d0u, {0}},
#elif defined(SD_LOADER_OLD_BOOT)
    {"oldfs.bin",    0x03000000u, 10147328u, 0x91bfd6d8u, {0}},
    {"old.dtb",      0x1a000000u,     2323u, 0x16a9a30cu, {0}},
#elif defined(SD_LOADER_GUI_FIX_BOOT)
    {"fixfs.bin",    0x03000000u, 10147328u, 0x39bb37b4u, {0}},
    {"old.dtb",      0x1a000000u,     2323u, 0x16a9a30cu, {0}},
#elif defined(SD_LOADER_COMPACT_GUI_BOOT)
    {"compactfs.bin",0x03000000u, 10147328u, 0xa2678686u, {0}},
    {"old.dtb",      0x1a000000u,     2323u, 0x16a9a30cu, {0}},
#elif defined(SD_LOADER_MIN_GUI_BOOT)
    {"minfs.bin",    0x03000000u,  6434816u, 0xcd9de16au, {0}},
    {"minfs.dtb",    0x1a000000u,     2323u, 0xb10b5adeu, {0}},
#elif defined(SD_LOADER_MIN_SHADOW_BOOT)
    {"minfs-shadow.bin",0x03000000u, 6447104u, 0x13640f08u, {0}},
    {"minfs-shadow.dtb",0x1a000000u, 2323u, 0x388c4214u, {0}},
#elif defined(SD_LOADER_NO_SCRIPTS_BOOT)
    {"nofs.bin",     0x03000000u, 10151424u, 0xbbb53d2eu, {0}},
    {"nofs.dtb",     0x1a000000u,     2323u, 0xd8fba975u, {0}},
#elif defined(SD_LOADER_PAD_BOOT)
    {"padfs.bin",    0x03000000u, 10152448u, 0xa288de89u, {0}},
    {"soc.dtb",      0x1a000000u,     2323u, 0x9db36a7bu, {0}},
#else
    {"rootfs.cpio",  0x03000000u, 10152448u, 0x9ac21811u, {0}},
    {"soc.dtb",      0x1a000000u,     2323u, 0x9db36a7bu, {0}},
#endif
    {"pikafish.pff", 0x10000000u, 68122688u, 0x80322636u, {0}},
    {"pikafish.atk", 0x15000000u, 34603072u, 0xcba1dd72u, {0}}
};

static int read_sectors(void *ignored, uint32_t lba, uint32_t count,
                        uint8_t *destination)
{
    (void)ignored;
    return sd_read_sectors(lba, count, destination);
}

static int progress(void *ignored, uint32_t done, uint32_t total)
{
    (void)ignored;
    if (done == total || (done & 0xfffffu) < 16384u) {
        console_putc('.');
    }
    return console_getc_timeout(1u) == 0x1b;
}

static uint32_t copy_to_uncached(uint32_t physical, uint32_t count)
{
    volatile const uint32_t *cached = (volatile const uint32_t *)(uintptr_t)physical;
    volatile uint32_t *uncached = (volatile uint32_t *)(uintptr_t)(physical | 0x80000000u);
    uint32_t words = (count + 3u) / 4u;
    uint32_t index;
    uint32_t crc;
    for (index = 0; index < words; ++index) uncached[index] = cached[index];
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    crc = crc32_fast(0xffffffffu,
                     (const void *)(uintptr_t)(physical | 0x80000000u),
                     count & ~3u);
    if (count & 3u) {
        uint32_t tail = uncached[count >> 2];
        uint32_t remain = count & 3u;
        while (remain--) {
            uint32_t bit;
            crc ^= tail & 255u;
            for (bit = 0; bit < 8u; ++bit)
                crc = (crc >> 1) ^ (0xedb88320u & -(crc & 1u));
            tail >>= 8;
        }
    }
    return crc ^ 0xffffffffu;
}

static int skip_stageb_probe(void)
{
    static const char name[] = "etc/init.d/S94stageb_probe";
    const uint8_t *rootfs = (const uint8_t *)(uintptr_t)0x03000000u;
    uint32_t offset;
    uint32_t found = 0xffffffffu;
    uint32_t length = 10152448u;
    for (offset = 0; offset + sizeof(name) <= length; ++offset) {
        uint32_t index;
        for (index = 0; index < sizeof(name) - 1u; ++index)
            if (rootfs[offset + index] != (uint8_t)name[index]) break;
        if (index == sizeof(name) - 1u) {
            if (found != 0xffffffffu) return 0;
            found = offset;
        }
    }
    if (found == 0xffffffffu) return 0;
    {
        uint32_t address = 0x03000000u + found + 11u;
        uint32_t aligned = address & ~3u;
        uint32_t shift = (address & 3u) * 8u;
        volatile uint32_t *cached = (volatile uint32_t *)(uintptr_t)aligned;
        volatile uint32_t *uncached =
            (volatile uint32_t *)(uintptr_t)(aligned | 0x80000000u);
        uint32_t value = (*cached & ~(255u << shift)) | ((uint32_t)'T' << shift);
        *cached = value;
        *uncached = value;
        __asm__ volatile ("fence iorw, iorw" ::: "memory");
    }
    console_puts("PIKAFISH_PROBE_SKIP_PATCH\n");
    return 1;
}

#ifdef SD_LOADER_STANDALONE_DIAG
static int patch_standalone_diagnostic(void)
{
    static const char diagnostic[] =
        "#!/bin/sh\n"
        "[ \"$1\" = start ] || exit 0\n"
        "echo PFSB_STANDALONE_BEGIN >/dev/console\n"
        "echo PFSB_SHA_FIRST >/dev/console\n"
        "sha256sum /opt/pikafish/stageb-mac.bin >/dev/console 2>&1\n"
        "echo PFSB_GOLDEN_SHA >/dev/console\n"
        "sha256sum /opt/pikafish/stageb-golden.bin /opt/pikafish/stageb-position-golden.bin >/dev/console 2>&1\n"
        "echo PFSB_SHA_SECOND >/dev/console\n"
        "sha256sum /opt/pikafish/stageb-mac.bin >/dev/console 2>&1\n"
        "echo PFSB_HEADER >/dev/console\n"
        "dd if=/opt/pikafish/stageb-mac.bin bs=4096 count=1 2>/dev/null | sha256sum >/dev/console\n"
        "for i in 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do\n"
        " echo PFSB_SLOT=$i >/dev/console\n"
        " dd if=/opt/pikafish/stageb-mac.bin bs=4096 skip=$((1+9*i)) count=9 2>/dev/null | sha256sum >/dev/console\n"
        "done\n"
        "for j in 0 1 2 3 4 5 6 7 8; do\n"
        " echo PFSB_LAST_BLOCK=$j >/dev/console\n"
        " dd if=/opt/pikafish/stageb-mac.bin bs=4096 skip=$((136+j)) count=1 2>/dev/null | sha256sum >/dev/console\n"
        "done\n"
        "/usr/bin/pikafish-stageb-board-accept >/dev/console 2>&1\n"
        "echo PFSB_STANDALONE_DONE status=$? >/dev/console\n";
    const uint32_t start = 0x03000000u + 3781972u;
    const uint32_t bytes = 1642u;
    const uint8_t *old = (const uint8_t *)(uintptr_t)start;
    uint32_t offset;
    if (sizeof(diagnostic) > bytes || old[0] != '#' || old[1] != '!'
        || old[2] != '/' || old[3] != 'b') return 0;
    for (offset = 0; offset < bytes; ++offset) {
        uint32_t address = start + offset;
        uint32_t aligned = address & ~3u;
        uint32_t shift = (address & 3u) * 8u;
        uint8_t replacement = offset < sizeof(diagnostic) - 1u
                            ? (uint8_t)diagnostic[offset] : (uint8_t)'\n';
        volatile uint32_t *cached = (volatile uint32_t *)(uintptr_t)aligned;
        volatile uint32_t *uncached =
            (volatile uint32_t *)(uintptr_t)(aligned | 0x80000000u);
        uint32_t value = (*cached & ~(255u << shift))
                       | ((uint32_t)replacement << shift);
        *cached = value;
        *uncached = value;
    }
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    console_puts("PIKAFISH_STANDALONE_DIAG_PATCH\n");
    return 1;
}
#endif

#ifdef SD_LOADER_GUI_AUTOMOVE
static int patch_gui_automove(void)
{
    static const char diagnostic[] =
        "#!/bin/sh\n"
        "[ \"$1\" = start ] || exit 0\n"
        "echo XQ_TIMER_BEFORE_GUI_BEGIN >/dev/console\n"
        "sleep 5\n"
        "echo XQ_TIMER_BEFORE_GUI_PASS >/dev/console\n"
        "export PIKAFISH_STAGEB_ACCEL=1 PIKAFISH_MAC_BACKEND=mmio-shadow\n"
        "mkfifo /run/xiangqi-pikafish.in\n"
        "/usr/bin/xiangqi-pikafish </dev/null >/dev/console 2>&1 &\n"
        "echo $! >/run/xiangqi-pikafish.pid\n"
        "echo XQ_AUTO_MOVE_GUI_LAUNCHED >/dev/console\n"
        "echo XQ_STATUS_WRITE_BEGIN >/dev/console\n"
        "printf 'XQ_STATUS\\n' >/run/xiangqi-pikafish.in\n"
        "echo XQ_STATUS_WRITE_PASS >/dev/console\n"
        "echo XQ_TIMER_AFTER_GUI_BEGIN >/dev/console\n"
        "sleep 12\n"
        "echo XQ_TIMER_AFTER_GUI_PASS >/dev/console\n"
        "echo XQ_AUTO_MOVE_SUBMIT >/dev/console\n"
        "printf 'XQ_MOVE h2e2\\n' >/run/xiangqi-pikafish.in\n"
        "echo XQ_AUTO_MOVE_WRITTEN >/dev/console\n";
    const uint32_t start = 0x03000000u + 3781972u;
    const uint32_t bytes = 1642u;
    const uint8_t *old = (const uint8_t *)(uintptr_t)start;
    uint32_t offset;
    if (sizeof(diagnostic) > bytes || old[0] != '#' || old[1] != '!'
        || old[2] != '/' || old[3] != 'b') return 0;
    for (offset = 0; offset < bytes; ++offset) {
        uint32_t address = start + offset;
        uint32_t aligned = address & ~3u;
        uint32_t shift = (address & 3u) * 8u;
        uint8_t replacement = offset < sizeof(diagnostic) - 1u
                            ? (uint8_t)diagnostic[offset] : (uint8_t)'\n';
        volatile uint32_t *cached = (volatile uint32_t *)(uintptr_t)aligned;
        volatile uint32_t *uncached =
            (volatile uint32_t *)(uintptr_t)(aligned | 0x80000000u);
        uint32_t value = (*cached & ~(255u << shift))
                       | ((uint32_t)replacement << shift);
        *cached = value;
        *uncached = value;
    }
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    console_puts("PIKAFISH_GUI_AUTOMOVE_PATCH\n");
    return 1;
}
#endif

#ifdef SD_LOADER_SYNC_INITRD
static int patch_sync_initrd_bootarg(void)
{
    static const char old_arg[] = "clocksource=jiffies";
    static const char new_arg[] = "                   ";
    const uint8_t *dtb = (const uint8_t *)(uintptr_t)0x1a000000u;
    uint32_t offset;
    uint32_t found = 0xffffffffu;
    for (offset = 0; offset + sizeof(old_arg) <= 2323u; ++offset) {
        uint32_t index;
        for (index = 0; index < sizeof(old_arg) - 1u; ++index)
            if (dtb[offset + index] != (uint8_t)old_arg[index]) break;
        if (index == sizeof(old_arg) - 1u) {
            if (found != 0xffffffffu) return 0;
            found = offset;
        }
    }
    if (found == 0xffffffffu || sizeof(old_arg) != sizeof(new_arg)) return 0;
    for (offset = 0; offset < sizeof(old_arg) - 1u; ++offset) {
        uint32_t address = 0x1a000000u + found + offset;
        uint32_t aligned = address & ~3u;
        uint32_t shift = (address & 3u) * 8u;
        volatile uint32_t *cached = (volatile uint32_t *)(uintptr_t)aligned;
        volatile uint32_t *uncached = (volatile uint32_t *)(uintptr_t)(aligned | 0x80000000u);
        uint32_t value = (*cached & ~(255u << shift)) | ((uint32_t)(uint8_t)new_arg[offset] << shift);
        *cached = value;
        *uncached = value;
    }
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
    console_puts("PIKAFISH_SYNC_INITRD_BOOTARG_PATCH\n");
    return 1;
}
#endif

#ifdef SD_LOADER_SMODE_TIMER_PROBE
static void patch_smode_timer_payload(void)
{
    uint32_t index;
    const uint32_t words = (sizeof(smode_timer_bin) + 3u) / 4u;
    volatile uint32_t *cached = (volatile uint32_t *)(uintptr_t)0x00400000u;
    volatile uint32_t *uncached = (volatile uint32_t *)(uintptr_t)0x80400000u;
    for (index = 0; index < words; ++index) {
        uint32_t byte_index;
        uint32_t value = 0u;
        for (byte_index = 0; byte_index < 4u; ++byte_index) {
            const uint32_t position = index * 4u + byte_index;
            if (position < sizeof(smode_timer_bin))
                value |= (uint32_t)smode_timer_bin[position] << (byte_index * 8u);
        }
        cached[index] = value;
        uncached[index] = value;
    }
    __asm__ volatile ("fence iorw, iorw\n\t.word 0x0000100f" ::: "memory");
    console_puts("S_TIMER_PAYLOAD_PATCH bytes=");
    console_dec(sizeof(smode_timer_bin));
    console_putc('\n');
}
#endif

#ifdef SD_LOADER_SBI_TIMER_BRIDGE
static int patch_sbi_timer_bridge(void)
{
    const uint32_t dtb_timebase_offset = 1048u;
    const uint32_t old_timebase_le = 0x604ff302u;
    const uint32_t new_timebase_le = 0x405f8a03u;
    const uint32_t fw_words = (sizeof(fw_jump_bin) + 3u) / 4u;
    volatile uint32_t *dtb_cached =
        (volatile uint32_t *)(uintptr_t)(0x1a000000u + dtb_timebase_offset);
    volatile uint32_t *dtb_uncached =
        (volatile uint32_t *)(uintptr_t)(0x9a000000u + dtb_timebase_offset);
    volatile uint32_t *fw_cached = (volatile uint32_t *)(uintptr_t)0x18000000u;
    volatile uint32_t *fw_uncached = (volatile uint32_t *)(uintptr_t)0x98000000u;
    uint32_t index;
    if (*dtb_cached != old_timebase_le || sizeof(fw_jump_bin) > 0x50000u)
        return 0;
    *dtb_cached = new_timebase_le;
    *dtb_uncached = new_timebase_le;
    for (index = 0; index < fw_words; ++index) {
        uint32_t byte_index;
        uint32_t value = 0u;
        for (byte_index = 0; byte_index < 4u; ++byte_index) {
            const uint32_t position = index * 4u + byte_index;
            if (position < sizeof(fw_jump_bin))
                value |= (uint32_t)fw_jump_bin[position] << (byte_index * 8u);
        }
        fw_cached[index] = value;
        fw_uncached[index] = value;
    }
    __asm__ volatile ("fence iorw, iorw\n\t.word 0x0000100f" ::: "memory");
    console_puts("SBI_TIMER_BRIDGE_PATCH fw_bytes=");
    console_dec(sizeof(fw_jump_bin));
    console_puts(" cpu_time_hz=59400000 mtime_hz=49500000\n");
    return 1;
}
#endif

int main(void)
{
    uint32_t index;
    int status;
    const uint32_t count = sizeof(payloads) / sizeof(payloads[0]);
    console_puts("PIKAFISH_SD_LOADER_BEGIN\n");
    ddr_wait_ready();
#ifdef SD_LOADER_TIMER_HW_PROBE
    if (!probe_machine_timer()) return 1;
#endif
    status = sd_init();
    if (status) {
        console_puts("SD init failed: "); console_dec((uint32_t)-status); console_putc('\n');
        return 1;
    }
    status = fat_ro_mount(&volume, read_sectors, 0, sd_card_info()->sector_count);
    if (status) {
        console_puts("FAT mount failed: "); console_puts(fat_ro_error_string(status));
        console_putc('\n'); sd_release(); return 1;
    }
    for (index = 0; index < count; ++index) {
        payload_t *p = &payloads[index];
        status = fat_ro_find(&volume, p->name, &p->file);
        if (status || p->file.size != p->bytes ||
            !ddr_range_valid(p->address, p->bytes + 3u)) {
            console_puts("SD payload invalid: "); console_puts(p->name);
            console_putc('\n'); sd_release(); return 1;
        }
    }
    for (index = 0; index < count; ++index) {
        payload_t *p = &payloads[index];
        uint32_t actual;
        console_puts("Loading "); console_puts(p->name); console_puts(" bytes=");
        console_dec(p->bytes); console_putc('\n');
        status = fat_ro_load(&volume, &p->file,
                             (void *)(uintptr_t)p->address, p->bytes,
                             progress, 0);
        if (status) {
            console_puts("SD load failed: "); console_puts(fat_ro_error_string(status));
            console_putc('\n'); sd_release(); return 1;
        }
        console_puts(" SD_READ_DONE\n");
        actual = copy_to_uncached(p->address, p->bytes);
        console_puts(" SD_ALIAS_DONE");
        console_puts(" CRC32="); console_hex(actual); console_putc('\n');
        if (p->crc32 && actual != p->crc32) {
            console_puts("SD payload CRC mismatch\n"); sd_release(); return 1;
        }
    }
#ifdef SD_LOADER_STANDALONE_DIAG
    {
        uint32_t crc = crc32_fast(0xffffffffu,
            (const void *)(uintptr_t)0x83000000u, payloads[2].bytes)
            ^ 0xffffffffu;
        console_puts("ROOTFS_AFTER_ALL_LOADS_CRC32=");
        console_hex(crc);
        console_putc('\n');
        if (crc != payloads[2].crc32) return 1;
    }
#endif
    if (SKIP_STAGEB_PROBE && !skip_stageb_probe()) {
        console_puts("SD probe patch failed\n");
        return 1;
    }
#ifdef SD_LOADER_STANDALONE_DIAG
    if (!patch_standalone_diagnostic()) {
        console_puts("SD standalone diagnostic patch failed\n");
        return 1;
    }
#endif
#ifdef SD_LOADER_SYNC_INITRD
    if (!patch_sync_initrd_bootarg()) {
        console_puts("SD sync initrd bootarg patch failed\n");
        return 1;
    }
#endif
 #ifdef SD_LOADER_GUI_AUTOMOVE
    if (!patch_gui_automove()) {
        console_puts("SD GUI automove patch failed\n");
        return 1;
    }
#endif
 #ifdef SD_LOADER_SMODE_TIMER_PROBE
    patch_smode_timer_payload();
#endif
#ifdef SD_LOADER_SBI_TIMER_BRIDGE
    if (!patch_sbi_timer_bridge()) {
        console_puts("SBI timer bridge patch failed\n");
        return 1;
    }
#endif
    sd_release();
    console_puts("PIKAFISH_SD_LOADER_PASS; starting OpenSBI\n");
    delay_cycles(TIMEBASE_HZ * 5u);
    __asm__ volatile (".word 0x0000100f" ::: "memory");
    jump_to(0x18000000u, 0u, 0x1a000000u);
    return 0;
}
