#ifndef FAT_BOOT_PREFIX_H
#define FAT_BOOT_PREFIX_H
#include "fat_camera.h"
/* Explicit boot-payload update only. Caller must already have committed and
 * verified an immutable backup and freshly matched CID. FAT/directory metadata
 * never changes. Only a prefix within the first allocated cluster is written;
 * bytes after prefix in its last sector are preserved from full_file. */
int fat_boot_patch_prefix(fat_ro_volume_t *,const fat_ro_file_t *,
                          const uint8_t *full_file,uint32_t prefix_bytes,
                          fatcam_write_fn,void *);
#endif
