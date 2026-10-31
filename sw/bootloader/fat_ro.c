#include "fat_ro.h"

#define FAT_RO_MOUNT_COOKIE 0x46524f31u /* "FRO1" */

#define FAT_ATTR_DIRECTORY  0x10u
#define FAT_ATTR_VOLUME_ID  0x08u
#define FAT_ATTR_LONG_NAME  0x0fu
#define FAT_LFN_LAST        0x40u
#define FAT_LFN_MAX_ENTRIES 20u
#define FAT_LFN_UNITS       (FAT_LFN_MAX_ENTRIES * 13u)
#define FAT_RO_MAX_READ_SECTORS 32u

typedef struct {
    uint16_t unit[FAT_LFN_UNITS];
    uint8_t active;
    uint8_t expected_ordinal;
    uint8_t entry_count;
    uint8_t checksum;
} fat_lfn_state_t;

static const uint8_t fat_lfn_offsets[13] = {
    1u, 3u, 5u, 7u, 9u,
    14u, 16u, 18u, 20u, 22u, 24u,
    28u, 30u
};

static uint16_t fat_get_le16(const uint8_t *p)
{
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

static uint32_t fat_get_le32(const uint8_t *p)
{
    return (uint32_t)p[0] |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static void fat_clear(void *destination, uint32_t count)
{
    uint8_t *p = (uint8_t *)destination;

    while (count != 0u) {
        *p = 0u;
        ++p;
        --count;
    }
}

static void fat_copy(void *destination, const void *source, uint32_t count)
{
    uint8_t *d = (uint8_t *)destination;
    const uint8_t *s = (const uint8_t *)source;

    while (count != 0u) {
        *d = *s;
        ++d;
        ++s;
        --count;
    }
}

static int fat_add_u32(uint32_t a, uint32_t b, uint32_t *result)
{
    if (b > 0xffffffffu - a) {
        return 0;
    }
    *result = a + b;
    return 1;
}

static int fat_mul_u32(uint32_t a, uint32_t b, uint32_t *result)
{
    if ((a != 0u) && (b > 0xffffffffu / a)) {
        return 0;
    }
    *result = a * b;
    return 1;
}

static int fat_is_power_of_two(uint8_t value)
{
    return (value != 0u) && ((value & (uint8_t)(value - 1u)) == 0u);
}

static int fat_volume_ready(const fat_ro_volume_t *volume)
{
    return (volume != NULL) &&
           (volume->mount_cookie == FAT_RO_MOUNT_COOKIE) &&
           (volume->read_sectors != NULL) &&
           ((volume->fat_type == FAT_RO_TYPE_16) ||
            (volume->fat_type == FAT_RO_TYPE_32));
}

static int fat_read_raw(fat_ro_volume_t *volume, uint32_t lba,
                        uint32_t count, uint8_t *destination)
{
    if ((count == 0u) || (count > FAT_RO_MAX_READ_SECTORS)) {
        return FAT_RO_ERR_ARGUMENT;
    }
    if ((volume->media_sectors != 0u) &&
        ((lba >= volume->media_sectors) ||
         (count > volume->media_sectors - lba))) {
        return FAT_RO_ERR_RANGE;
    }
    if (volume->read_sectors(volume->read_user, lba, count,
                             destination) != 0) {
        return FAT_RO_ERR_IO;
    }
    return FAT_RO_OK;
}

static int fat_read_volume(fat_ro_volume_t *volume, uint32_t lba,
                           uint32_t count, uint8_t *destination)
{
    if ((lba < volume->partition_lba) ||
        ((lba - volume->partition_lba) >= volume->total_sectors) ||
        (count > volume->total_sectors -
                 (lba - volume->partition_lba))) {
        return FAT_RO_ERR_RANGE;
    }
    return fat_read_raw(volume, lba, count, destination);
}

static uint8_t fat_partition_family(uint8_t type)
{
    switch (type) {
    case 0x01u:
        return 12u;
    case 0x04u:
    case 0x06u:
    case 0x0eu:
    case 0x14u:
    case 0x16u:
    case 0x1eu:
        return FAT_RO_TYPE_16;
    case 0x0bu:
    case 0x0cu:
    case 0x1bu:
    case 0x1cu:
        return FAT_RO_TYPE_32;
    default:
        return 0u;
    }
}

static void fat_copy_volume_label(char label[12], const uint8_t *source)
{
    uint32_t i;
    uint32_t length = 11u;

    while ((length != 0u) && (source[length - 1u] == (uint8_t)' ')) {
        --length;
    }
    for (i = 0u; i < length; ++i) {
        uint8_t c = source[i];
        label[i] = ((c >= 0x20u) && (c <= 0x7eu)) ? (char)c : '?';
    }
    label[length] = '\0';
}

static int fat_parse_boot_sector(fat_ro_volume_t *volume,
                                 uint32_t partition_lba,
                                 uint32_t partition_sectors,
                                 uint8_t expected_family)
{
    const uint8_t *boot = volume->sector;
    uint16_t bytes_per_sector;
    uint16_t reserved_sectors;
    uint16_t root_entries;
    uint16_t total_sectors_16;
    uint16_t fat_sectors_16;
    uint32_t total_sectors_32;
    uint32_t fat_sectors_32;
    uint32_t total_sectors;
    uint32_t fat_sectors;
    uint32_t root_dir_sectors;
    uint32_t fat_area_sectors;
    uint32_t non_data_sectors;
    uint32_t data_sectors;
    uint32_t cluster_count;
    uint32_t fat_bytes;
    uint32_t fat_entries;
    uint32_t volume_end;
    uint32_t first_fat_lba;
    uint32_t fat_area_end;
    uint32_t data_lba;
    uint32_t active_fat_lba;
    uint32_t root_cluster = 0u;
    uint32_t volume_serial;
    uint16_t ext_flags = 0u;
    uint8_t sectors_per_cluster;
    uint8_t fat_count;
    uint8_t fat_type;
    uint8_t active_fat = 0u;
    const uint8_t *label_source;

    if ((boot[510] != 0x55u) || (boot[511] != 0xaau) ||
        !(((boot[0] == 0xebu) && (boot[2] == 0x90u)) ||
          (boot[0] == 0xe9u))) {
        return FAT_RO_ERR_NO_FS;
    }

    bytes_per_sector = fat_get_le16(&boot[11]);
    sectors_per_cluster = boot[13];
    reserved_sectors = fat_get_le16(&boot[14]);
    fat_count = boot[16];
    root_entries = fat_get_le16(&boot[17]);
    total_sectors_16 = fat_get_le16(&boot[19]);
    fat_sectors_16 = fat_get_le16(&boot[22]);
    total_sectors_32 = fat_get_le32(&boot[32]);
    fat_sectors_32 = fat_get_le32(&boot[36]);

    if (bytes_per_sector != FAT_RO_SECTOR_SIZE) {
        return FAT_RO_ERR_UNSUPPORTED;
    }
    if (!fat_is_power_of_two(sectors_per_cluster) ||
        (sectors_per_cluster > 128u) ||
        (reserved_sectors == 0u) ||
        (fat_count == 0u) || (fat_count > 4u)) {
        return FAT_RO_ERR_CORRUPT;
    }
    if ((total_sectors_16 != 0u) && (total_sectors_32 != 0u)) {
        return FAT_RO_ERR_CORRUPT;
    }
    total_sectors = (total_sectors_16 != 0u) ?
                    (uint32_t)total_sectors_16 : total_sectors_32;
    if (total_sectors == 0u) {
        return FAT_RO_ERR_CORRUPT;
    }
    if ((partition_sectors != 0u) && (total_sectors > partition_sectors)) {
        return FAT_RO_ERR_CORRUPT;
    }
    if (!fat_add_u32(partition_lba, total_sectors, &volume_end)) {
        return FAT_RO_ERR_CORRUPT;
    }
    if ((volume->media_sectors != 0u) &&
        ((partition_lba >= volume->media_sectors) ||
         (total_sectors > volume->media_sectors - partition_lba))) {
        return FAT_RO_ERR_RANGE;
    }

    if (!fat_mul_u32((uint32_t)root_entries, 32u, &root_dir_sectors)) {
        return FAT_RO_ERR_CORRUPT;
    }
    if ((root_dir_sectors & (FAT_RO_SECTOR_SIZE - 1u)) != 0u) {
        return FAT_RO_ERR_CORRUPT;
    }
    root_dir_sectors /= FAT_RO_SECTOR_SIZE;

    fat_sectors = (fat_sectors_16 != 0u) ?
                  (uint32_t)fat_sectors_16 : fat_sectors_32;
    if (fat_sectors == 0u) {
        return FAT_RO_ERR_CORRUPT;
    }
    if (!fat_mul_u32((uint32_t)fat_count, fat_sectors,
                     &fat_area_sectors) ||
        !fat_add_u32((uint32_t)reserved_sectors, fat_area_sectors,
                     &non_data_sectors) ||
        !fat_add_u32(non_data_sectors, root_dir_sectors,
                     &non_data_sectors) ||
        (non_data_sectors >= total_sectors)) {
        return FAT_RO_ERR_CORRUPT;
    }

    data_sectors = total_sectors - non_data_sectors;
    cluster_count = data_sectors / (uint32_t)sectors_per_cluster;
    if (cluster_count < 4085u) {
        return FAT_RO_ERR_UNSUPPORTED;
    }
    fat_type = (cluster_count < 65525u) ? FAT_RO_TYPE_16 : FAT_RO_TYPE_32;
    if ((expected_family != 0u) && (expected_family != fat_type)) {
        return FAT_RO_ERR_CORRUPT;
    }

    if (fat_type == FAT_RO_TYPE_16) {
        /* Offset 36 is BPB_FATSz32 only for FAT32.  On FAT16 those bytes are
         * the drive/extended-boot fields and must not be interpreted as a
         * second FAT-size value. */
        if ((root_entries == 0u) || (fat_sectors_16 == 0u)) {
            return FAT_RO_ERR_CORRUPT;
        }
        label_source = &boot[43];
        volume_serial = fat_get_le32(&boot[39]);
    } else {
        uint32_t raw_root_cluster;

        if ((root_entries != 0u) || (fat_sectors_16 != 0u) ||
            (fat_sectors_32 == 0u) || (root_dir_sectors != 0u) ||
            (fat_get_le16(&boot[42]) != 0u)) {
            return FAT_RO_ERR_CORRUPT;
        }
        ext_flags = fat_get_le16(&boot[40]);
        if ((ext_flags & 0x0080u) != 0u) {
            active_fat = (uint8_t)(ext_flags & 0x000fu);
            if (active_fat >= fat_count) {
                return FAT_RO_ERR_CORRUPT;
            }
        }
        raw_root_cluster = fat_get_le32(&boot[44]);
        if ((raw_root_cluster & 0xf0000000u) != 0u) {
            return FAT_RO_ERR_CORRUPT;
        }
        root_cluster = raw_root_cluster;
        label_source = &boot[71];
        volume_serial = fat_get_le32(&boot[67]);
    }

    if (!fat_mul_u32(fat_sectors, FAT_RO_SECTOR_SIZE, &fat_bytes)) {
        return FAT_RO_ERR_CORRUPT;
    }
    fat_entries = fat_bytes / ((fat_type == FAT_RO_TYPE_16) ? 2u : 4u);
    if ((fat_entries < 2u) || (cluster_count > fat_entries - 2u)) {
        return FAT_RO_ERR_CORRUPT;
    }
    if ((fat_type == FAT_RO_TYPE_32) &&
        ((cluster_count + 1u) > 0x0fffffefu)) {
        return FAT_RO_ERR_UNSUPPORTED;
    }

    if (!fat_add_u32(partition_lba, (uint32_t)reserved_sectors,
                     &first_fat_lba) ||
        !fat_add_u32(first_fat_lba, fat_area_sectors, &fat_area_end) ||
        !fat_add_u32(fat_area_end, root_dir_sectors, &data_lba) ||
        !fat_add_u32(first_fat_lba,
                     (uint32_t)active_fat * fat_sectors,
                     &active_fat_lba) ||
        (data_lba >= volume_end)) {
        return FAT_RO_ERR_CORRUPT;
    }

    if ((fat_type == FAT_RO_TYPE_32) &&
        ((root_cluster < 2u) ||
         (root_cluster > cluster_count + 1u) ||
         (root_cluster >= 0x0ffffff0u))) {
        return FAT_RO_ERR_CORRUPT;
    }

    volume->partition_lba = partition_lba;
    volume->total_sectors = total_sectors;
    volume->first_fat_lba = first_fat_lba;
    volume->fat_sectors = fat_sectors;
    volume->root_dir_lba = (fat_type == FAT_RO_TYPE_16) ? fat_area_end : 0u;
    volume->root_dir_sectors = root_dir_sectors;
    volume->data_lba = data_lba;
    volume->cluster_count = cluster_count;
    volume->root_cluster = root_cluster;
    volume->cluster_size_bytes =
        (uint32_t)sectors_per_cluster * FAT_RO_SECTOR_SIZE;
    volume->volume_serial = volume_serial;
    volume->sectors_per_cluster = sectors_per_cluster;
    volume->fat_count = fat_count;
    volume->active_fat = active_fat;
    volume->fat_type = fat_type;
    volume->active_fat_lba = active_fat_lba;
    volume->last_data_cluster = cluster_count + 1u;
    volume->fat_cache_valid = 0u;
    fat_copy_volume_label(volume->volume_label, label_source);
    volume->mount_cookie = FAT_RO_MOUNT_COOKIE;
    return FAT_RO_OK;
}

int fat_ro_mount(fat_ro_volume_t *volume,
                 fat_ro_read_sectors_fn read_sectors,
                 void *read_user,
                 uint32_t media_sectors)
{
    uint32_t i;
    int status;
    int candidate_status = FAT_RO_ERR_NO_FS;

    if ((volume == NULL) || (read_sectors == NULL)) {
        return FAT_RO_ERR_ARGUMENT;
    }

    fat_clear(volume, (uint32_t)sizeof(*volume));
    volume->read_sectors = read_sectors;
    volume->read_user = read_user;
    volume->media_sectors = media_sectors;

    status = fat_read_raw(volume, 0u, 1u, volume->sector);
    if (status != FAT_RO_OK) {
        return status;
    }

    status = fat_parse_boot_sector(volume, 0u, media_sectors, 0u);
    if (status == FAT_RO_OK) {
        return FAT_RO_OK;
    }
    candidate_status = status;

    if ((volume->sector[510] != 0x55u) ||
        (volume->sector[511] != 0xaau)) {
        volume->mount_cookie = 0u;
        return candidate_status;
    }

    /* The MBR is needed after each candidate boot sector read. */
    status = fat_read_raw(volume, 0u, 1u, volume->sector);
    if (status != FAT_RO_OK) {
        return status;
    }
    for (i = 0u; i < 4u; ++i) {
        uint8_t entry[16];
        uint8_t family;
        uint32_t j;
        uint32_t start_lba;
        uint32_t sector_count;
        uint32_t partition_end;

        for (j = 0u; j < 16u; ++j) {
            entry[j] = volume->sector[446u + i * 16u + j];
        }
        family = fat_partition_family(entry[4]);
        if ((family == 0u) ||
            ((entry[0] != 0u) && (entry[0] != 0x80u))) {
            continue;
        }
        start_lba = fat_get_le32(&entry[8]);
        sector_count = fat_get_le32(&entry[12]);
        if ((start_lba == 0u) || (sector_count == 0u) ||
            !fat_add_u32(start_lba, sector_count, &partition_end) ||
            ((media_sectors != 0u) &&
             ((start_lba >= media_sectors) ||
              (sector_count > media_sectors - start_lba)))) {
            candidate_status = FAT_RO_ERR_CORRUPT;
            continue;
        }

        status = fat_read_raw(volume, start_lba, 1u, volume->sector);
        if (status != FAT_RO_OK) {
            volume->mount_cookie = 0u;
            return status;
        }
        status = fat_parse_boot_sector(volume, start_lba, sector_count,
                                       family);
        if (status == FAT_RO_OK) {
            return FAT_RO_OK;
        }
        if ((status == FAT_RO_ERR_CORRUPT) ||
            (status == FAT_RO_ERR_UNSUPPORTED)) {
            candidate_status = status;
        }

        /* Restore sector zero before examining the next MBR entry. */
        status = fat_read_raw(volume, 0u, 1u, volume->sector);
        if (status != FAT_RO_OK) {
            volume->mount_cookie = 0u;
            return status;
        }
    }

    volume->mount_cookie = 0u;
    return candidate_status;
}

static int fat_cluster_is_data(const fat_ro_volume_t *volume,
                               uint32_t cluster)
{
    if ((cluster < 2u) || (cluster > volume->last_data_cluster)) {
        return 0;
    }
    if (volume->fat_type == FAT_RO_TYPE_16) {
        return cluster < 0xfff0u;
    }
    return cluster < 0x0ffffff0u;
}

static int fat_cluster_lba(const fat_ro_volume_t *volume,
                           uint32_t cluster, uint32_t *lba)
{
    uint32_t sector_offset;

    if (!fat_cluster_is_data(volume, cluster) ||
        !fat_mul_u32(cluster - 2u,
                     (uint32_t)volume->sectors_per_cluster,
                     &sector_offset) ||
        !fat_add_u32(volume->data_lba, sector_offset, lba)) {
        return FAT_RO_ERR_CHAIN;
    }
    if ((*lba < volume->partition_lba) ||
        ((*lba - volume->partition_lba) >= volume->total_sectors)) {
        return FAT_RO_ERR_CHAIN;
    }
    return FAT_RO_OK;
}

static int fat_read_fat_sector(fat_ro_volume_t *volume, uint32_t lba)
{
    int status;

    if ((volume->fat_cache_valid != 0u) &&
        (volume->fat_cache_lba == lba)) {
        return FAT_RO_OK;
    }
    volume->fat_cache_valid = 0u;
    status = fat_read_volume(volume, lba, 1u, volume->fat_cache);
    if (status != FAT_RO_OK) {
        return status;
    }
    volume->fat_cache_lba = lba;
    volume->fat_cache_valid = 1u;
    return FAT_RO_OK;
}

static int fat_next_cluster(fat_ro_volume_t *volume, uint32_t cluster,
                            uint32_t *next_cluster, int *at_end)
{
    uint32_t byte_offset;
    uint32_t sector_offset;
    uint32_t entry_offset;
    uint32_t lba;
    uint32_t value;
    int status;

    if (!fat_cluster_is_data(volume, cluster)) {
        return FAT_RO_ERR_CHAIN;
    }
    if (volume->fat_type == FAT_RO_TYPE_16) {
        byte_offset = cluster * 2u;
    } else {
        if (!fat_mul_u32(cluster, 4u, &byte_offset)) {
            return FAT_RO_ERR_CHAIN;
        }
    }
    sector_offset = byte_offset / FAT_RO_SECTOR_SIZE;
    entry_offset = byte_offset & (FAT_RO_SECTOR_SIZE - 1u);
    if ((sector_offset >= volume->fat_sectors) ||
        !fat_add_u32(volume->active_fat_lba, sector_offset, &lba)) {
        return FAT_RO_ERR_CHAIN;
    }
    status = fat_read_fat_sector(volume, lba);
    if (status != FAT_RO_OK) {
        return status;
    }

    if (volume->fat_type == FAT_RO_TYPE_16) {
        value = (uint32_t)fat_get_le16(&volume->fat_cache[entry_offset]);
        if (value >= 0xfff8u) {
            *at_end = 1;
            *next_cluster = 0u;
            return FAT_RO_OK;
        }
        if ((value >= 0xfff0u) || !fat_cluster_is_data(volume, value)) {
            return FAT_RO_ERR_CHAIN;
        }
    } else {
        value = fat_get_le32(&volume->fat_cache[entry_offset]) &
                0x0fffffffu;
        if (value >= 0x0ffffff8u) {
            *at_end = 1;
            *next_cluster = 0u;
            return FAT_RO_OK;
        }
        if ((value >= 0x0ffffff0u) || !fat_cluster_is_data(volume, value)) {
            return FAT_RO_ERR_CHAIN;
        }
    }

    *at_end = 0;
    *next_cluster = value;
    return FAT_RO_OK;
}

static void fat_lfn_reset(fat_lfn_state_t *state)
{
    state->active = 0u;
    state->expected_ordinal = 0u;
    state->entry_count = 0u;
    state->checksum = 0u;
}

static void fat_lfn_start(fat_lfn_state_t *state, uint8_t ordinal,
                          uint8_t checksum)
{
    uint32_t i;

    for (i = 0u; i < FAT_LFN_UNITS; ++i) {
        state->unit[i] = 0xffffu;
    }
    state->active = 1u;
    state->expected_ordinal = ordinal;
    state->entry_count = ordinal;
    state->checksum = checksum;
}

static void fat_lfn_consume(fat_lfn_state_t *state, const uint8_t *entry)
{
    uint8_t order = entry[0];
    uint8_t ordinal = (uint8_t)(order & 0x3fu);
    uint8_t is_last = (uint8_t)(order & FAT_LFN_LAST);
    uint32_t i;
    uint32_t base;

    if (((order & 0x80u) != 0u) || (ordinal == 0u) ||
        (ordinal > FAT_LFN_MAX_ENTRIES) ||
        (entry[11] != FAT_ATTR_LONG_NAME) ||
        (entry[12] != 0u) ||
        (fat_get_le16(&entry[26]) != 0u)) {
        fat_lfn_reset(state);
        return;
    }

    if (is_last != 0u) {
        fat_lfn_start(state, ordinal, entry[13]);
    } else if ((state->active == 0u) ||
               (state->expected_ordinal != ordinal) ||
               (state->checksum != entry[13])) {
        fat_lfn_reset(state);
        return;
    }

    if ((state->active == 0u) ||
        (state->expected_ordinal != ordinal) ||
        (state->checksum != entry[13])) {
        fat_lfn_reset(state);
        return;
    }

    base = ((uint32_t)ordinal - 1u) * 13u;
    for (i = 0u; i < 13u; ++i) {
        state->unit[base + i] = fat_get_le16(&entry[fat_lfn_offsets[i]]);
    }
    --state->expected_ordinal;
}

static uint8_t fat_short_checksum(const uint8_t *entry)
{
    uint32_t i;
    uint8_t checksum = 0u;

    for (i = 0u; i < 11u; ++i) {
        checksum = (uint8_t)(((checksum & 1u) != 0u ? 0x80u : 0u) |
                             (checksum >> 1));
        checksum = (uint8_t)(checksum + entry[i]);
    }
    return checksum;
}

static int fat_lfn_ascii(const fat_lfn_state_t *state,
                         uint8_t short_checksum, char name[256])
{
    uint32_t slots;
    uint32_t length;
    uint32_t i;
    int terminated = 0;

    if ((state->active == 0u) || (state->expected_ordinal != 0u) ||
        (state->entry_count == 0u) ||
        (state->entry_count > FAT_LFN_MAX_ENTRIES) ||
        (state->checksum != short_checksum)) {
        return 0;
    }

    slots = (uint32_t)state->entry_count * 13u;
    length = slots;
    for (i = 0u; i < slots; ++i) {
        uint16_t unit = state->unit[i];

        if (!terminated) {
            if (unit == 0u) {
                terminated = 1;
                length = i;
            } else if (unit == 0xffffu) {
                return 0;
            }
        } else if (unit != 0xffffu) {
            return 0;
        }
    }

    if ((length == 0u) || (length > FAT_RO_NAME_MAX) ||
        ((state->entry_count > 1u) &&
         (length <= ((uint32_t)state->entry_count - 1u) * 13u))) {
        return 0;
    }
    if ((!terminated) && (slots > FAT_RO_NAME_MAX)) {
        return 0;
    }

    for (i = 0u; i < length; ++i) {
        uint16_t unit = state->unit[i];

        if ((unit < 0x20u) || (unit > 0x7eu) ||
            (unit == (uint16_t)'"') || (unit == (uint16_t)'*') ||
            (unit == (uint16_t)'/') || (unit == (uint16_t)':') ||
            (unit == (uint16_t)'<') || (unit == (uint16_t)'>') ||
            (unit == (uint16_t)'?') || (unit == (uint16_t)'\\') ||
            (unit == (uint16_t)'|')) {
            return 0;
        }
        name[i] = (char)unit;
    }
    name[length] = '\0';
    return 1;
}

static char fat_ascii_lower(char c)
{
    if ((c >= 'A') && (c <= 'Z')) {
        return (char)(c + ('a' - 'A'));
    }
    return c;
}

static int fat_ascii_equal(const char *a, const char *b)
{
    uint32_t i = 0u;

    for (;;) {
        char ca = a[i];
        char cb = b[i];

        if (fat_ascii_lower(ca) != fat_ascii_lower(cb)) {
            return 0;
        }
        if (ca == '\0') {
            return 1;
        }
        ++i;
    }
}

static int fat_query_valid(const char *name)
{
    uint32_t i;

    if (name == NULL) {
        return 0;
    }
    for (i = 0u; i <= FAT_RO_NAME_MAX; ++i) {
        uint8_t c = (uint8_t)name[i];

        if (c == 0u) {
            return i != 0u;
        }
        if ((c < 0x20u) || (c > 0x7eu) ||
            (c == (uint8_t)'/') || (c == (uint8_t)'\\') ||
            (c == (uint8_t)':')) {
            return 0;
        }
    }
    return 0;
}

static int fat_short_name(const uint8_t *entry, char name[13])
{
    uint32_t base_length = 8u;
    uint32_t extension_length = 3u;
    uint32_t output = 0u;
    uint32_t i;
    uint8_t nt_case = entry[12];
    int ascii = 1;

    while ((base_length != 0u) &&
           (entry[base_length - 1u] == (uint8_t)' ')) {
        --base_length;
    }
    while ((extension_length != 0u) &&
           (entry[8u + extension_length - 1u] == (uint8_t)' ')) {
        --extension_length;
    }
    if (base_length == 0u) {
        name[0] = '\0';
        return 0;
    }

    for (i = 0u; i < base_length; ++i) {
        uint8_t c = entry[i];

        if ((i == 0u) && (c == 0x05u)) {
            c = 0xe5u;
        }
        if ((c == (uint8_t)' ') || (c < 0x20u) || (c > 0x7eu)) {
            ascii = 0;
            name[output++] = '?';
        } else {
            char printable = (char)c;
            if ((nt_case & 0x08u) != 0u) {
                printable = fat_ascii_lower(printable);
            }
            name[output++] = printable;
        }
    }
    if (extension_length != 0u) {
        name[output++] = '.';
        for (i = 0u; i < extension_length; ++i) {
            uint8_t c = entry[8u + i];

            if ((c == (uint8_t)' ') || (c < 0x20u) || (c > 0x7eu)) {
                ascii = 0;
                name[output++] = '?';
            } else {
                char printable = (char)c;
                if ((nt_case & 0x10u) != 0u) {
                    printable = fat_ascii_lower(printable);
                }
                name[output++] = printable;
            }
        }
    }
    name[output] = '\0';
    return ascii;
}

static void fat_copy_name(char *destination, const char *source,
                          uint32_t capacity)
{
    uint32_t i = 0u;

    if (capacity == 0u) {
        return;
    }
    while ((i + 1u < capacity) && (source[i] != '\0')) {
        destination[i] = source[i];
        ++i;
    }
    destination[i] = '\0';
}

static int fat_process_short_entry(fat_ro_volume_t *volume,
                                   const uint8_t *entry,
                                   const fat_lfn_state_t *lfn,
                                   const char *query,
                                   fat_ro_file_t *file)
{
    char short_name[13];
    char long_name[256];
    uint32_t first_cluster;
    uint32_t size;
    uint32_t required_clusters;
    int short_is_ascii;
    int long_is_ascii;
    int matched;

    if (((entry[11] & FAT_ATTR_VOLUME_ID) != 0u) ||
        ((entry[11] & FAT_ATTR_DIRECTORY) != 0u)) {
        return 0;
    }

    short_is_ascii = fat_short_name(entry, short_name);
    long_is_ascii = fat_lfn_ascii(lfn, fat_short_checksum(entry), long_name);
    matched = (short_is_ascii && fat_ascii_equal(query, short_name)) ||
              (long_is_ascii && fat_ascii_equal(query, long_name));
    if (!matched) {
        return 0;
    }

    if (volume->fat_type == FAT_RO_TYPE_16) {
        if (fat_get_le16(&entry[20]) != 0u) {
            return FAT_RO_ERR_CORRUPT;
        }
        first_cluster = (uint32_t)fat_get_le16(&entry[26]);
    } else {
        uint16_t high = fat_get_le16(&entry[20]);

        if ((high & 0xf000u) != 0u) {
            return FAT_RO_ERR_CORRUPT;
        }
        first_cluster = ((uint32_t)high << 16) |
                        (uint32_t)fat_get_le16(&entry[26]);
    }
    size = fat_get_le32(&entry[28]);
    if (size == 0u) {
        if ((first_cluster != 0u) &&
            !fat_cluster_is_data(volume, first_cluster)) {
            return FAT_RO_ERR_CORRUPT;
        }
    } else {
        if (!fat_cluster_is_data(volume, first_cluster)) {
            return FAT_RO_ERR_CORRUPT;
        }
        required_clusters = size / volume->cluster_size_bytes;
        if ((size % volume->cluster_size_bytes) != 0u) {
            ++required_clusters;
        }
        if (required_clusters > volume->cluster_count) {
            return FAT_RO_ERR_CORRUPT;
        }
    }

    fat_clear(file, (uint32_t)sizeof(*file));
    file->size = size;
    file->first_cluster = first_cluster;
    file->attributes = entry[11];
    file->has_long_name = (uint8_t)(long_is_ascii ? 1u : 0u);
    fat_copy_name(file->short_name, short_name,
                  (uint32_t)sizeof(file->short_name));
    fat_copy_name(file->name, long_is_ascii ? long_name : short_name,
                  (uint32_t)sizeof(file->name));
    return 1;
}

static int fat_scan_directory_sector(fat_ro_volume_t *volume,
                                     const char *query,
                                     fat_ro_file_t *file,
                                     fat_lfn_state_t *lfn,
                                     int *at_directory_end)
{
    uint32_t offset;

    for (offset = 0u; offset < FAT_RO_SECTOR_SIZE; offset += 32u) {
        const uint8_t *entry = &volume->sector[offset];
        int status;

        if (entry[0] == 0u) {
            *at_directory_end = 1;
            return 0;
        }
        if (entry[0] == 0xe5u) {
            fat_lfn_reset(lfn);
            continue;
        }
        if (entry[11] == FAT_ATTR_LONG_NAME) {
            fat_lfn_consume(lfn, entry);
            continue;
        }

        status = fat_process_short_entry(volume, entry, lfn, query, file);
        fat_lfn_reset(lfn);
        if (status != 0) {
            return status;
        }
    }
    return 0;
}

int fat_ro_find(fat_ro_volume_t *volume, const char *name,
                fat_ro_file_t *file)
{
    fat_lfn_state_t lfn;
    int status;
    int at_directory_end = 0;

    if (!fat_volume_ready(volume) || (file == NULL) ||
        !fat_query_valid(name)) {
        return FAT_RO_ERR_ARGUMENT;
    }
    fat_clear(file, (uint32_t)sizeof(*file));
    fat_lfn_reset(&lfn);

    if (volume->fat_type == FAT_RO_TYPE_16) {
        uint32_t sector;

        for (sector = 0u; sector < volume->root_dir_sectors; ++sector) {
            uint32_t lba;

            if (!fat_add_u32(volume->root_dir_lba, sector, &lba)) {
                return FAT_RO_ERR_CORRUPT;
            }
            status = fat_read_volume(volume, lba, 1u, volume->sector);
            if (status != FAT_RO_OK) {
                return status;
            }
            status = fat_scan_directory_sector(volume, name, file, &lfn,
                                               &at_directory_end);
            if (status > 0) {
                return FAT_RO_OK;
            }
            if (status < 0) {
                return status;
            }
            if (at_directory_end) {
                return FAT_RO_ERR_NOT_FOUND;
            }
        }
        return FAT_RO_ERR_NOT_FOUND;
    }

    {
        uint32_t cluster = volume->root_cluster;
        uint32_t fast = cluster;
        uint32_t clusters_seen = 0u;
        int fast_active = 1;

        for (;;) {
            uint32_t base_lba;
            uint32_t sector;
            uint32_t next;
            int at_end;

            ++clusters_seen;
            if (clusters_seen > volume->cluster_count) {
                return FAT_RO_ERR_CHAIN;
            }
            status = fat_cluster_lba(volume, cluster, &base_lba);
            if (status != FAT_RO_OK) {
                return status;
            }
            for (sector = 0u;
                 sector < (uint32_t)volume->sectors_per_cluster;
                 ++sector) {
                uint32_t lba;

                if (!fat_add_u32(base_lba, sector, &lba)) {
                    return FAT_RO_ERR_CHAIN;
                }
                status = fat_read_volume(volume, lba, 1u, volume->sector);
                if (status != FAT_RO_OK) {
                    return status;
                }
                status = fat_scan_directory_sector(volume, name, file, &lfn,
                                                   &at_directory_end);
                if (status > 0) {
                    return FAT_RO_OK;
                }
                if (status < 0) {
                    return status;
                }
                if (at_directory_end) {
                    return FAT_RO_ERR_NOT_FOUND;
                }
            }

            status = fat_next_cluster(volume, cluster, &next, &at_end);
            if (status != FAT_RO_OK) {
                return status;
            }
            if (at_end) {
                return FAT_RO_ERR_NOT_FOUND;
            }
            cluster = next;

            if (fast_active) {
                uint32_t fast_once;
                int fast_end;

                status = fat_next_cluster(volume, fast, &fast_once,
                                          &fast_end);
                if (status != FAT_RO_OK) {
                    return status;
                }
                if (fast_end) {
                    fast_active = 0;
                } else {
                    status = fat_next_cluster(volume, fast_once, &fast,
                                              &fast_end);
                    if (status != FAT_RO_OK) {
                        return status;
                    }
                    if (fast_end) {
                        fast_active = 0;
                    } else if (fast == cluster) {
                        return FAT_RO_ERR_CHAIN;
                    }
                }
            }
        }
    }
}

static int fat_advance_load_cluster(fat_ro_volume_t *volume,
                                    uint32_t *cluster,
                                    uint32_t *fast,
                                    int *fast_active,
                                    uint32_t *clusters_seen)
{
    uint32_t next;
    int at_end;
    int status;

    status = fat_next_cluster(volume, *cluster, &next, &at_end);
    if (status != FAT_RO_OK) {
        return status;
    }
    if (at_end) {
        return FAT_RO_ERR_CHAIN;
    }
    *cluster = next;
    ++*clusters_seen;
    if (*clusters_seen > volume->cluster_count) {
        return FAT_RO_ERR_CHAIN;
    }

    if (*fast_active != 0) {
        uint32_t fast_once;
        int fast_end;

        status = fat_next_cluster(volume, *fast, &fast_once, &fast_end);
        if (status != FAT_RO_OK) {
            return status;
        }
        if (fast_end) {
            *fast_active = 0;
        } else {
            status = fat_next_cluster(volume, fast_once, fast, &fast_end);
            if (status != FAT_RO_OK) {
                return status;
            }
            if (fast_end) {
                *fast_active = 0;
            } else if (*fast == *cluster) {
                return FAT_RO_ERR_CHAIN;
            }
        }
    }
    return FAT_RO_OK;
}

int fat_ro_load(fat_ro_volume_t *volume, const fat_ro_file_t *file,
                void *destination, uint32_t capacity,
                fat_ro_progress_fn progress, void *progress_user)
{
    uint8_t *output = (uint8_t *)destination;
    uint32_t remaining;
    uint32_t done = 0u;
    uint32_t cluster;
    uint32_t fast;
    uint32_t sector = 0u;
    uint32_t clusters_seen = 1u;
    uint32_t required_clusters;
    int fast_active = 1;
    int status;

    if (!fat_volume_ready(volume) || (file == NULL)) {
        return FAT_RO_ERR_ARGUMENT;
    }
    if ((file->size > capacity) ||
        ((file->size != 0u) && (destination == NULL)) ||
        ((file->size != 0u) &&
         ((uintptr_t)destination >
          (uintptr_t)-1 - (uintptr_t)(file->size - 1u)))) {
        return FAT_RO_ERR_RANGE;
    }
    if ((progress != NULL) &&
        (progress(progress_user, 0u, file->size) != 0)) {
        return FAT_RO_ERR_ABORTED;
    }
    if (file->size == 0u) {
        return FAT_RO_OK;
    }
    if (!fat_cluster_is_data(volume, file->first_cluster)) {
        return FAT_RO_ERR_CHAIN;
    }
    required_clusters = file->size / volume->cluster_size_bytes;
    if ((file->size % volume->cluster_size_bytes) != 0u) {
        ++required_clusters;
    }
    if (required_clusters > volume->cluster_count) {
        return FAT_RO_ERR_CHAIN;
    }

    remaining = file->size;
    cluster = file->first_cluster;
    fast = cluster;
    while (remaining != 0u) {
        uint32_t base_lba;
        uint32_t lba;

        status = fat_cluster_lba(volume, cluster, &base_lba);
        if (status != FAT_RO_OK) {
            return status;
        }
        if ((sector >= (uint32_t)volume->sectors_per_cluster) ||
            !fat_add_u32(base_lba, sector, &lba)) {
            return FAT_RO_ERR_CHAIN;
        }

        if (remaining >= FAT_RO_SECTOR_SIZE) {
            uint32_t full_sectors = remaining / FAT_RO_SECTOR_SIZE;
            uint32_t batch = 0u;
            uint32_t scan_cluster = cluster;
            uint32_t scan_sector = sector;
            uint32_t consumed;
            uint32_t bytes;

            while ((batch < FAT_RO_MAX_READ_SECTORS) &&
                   (batch < full_sectors)) {
                uint32_t available =
                    (uint32_t)volume->sectors_per_cluster - scan_sector;
                uint32_t take = full_sectors - batch;

                if (take > FAT_RO_MAX_READ_SECTORS - batch) {
                    take = FAT_RO_MAX_READ_SECTORS - batch;
                }
                if (take > available) {
                    take = available;
                }
                batch += take;
                scan_sector += take;
                if ((batch == FAT_RO_MAX_READ_SECTORS) ||
                    (batch == full_sectors) ||
                    (scan_sector <
                     (uint32_t)volume->sectors_per_cluster)) {
                    break;
                }
                {
                    uint32_t next;
                    int at_end;

                    status = fat_next_cluster(volume, scan_cluster,
                                              &next, &at_end);
                    if (status != FAT_RO_OK) {
                        return status;
                    }
                    if (at_end || (next != scan_cluster + 1u)) {
                        break;
                    }
                    scan_cluster = next;
                    scan_sector = 0u;
                }
            }
            if ((batch == 0u) ||
                !fat_mul_u32(batch, FAT_RO_SECTOR_SIZE, &bytes)) {
                return FAT_RO_ERR_CHAIN;
            }
            status = fat_read_volume(volume, lba, batch, &output[done]);
            if (status != FAT_RO_OK) {
                return status;
            }
            done += bytes;
            remaining -= bytes;

            consumed = batch;
            while (consumed != 0u) {
                uint32_t available =
                    (uint32_t)volume->sectors_per_cluster - sector;
                uint32_t take = (consumed < available) ?
                                consumed : available;

                sector += take;
                consumed -= take;
                if ((sector ==
                     (uint32_t)volume->sectors_per_cluster) &&
                    ((remaining != 0u) || (consumed != 0u))) {
                    status = fat_advance_load_cluster(volume, &cluster,
                                                      &fast, &fast_active,
                                                      &clusters_seen);
                    if (status != FAT_RO_OK) {
                        return status;
                    }
                    sector = 0u;
                }
            }
            if ((progress != NULL) &&
                (progress(progress_user, done, file->size) != 0)) {
                return FAT_RO_ERR_ABORTED;
            }
        } else {
            status = fat_read_volume(volume, lba, 1u, volume->sector);
            if (status != FAT_RO_OK) {
                return status;
            }
            fat_copy(&output[done], volume->sector, remaining);
            done += remaining;
            remaining = 0u;
            if ((progress != NULL) &&
                (progress(progress_user, done, file->size) != 0)) {
                return FAT_RO_ERR_ABORTED;
            }
        }
    }
    return FAT_RO_OK;
}

const char *fat_ro_error_string(int status)
{
    switch (status) {
    case FAT_RO_OK:
        return "ok";
    case FAT_RO_ERR_ARGUMENT:
        return "invalid argument";
    case FAT_RO_ERR_IO:
        return "sector I/O failed";
    case FAT_RO_ERR_NO_FS:
        return "no FAT filesystem";
    case FAT_RO_ERR_UNSUPPORTED:
        return "unsupported FAT layout";
    case FAT_RO_ERR_CORRUPT:
        return "corrupt FAT metadata";
    case FAT_RO_ERR_NOT_FOUND:
        return "file not found";
    case FAT_RO_ERR_RANGE:
        return "out of range";
    case FAT_RO_ERR_CHAIN:
        return "invalid FAT cluster chain";
    case FAT_RO_ERR_ABORTED:
        return "load aborted";
    default:
        return "unknown FAT error";
    }
}
