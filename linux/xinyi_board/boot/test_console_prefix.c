/* Actual exported original + loader bytes, synthetic sectors only. */
#include "fat_boot_prefix.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned char disk[256*512],baseline[sizeof(disk)],expected[sizeof(disk)];
static unsigned writes,fault_at,apply_fault,corrupt_read;
static int rd(void *user,uint32_t lba,uint32_t count,uint8_t *out)
{
    (void)user;assert(lba+count<=256);memcpy(out,disk+lba*512,count*512);
    if(corrupt_read)out[0]^=1;return 0;
}
static int wr(void *user,uint32_t lba,const uint8_t *data)
{
    (void)user;assert(lba<256);writes++;
    if(writes==fault_at){if(apply_fault)memcpy(disk+lba*512,data,512);return -1;}
    memcpy(disk+lba*512,data,512);return 0;
}
static unsigned char *read_file(const char *name,unsigned *bytes)
{
    FILE *file=fopen(name,"rb");assert(file);assert(!fseek(file,0,SEEK_END));
    long size=ftell(file);assert(size>0 && size<65536);*bytes=(unsigned)size;
    rewind(file);unsigned char *data=malloc(*bytes);assert(data);
    assert(fread(data,1,*bytes,file)==*bytes);assert(!fclose(file));return data;
}
int main(int argc,char **argv)
{
    assert(argc==3);unsigned original_bytes,loader_bytes;
    unsigned char *original=read_file(argv[1],&original_bytes),*loader=read_file(argv[2],&loader_bytes);
    assert(loader_bytes<=32768 && loader_bytes<=original_bytes);
    unsigned char *image=malloc(original_bytes);assert(image);memcpy(image,original,original_bytes);memcpy(image,loader,loader_bytes);
    memset(disk,0xa5,sizeof(disk));memcpy(disk+128*512,original,original_bytes);
    memcpy(baseline,disk,sizeof(disk));memcpy(expected,disk,sizeof(disk));memcpy(expected+128*512,loader,loader_bytes);
    fat_ro_volume_t v={.fat_type=32,.cluster_size_bytes=32768,.sectors_per_cluster=64,
        .data_lba=64,.partition_lba=32,.total_sectors=224,.last_data_cluster=4,.read_sectors=rd};
    fat_ro_file_t f={.size=original_bytes,.first_cluster=3,.attributes=0x20};
    unsigned blocks=(loader_bytes+511)/512;
    assert(!fat_boot_patch_prefix(&v,&f,image,loader_bytes,wr,NULL));assert(writes==blocks);
    assert(!memcmp(disk,expected,sizeof(disk))); /* Includes tail, other sectors and metadata. */
    writes=0;assert(!fat_boot_patch_prefix(&v,&f,original,loader_bytes,wr,NULL));assert(!memcmp(disk,baseline,sizeof(disk)));
    for(unsigned applied=0;applied<2;applied++)for(unsigned which=0;which<3;which++){
        unsigned at=which==0?1:which==1?blocks/2:blocks;
        memcpy(disk,baseline,sizeof(disk));writes=0;fault_at=at;apply_fault=applied;
        assert(fat_boot_patch_prefix(&v,&f,image,loader_bytes,wr,NULL)==FC_IO);assert(writes==at);
        fault_at=0;writes=0;assert(!fat_boot_patch_prefix(&v,&f,original,loader_bytes,wr,NULL));assert(!memcmp(disk,baseline,sizeof(disk)));
    }
    writes=0;corrupt_read=1;assert(fat_boot_patch_prefix(&v,&f,image,loader_bytes,wr,NULL)==FC_IO);assert(writes==1);
    corrupt_read=0;assert(!fat_boot_patch_prefix(&v,&f,original,loader_bytes,wr,NULL));assert(!memcmp(disk,baseline,sizeof(disk)));
    writes=0;assert(fat_boot_patch_prefix(&v,&f,image,original_bytes+1,wr,NULL)==FC_CORRUPT);
    v.cluster_size_bytes=16384;assert(fat_boot_patch_prefix(&v,&f,image,loader_bytes,wr,NULL)==FC_CORRUPT);v.cluster_size_bytes=32768;
    f.attributes=0x10;assert(fat_boot_patch_prefix(&v,&f,image,loader_bytes,wr,NULL)==FC_CORRUPT);f.attributes=0x20;
    f.first_cluster=1;assert(fat_boot_patch_prefix(&v,&f,image,loader_bytes,wr,NULL)==FC_CORRUPT);f.first_cluster=3;
    assert(fat_boot_patch_prefix(&v,&f,image,0,wr,NULL)==FC_CORRUPT);assert(!writes);
    free(image);free(loader);free(original);puts("EXACT_ENTRY_PREFIX_TAIL_METADATA_FAILURE_RESTORE_PASS");return 0;
}
