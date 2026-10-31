/* Synthetic ordinary-RAM CPU comparison only. Never accesses a board. */
#define _POSIX_C_SOURCE 200809L
#include "xinyi_fb.c"
#include "xinyi_game_row_r22.h"
#include "xinyi_game_row_scalar_r23.h"
#include <assert.h>
#include <time.h>
#include <unistd.h>
volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];
typedef void (*paint_fn)(volatile uint16_t *,unsigned);
static paint_fn volatile painters[3]={xy21_game_base,xy22_game_rows,xy23_game_rows};
static uint64_t cpu_ns(void)
{struct timespec t;assert(!clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&t));return(uint64_t)t.tv_sec*1000000000u+(unsigned)t.tv_nsec;}
int main(void)
{
    alarm(90);setvbuf(stdout,NULL,_IOLBF,0);
    unsigned char *reference=malloc(4147232),*actual=malloc(4147232);assert(reference && actual);
    for(unsigned mode=0;mode<3;mode++){
        memset(reference,0xa5,4147232);painters[0]((volatile uint16_t *)(void *)(reference+16),mode);
        for(unsigned kind=1;kind<3;kind++){
            memset(actual,0xa5,4147232);painters[kind]((volatile uint16_t *)(void *)(actual+16),mode);
            assert(!memcmp(reference,actual,4147232));
            for(unsigned i=0;i<16;i++)assert(actual[i]==0xa5 && actual[4147216+i]==0xa5);
        }
    }
    puts("R23_CPU_PIXELS modes=3 bytes=4147200 guards=1 exact=1 no_device=1");
    for(unsigned kind=0;kind<3;kind++)for(unsigned i=0;i<2;i++)painters[kind]((volatile uint16_t *)(void *)(actual+16),0);
    for(unsigned pair=0;pair<4;pair++){
        uint64_t times[3];
        for(unsigned turn=0;turn<3;turn++){
            unsigned kind=pair&1u?2u-turn:turn;uint64_t before=cpu_ns();
            for(unsigned draw=0;draw<8;draw++)painters[kind]((volatile uint16_t *)(void *)(actual+16),0);
            times[kind]=cpu_ns()-before;
        }
        printf("R23_CPU pair=%u draws=8 r21_ns=%llu r22_ns=%llu r23_ns=%llu\n",pair,
            (unsigned long long)times[0],(unsigned long long)times[1],(unsigned long long)times[2]);
    }
    free(actual);free(reference);return 0;
}
