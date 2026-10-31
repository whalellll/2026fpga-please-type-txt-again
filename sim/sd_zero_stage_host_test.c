#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "fat_ro.h"

#define WORDS (1024u*1024u/4u)
static uint32_t stage[WORDS], published[WORDS+2u];
#define SD_BOOT_ZERO_STAGE ((void *)stage)
#define SD_BOOT_ZERO_DEST ((volatile uint32_t *)&published[1])
#include "sd_boot_load.h"

static int calls, injected;
static void *last_destination;
static uint32_t last_capacity;
int fat_ro_load(fat_ro_volume_t *v,const fat_ro_file_t *f,void *dst,uint32_t cap,
                fat_ro_progress_fn cb,void *user)
{
    uint32_t i;
    (void)v;(void)cb;(void)user;
    calls++;last_destination=dst;last_capacity=cap;
    if(!f)return FAT_RO_ERR_ARGUMENT;
    if(f->size>cap || (f->size && !dst))return FAT_RO_ERR_RANGE;
    if(injected)return injected;
    for(i=0;i<f->size;i++)((uint8_t *)dst)[i]=(uint8_t)(i*37u+11u);
    return FAT_RO_OK;
}
static void check(int condition,const char *message)
{if(!condition){fprintf(stderr,"SD_ZERO_STAGE_FAIL %s\n",message);exit(1);}}
int main(void)
{
    const uint32_t sizes[]={0,1,3,4,511,512,14232,14336,1024u*1024u};
    fat_ro_volume_t volume={0};fat_ro_file_t file={0};
    uint32_t i,j,normal[16];int before;
    for(i=0;i<sizeof(sizes)/sizeof(sizes[0]);i++){
        file.size=sizes[i];memset(stage,0xcc,sizeof(stage));
        memset(published,0xa5,sizeof(published));injected=0;
        check(sd_boot_load_image(&volume,&file,0,0x01c00000u,NULL,NULL)==0,"zero load rejected");
        check(last_destination==stage && last_capacity==1024u*1024u,"not bounded staging");
        for(j=0;j<file.size;j++)check(((uint8_t *)&published[1])[j]==(uint8_t)(j*37u+11u),"published bytes differ");
        check(published[0]==0xa5a5a5a5u,"leading guard changed");
        check(published[1+(file.size+3u)/4u]==0xa5a5a5a5u,"trailing guard changed");
    }
    file.size=1024u*1024u+1u;before=calls;
    check(sd_boot_load_image(&volume,&file,0,0x01c00000u,NULL,NULL)==FAT_RO_ERR_RANGE,"oversize accepted");
    check(calls==before,"oversize reached reader");
    file.size=32;before=calls;
    check(sd_boot_load_image(&volume,&file,0,31,NULL,NULL)==FAT_RO_ERR_RANGE,"caller capacity ignored");
    check(calls==before,"capacity violation reached reader");
    injected=FAT_RO_ERR_ABORTED;memset(published,0xa5,sizeof(published));
    check(sd_boot_load_image(&volume,&file,0,64,NULL,NULL)==FAT_RO_ERR_ABORTED,"abort lost");
    check(published[1]==0xa5a5a5a5u,"aborted bytes published");
    injected=FAT_RO_ERR_IO;
    check(sd_boot_load_image(&volume,&file,0,64,NULL,NULL)==FAT_RO_ERR_IO,"IO error lost");
    check(published[1]==0xa5a5a5a5u,"failed bytes published");
    injected=0;memset(normal,0,sizeof(normal));
    check(sd_boot_load_image(&volume,&file,(uintptr_t)normal,sizeof(normal),NULL,NULL)==0,"normal destination rejected");
    check(last_destination==normal && last_capacity==sizeof(normal),"normal path changed");
    check(sd_boot_load_image(&volume,NULL,0,64,NULL,NULL)==FAT_RO_ERR_ARGUMENT,"NULL file unchecked");
    puts("SD_ZERO_STAGE_HOST_PASS lengths=9 bounds=2 abort=1 io=1 nonzero=1 null_file=1");
    return 0;
}
