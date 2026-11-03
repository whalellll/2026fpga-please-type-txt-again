/* VOICE namespace adaptation of sw/bootloader/fat_camera.c.
 * Source SHA256 b41ec1870740fc9f1a5de2d06b0ec63a6ce9056667b50b824db651fd8f697d15.
 * Transaction/writeback/verification/rollback logic retained. */
#include "fat_camera.h"
#include "crc32_fast.h"
#include <string.h>

#define EOC 0x0fffffffu
#define CLEAN 0x08000000u
#define NO_ERROR 0x04000000u
typedef uint32_t fatcam_alias_word_t __attribute__((__may_alias__));
static void copy_data(uint8_t *dst,const uint8_t *src,uint32_t count)
{
#if defined(__BYTE_ORDER__) && (__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__)
 uint32_t word;
 while(count&&((uintptr_t)dst&3u)){*dst++=*src++;count--;}
 while(count>=4u){
  if(((uintptr_t)src&3u)==0u)word=*(volatile const fatcam_alias_word_t *)(const void *)src;
  else word=(uint32_t)src[0]|((uint32_t)src[1]<<8)|((uint32_t)src[2]<<16)|((uint32_t)src[3]<<24);
  *(volatile fatcam_alias_word_t *)(void *)dst=word;
  dst+=4;src+=4;count-=4;
 }
#endif
 while(count--)*dst++=*src++;
}
static uint16_t le16(const uint8_t *p){return (uint16_t)(p[0]|((uint16_t)p[1]<<8));}
static uint32_t le32(const uint8_t *p){return p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void put16(uint8_t *p,uint16_t v){p[0]=(uint8_t)v;p[1]=(uint8_t)(v>>8);}
static void put32(uint8_t *p,uint32_t v){put16(p,(uint16_t)v);put16(p+2,(uint16_t)(v>>16));}
static int poll(fatcam_t *c){return c->poll?c->poll(c->user,c->file[0].done,c->file[0].length,c->cleanup):0;}
static int read1(fatcam_t *c,uint32_t lba,uint8_t *b)
{
 int r=poll(c);if(r)return r;
 if(lba<c->volume.partition_lba||lba-c->volume.partition_lba>=c->volume.total_sectors)return FC_CORRUPT;
 return c->volume.read_sectors(c->user,lba,1,b)?FC_IO:0;
}
static int write1(fatcam_t *c,uint32_t lba,const uint8_t *b)
{
 int r=poll(c);if(r)return r;
 if(lba<c->volume.partition_lba||lba-c->volume.partition_lba>=c->volume.total_sectors)return FC_CORRUPT;
 if(c->write(c->user,lba,b))return FC_IO;
 /* Metadata writes are verified before proceeding; read uses separate buffer. */
 if(c->volume.read_sectors(c->user,lba,1,c->verify)||memcmp(b,c->verify,512))return FC_IO;
 return 0;
}
static uint32_t fatbase(fatcam_t *c,unsigned copy)
{return c->volume.first_fat_lba+copy*c->volume.fat_sectors;}
static int fatread(fatcam_t *c,uint32_t index)
{
 int r=read1(c,fatbase(c,c->volume.active_fat)+index,c->sector);if(r)return r;
 if(c->mirrored&&c->volume.fat_count==2){
  r=read1(c,fatbase(c,1)+index,c->verify);if(r)return r;
  if(memcmp(c->sector,c->verify,512))return FC_CORRUPT;
 }
 return 0;
}
static int fatwrite(fatcam_t *c,uint32_t index)
{
 unsigned i;int r;
 for(i=0;i<c->volume.fat_count;i++){
  if(!c->mirrored&&i!=c->volume.active_fat)continue;
  r=write1(c,fatbase(c,i)+index,c->sector);if(r)return r;
 }
 return 0;
}
static int next(fatcam_t *c,uint32_t cluster,uint32_t *n)
{
 int r;if(cluster<2||cluster>c->volume.last_data_cluster)return FC_CORRUPT;
 r=fatread(c,cluster/128);if(r)return r;
 *n=le32(c->sector+(cluster%128)*4)&EOC;
 if(*n>=0x0ffffff8u)return 0;
 if(*n<2||*n>c->volume.last_data_cluster||*n==cluster)return FC_CORRUPT;
 return 0;
}
static uint32_t data(fatcam_t *c,uint32_t cluster)
{return c->volume.data_lba+(cluster-2)*c->volume.sectors_per_cluster;}
static int clean(fatcam_t *c,int value)
{
 uint32_t v;int r=fatread(c,0);
 if(r==FC_CORRUPT&&c->cleanup)r=read1(c,fatbase(c,c->volume.active_fat),c->sector);
 if(r)return r;
 v=le32(c->sector+4);put32(c->sector+4,value?v|CLEAN:v&~CLEAN);
 if(!value)c->dirty=1; /* Even an uncertain first write requires rollback. */
 r=fatwrite(c,0);if(!r&&value)c->dirty=0;
 return r;
}
static int fsinfo_unknown(fatcam_t *c,uint32_t lba)
{
 int r;if(!lba)return 0;r=read1(c,lba,c->sector);if(r)return r;
 if(le32(c->sector)!=0x41615252u||le32(c->sector+484)!=0x61417272u||le32(c->sector+508)!=0xaa550000u)return 0;
 put32(c->sector+488,0xffffffffu);put32(c->sector+492,0xffffffffu);
 return write1(c,lba,c->sector);
}
static int start_mutation(fatcam_t *c)
{
 int r=clean(c,0);if(r)return r;
 r=fsinfo_unknown(c,c->fsinfo);if(r)return r;
 return fsinfo_unknown(c,c->backup_fsinfo);
}
int fatcam_open(fatcam_t *c,fat_ro_read_sectors_fn rd,fatcam_write_fn wr,void *user,
                uint32_t sectors,uint32_t *work,fatcam_poll_fn p)
{
 uint16_t flags,res,info,backup;int r;
 if(!c||!rd||!wr||!work||!sectors)return FC_FS;
 memset(c,0,sizeof(*c));c->write=wr;c->user=user;c->poll=p;c->clusters=work;
 if(fat_ro_mount(&c->volume,rd,user,sectors)||c->volume.fat_type!=32||c->volume.fat_count>2)return FC_FS;
 r=read1(c,c->volume.partition_lba,c->sector);if(r)return r;
 flags=le16(c->sector+40);c->mirrored=(flags&0x80)==0;
 res=le16(c->sector+14);info=le16(c->sector+48);backup=le16(c->sector+50);
 if(info&&info<res)c->fsinfo=c->volume.partition_lba+info;
 if(info&&backup&&backup!=0xffffu&&(uint32_t)backup+info<res)c->backup_fsinfo=c->volume.partition_lba+backup+info;
 r=fatread(c,0);if(r)return r;
 if((le32(c->sector+4)&(CLEAN|NO_ERROR))!=(CLEAN|NO_ERROR))return FC_REPAIR;
 return 0;
}
static uint32_t entry_cluster(const uint8_t *e){return ((uint32_t)le16(e+20)<<16)|le16(e+26);}
static void entry(uint8_t *e,const char name[11],uint8_t attr,uint32_t cluster,uint32_t length)
{
 memset(e,0,32);memcpy(e,name,11);e[11]=attr;
 put16(e+16,0x0021);put16(e+18,0x0021);put16(e+24,0x0021); /* No RTC: FAT epoch. */
 put16(e+20,(uint16_t)(cluster>>16));put16(e+26,(uint16_t)cluster);put32(e+28,length);
}
/* Collect free clusters in ascending order, checking mirrored FATs. No writes
 * occur until the complete list exists, so a full card is a clean failure. */
static int allocate(fatcam_t *c,uint32_t count)
{
 uint32_t cluster=2,idx=0xffffffffu,v;int r;
 c->allocated=0;if(count>FATCAM_MAX_CLUSTERS)return FC_FULL;
 for(;cluster<=c->volume.last_data_cluster&&c->allocated<count;cluster++){
  if(idx!=cluster/128){idx=cluster/128;r=fatread(c,idx);if(r)return r;}
  v=le32(c->sector+(cluster%128)*4)&EOC;
  if(v==0)c->clusters[c->allocated++]=cluster;
 }
 return c->allocated==count?0:FC_FULL;
}
/* Batch regular entries by FAT sector. All indices are previously validated
 * free clusters owned by this transaction; preserve the reserved high nibble. */
static int links(fatcam_t *c,int release)
{
 uint32_t i=0,j,idx,v,end0=c->file[0].count;int r;
 while(i<c->allocated){
  idx=c->clusters[i]/128;r=fatread(c,idx);
  /* A partial mirror write can leave this sector mismatched. During rollback,
   * start from the active copy and repair only our formerly free entries. */
  if(r==FC_CORRUPT&&c->cleanup)r=read1(c,fatbase(c,c->volume.active_fat)+idx,c->sector);
  if(r)return r;
  for(j=i;j<c->allocated&&c->clusters[j]/128==idx;j++){
   uint8_t *e=c->sector+(c->clusters[j]%128)*4;
   v=release?0:((j+1==end0||j+1==c->allocated)?EOC:c->clusters[j+1]);
   put32(e,(le32(e)&0xf0000000u)|v);
  }
  r=fatwrite(c,idx);if(r)return r;i=j;
 }
 return 0;
}
static int root_slot(fatcam_t *c,uint32_t *lba,unsigned *off)
{
 uint32_t cluster=c->volume.root_cluster,n,hops=0,s;unsigned i;int r;int free_found=0;
 while(hops++<c->volume.cluster_count){
  for(s=0;s<c->volume.sectors_per_cluster;s++){
   r=read1(c,data(c,cluster)+s,c->sector);if(r)return r;
   for(i=0;i<512;i+=32){
    uint8_t *e=c->sector+i;
    if((e[0]==0||e[0]==0xe5)&&!free_found){*lba=data(c,cluster)+s;*off=i;free_found=1;}
    if(e[0]==0)return free_found?0:FC_FULL;
    if(e[0]!=0xe5&&e[11]!=0x0f&&!memcmp(e,"VOICE      ",11)){
     if(!(e[11]&0x10)||e[11]&0x08)return FC_CORRUPT;
     c->dir_cluster=entry_cluster(e);
     if(c->dir_cluster==c->volume.root_cluster)return FC_CORRUPT;
     return next(c,c->dir_cluster,&n);
    }
   }
  }
  r=next(c,cluster,&n);if(r)return r;if(n>=0x0ffffff8u)return free_found?0:FC_FULL;cluster=n;
 }
 return FC_CORRUPT;
}
static int create_directory(fatcam_t *c,uint32_t root_lba,unsigned off)
{
 uint32_t cluster,s;int r;
 r=allocate(c,1);if(r)return r;c->file[0].count=1;
 r=start_mutation(c);if(r)return r;
 r=links(c,0);if(r)return r;cluster=c->clusters[0];
 for(s=0;s<c->volume.sectors_per_cluster;s++){
  memset(c->sector,0,512);
  if(s==0){entry(c->sector,".          ",0x10,cluster,0);
   entry(c->sector+32,"..         ",0x10,0,0);}
  r=write1(c,data(c,cluster)+s,c->sector);if(r)return r;
 }
 r=read1(c,root_lba,c->original);if(r)return r;
 c->dir_lba=root_lba;c->dir_offset=(uint16_t)off;c->staged=1;
 memcpy(c->sector,c->original,512);
 if(c->sector[off]==0)memset(c->sector+off,0,512-off);
 entry(c->sector+off,"VOICE      ",0x10,cluster,0);
 r=write1(c,root_lba,c->sector);if(r)return r;
 r=clean(c,1);if(r)return r;
 c->dir_cluster=cluster;c->allocated=0;c->staged=0;c->file[0].count=0;
 return 0;
}
static uint32_t name_id(const uint8_t *e)
{
 unsigned i;uint32_t n=0;
 if((memcmp(e,"REC",3)&&memcmp(e,"JSN",3))||e[0]==0xe5)return 0;
 for(i=3;i<8;i++){if(e[i]<'0'||e[i]>'9')return 0;n=n*10+(e[i]-'0');}
 return n;
}
static uint32_t lfn_id(const uint8_t *e)
{
 static const uint8_t pos[13]={1,3,5,7,9,14,16,18,20,22,24,28,30};
 uint8_t name[14];unsigned i;
 if(e[11]!=0x0f||(e[0]&0x1f)!=1)return 0;
 for(i=0;i<13;i++){if(e[pos[i]+1])return 0;name[i]=e[pos[i]];}
 name[13]=0;
 if(memcmp(name+8,".JSON",5)&&memcmp(name+8,".WAV",4)&&memcmp(name+8,".TMP",4))return 0;
 return name_id(name);
}
static void shortname(uint32_t id,char name[11],const char *prefix,const char *ext)
{
 int i;memcpy(name,prefix,3);memcpy(name+8,ext,3);
 for(i=7;i>=3;i--){name[i]=(char)('0'+id%10);id/=10;}
}
void fatcam_name(uint32_t id,char name[13])
{char s[11];shortname(id,s,"REC","WAV");memcpy(name,s,8);name[8]='.';memcpy(name+9,s+8,3);name[12]=0;}
static int directory_slots(fatcam_t *c)
{
 uint32_t cluster=c->dir_cluster,n,hops=0,s,maxid=0,found_lba=0,last=cluster;
 unsigned i,run,found_off=0;int r,ended=0;
 while(hops++<c->volume.cluster_count){
  last=cluster;
  for(s=0;s<c->volume.sectors_per_cluster;s++){
   r=read1(c,data(c,cluster)+s,c->sector);if(r)return r;run=0;
   for(i=0;i<512;i+=32){
    uint8_t *e=c->sector+i;uint32_t id;
    if(!e[0])ended=1;
    if(ended||e[0]==0xe5){run++;if(run==3&&!found_lba){found_lba=data(c,cluster)+s;found_off=i-64;}}
    else{run=0;id=e[11]==0x0f?lfn_id(e):name_id(e);if(id>maxid)maxid=id;}
   }
  }
  r=next(c,cluster,&n);if(r)return r;
  if(n>=0x0ffffff8u)break;
  cluster=n;
 }
 if(hops>c->volume.cluster_count||maxid>=99999)return FC_FULL;
 if(!found_lba){
  /* Grow only VOICE. A new zeroed cluster is linked before it can hold files. */
  uint32_t idx;uint8_t *e;
  r=allocate(c,1);if(r)return r;c->file[0].count=1;
  r=start_mutation(c);if(r)return r;r=links(c,0);if(r)return r;
  for(s=0;s<c->volume.sectors_per_cluster;s++){memset(c->sector,0,512);r=write1(c,data(c,c->clusters[0])+s,c->sector);if(r)return r;}
  idx=last/128;r=fatread(c,idx);if(r)return r;e=c->sector+(last%128)*4;
  put32(e,(le32(e)&0xf0000000u)|c->clusters[0]);
  r=fatwrite(c,idx);if(r){/* An uncertain link must not free its target. */c->unsafe=1;return FC_REPAIR;}
  found_lba=data(c,c->clusters[0]);c->allocated=0;c->file[0].count=0;
  r=clean(c,1);if(r)return r;
 }
 c->id=maxid+1;c->dir_lba=found_lba;c->dir_offset=(uint16_t)found_off;
 return read1(c,found_lba,c->original);
}
/* When a directory grows, its old0x00 terminator must advance past all prior
 * padding slots. Otherwise Windows stops before the new cluster. Only VOICE
 * directory padding is changed; no existing live entry is altered. */
static int advance_end(fatcam_t *c)
{
 uint32_t cluster=c->dir_cluster,s,n,hops=0;unsigned i;int ended=0,r,changed;
 while(hops++<c->volume.cluster_count){
  for(s=0;s<c->volume.sectors_per_cluster;s++){
   uint32_t lba=data(c,cluster)+s;
   r=read1(c,lba,c->sector);if(r)return r;changed=0;
   for(i=0;i<512;i+=32){
    if(!c->sector[i])ended=1;
    if(lba==c->dir_lba&&i==c->dir_offset){
     if(ended)memset(c->sector+i,0,512-i);
     memcpy(c->original,c->sector,512);return 0;
    }
    if(ended){memset(c->sector+i,0,32);c->sector[i]=0xe5;changed=1;}
   }
   if(changed){r=write1(c,lba,c->sector);if(r)return r;}
  }
  r=next(c,cluster,&n);if(r)return r;if(n>=0x0ffffff8u)return FC_CORRUPT;cluster=n;
 }
 return FC_CORRUPT;
}
int fatcam_begin(fatcam_t *c,uint32_t wav_length,uint32_t json_length)
{
 uint32_t root_lba=0,bytes=c->volume.cluster_size_bytes;unsigned off=0,f;int r;char name[11];
 if(!wav_length||!json_length||c->dirty||c->staged)return FC_CORRUPT;
 r=root_slot(c,&root_lba,&off);if(r)return r;
 if(!c->dir_cluster){r=create_directory(c,root_lba,off);if(r)return r;}
 r=read1(c,data(c,c->dir_cluster),c->sector);if(r)return r;
 if(memcmp(c->sector,".          ",11)||c->sector[11]!=0x10||entry_cluster(c->sector)!=c->dir_cluster||
    memcmp(c->sector+32,"..         ",11)||c->sector[43]!=0x10||
    (entry_cluster(c->sector+32)!=0&&entry_cluster(c->sector+32)!=c->volume.root_cluster))return FC_CORRUPT;
 r=directory_slots(c);if(r)return r;
 memset(c->file,0,sizeof(c->file));
 c->file[0].length=wav_length;c->file[1].length=json_length;
 for(f=0;f<2;f++){c->file[f].count=(c->file[f].length-1)/bytes+1;c->file[f].crc=0xffffffffu;}
 c->file[1].first=c->file[0].count;
 r=allocate(c,c->file[0].count+c->file[1].count);if(r){c->allocated=0;return r;}
 r=start_mutation(c);if(r)return r;
 r=advance_end(c);if(r)return r;
 r=links(c,0);if(r)return r;
 memcpy(c->sector,c->original,512);
 if(c->sector[c->dir_offset]==0)memset(c->sector+c->dir_offset,0,512-c->dir_offset);
 shortname(c->id,name,"REC","TMP");entry(c->sector+c->dir_offset,name,0x02,c->clusters[0],0);
 c->sector[c->dir_offset+32]=0xe5;
 shortname(c->id,name,"JSN","TMP");entry(c->sector+c->dir_offset+64,name,0x02,c->clusters[c->file[1].first],0);
 c->staged=1;return write1(c,c->dir_lba,c->sector);
}
static uint32_t file_lba(fatcam_t *c,fatcam_file_t *f,uint32_t offset)
{return data(c,c->clusters[f->first+offset/c->volume.cluster_size_bytes])+(offset%c->volume.cluster_size_bytes)/512;}
int fatcam_set_batch(fatcam_t *c,fatcam_batch_write_fn wr,uint8_t *buffer,uint32_t sectors)
{
 if(!c||c->staged||c->dirty||!wr||!buffer||((uintptr_t)buffer&3u)||!sectors||sectors>32u)return FC_CORRUPT;
 c->batch_write=wr;c->batch_buffer=buffer;c->batch_capacity=(uint8_t)sectors;c->batch_blocks=0;
 return 0;
}
static int flush_batch(fatcam_t *c)
{
 int r;if(!c->batch_blocks)return 0;
 r=poll(c);if(r)return r;
 r=c->batch_write(c->user,c->batch_lba,c->batch_blocks,c->batch_buffer);
 if(r)return r;
 c->batch_blocks=0;return 0;
}
static int write_data(fatcam_t *c,unsigned index,uint32_t lba,const uint8_t *b)
{
 int r;
 if(!c->batch_write){r=poll(c);if(r)return r;return c->write(c->user,lba,b)?FC_IO:0;}
 /* Never span a fragmented chain or interleave different file streams. */
 if(c->batch_blocks&&(c->batch_file!=index||lba!=c->batch_lba+c->batch_blocks)){
  r=flush_batch(c);if(r)return r;
 }
 if(!c->batch_blocks){c->batch_lba=lba;c->batch_file=(uint8_t)index;}
 copy_data(c->batch_buffer+(uint32_t)c->batch_blocks*512u,b,512u);c->batch_blocks++;
 return c->batch_blocks==c->batch_capacity?flush_batch(c):0;
}
int fatcam_write(fatcam_t *c,unsigned index,const uint8_t *b,uint32_t count)
{
 fatcam_file_t *f;uint32_t n;int r;
 if(index>1||!c->staged)return FC_CORRUPT;
 f=&c->file[index];
 if(count>f->length-f->done)return FC_CORRUPT;
 f->verified=0;
 while(count){
  n=512-f->used;if(n>count)n=count;copy_data(f->sector+f->used,b,n);
  f->crc=crc32_fast(f->crc,b,n);f->used=(uint16_t)(f->used+n);f->done+=n;b+=n;count-=n;
  if(f->used==512){
   r=write_data(c,index,file_lba(c,f,f->done-512),f->sector);if(r)return r;
   f->used=0;
  }
 }
 return 0;
}
int fatcam_finish(fatcam_t *c,unsigned index,uint32_t expected_crc)
{
 uint8_t buffer[8u*512u];
 fatcam_file_t *f;uint32_t off,n,crc=0xffffffffu,k,v,lba,blocks;int r;
 if(index>1)return FC_CORRUPT;
 f=&c->file[index];
 if(f->done!=f->length||(f->crc^0xffffffffu)!=expected_crc)return FC_CORRUPT;
 r=flush_batch(c);if(r)return r;
 if(f->used){memset(f->sector+f->used,0,512-f->used);r=write1(c,file_lba(c,f,f->done-f->used),f->sector);if(r)return r;f->used=0;}
 for(k=0;k<f->count;k++){
  r=next(c,c->clusters[f->first+k],&v);if(r)return r;
  if(v!=(k+1==f->count?EOC:c->clusters[f->first+k+1]))return FC_CORRUPT;
 }
 for(off=0;off<f->length;off+=n){
  lba=file_lba(c,f,off);blocks=(f->length-off+511u)/512u;
  if(blocks>8u)blocks=8u;
  for(k=1;k<blocks;k++)if(file_lba(c,f,off+k*512u)!=lba+k)break;
  blocks=k;r=poll(c);if(r)return r;
  if(lba<c->volume.partition_lba||lba-c->volume.partition_lba>=c->volume.total_sectors||
     blocks>c->volume.total_sectors-(lba-c->volume.partition_lba))return FC_CORRUPT;
  if(c->volume.read_sectors(c->user,lba,blocks,buffer))return FC_IO;
  n=f->length-off;if(n>blocks*512u)n=blocks*512u;crc=crc32_fast(crc,buffer,n);
 }
 if((crc^0xffffffffu)!=expected_crc)return FC_IO;
 f->verified=1;return 0;
}
int fatcam_commit(fatcam_t *c)
{
 static const uint8_t pos[13]={1,3,5,7,9,14,16,18,20,22,24,28,30};
 char name[11],longname[13];uint8_t sum=0,*e;unsigned i;int r;
 if(!c->staged||!c->file[0].verified||!c->file[1].verified)return FC_CORRUPT;
 memcpy(c->sector,c->original,512);
 if(c->sector[c->dir_offset]==0)memset(c->sector+c->dir_offset,0,512-c->dir_offset);
 shortname(c->id,name,"REC","WAV");entry(c->sector+c->dir_offset,name,0x20,c->clusters[0],c->file[0].length);
 shortname(c->id,name,"REC","JSN");entry(c->sector+c->dir_offset+64,name,0x20,c->clusters[c->file[1].first],c->file[1].length);
 for(i=0;i<11;i++)sum=(uint8_t)(((sum&1)?0x80:0)+(sum>>1)+(uint8_t)name[i]);
 memcpy(longname,name,8);memcpy(longname+8,".JSON",5);
 e=c->sector+c->dir_offset+32;memset(e,0,32);e[0]=0x41;e[11]=0x0f;e[13]=sum;
 for(i=0;i<13;i++)put16(e+pos[i],(uint8_t)longname[i]);
 c->published=1;r=write1(c,c->dir_lba,c->sector);if(r)return r;
 r=clean(c,1);if(r)return r;
 c->allocated=0;c->staged=0;c->published=0;return 0;
}
int fatcam_abort(fatcam_t *c)
{
 int r=0;c->cleanup=1;c->batch_blocks=0;
 if(c->unsafe)return FC_REPAIR;
 /* Unpublish first, then free owned chains. Never expose a freed final file. */
 if(c->staged){r=write1(c,c->dir_lba,c->original);if(r)return FC_REPAIR;c->staged=0;c->published=0;}
 if(c->allocated&&c->dirty){r=links(c,1);if(r)return FC_REPAIR;c->allocated=0;}
 if(c->dirty){r=clean(c,1);if(r)return FC_REPAIR;}
 c->cleanup=0;return 0;
}
const char *fatcam_error(int r)
{
 switch(r){case FC_CANCEL:return "CANCELLED";case FC_IO:return "SD I/O";case FC_FS:return "SDHC FAT32 REQUIRED";
 case FC_FULL:return "CARD/DIRECTORY FULL";case FC_REPAIR:return "FAT REPAIR REQUIRED";case FC_TIMEOUT:return "TIMEOUT";
 default:return "FAT CORRUPT";}
}
