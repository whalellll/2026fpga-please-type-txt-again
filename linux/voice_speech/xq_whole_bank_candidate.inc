#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include "xq_whole_bank.h"
#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error Whole_bank_transport_requires_little_endian_CPU
#endif
#define HEADER_BYTES 128u
#define RECORD_BYTES 16u
#define CONFIG_BYTES 96u
#define INDEX_BYTES (XQ_WHOLE_BANK_ENTRIES*RECORD_BYTES)
#define META_BYTES (HEADER_BYTES+INDEX_BYTES)
#define DATA_OFFSET ((META_BYTES+4095u)&~4095u)
static uint8_t *metadata;
static uint32_t bank_bytes,bank_span;
static uint32_t crc_table[256];
static int crc_ready;
static uint32_t le32(const uint8_t *p)
{return(uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static uint32_t be32(const uint8_t *p)
{return((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];}
static void put32(uint8_t *p,uint32_t v)
{for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static uint32_t crc32(const uint8_t *p,size_t n)
{
    if(!crc_ready){
        for(unsigned i=0;i<256;i++){uint32_t v=i;for(unsigned j=0;j<8;j++)v=(v>>1)^((0u-(v&1u))&0xedb88320u);crc_table[i]=v;}
        crc_ready=1;
    }
    uint32_t c=UINT32_MAX;
    while(n--)c=crc_table[(c^*p++)&255u]^(c>>8);
    return~c;
}
static int zeros(const uint8_t *p,unsigned n)
{for(unsigned i=0;i<n;i++)if(p[i])return 0;return 1;}
static int key_valid(const uint8_t *t)
{
    int piece=t[0]>=16 && t[0]<=24 && t[1]>=1 && t[1]<=9;
    int disambiguated=((t[0]>=1 && t[0]<=9)||(t[0]>=28 && t[0]<=30)) && t[1]>=16 && t[1]<=24;
    return (piece || disambiguated) && t[2]>=25 && t[2]<=27 && t[3]>=1 && t[3]<=9;
}
/* Exact-length reads cover sysfs properties too; no buffered/file-size guess.
 * An existing bad/short/trailing descriptor is never treated as absent. */
static int read_exact_file(const char *path,uint8_t *out,unsigned bytes,int absent_allowed)
{
    int fd=open(path,O_RDONLY|O_CLOEXEC),okay=1;
    if(fd<0)return absent_allowed && errno==ENOENT?0:-1;
    unsigned used=0;
    while(used<bytes){
        ssize_t n=read(fd,out+used,bytes-used);
        if(n<0 && errno==EINTR)continue;
        if(n<=0){okay=0;break;}
        used+=(unsigned)n;
    }
    if(okay){uint8_t tail;ssize_t n;
        do{n=read(fd,&tail,1);}while(n<0 && errno==EINTR);
        if(n!=0)okay=0;
    }
    if(close(fd))okay=0;
    return okay?1:-1;
}
void xq_whole_bank_release(void)
{free(metadata);metadata=NULL;bank_bytes=bank_span=0;}
int xq_whole_bank_prepare(const char *directory)
{
    uint8_t cfg[CONFIG_BYTES],reg[8],empty=0;char path[512];
    int fd=-1,result=-1;void *map=MAP_FAILED;uint8_t *copy=NULL;
    xq_whole_bank_release();
    if(!directory || !*directory)return -1;
    int used=snprintf(path,sizeof(path),"%s/%s",directory,XQ_WHOLE_BANK_CONFIG_NAME);
    if(used<0 || (unsigned)used>=sizeof(path))return -1;
    int found=read_exact_file(path,cfg,sizeof(cfg),1);if(found<=0)return found;
    if(memcmp(cfg,"XQWBCFG1",8) || le32(cfg+8)!=1 || le32(cfg+12)!=XQ_WHOLE_BANK_BASE ||
       le32(cfg+28)!=XQ_WHOLE_BANK_ENTRIES || !zeros(cfg+68,28) || zeros(cfg+32,32))return -1;
    uint32_t expected=le32(cfg+24),span=le32(cfg+16),bytes=le32(cfg+20),cfg_crc=le32(cfg+64);
    put32(cfg+64,0);
    if(crc32(cfg,sizeof(cfg))!=cfg_crc || bytes<DATA_OFFSET+XQ_WHOLE_BANK_ENTRIES*4u ||
       bytes>UINT32_MAX-4095u || span!=((bytes+4095u)&~4095u) ||
       span>=XQ_WHOLE_BANK_LIMIT-XQ_WHOLE_BANK_BASE)return -1;
    /* Authenticate the exact boot reservation before opening /dev/mem. */
    if(read_exact_file(XQ_WHOLE_BANK_DT_NODE "/reg",reg,8,0)!=1 ||
       be32(reg)!=XQ_WHOLE_BANK_BASE || be32(reg+4)!=span ||
       read_exact_file(XQ_WHOLE_BANK_DT_NODE "/no-map",&empty,0,0)!=1)return -1;
    copy=malloc(DATA_OFFSET);if(!copy)return -1;
    fd=open("/dev/mem",O_RDONLY|O_SYNC|O_CLOEXEC);if(fd<0)goto done;
    map=mmap(NULL,DATA_OFFSET,PROT_READ,MAP_SHARED,fd,(off_t)XQ_WHOLE_BANK_BASE);
    if(map==MAP_FAILED)goto done;
    /* These are immutable DDR bytes, using aligned volatile word loads. */
    for(unsigned i=0;i<DATA_OFFSET/4;i++){
        uint32_t word=((volatile const uint32_t *)map)[i];memcpy(copy+i*4,&word,4);
    }
    if(munmap(map,DATA_OFFSET))goto done;
    map=MAP_FAILED;
    if(close(fd)){fd=-1;goto done;}fd=-1;
    if(memcmp(copy,"XQWBANK1",8) || le32(copy+8)!=1 || le32(copy+12)!=HEADER_BYTES ||
       le32(copy+16)!=16000 || le32(copy+20)!=1 || le32(copy+24)!=1 ||
       le32(copy+28)!=XQ_WHOLE_BANK_ENTRIES || le32(copy+32)!=HEADER_BYTES ||
       le32(copy+36)!=RECORD_BYTES || le32(copy+40)!=DATA_OFFSET || le32(copy+44)!=bytes ||
       le32(copy+52)!=expected || memcmp(copy+56,cfg+32,32) || !zeros(copy+88,40) ||
       !zeros(copy+META_BYTES,DATA_OFFSET-META_BYTES))goto done;
    if(crc32(copy+HEADER_BYTES,INDEX_BYTES)!=le32(copy+48))goto done;
    put32(copy+52,0);
    if(crc32(copy,META_BYTES)!=expected)goto done;
    put32(copy+52,expected);
    uint32_t end=DATA_OFFSET;
    for(unsigned i=0;i<XQ_WHOLE_BANK_ENTRIES;i++){
        uint8_t *r=copy+HEADER_BYTES+i*RECORD_BYTES;
        uint32_t offset=le32(r+4),length=le32(r+8);
        if(!key_valid(r) || (i && memcmp(r-RECORD_BYTES,r,4)>=0) ||
           offset!=end || !length || (length&1u) || length>XQ_WHOLE_BANK_MAX_SAMPLES*2u ||
           offset>bytes || length>bytes-offset)goto done;
        end=offset+length;if(end>UINT32_MAX-3u)goto done;end=(end+3u)&~3u;
    }
    if(end!=bytes)goto done;
    metadata=copy;copy=NULL;bank_bytes=bytes;bank_span=span;result=1;
done:
    if(map!=MAP_FAILED)(void)munmap(map,DATA_OFFSET);
    if(fd>=0)(void)close(fd);
    free(copy);return result;
}
static int load_complete(const uint8_t tokens[4],int16_t *destination,unsigned capacity,
                         int16_t **allocated,unsigned *count)
{
    if(!count)return -1;
    *count=0;if(allocated)*allocated=NULL;
    if(!tokens || !key_valid(tokens))return -1;
    if(!metadata)return 0;
    unsigned lo=0,hi=XQ_WHOLE_BANK_ENTRIES;
    while(lo<hi){unsigned mid=lo+(hi-lo)/2;int c=memcmp(tokens,metadata+HEADER_BYTES+mid*RECORD_BYTES,4);if(c>0)lo=mid+1;else hi=mid;}
    if(lo==XQ_WHOLE_BANK_ENTRIES)return 0;
    const uint8_t *r=metadata+HEADER_BYTES+lo*RECORD_BYTES;if(memcmp(tokens,r,4))return 0;
    uint32_t offset=le32(r+4),length=le32(r+8),wanted_crc=le32(r+12);
    if(!length || (length&1u) || length>XQ_WHOLE_BANK_MAX_SAMPLES*2u || offset>bank_bytes || length>bank_bytes-offset)return -1;
    if(destination && capacity<length/2)return -1;
    uint32_t padded=(length+3u)&~3u,map_bytes=0;
    int fd=-1,result=-1;void *map=MAP_FAILED;int16_t *out=destination?destination:malloc(length);
    if(!out)return -1;
    fd=open("/dev/mem",O_RDONLY|O_SYNC|O_CLOEXEC);if(fd<0)goto done;
    for(uint32_t copied=0;copied<padded;){
        uint32_t absolute=offset+copied,page=absolute&~4095u,in_page=absolute-page;
        uint32_t take=padded-copied;
        if(take>32768u-in_page)take=32768u-in_page;
        map_bytes=(in_page+take+4095u)&~4095u;
        if(page>bank_span || map_bytes>bank_span-page)goto done;
        map=mmap(NULL,map_bytes,PROT_READ,MAP_SHARED,fd,(off_t)XQ_WHOLE_BANK_BASE+page);
        if(map==MAP_FAILED)goto done;
        const volatile uint32_t *source=(const volatile uint32_t *)((const uint8_t *)map+in_page);
        for(unsigned i=0;i<take/4;i++){
            uint32_t v=source[i];unsigned a=v&65535u,b=v>>16,at=copied/2+i*2;
            if(at<length/2)out[at]=(int16_t)(a<32768u?(int)a:(int)a-65536);
            if(at+1<length/2)out[at+1]=(int16_t)(b<32768u?(int)b:(int)b-65536);
        }
        if(munmap(map,map_bytes))goto done;
        map=MAP_FAILED;
        copied+=take;
    }
    if(close(fd)){fd=-1;goto done;}fd=-1;
    if(crc32((const uint8_t *)out,length)!=wanted_crc)goto done;
    if(allocated)*allocated=out;
    *count=length/2;out=NULL;result=1;
done:
    if(map!=MAP_FAILED)(void)munmap(map,map_bytes);
    if(fd>=0)(void)close(fd);
    if(!destination)free(out);
    return result;
}
int xq_whole_bank_load(const uint8_t tokens[4],int16_t **samples,unsigned *count)
{
    if(!samples || !count)return -1;
    return load_complete(tokens,NULL,0,samples,count);
}
int xq_whole_bank_load_into(const uint8_t tokens[4],int16_t *samples,unsigned capacity,unsigned *count)
{
    if(!samples){if(count)*count=0;return -1;}
    return load_complete(tokens,samples,capacity,NULL,count);
}
