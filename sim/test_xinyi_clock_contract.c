/* Exact build/board clock binding: another supported clock must be rejected. */
#include "platform.h"
#include <assert.h>
#include <stdio.h>
typedef uint64_t u64;
#include "pg2l_timer_bridge.h"
int main(void)
{
    uint32_t camera[64]={0},video[64]={0},sys[1024]={0};
    camera[0]=CAMERA_ID_VALUE;camera[1]=CAMERA_VERSION_VALUE;
    video[0]=0x58514642;video[1]=0x10000;video[4]=0x1b800000;video[5]=0x1bc00000;
    video[6]=3840;video[7]=(1080u<<16)|1920u;video[8]=4147200;
    sys[0x300/4]=0x53563300;sys[0x304/4]=1;sys[0x30c/4]=31;
    sys[0x314/4]=XINYI_CPU_HZ;sys[0x318/4]=49500000;
    sys[0x400/4]=0x43483935;sys[0x404/4]=0x20020;
    assert(xy_platform_validate_mmio(camera,video,sys));
    const uint32_t bad[]={XINYI_CPU_HZ==60000000u?70000000u:60000000u,
                         XINYI_CPU_HZ-1u,XINYI_CPU_HZ+1u,80000000u,0u};
    for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);++i){
        sys[0x314/4]=bad[i];assert(!xy_platform_validate_mmio(camera,video,sys));
    }
    sys[0x314/4]=XINYI_CPU_HZ;sys[0x318/4]=XINYI_CPU_HZ;
    assert(!xy_platform_validate_mmio(camera,video,sys));
    assert(pg2l_timer_deadline(1000u+XINYI_CPU_HZ,1000u,2000u)==49502000u);
    assert(pg2l_timer_deadline(UINT64_MAX,1000u,2000u)==UINT64_MAX);
    assert(pg2l_timer_deadline(999u,1000u,2000u)==2001u);
    assert(pg2l_timer_deadline(1000u+XINYI_CPU_HZ,1000u,UINT64_MAX-1u)==UINT64_MAX);
    printf("XINYI_EXACT_CLOCK_PASS cpu=%u cases=7 NOT_BOARD\n",XINYI_CPU_HZ);
    return 0;
}
