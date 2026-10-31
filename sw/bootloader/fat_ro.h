#ifndef FAT_RO_H
#define FAT_RO_H

#include <stddef.h>
#include <stdint.h>

#define FAT_RO_SECTOR_SIZE 512u
#define FAT_RO_NAME_MAX    255u

#define FAT_RO_TYPE_16 16u
#define FAT_RO_TYPE_32 32u

/* read_sectors returns zero on success and nonzero on an I/O failure.
 * count is always in the range 1..32 and destination has room for
 * count * FAT_RO_SECTOR_SIZE bytes. */
typedef int (*fat_ro_read_sectors_fn)(void *user, uint32_t lba,
                                      uint32_t count,
                                      uint8_t *destination);

/* Called before loading and after each completed read batch (or final partial
 * sector).  Return nonzero to abort the load.  The callback is optional. */
typedef int (*fat_ro_progress_fn)(void *user, uint32_t bytes_done,
                                  uint32_t bytes_total);

enum fat_ro_status {
    FAT_RO_OK              = 0,
    FAT_RO_ERR_ARGUMENT    = -1,
    FAT_RO_ERR_IO          = -2,
    FAT_RO_ERR_NO_FS       = -3,
    FAT_RO_ERR_UNSUPPORTED = -4,
    FAT_RO_ERR_CORRUPT     = -5,
    FAT_RO_ERR_NOT_FOUND   = -6,
    FAT_RO_ERR_RANGE       = -7,
    FAT_RO_ERR_CHAIN       = -8,
    FAT_RO_ERR_ABORTED     = -9
};

typedef struct {
    /* Publicly useful volume information. */
    uint32_t media_sectors;
    uint32_t partition_lba;
    uint32_t total_sectors;
    uint32_t first_fat_lba;
    uint32_t fat_sectors;
    uint32_t root_dir_lba;
    uint32_t root_dir_sectors;
    uint32_t data_lba;
    uint32_t cluster_count;
    uint32_t root_cluster;
    uint32_t cluster_size_bytes;
    uint32_t volume_serial;
    uint8_t sectors_per_cluster;
    uint8_t fat_count;
    uint8_t active_fat;
    uint8_t fat_type;
    char volume_label[12];

    /* Private implementation state; callers must not alter these fields. */
    fat_ro_read_sectors_fn read_sectors;
    void *read_user;
    uint32_t active_fat_lba;
    uint32_t last_data_cluster;
    uint32_t fat_cache_lba;
    uint32_t mount_cookie;
    uint8_t fat_cache_valid;
    uint8_t sector[FAT_RO_SECTOR_SIZE];
    uint8_t fat_cache[FAT_RO_SECTOR_SIZE];
} fat_ro_volume_t;

typedef struct {
    uint32_t size;
    uint32_t first_cluster;
    uint8_t attributes;
    uint8_t has_long_name;
    char short_name[13];
    char name[FAT_RO_NAME_MAX + 1u];
} fat_ro_file_t;

/* media_sectors is the card capacity in 512-byte sectors.  Zero is allowed
 * when the device cannot report its capacity, but supplying it enables
 * stronger boundary validation. */
int fat_ro_mount(fat_ro_volume_t *volume,
                 fat_ro_read_sectors_fn read_sectors,
                 void *read_user,
                 uint32_t media_sectors);

/* Finds a regular file in the root directory.  The requested name must be
 * ASCII and is matched case-insensitively against a validated VFAT long name
 * and the 8.3 short name. */
int fat_ro_find(fat_ro_volume_t *volume, const char *name,
                fat_ro_file_t *file);

/* Loads the complete file into destination.  capacity must be at least the
 * file size.  progress may be NULL; otherwise it can also request abort. */
int fat_ro_load(fat_ro_volume_t *volume, const fat_ro_file_t *file,
                void *destination, uint32_t capacity,
                fat_ro_progress_fn progress, void *progress_user);

const char *fat_ro_error_string(int status);

#endif
