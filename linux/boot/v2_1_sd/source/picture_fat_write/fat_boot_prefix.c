#include "fat_boot_prefix.h"
#include <string.h>
int fat_boot_patch_prefix(fat_ro_volume_t *v,const fat_ro_file_t *f,
                          const uint8_t *full,uint32_t bytes,
                          fatcam_write_fn write,void *user)
{
 uint32_t lba,blocks,i;uint8_t sector[512] __attribute__((aligned(4)));
 uint8_t check[512] __attribute__((aligned(4)));
 if(!v||!f||!full||!write||v->fat_type!=32||!bytes||bytes>f->size||
    bytes>v->cluster_size_bytes||f->first_cluster<2||
    f->first_cluster>v->last_data_cluster||f->attributes&0x18)return FC_CORRUPT;
 blocks=(bytes+511u)/512u;
 /* Also require the preserved tail of the final sector to exist in RAM. */
 if(blocks>f->size/512u||blocks>v->sectors_per_cluster)return FC_CORRUPT;
 lba=v->data_lba+(f->first_cluster-2u)*v->sectors_per_cluster;
 if(lba<v->data_lba||lba<v->partition_lba||
    lba-v->partition_lba>=v->total_sectors||blocks>v->total_sectors-(lba-v->partition_lba))return FC_CORRUPT;
 for(i=0;i<blocks;i++){
  memcpy(sector,full+i*512u,512);
  /* An uncertain write is never retried. Recovery is a separate explicit
   * operation after CID verification using the already-verified backup. */
  if(write(user,lba+i,sector))return FC_IO;
  if(v->read_sectors(v->read_user,lba+i,1,check)||memcmp(sector,check,512))return FC_IO;
 }
 return 0;
}
