/* All file/device/map/allocation operations of the real reader are explicit
 * link-time mocks. No test branches or transport hooks enter deployment. */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include "xq_whole_bank.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#define META_END (128u+5103u*16u)
#define DATA_AT 81920u
static uint8_t bank[1048576],cfg[96],reg[9],nomap[1];
static unsigned length[16],position[16],opened[16],live_fds,live_maps,allocations;
static unsigned phase,map_calls,max_clip_map,mem_opens,checks;
static int missing_cfg,missing_reg,missing_nomap,fail_read,fail_map,fail_mem,fail_malloc,fail_close,fail_unmap;
static void *mapped;static size_t mapped_length;
void *__real_malloc(size_t);void __real_free(void *);
int __real_munmap(void *,size_t);
static uint32_t le(const uint8_t *p){return(uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void put(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(8*i));}
static void big(uint8_t *p,uint32_t v){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(v>>(24-8*i));}
static uint32_t crc(const uint8_t *p,unsigned n){uint32_t c=UINT32_MAX;while(n--){c^=*p++;for(unsigned j=0;j<8;j++)c=(c>>1)^((0u-(c&1u))&0xedb88320u);}return~c;}
static int key(unsigned a,unsigned b){return(a>=16 && a<=24 && b>=1 && b<=9)||(((a>=1 && a<=9)||(a>=28 && a<=30))&&b>=16 && b<=24);}
static void bind_crc(void)
{
    put(bank+48,crc(bank+128,5103*16));put(bank+52,0);put(bank+52,crc(bank,META_END));
    put(cfg+24,le(bank+52));put(cfg+64,0);put(cfg+64,crc(cfg,96));
}
static void clean(void){assert(live_fds==0 && live_maps==0);}
static void fixture(unsigned last_length)
{
    xq_whole_bank_release();clean();assert(allocations==0);
    memset(bank,0,sizeof(bank));memset(cfg,0,sizeof(cfg));memset(reg,0,sizeof(reg));
    memset(opened,0,sizeof(opened));memset(position,0,sizeof(position));
    missing_cfg=missing_reg=missing_nomap=fail_read=fail_map=fail_mem=fail_malloc=fail_close=fail_unmap=0;
    phase=0;map_calls=max_clip_map=mem_opens=0;length[10]=96;length[11]=8;length[12]=0;
    memcpy(bank,"XQWBANK1",8);put(bank+8,1);put(bank+12,128);put(bank+16,16000);put(bank+20,1);put(bank+24,1);
    put(bank+28,5103);put(bank+32,128);put(bank+36,16);put(bank+40,DATA_AT);memset(bank+56,0x5a,32);
    unsigned index=0,at=DATA_AT;
    for(unsigned a=1;a<=30;a++)for(unsigned b=1;b<=24;b++)if(key(a,b))for(unsigned action=25;action<=27;action++)for(unsigned target=1;target<=9;target++){
        unsigned n=index==5102?last_length:2;uint8_t *r=bank+128+16*index;
        r[0]=(uint8_t)a;r[1]=(uint8_t)b;r[2]=(uint8_t)action;r[3]=(uint8_t)target;put(r+4,at);put(r+8,n);
        for(unsigned j=0;j<n/2;j++){unsigned v=(index*19u+j*7993u+257u)&65535u;bank[at+j*2]=(uint8_t)v;bank[at+j*2+1]=(uint8_t)(v>>8);}
        put(r+12,crc(bank+at,n));at=(at+n+3u)&~3u;index++;
    }
    assert(index==5103);put(bank+44,at);
    memcpy(cfg,"XQWBCFG1",8);put(cfg+8,1);put(cfg+12,XQ_WHOLE_BANK_BASE);put(cfg+16,(at+4095u)&~4095u);put(cfg+20,at);put(cfg+28,5103);memcpy(cfg+32,bank+56,32);
    big(reg,XQ_WHOLE_BANK_BASE);big(reg+4,le(cfg+16));bind_crc();
}
int __wrap_open(const char *path,int flags,...)
{
    assert((flags&O_ACCMODE)==O_RDONLY);int fd;
    if(!strcmp(path,"/fixture/whole-bank.cfg")){if(missing_cfg){errno=ENOENT;return -1;}fd=10;}
    else if(!strcmp(path,XQ_WHOLE_BANK_DT_NODE "/reg")){if(missing_reg){errno=ENOENT;return -1;}fd=11;}
    else if(!strcmp(path,XQ_WHOLE_BANK_DT_NODE "/no-map")){if(missing_nomap){errno=ENOENT;return -1;}fd=12;}
    else {assert(!strcmp(path,"/dev/mem"));mem_opens++;if(fail_mem){errno=EIO;return -1;}fd=13;}
    assert(!opened[fd]);opened[fd]=1;position[fd]=0;live_fds++;return fd;
}
int __wrap_open64(const char *path,int flags,...){return __wrap_open(path,flags);}
ssize_t __wrap_read(int fd,void *out,size_t count)
{
    assert(fd>=10 && fd<=12 && opened[fd]);
    if(fail_read==fd){errno=EIO;return -1;}
    unsigned left=length[fd]-position[fd];if(count>left)count=left;
    const uint8_t *source=fd==10?cfg:fd==11?reg:nomap;
    memcpy(out,source+position[fd],count);position[fd]+=(unsigned)count;return(ssize_t)count;
}
ssize_t __wrap___read_chk(int fd,void *out,size_t count,size_t capacity)
{assert(count<=capacity);return __wrap_read(fd,out,count);}
int __wrap_close(int fd)
{
    assert(fd>=10 && fd<=13 && opened[fd]);opened[fd]=0;live_fds--;
    if(fail_close==fd){fail_close=0;errno=EIO;return -1;}return 0;
}
void *__wrap_mmap(void *address,size_t bytes,int prot,int flags,int fd,off_t offset)
{
    assert(!address && prot==PROT_READ && flags==MAP_SHARED && fd==13 && opened[fd]);
    assert(!live_maps && position[11]==8 && length[12]==0);
    assert(offset>=XQ_WHOLE_BANK_BASE && !((uint64_t)offset&4095u));
    assert(bytes && !(bytes&4095u) && (uint64_t)offset-XQ_WHOLE_BANK_BASE+bytes<=le(cfg+16));
    if(phase==1)assert(offset==XQ_WHOLE_BANK_BASE && bytes==DATA_AT);
    else {assert(phase==2 && bytes<=32768);if(bytes>max_clip_map)max_clip_map=(unsigned)bytes;}
    map_calls++;if(fail_map){fail_map=0;errno=EIO;return MAP_FAILED;}
    mapped=bank+((uint64_t)offset-XQ_WHOLE_BANK_BASE);mapped_length=bytes;live_maps=1;return mapped;
}
void *__wrap_mmap64(void *p,size_t n,int prot,int flags,int fd,int64_t at)
{return __wrap_mmap(p,n,prot,flags,fd,(off_t)at);}
int __wrap_munmap(void *p,size_t bytes)
{
    /* Static musl uses the public symbol when releasing its own malloc VMAs.
     * Only our synthetic physical-bank addresses belong to this mock. */
    if((uintptr_t)p<(uintptr_t)bank || (uintptr_t)p>=(uintptr_t)bank+sizeof(bank))return __real_munmap(p,bytes);
    assert(live_maps==1 && p==mapped && bytes==mapped_length);
    if(fail_unmap){fail_unmap=0;errno=EIO;return -1;}
    live_maps=0;return 0;
}
void *__wrap_malloc(size_t n){if(fail_malloc){fail_malloc=0;return NULL;}void *p=__real_malloc(n);if(p)allocations++;return p;}
void __wrap_free(void *p){if(p){assert(allocations);allocations--;__real_free(p);}}
static int prepare(void){phase=1;int r=xq_whole_bank_prepare("/fixture");clean();checks++;return r;}
static int load(const uint8_t *key,int16_t **out,unsigned *count){phase=2;int r=xq_whole_bank_load(key,out,count);clean();checks++;return r;}
static void bad_prepare(void){assert(prepare()==-1);assert(allocations==0);uint8_t k[4]={22,2,27,5};int16_t *p=NULL;unsigned n=9;assert(load(k,&p,&n)==0 && !p && !n);}
int main(void)
{
    int16_t *samples=NULL;unsigned count=0;
    fixture(2);missing_cfg=1;assert(prepare()==0 && mem_opens==0);
    fixture(2);missing_reg=1;bad_prepare();assert(mem_opens==0);
    fixture(2);missing_nomap=1;bad_prepare();assert(mem_opens==0);
    fixture(2);length[11]=7;bad_prepare();assert(mem_opens==0);
    fixture(2);length[11]=9;bad_prepare();assert(mem_opens==0);
    fixture(2);length[12]=1;bad_prepare();assert(mem_opens==0);
    fixture(2);big(reg+4,le(cfg+16)+4096);bad_prepare();assert(mem_opens==0);
    fixture(2);cfg[0]^=1;bad_prepare();assert(mem_opens==0);
    fixture(2);cfg[64]^=1;bad_prepare();assert(mem_opens==0);
    fixture(2);put(cfg+12,0x04001000);put(cfg+64,0);put(cfg+64,crc(cfg,96));bad_prepare();assert(mem_opens==0);
    fixture(2);put(cfg+16,XQ_WHOLE_BANK_LIMIT-XQ_WHOLE_BANK_BASE);put(cfg+64,0);put(cfg+64,crc(cfg,96));bad_prepare();assert(mem_opens==0);
    fixture(2);length[10]=95;bad_prepare();
    fixture(2);fail_read=10;bad_prepare();
    fixture(2);fail_read=11;bad_prepare();
    fixture(2);fail_close=10;bad_prepare();
    fixture(2);fail_mem=1;bad_prepare();
    fixture(2);fail_map=1;bad_prepare();
    fixture(2);fail_malloc=1;bad_prepare();
    fixture(2);fail_unmap=1;bad_prepare();
    fixture(2);fail_close=13;bad_prepare();
    fixture(2);bank[0]^=1;bind_crc();bad_prepare();
    fixture(2);bank[48]^=1;put(bank+52,0);put(bank+52,crc(bank,META_END));put(cfg+24,le(bank+52));put(cfg+64,0);put(cfg+64,crc(cfg,96));bad_prepare();
    fixture(2);bank[52]^=1;bad_prepare();
    fixture(2);bank[56]^=1;bind_crc();bad_prepare();
    fixture(2);put(bank+28,5102);bind_crc();bad_prepare();
    fixture(2);put(bank+36,20);bind_crc();bad_prepare();
    fixture(2);bank[128]=0;bind_crc();bad_prepare();
    fixture(2);memcpy(bank+144,bank+128,4);bind_crc();bad_prepare();
    fixture(2);put(bank+128+8,0);bind_crc();bad_prepare();
    fixture(2);put(bank+128+8,3);bind_crc();bad_prepare();
    fixture(2);put(bank+128+8,30722);bind_crc();bad_prepare();
    fixture(2);put(bank+128+4,UINT32_MAX-1u);bind_crc();bad_prepare();
    fixture(2);put(bank+128+4,DATA_AT+4);bind_crc();bad_prepare();
    fixture(2);bank[META_END]=1;bad_prepare();
    fixture(2);assert(prepare()==1);
    for(unsigned i=0;i<5103;i++){
        uint8_t *k=bank+128+i*16;assert(load(k,&samples,&count)==1 && count==1 && samples);
        unsigned expected=(i*19u+257u)&65535u;assert(samples[0]==(expected<32768u?(int)expected:(int)expected-65536));
        free(samples);samples=NULL;
    }
    uint8_t last[4]={30,24,27,9},invalid[4]={0,16,25,1};
    assert(load(invalid,&samples,&count)==-1 && !samples && !count);
    uint32_t offset=le(bank+128+5102*16+4);bank[offset]^=1;
    assert(load(last,&samples,&count)==-1 && !samples && !count);bank[offset]^=1;
    fail_map=1;assert(load(last,&samples,&count)==-1 && !samples && !count);
    fail_mem=1;assert(load(last,&samples,&count)==-1 && !samples && !count);fail_mem=0;
    fail_malloc=1;assert(load(last,&samples,&count)==-1 && !samples && !count);
    fail_unmap=1;assert(load(last,&samples,&count)==-1 && !samples && !count);
    fail_close=13;assert(load(last,&samples,&count)==-1 && !samples && !count);
    assert(load(last,&samples,&count)==1 && count==1);free(samples);samples=NULL;
    /* The longest allowed clip straddles a page and uses two <=32KiB maps. */
    fixture(30720);assert(prepare()==1);unsigned previous=map_calls;
    assert(load(last,&samples,&count)==1 && count==15360 && max_clip_map<=32768 && map_calls==previous+2);
    free(samples);samples=NULL;
    /* A bad reprepare must discard the old bank, then a good one recovers. */
    cfg[0]^=1;bad_prepare();fixture(2);assert(prepare()==1);assert(load(last,&samples,&count)==1);free(samples);
    xq_whole_bank_release();clean();assert(allocations==0);
    printf("WHOLE_BANK_MOCK_ALL5103_KEYS_GUARDS_BOUNDS_IO_CRC_OOM_RELEASE_RECOVERY_PASS checks=%u\n",checks);return 0;
}
