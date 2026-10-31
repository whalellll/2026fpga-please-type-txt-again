/* Bounded synthetic GUI ordering probe. Board mode restores the inactive GUI
 * bank and original video control; --dry never opens a device. */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include "platform.h"
#include "xinyi_fb.c"
#include <assert.h>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];
static uint32_t crc_table[256];
static volatile uint32_t sink;
static uint64_t probe_us(void)
{struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))exit(9);return(uint64_t)t.tv_sec*1000000u+(unsigned)t.tv_nsec/1000u;}
static void publish(void)
{
#ifdef __riscv
    __asm__ volatile("fence iorw,iorw\n.word 0x0000100f\nfence iorw,iorw":::"memory");
#else
    __sync_synchronize();
#endif
}
static uint32_t frame_crc(const volatile uint32_t *p)
{
    uint32_t c=~0u;
    for(unsigned i=0;i<1036800;i++){
        uint32_t v=p[i];for(unsigned b=0;b<4;b++){c=crc_table[(c^v)&255u]^(c>>8);v>>=8;}
    }
    return ~c;
}
#include "xinyi_game_row_r22.h"
#include "xinyi_game_row_scalar_r23.h"
static void decode_only(unsigned mode)
{
    const xy15_run *parts[2]={xy21_game_left,xy21_game_right[mode]};uint32_t value=0;
    for(unsigned part=0;part<2;part++){
        const volatile xy15_run *run=parts[part];unsigned total=(part?481u:479u)*1080u,at=0;
        while(at<total){unsigned count=run->count;value^=run->value;at+=count;run++;}
    }
    sink=value;
}
static int dry(void)
{
    unsigned char *a=malloc(4147232),*b=malloc(4147232);assert(a && b);
    for(unsigned mode=0;mode<3;mode++){
        memset(a,0xa5,4147232);memset(b,0xa5,4147232);
        xy21_game_base((volatile uint16_t *)(void *)(a+16),mode);
        for(unsigned kind=0;kind<2;kind++){
            memset(b,0xa5,4147232);
            if(kind)xy23_game_rows((volatile uint16_t *)(void *)(b+16),mode);
            else xy22_game_rows((volatile uint16_t *)(void *)(b+16),mode);
            assert(!memcmp(a,b,4147232));
            for(unsigned i=0;i<16;i++)assert(b[i]==0xa5 && b[4147216+i]==0xa5);
        }
        printf("R23_DRY mode=%u bytes=4147200 crc32=%08x exact=1 guards=1\n",mode,frame_crc((uint32_t *)(void *)(b+16)));
    }
    free(a);free(b);return 0;
}
static int video_wait(volatile uint32_t *v,unsigned on,unsigned front)
{
    uint32_t before=v[9];uint64_t start=probe_us();v[2]=on?(1u|(front<<1)):0u;publish();
    while(on?((v[3]&6u)!=(2u|(front<<2)) || (uint32_t)(v[9]-before)<2u):(v[3]&3u)){
        if(probe_us()-start>500000)return 0;
        const struct timespec t={0,1000000};nanosleep(&t,NULL);
    }
    return !(v[3]&0x28u);
}
int main(int argc,char **argv)
{
    alarm(180);setvbuf(stdout,NULL,_IOLBF,0);
    for(unsigned i=0;i<256;i++){uint32_t v=i;for(unsigned b=0;b<8;b++)v=(v>>1)^(0xedb88320u&-(v&1u));crc_table[i]=v;}
    if(argc==2 && !strcmp(argv[1],"--dry"))return dry();
    if(argc!=3 || strcmp(argv[1],"--board") || (strcmp(argv[2],"0") && strcmp(argv[2],"1")))return 2;
    if(!xy_platform_reservations_cover("/proc/device-tree"))return 3;
    int lock=open("/run/xq-camera.lock",O_CREAT|O_RDWR|O_CLOEXEC,0600);
    if(lock<0 || flock(lock,LOCK_EX|LOCK_NB))return 4;
    int fd=open("/dev/mem",O_RDWR|O_SYNC|O_CLOEXEC);if(fd<0)return 5;
    volatile uint32_t *sys=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0x1fe00000u);
    volatile uint32_t *video=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0x1fe11000u);
    volatile uint32_t *camera=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0x1fe12000u);
    if(sys==MAP_FAILED || video==MAP_FAILED || camera==MAP_FAILED)return 6;
    if(sys[0x314/4]!=60000000u || sys[0x308/4]!=49500000u || video[0]!=0x58514642u ||
       video[4]!=0x1b800000u || video[5]!=0x1bc00000u || video[6]!=3840u ||
       video[8]!=4147200u || (video[2]&1u) || (video[3]&0x2bu) ||
       (camera[2]&1u) || (camera[3]&0x71u)!=0x20u)return 7;
    unsigned front=(unsigned)(argv[2][0]-'0'),back=front^1u;uint32_t base=video[4+back],old=video[2];
    volatile uint32_t *plain=mmap(NULL,4147200,PROT_READ|PROT_WRITE,MAP_SHARED,fd,(off_t)(base|0x80000000u));
    volatile uint32_t *cached=mmap(NULL,4147200,PROT_READ|PROT_WRITE,MAP_SHARED,fd,(off_t)base);
    uint32_t *backup=malloc(4147200);if(plain==MAP_FAILED || cached==MAP_FAILED || !backup)return 8;
    publish();for(unsigned i=0;i<1036800;i++)backup[i]=plain[i];
    uint32_t original=frame_crc(plain);int okay=1;
    for(unsigned on=0;on<2 && okay;on++){
        if(!video_wait(video,on,front)){okay=0;break;}
        static const unsigned orders[2][5]={{0,1,2,3,4},{0,3,2,1,4}};
        for(unsigned round=0;round<2 && okay;round++)for(unsigned step=0;step<5 && okay;step++){
            if((camera[2]&1u) || (video[3]&0x28u) ||
               (on && (video[3]&6u)!=(2u|(front<<2)))){okay=0;break;}
            unsigned kind=orders[round][step];
            uint64_t started=probe_us();
            if(kind==0)xy15_template_fill(cached,1036800,0xd5eed5eeu);
            else if(kind==1)xy21_game_base((volatile uint16_t *)(uintptr_t)cached,0);
            else if(kind==2)xy22_game_rows((volatile uint16_t *)(uintptr_t)cached,0);
            else if(kind==3)xy23_game_rows((volatile uint16_t *)(uintptr_t)cached,0);
            else decode_only(0);
            if(kind!=4)publish();
            uint64_t elapsed=probe_us()-started;uint32_t crc=kind<4?frame_crc(plain):0;
            if(kind==0 && crc!=0x96789036u)okay=0;
            if((kind>=1 && kind<=3) && crc!=0x0a3b9393u)okay=0;
            if(on && (video[3]&6u)!=(2u|(front<<2)))okay=0;
            if(video[3]&0x28u || camera[2]&1u)okay=0;
            printf("R23_ORDER video=%u round=%u kind=%u us=%llu crc32=%08x valid=%u inactive_bank=%u\n",on,round,kind,(unsigned long long)elapsed,crc,okay,back);
        }
    }
    if(!video_wait(video,0,front))okay=0;
    for(unsigned i=0;i<1036800;i++){cached[i]=backup[i];}
    publish();
    int restored=frame_crc(plain)==original;video[2]=old;publish();
    printf("R23_ORDER_RESTORED memory=%u control=%u pass=%u\n",restored,video[2]==old,okay && restored);
    free(backup);munmap((void *)cached,4147200);munmap((void *)plain,4147200);close(fd);close(lock);
    return okay && restored?0:9;
}
