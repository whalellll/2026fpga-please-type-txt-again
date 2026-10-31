#ifndef FAT_CAMERA_H
#define FAT_CAMERA_H
#include "fat_ro.h"

/* Sole writer: one camera transaction, no concurrent filesystem access.
 * Workspace is caller-owned and may live above the immutable DDR snapshot. */
#define FATCAM_MAX_CLUSTERS 6144u
enum { FC_OK=0, FC_CANCEL=1, FC_IO=-1, FC_FS=-2, FC_FULL=-3,
       FC_CORRUPT=-4, FC_REPAIR=-5, FC_TIMEOUT=-6 };
typedef int (*fatcam_write_fn)(void *,uint32_t,const uint8_t *);
/* Optional data-only contiguous write. Return an FC_* result; metadata keeps
 * the single-sector write/readback path. Caller owns an aligned staging area. */
typedef int (*fatcam_batch_write_fn)(void *,uint32_t,uint32_t,const uint8_t *);
typedef int (*fatcam_poll_fn)(void *,uint32_t,uint32_t,int);
typedef struct {
 uint32_t first,count,length,done,crc;
 uint16_t used;uint8_t verified;
 uint8_t sector[512] __attribute__((aligned(4)));
} fatcam_file_t;
typedef struct {
 fat_ro_volume_t volume;
 fatcam_write_fn write;
 fatcam_batch_write_fn batch_write;
 fatcam_poll_fn poll;
 void *user;
 uint32_t *clusters,allocated,id,dir_lba,dir_cluster,fsinfo,backup_fsinfo;
 uint8_t *batch_buffer;
 uint32_t batch_lba;
 uint8_t batch_capacity,batch_blocks,batch_file;
 uint16_t dir_offset;
 uint8_t mirrored,dirty,staged,published,cleanup,unsafe;
 uint8_t sector[512] __attribute__((aligned(4)));
 uint8_t verify[512],original[512];
 fatcam_file_t file[2];
} fatcam_t;
int fatcam_open(fatcam_t *,fat_ro_read_sectors_fn,fatcam_write_fn,void *,
               uint32_t,uint32_t *,fatcam_poll_fn);
int fatcam_begin(fatcam_t *,uint32_t png_length,uint32_t json_length);
int fatcam_set_batch(fatcam_t *,fatcam_batch_write_fn,uint8_t *,uint32_t sectors);
int fatcam_write(fatcam_t *,unsigned file,const uint8_t *,uint32_t);
int fatcam_finish(fatcam_t *,unsigned file,uint32_t expected_crc);
int fatcam_commit(fatcam_t *);
int fatcam_abort(fatcam_t *);
const char *fatcam_error(int);
void fatcam_name(uint32_t id,char name[13]); /* IMG00001.PNG */
#endif
