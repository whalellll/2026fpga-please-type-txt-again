#ifndef SD_BOOT_LOAD_H
#define SD_BOOT_LOAD_H
#include <stdint.h>
#include "fat_ro.h"

/* The generic FAT reader correctly rejects NULL. The ROM's address-zero
 * bootstrap therefore loads through cached DDR staging, then publishes only
 * word stores through the uncached alias. Keep staging bounded and disjoint
 * from the low bootstrap, DTB, ROM/stack, and all DMA-reserved regions.
 * This path supports the delivered <=1MiB SD bootstrap, not a large kernel.
 */
#define SD_BOOT_ZERO_STAGE_LIMIT (1024u*1024u)
#ifndef SD_BOOT_ZERO_STAGE
#define SD_BOOT_ZERO_STAGE ((void *)(uintptr_t)0x01000000u)
#endif
#ifndef SD_BOOT_ZERO_DEST
#define SD_BOOT_ZERO_DEST ((volatile uint32_t *)(uintptr_t)0x80000000u)
#endif

static inline int sd_boot_load_image(fat_ro_volume_t *volume,
        const fat_ro_file_t *file,uintptr_t address,uint32_t capacity,
        fat_ro_progress_fn progress,void *user)
{
    if(address==0 && file!=0){
        uint32_t i;
        int status;
        const uint32_t *zero_in_words=(const uint32_t *)SD_BOOT_ZERO_STAGE;
        volatile uint32_t *zero_out_words=SD_BOOT_ZERO_DEST;
        if(file->size>capacity || file->size>SD_BOOT_ZERO_STAGE_LIMIT)
            return FAT_RO_ERR_RANGE;
        status=fat_ro_load(volume,file,SD_BOOT_ZERO_STAGE,
                          SD_BOOT_ZERO_STAGE_LIMIT,progress,user);
        if(status)return status;
        for(i=0;i<(file->size+3u)/4u;i++)zero_out_words[i]=zero_in_words[i];
        return FAT_RO_OK;
    }
    return fat_ro_load(volume,file,(void *)address,capacity,progress,user);
}
#endif
