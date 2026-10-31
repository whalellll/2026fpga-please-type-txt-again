/* Reuse the tested project writer unchanged. This candidate-only extension
 * can advance root-directory padding into an already allocated sector.
 * It neither grows the root chain nor changes an existing live entry. */
#include "../../../linux/boot/v2_1_sd/source/picture_fat_write/fat_camera.c"
int xqns_begin_root_pair(fatcam_t *c,const char name0[11],uint32_t length0,
                        const char name1[11],uint32_t length1)
{
    uint32_t cl,n,hops=0,s,slot=0;unsigned off=0,i,f;int r,ended=0;
    const char *names[2]={name0,name1};
    if(!c||!length0||!length1||c->dirty||c->staged||
       !root_name_valid(name0)||!root_name_valid(name1)||!memcmp(name0,name1,11))return FC_CORRUPT;
    cl=c->volume.root_cluster;
    while(hops++<c->volume.cluster_count){
        for(s=0;s<c->volume.sectors_per_cluster;s++){
            unsigned run=0;
            r=read1(c,data(c,cl)+s,c->sector);if(r)return r;
            for(i=0;i<512;i+=32){
                const uint8_t *e=c->sector+i;
                if(!e[0])ended=1;
                if(ended||e[0]==0xe5){run++;if(run==2&&!slot){slot=data(c,cl)+s;off=i-32;}}
                else {run=0;if(e[11]!=0x0f&&(!memcmp(e,name0,11)||!memcmp(e,name1,11)))return FC_CORRUPT;}
            }
            if(ended&&slot)break;
        }
        if(ended&&slot)break;
        r=next(c,cl,&n);if(r)return r;if(n>=0x0ffffff8u)break;cl=n;
    }
    if(hops>c->volume.cluster_count)return FC_CORRUPT;
    if(!slot)return FC_FULL;
    memset(c->file,0,sizeof(c->file));
    c->file[0].length=length0;c->file[1].length=length1;
    for(f=0;f<2;f++){
        c->file[f].count=(c->file[f].length-1)/c->volume.cluster_size_bytes+1;
        c->file[f].crc=0xffffffffu;memcpy(c->root_names[f],names[f],11);
    }
    if(c->file[0].count>FATCAM_MAX_CLUSTERS||c->file[1].count>FATCAM_MAX_CLUSTERS-c->file[0].count)return FC_FULL;
    c->file[1].first=c->file[0].count;c->dir_lba=slot;c->dir_offset=(uint16_t)off;
    c->dir_cluster=c->volume.root_cluster;c->root_pair=1;
    r=read1(c,slot,c->original);if(r)return r;
    r=allocate(c,c->file[0].count+c->file[1].count);if(r){c->allocated=0;return r;}
    r=start_mutation(c);if(r)return r;
    /* Move only 0x00 padding to 0xe5 before a later-sector publication.
     * A failed/aborted transaction still has a valid directory terminator. */
    r=advance_end(c);if(r)return r;
    r=links(c,0);if(r)return r;c->staged=1;return 0;
}
