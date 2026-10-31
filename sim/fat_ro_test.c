#include <stdint.h>

#include "fat_ro.h"

#define TEST_TOTAL_SECTORS 70000u
#define TEST_RESERVED      32u
#define TEST_FAT_SECTORS   547u
#define TEST_DATA_LBA      (TEST_RESERVED + TEST_FAT_SECTORS)
#define TEST_MBR_BASE      2048u
#define TEST_MEDIA_SECTORS (TEST_MBR_BASE + TEST_TOTAL_SECTORS)
#define TEST_FAT16_SECTORS 10000u
#define TEST_FAT16_FAT     40u
#define TEST_FAT16_ROOT    32u
#define TEST_FAT16_DATA    (1u + TEST_FAT16_FAT + TEST_FAT16_ROOT)
#define TEST_ROOT_SIZE     1300u
#define TEST_SHORT_SIZE    73u

#define RESULT_PASS (*(volatile uint32_t *)(uintptr_t)0x80000000u)
#define RESULT_FAIL (*(volatile uint32_t *)(uintptr_t)0x80000004u)

enum image_mode {
    IMAGE_VALID = 0,
    IMAGE_BAD_LFN_CHECKSUM,
    IMAGE_BAD_LFN_ORDER,
    IMAGE_BAD_LFN_TYPE,
    IMAGE_BAD_LFN_CLUSTER,
    IMAGE_BAD_CHAIN,
    IMAGE_SELF_LOOP,
    IMAGE_LOOP_CHAIN,
    IMAGE_CONTIGUOUS,
    IMAGE_MBR,
    IMAGE_MBR_OUT_OF_RANGE,
    IMAGE_FAT16_MBR
};

typedef struct {
    uint32_t mode;
    uint32_t reads;
    uint32_t sectors;
    uint32_t max_count;
} test_disk_t;

typedef struct {
    uint32_t calls;
    uint32_t previous;
    uint32_t total;
    uint32_t invalid;
} progress_state_t;

static fat_ro_volume_t volume;
static uint8_t loaded[TEST_ROOT_SIZE + 16u];

static void put16(uint8_t *p, uint32_t offset, uint16_t value)
{
    p[offset] = (uint8_t)value;
    p[offset + 1u] = (uint8_t)(value >> 8);
}

static void put32(uint8_t *p, uint32_t offset, uint32_t value)
{
    p[offset] = (uint8_t)value;
    p[offset + 1u] = (uint8_t)(value >> 8);
    p[offset + 2u] = (uint8_t)(value >> 16);
    p[offset + 3u] = (uint8_t)(value >> 24);
}

static void fill(uint8_t *p, uint8_t value, uint32_t length)
{
    uint32_t i;
    for (i = 0u; i < length; ++i)
        p[i] = value;
}

static int string_equal(const char *a, const char *b)
{
    while (*a != '\0' && *a == *b) {
        ++a;
        ++b;
    }
    return *a == *b;
}

static uint8_t lfn_checksum(const uint8_t short_name[11])
{
    uint32_t i;
    uint8_t sum = 0u;
    for (i = 0u; i < 11u; ++i)
        sum = (uint8_t)(((sum & 1u) != 0u ? 0x80u : 0u) +
                        (sum >> 1) + short_name[i]);
    return sum;
}

static void write_short_entry(uint8_t *entry, const uint8_t name[11],
                              uint32_t first_cluster, uint32_t size)
{
    uint32_t i;
    fill(entry, 0u, 32u);
    for (i = 0u; i < 11u; ++i)
        entry[i] = name[i];
    entry[11] = 0x20u;
    put16(entry, 20u, (uint16_t)(first_cluster >> 16));
    put16(entry, 26u, (uint16_t)first_cluster);
    put32(entry, 28u, size);
}

static void write_lfn_entry(uint8_t *entry, uint8_t order, uint8_t checksum,
                            const char *name)
{
    static const uint8_t offsets[13] = {
        1u, 3u, 5u, 7u, 9u, 14u, 16u, 18u, 20u, 22u, 24u, 28u, 30u
    };
    uint32_t i;
    int ended = 0;

    fill(entry, 0xffu, 32u);
    entry[0] = order;
    entry[11] = 0x0fu;
    entry[12] = 0u;
    entry[13] = checksum;
    entry[26] = 0u;
    entry[27] = 0u;
    for (i = 0u; i < 13u; ++i) {
        uint16_t ch;
        if (ended != 0) {
            ch = 0xffffu;
        } else if (*name == '\0') {
            ch = 0u;
            ended = 1;
        } else {
            ch = (uint8_t)*name;
            ++name;
        }
        put16(entry, offsets[i], ch);
    }
}

static uint32_t fat_value(uint32_t entry, uint32_t mode)
{
    if (entry == 0u)
        return 0x0ffffff8u;
    if (mode == IMAGE_CONTIGUOUS) {
        if (entry == 1u || entry == 2u || entry == 5u || entry == 6u)
            return 0x0fffffffu;
        if (entry == 3u)
            return 4u;
        if (entry == 4u)
            return 5u;
        return 0u;
    }
    if (entry == 1u || entry == 2u || entry == 4u || entry == 6u)
        return 0x0fffffffu;
    if (entry == 3u)
        return mode == IMAGE_BAD_CHAIN ? 0x0ffffff7u :
               (mode == IMAGE_SELF_LOOP ? 3u : 9u);
    if (entry == 9u)
        return mode == IMAGE_LOOP_CHAIN ? 3u : 4u;
    return 0u;
}

static uint8_t root_data_byte(uint32_t offset)
{
    return (uint8_t)((offset * 37u + 11u) & 0xffu);
}

static uint8_t short_data_byte(uint32_t offset)
{
    return (uint8_t)(0xa5u ^ (offset * 3u));
}

static void make_boot_sector(uint8_t *sector, uint32_t hidden_sectors)
{
    static const uint8_t oem[8] = {'F','A','T','R','O','T','E','S'};
    static const uint8_t label[11] = {'F','A','T','R','O',' ','T','E','S','T',' '};
    static const uint8_t type[8] = {'F','A','T','3','2',' ',' ',' '};
    uint32_t i;

    fill(sector, 0u, FAT_RO_SECTOR_SIZE);
    sector[0] = 0xebu;
    sector[1] = 0x58u;
    sector[2] = 0x90u;
    for (i = 0u; i < 8u; ++i)
        sector[3u + i] = oem[i];
    put16(sector, 11u, FAT_RO_SECTOR_SIZE);
    sector[13] = 1u;
    put16(sector, 14u, TEST_RESERVED);
    sector[16] = 1u;
    put16(sector, 17u, 0u);
    put16(sector, 19u, 0u);
    sector[21] = 0xf8u;
    put16(sector, 22u, 0u);
    put16(sector, 24u, 63u);
    put16(sector, 26u, 255u);
    put32(sector, 28u, hidden_sectors);
    put32(sector, 32u, TEST_TOTAL_SECTORS);
    put32(sector, 36u, TEST_FAT_SECTORS);
    put16(sector, 40u, 0u);
    put16(sector, 42u, 0u);
    put32(sector, 44u, 2u);
    put16(sector, 48u, 1u);
    put16(sector, 50u, 6u);
    sector[64] = 0x80u;
    sector[66] = 0x29u;
    put32(sector, 67u, 0x76543210u);
    for (i = 0u; i < 11u; ++i)
        sector[71u + i] = label[i];
    for (i = 0u; i < 8u; ++i)
        sector[82u + i] = type[i];
    sector[510] = 0x55u;
    sector[511] = 0xaau;
}

static void make_fat16_boot_sector(uint8_t *sector)
{
    static const uint8_t oem[8] = {'F','A','T','1','6','T','E','S'};
    static const uint8_t label[11] = {'F','A','T','1','6',' ','T','E','S','T',' '};
    static const uint8_t type[8] = {'F','A','T','1','6',' ',' ',' '};
    uint32_t i;

    fill(sector, 0u, FAT_RO_SECTOR_SIZE);
    sector[0] = 0xebu;
    sector[1] = 0x3cu;
    sector[2] = 0x90u;
    for (i = 0u; i < 8u; ++i)
        sector[3u + i] = oem[i];
    put16(sector, 11u, FAT_RO_SECTOR_SIZE);
    sector[13] = 1u;
    put16(sector, 14u, 1u);
    sector[16] = 1u;
    put16(sector, 17u, 512u);
    put16(sector, 19u, TEST_FAT16_SECTORS);
    sector[21] = 0xf8u;
    put16(sector, 22u, TEST_FAT16_FAT);
    put16(sector, 24u, 63u);
    put16(sector, 26u, 255u);
    put32(sector, 28u, TEST_MBR_BASE);
    put32(sector, 32u, 0u);
    sector[36] = 0x80u;
    sector[37] = 0u;
    sector[38] = 0x29u;
    put32(sector, 39u, 0x12345678u);
    for (i = 0u; i < 11u; ++i)
        sector[43u + i] = label[i];
    for (i = 0u; i < 8u; ++i)
        sector[54u + i] = type[i];
    sector[510] = 0x55u;
    sector[511] = 0xaau;
}

static void make_mbr(uint8_t *sector, uint32_t mode)
{
    uint8_t *entry;
    uint32_t sectors = mode == IMAGE_FAT16_MBR ?
                       TEST_FAT16_SECTORS : TEST_TOTAL_SECTORS;

    fill(sector, 0u, FAT_RO_SECTOR_SIZE);
    entry = sector + 446u;
    entry[0] = 0x80u;
    entry[4] = mode == IMAGE_FAT16_MBR ? 0x06u : 0x0cu;
    put32(entry, 8u, TEST_MBR_BASE);
    if (mode == IMAGE_MBR_OUT_OF_RANGE)
        ++sectors;
    put32(entry, 12u, sectors);
    sector[510] = 0x55u;
    sector[511] = 0xaau;
}

static void make_fat_sector(uint8_t *sector, uint32_t lba, uint32_t mode)
{
    uint32_t first = (lba - TEST_RESERVED) * 128u;
    uint32_t i;
    fill(sector, 0u, FAT_RO_SECTOR_SIZE);
    for (i = 0u; i < 128u; ++i)
        put32(sector, i * 4u, fat_value(first + i, mode));
}

static void make_fat16_sector(uint8_t *sector, uint32_t relative_lba)
{
    uint32_t first = (relative_lba - 1u) * 256u;
    uint32_t i;
    fill(sector, 0u, FAT_RO_SECTOR_SIZE);
    for (i = 0u; i < 256u; ++i) {
        uint32_t entry = first + i;
        uint16_t value = 0u;
        if (entry == 0u)
            value = 0xfff8u;
        else if (entry == 1u || entry == 2u || entry == 4u || entry == 6u)
            value = 0xffffu;
        else if (entry == 3u)
            value = 9u;
        else if (entry == 9u)
            value = 4u;
        put16(sector, i * 2u, value);
    }
}

static void make_root_sector(uint8_t *sector, uint32_t mode)
{
    static const uint8_t root_short[11] = {
        'R','O','O','T','F','S','~','1','C','P','I'
    };
    static const uint8_t image_short[11] = {
        'I','M','A','G','E',' ',' ',' ',' ',' ',' '
    };
    uint8_t checksum = lfn_checksum(root_short);
    uint8_t order = mode == IMAGE_BAD_LFN_ORDER ? 0x42u : 0x41u;

    fill(sector, 0u, FAT_RO_SECTOR_SIZE);
    if (mode == IMAGE_BAD_LFN_CHECKSUM)
        checksum ^= 0x5au;
    write_lfn_entry(sector, order, checksum, "rootfs.cpio");
    if (mode == IMAGE_BAD_LFN_TYPE)
        sector[12] = 1u;
    if (mode == IMAGE_BAD_LFN_CLUSTER)
        put16(sector, 26u, 1u);
    write_short_entry(sector + 32u, root_short, 3u, TEST_ROOT_SIZE);
    write_short_entry(sector + 64u, image_short, 6u, TEST_SHORT_SIZE);
    sector[96] = 0u;
}

static void make_file_sector(uint8_t *sector, uint32_t ordinal, int is_short)
{
    uint32_t i;
    fill(sector, 0u, FAT_RO_SECTOR_SIZE);
    for (i = 0u; i < FAT_RO_SECTOR_SIZE; ++i) {
        uint32_t offset = ordinal * FAT_RO_SECTOR_SIZE + i;
        sector[i] = is_short != 0 ? short_data_byte(offset) :
                                   root_data_byte(offset);
    }
}

static int test_make_sector(void *user, uint32_t lba, uint8_t *sector)
{
    test_disk_t *disk = (test_disk_t *)user;
    uint32_t base = (disk->mode == IMAGE_MBR ||
                     disk->mode == IMAGE_MBR_OUT_OF_RANGE ||
                     disk->mode == IMAGE_FAT16_MBR) ?
                    TEST_MBR_BASE : 0u;
    uint32_t relative;

    if (lba >= TEST_MEDIA_SECTORS)
        return -1;
    if (base != 0u && lba == 0u) {
        make_mbr(sector, disk->mode);
        return 0;
    }
    if (lba < base) {
        fill(sector, 0u, FAT_RO_SECTOR_SIZE);
        return 0;
    }
    relative = lba - base;
    if (disk->mode == IMAGE_FAT16_MBR) {
        if (relative == 0u) {
            make_fat16_boot_sector(sector);
        } else if (relative >= 1u && relative <= TEST_FAT16_FAT) {
            make_fat16_sector(sector, relative);
        } else if (relative == 1u + TEST_FAT16_FAT) {
            make_root_sector(sector, disk->mode);
        } else if (relative == TEST_FAT16_DATA + 1u) {
            make_file_sector(sector, 0u, 0);
        } else if (relative == TEST_FAT16_DATA + 7u) {
            make_file_sector(sector, 1u, 0);
        } else if (relative == TEST_FAT16_DATA + 2u) {
            make_file_sector(sector, 2u, 0);
        } else if (relative == TEST_FAT16_DATA + 4u) {
            make_file_sector(sector, 0u, 1);
        } else {
            fill(sector, 0u, FAT_RO_SECTOR_SIZE);
        }
        return 0;
    }
    if (relative == 0u) {
        make_boot_sector(sector, base);
    } else if (relative >= TEST_RESERVED &&
               relative < TEST_RESERVED + TEST_FAT_SECTORS) {
        make_fat_sector(sector, relative, disk->mode);
    } else if (relative == TEST_DATA_LBA) {
        make_root_sector(sector, disk->mode);
    } else if ((disk->mode == IMAGE_CONTIGUOUS) &&
               (relative == TEST_DATA_LBA + 1u)) {
        make_file_sector(sector, 0u, 0);
    } else if ((disk->mode == IMAGE_CONTIGUOUS) &&
               (relative == TEST_DATA_LBA + 2u)) {
        make_file_sector(sector, 1u, 0);
    } else if ((disk->mode == IMAGE_CONTIGUOUS) &&
               (relative == TEST_DATA_LBA + 3u)) {
        make_file_sector(sector, 2u, 0);
    } else if (relative == TEST_DATA_LBA + 1u) {
        make_file_sector(sector, 0u, 0);
    } else if (relative == TEST_DATA_LBA + 7u) {
        make_file_sector(sector, 1u, 0);
    } else if (relative == TEST_DATA_LBA + 2u) {
        make_file_sector(sector, 2u, 0);
    } else if (relative == TEST_DATA_LBA + 4u) {
        make_file_sector(sector, 0u, 1);
    } else {
        fill(sector, 0u, FAT_RO_SECTOR_SIZE);
    }
    return 0;
}

static int test_read_sectors(void *user, uint32_t lba, uint32_t count,
                             uint8_t *destination)
{
    test_disk_t *disk = (test_disk_t *)user;
    uint32_t i;

    if ((count == 0u) || (count > 32u))
        return -1;
    ++disk->reads;
    disk->sectors += count;
    if (count > disk->max_count)
        disk->max_count = count;
    for (i = 0u; i < count; ++i) {
        if (test_make_sector(user, lba + i,
                             destination + i * FAT_RO_SECTOR_SIZE) != 0)
            return -1;
    }
    return 0;
}

static int test_progress(void *user, uint32_t done, uint32_t total)
{
    progress_state_t *state = (progress_state_t *)user;
    if (total != TEST_ROOT_SIZE || done > total ||
        (state->calls != 0u && done < state->previous))
        state->invalid = 1u;
    state->previous = done;
    state->total = total;
    ++state->calls;
    return 0;
}

static void fail(uint32_t code) __attribute__((noreturn));
static void fail(uint32_t code)
{
    RESULT_FAIL = code;
    for (;;) {
    }
}

static void pass(void) __attribute__((noreturn));
static void pass(void)
{
    RESULT_PASS = 0xf470600du;
    for (;;) {
    }
}

int main(void)
{
    test_disk_t disk;
    fat_ro_file_t file;
    progress_state_t progress;
    uint32_t i;
    int status;

    disk.mode = IMAGE_VALID;
    disk.reads = 0u;
    disk.sectors = 0u;
    disk.max_count = 0u;
    status = fat_ro_mount(&volume, test_read_sectors, &disk,
                          TEST_MEDIA_SECTORS);
    if (status != FAT_RO_OK)
        fail(0xf0010000u | (uint32_t)(-status));
    if (volume.partition_lba != 0u || volume.fat_type != FAT_RO_TYPE_32 ||
        volume.root_cluster != 2u || volume.cluster_size_bytes != 512u)
        fail(0xf0020000u);

    status = fat_ro_find(&volume, "RoOtFs.CpIo", &file);
    if (status != FAT_RO_OK)
        fail(0xf0030000u | (uint32_t)(-status));
    if (file.size != TEST_ROOT_SIZE || file.first_cluster != 3u ||
        file.has_long_name == 0u || !string_equal(file.name, "rootfs.cpio") ||
        !string_equal(file.short_name, "ROOTFS~1.CPI"))
        fail(0xf0040000u);

    fill(loaded, 0xccu, sizeof(loaded));
    progress.calls = 0u;
    progress.previous = 0u;
    progress.total = 0u;
    progress.invalid = 0u;
    status = fat_ro_load(&volume, &file, loaded, sizeof(loaded),
                         test_progress, &progress);
    if (status != FAT_RO_OK)
        fail(0xf0050000u | (uint32_t)(-status));
    if (progress.invalid != 0u || progress.calls != 4u ||
        progress.previous != TEST_ROOT_SIZE ||
        progress.total != TEST_ROOT_SIZE)
        fail(0xf0060000u | progress.calls);
    for (i = 0u; i < TEST_ROOT_SIZE; ++i) {
        if (loaded[i] != root_data_byte(i))
            fail(0xf0070000u | (i & 0xffffu));
    }
    for (i = TEST_ROOT_SIZE; i < sizeof(loaded); ++i) {
        if (loaded[i] != 0xccu)
            fail(0xf0080000u | (i & 0xffffu));
    }

    status = fat_ro_find(&volume, "image", &file);
    if (status != FAT_RO_OK || file.size != TEST_SHORT_SIZE ||
        file.has_long_name != 0u || !string_equal(file.short_name, "IMAGE"))
        fail(0xf0090000u | (uint32_t)(status != FAT_RO_OK ? -status : 0));
    fill(loaded, 0xccu, sizeof(loaded));
    status = fat_ro_load(&volume, &file, loaded, sizeof(loaded), 0, 0);
    if (status != FAT_RO_OK)
        fail(0xf00a0000u | (uint32_t)(-status));
    for (i = 0u; i < TEST_SHORT_SIZE; ++i) {
        if (loaded[i] != short_data_byte(i))
            fail(0xf00b0000u | i);
    }

    disk.mode = IMAGE_CONTIGUOUS;
    disk.reads = 0u;
    disk.sectors = 0u;
    disk.max_count = 0u;
    status = fat_ro_mount(&volume, test_read_sectors, &disk,
                          TEST_MEDIA_SECTORS);
    if (status != FAT_RO_OK ||
        fat_ro_find(&volume, "rootfs.cpio", &file) != FAT_RO_OK)
        fail(0xf00c0000u);
    fill(loaded, 0xccu, sizeof(loaded));
    status = fat_ro_load(&volume, &file, loaded, sizeof(loaded), 0, 0);
    if (status != FAT_RO_OK || disk.max_count < 2u)
        fail(0xf00d0000u | disk.max_count);
    for (i = 0u; i < TEST_ROOT_SIZE; ++i) {
        if (loaded[i] != root_data_byte(i))
            fail(0xf00e0000u | (i & 0xffffu));
    }

    /* A final multi-sector batch must consume every cluster even when
     * remaining becomes zero. In particular SPC=1 and1024 bytes used to
     * spin with consumed=1, sector=1, available=0. Keep both data and guards. */
    {
        uint32_t exact;
        for (exact = 512u; exact <= 1024u; exact += 512u) {
            file.size = exact;
            fill(loaded, 0xccu, sizeof(loaded));
            status = fat_ro_load(&volume, &file, loaded, sizeof(loaded), 0, 0);
            if (status != FAT_RO_OK)
                fail(0xf0200000u | (uint32_t)(-status));
            for (i = 0u; i < exact; ++i) {
                if (loaded[i] != root_data_byte(i))
                    fail(0xf0210000u | i);
            }
            for (i = exact; i < sizeof(loaded); ++i) {
                if (loaded[i] != 0xccu)
                    fail(0xf0220000u | i);
            }
        }
    }

    disk.mode = IMAGE_BAD_LFN_CHECKSUM;
    status = fat_ro_mount(&volume, test_read_sectors, &disk,
                          TEST_MEDIA_SECTORS);
    if (status != FAT_RO_OK ||
        fat_ro_find(&volume, "rootfs.cpio", &file) != FAT_RO_ERR_NOT_FOUND)
        fail(0xf00f0000u);

    disk.mode = IMAGE_BAD_LFN_ORDER;
    status = fat_ro_mount(&volume, test_read_sectors, &disk,
                          TEST_MEDIA_SECTORS);
    if (status != FAT_RO_OK ||
        fat_ro_find(&volume, "rootfs.cpio", &file) != FAT_RO_ERR_NOT_FOUND)
        fail(0xf0100000u);

    disk.mode = IMAGE_BAD_LFN_TYPE;
    status = fat_ro_mount(&volume, test_read_sectors, &disk,
                          TEST_MEDIA_SECTORS);
    if (status != FAT_RO_OK ||
        fat_ro_find(&volume, "rootfs.cpio", &file) != FAT_RO_ERR_NOT_FOUND)
        fail(0xf0110000u);

    disk.mode = IMAGE_BAD_LFN_CLUSTER;
    status = fat_ro_mount(&volume, test_read_sectors, &disk,
                          TEST_MEDIA_SECTORS);
    if (status != FAT_RO_OK ||
        fat_ro_find(&volume, "rootfs.cpio", &file) != FAT_RO_ERR_NOT_FOUND)
        fail(0xf0120000u);

    disk.mode = IMAGE_BAD_CHAIN;
    status = fat_ro_mount(&volume, test_read_sectors, &disk,
                          TEST_MEDIA_SECTORS);
    if (status != FAT_RO_OK ||
        fat_ro_find(&volume, "rootfs.cpio", &file) != FAT_RO_OK)
        fail(0xf0130000u);
    status = fat_ro_load(&volume, &file, loaded, sizeof(loaded), 0, 0);
    if (status != FAT_RO_ERR_CHAIN)
        fail(0xf0140000u | (uint32_t)(status < 0 ? -status : status));

    disk.mode = IMAGE_SELF_LOOP;
    status = fat_ro_mount(&volume, test_read_sectors, &disk,
                          TEST_MEDIA_SECTORS);
    if (status != FAT_RO_OK ||
        fat_ro_find(&volume, "rootfs.cpio", &file) != FAT_RO_OK)
        fail(0xf0150000u);
    status = fat_ro_load(&volume, &file, loaded, sizeof(loaded), 0, 0);
    if (status != FAT_RO_ERR_CHAIN)
        fail(0xf0160000u | (uint32_t)(status < 0 ? -status : status));

    disk.mode = IMAGE_LOOP_CHAIN;
    status = fat_ro_mount(&volume, test_read_sectors, &disk,
                          TEST_MEDIA_SECTORS);
    if (status != FAT_RO_OK ||
        fat_ro_find(&volume, "rootfs.cpio", &file) != FAT_RO_OK)
        fail(0xf0170000u);
    status = fat_ro_load(&volume, &file, loaded, sizeof(loaded), 0, 0);
    if (status != FAT_RO_ERR_CHAIN)
        fail(0xf0180000u | (uint32_t)(status < 0 ? -status : status));

    disk.mode = IMAGE_MBR;
    status = fat_ro_mount(&volume, test_read_sectors, &disk,
                          TEST_MEDIA_SECTORS);
    if (status != FAT_RO_OK || volume.partition_lba != TEST_MBR_BASE ||
        fat_ro_find(&volume, "rootfs.cpio", &file) != FAT_RO_OK)
        fail(0xf0190000u | (uint32_t)(status < 0 ? -status : status));

    disk.mode = IMAGE_MBR_OUT_OF_RANGE;
    status = fat_ro_mount(&volume, test_read_sectors, &disk,
                          TEST_MEDIA_SECTORS);
    if (status != FAT_RO_ERR_CORRUPT)
        fail(0xf01a0000u | (uint32_t)(status < 0 ? -status : status));

    disk.mode = IMAGE_FAT16_MBR;
    status = fat_ro_mount(&volume, test_read_sectors, &disk,
                          TEST_MEDIA_SECTORS);
    if (status != FAT_RO_OK || volume.partition_lba != TEST_MBR_BASE ||
        volume.fat_type != FAT_RO_TYPE_16 ||
        volume.root_dir_lba != TEST_MBR_BASE + 1u + TEST_FAT16_FAT ||
        fat_ro_find(&volume, "rootfs.cpio", &file) != FAT_RO_OK)
        fail(0xf01b0000u | (uint32_t)(status < 0 ? -status : status));
    fill(loaded, 0xccu, sizeof(loaded));
    status = fat_ro_load(&volume, &file, loaded, sizeof(loaded), 0, 0);
    if (status != FAT_RO_OK)
        fail(0xf01c0000u | (uint32_t)(-status));
    for (i = 0u; i < TEST_ROOT_SIZE; ++i) {
        if (loaded[i] != root_data_byte(i))
            fail(0xf01d0000u | (i & 0xffffu));
    }

    if (disk.reads == 0u)
        fail(0xf01e0000u);
    pass();
}
