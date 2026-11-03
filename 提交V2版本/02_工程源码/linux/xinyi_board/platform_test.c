#define _GNU_SOURCE
#include "platform.h"
#include "crc32_fast.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <pty.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

typedef struct {
    uint32_t camera[1024],video[1024],sys[1024];
    uint32_t *banks[2],*snapshot;
    uint16_t *gui[2];
    uint64_t time;
    int hold,stop_count,stall_stop,cancel_copy;
    xy_platform *platform;
    uint32_t token;
} fixture;
static uint64_t clock_ms(void *p) {return ((fixture *)p)->time;}
static int hardware_poll(void *context,int waiting)
{
    fixture *f=context;
    uint32_t control=f->camera[2];
    (void)waiting;++f->time;
    if(control&CAMERA_CONTROL_STOP_REQUEST) {
        ++f->stop_count;
        f->camera[3]=f->stall_stop?CAMERA_STATUS_ENABLED|CAMERA_STATUS_WRITER_BUSY|
            CAMERA_STATUS_STOPPING:CAMERA_STATUS_ENABLED|CAMERA_STATUS_IDLE;
        f->hold=0;
    } else if(control&CAMERA_CONTROL_ENABLE) {
        f->camera[3]=CAMERA_STATUS_ENABLED|CAMERA_STATUS_CMOS1_INIT_DONE|
            CAMERA_STATUS_CMOS2_INIT_DONE|CAMERA_STATUS_FRAME_VALID;
        f->video[3]=3;
        if(control&CAMERA_CONTROL_SNAPSHOT_HOLD) {
            if(!f->hold) {f->hold=1;f->camera[7]=f->camera[4];}
            f->camera[3]|=CAMERA_STATUS_SNAPSHOT_READY|CAMERA_STATUS_SNAPSHOT_BUFFER1;
            if(f->cancel_copy && !waiting) {
                assert(xy_platform_cancel(f->platform,f->token));f->cancel_copy=0;
            }
        } else {++f->camera[4];f->hold=0;}
    } else {
        f->camera[3]=CAMERA_STATUS_IDLE;f->hold=0;
        f->video[3]=(f->video[2]&1)?3u|((f->video[2]&2)?4u:0u):0;
        ++f->video[9];
    }
    return 0;
}
static void setup(fixture *f)
{
    unsigned i;
    memset(f,0,sizeof(*f));
    f->camera[0]=CAMERA_ID_VALUE;f->camera[1]=CAMERA_VERSION_VALUE;f->camera[3]=CAMERA_STATUS_IDLE;
    f->video[0]=0x58514642;f->video[1]=0x10000;f->video[2]=1;f->video[3]=3;
    f->video[4]=0x1b800000;f->video[5]=0x1bc00000;f->video[6]=3840;
    f->video[7]=(1080u<<16)|1920u;f->video[8]=4147200;
    f->sys[0x300/4]=0x53563300;f->sys[0x304/4]=1;f->sys[0x30c/4]=31;
    f->sys[0x314/4]=XINYI_CPU_HZ;f->sys[0x318/4]=49500000;
    f->sys[0x400/4]=0x43483935;f->sys[0x404/4]=0x20020;
    f->banks[0]=malloc(XQV_FRAME_BYTES);f->banks[1]=malloc(XQV_FRAME_BYTES);
    f->snapshot=calloc(XQV_FRAME_BYTES/4,4);
    f->gui[0]=calloc(XY_PLATFORM_GUI_BYTES/2,2);f->gui[1]=calloc(XY_PLATFORM_GUI_BYTES/2,2);
    assert(f->banks[0] && f->banks[1] && f->snapshot && f->gui[0] && f->gui[1]);
    for(i=0;i<XQV_FRAME_BYTES/4;++i) {f->banks[0][i]=0x11220000u^i;f->banks[1][i]=0xaabb0000u^i;}
}
static xy_platform *attach(fixture *f)
{
    xqc_camera camera={.camera=f->camera,.fb=f->video,.sys=f->sys+0x300/4,
        .banks={f->banks[0],f->banks[1]},.snapshot=f->snapshot,.now_ms=clock_ms,
        .poll=hardware_poll,.context=f};
    f->platform=xy_platform_test_attach(&camera,f->sys,f->gui[0],f->gui[1]);
    assert(f->platform);return f->platform;
}
static void release(fixture *f)
{free(f->banks[0]);free(f->banks[1]);free(f->snapshot);free(f->gui[0]);free(f->gui[1]);}
static xy_platform_event complete(xy_platform *p)
{
    const struct timespec pause={0,1000000};
    unsigned i;
    xy_platform_event event;
    for(i=0;i<3000;++i) {
        if(xy_platform_poll(p,&event))return event;
        (void)nanosleep(&pause,NULL);
    }
    assert(!"bounded fixture completion timed out");
    memset(&event,0,sizeof(event));return event;
}
static void contract(fixture *f,const char *root)
{
    uint32_t saved;
    char path[1024];
    const char *bad[]={"missing-no-map","truncated-camera","bad-cells","bad-ranges","missing-clint"};
    unsigned i;
    snprintf(path,sizeof(path),"%s/covered",root);assert(xy_platform_reservations_cover(path));
    snprintf(path,sizeof(path),"%s/split",root);assert(xy_platform_reservations_cover(path));
    for(i=0;i<sizeof(bad)/sizeof(*bad);++i) {
        snprintf(path,sizeof(path),"%s/%s",root,bad[i]);assert(!xy_platform_reservations_cover(path));
    }
    assert(xy_platform_validate_mmio(f->camera,f->video,f->sys));
    f->camera[CAMERA_REG_CAPABILITIES/4]=1;
    assert(!xy_platform_validate_mmio(f->camera,f->video,f->sys));
    f->camera[CAMERA_REG_CAPABILITIES/4]=0;
    saved=f->video[4];f->video[4]=0x1b200000;assert(!xy_platform_validate_mmio(f->camera,f->video,f->sys));f->video[4]=saved;
    saved=f->video[7];f->video[7]=(720u<<16)|1280;assert(!xy_platform_validate_mmio(f->camera,f->video,f->sys));f->video[7]=saved;
    f->sys[0x314/4]=80000000;assert(!xy_platform_validate_mmio(f->camera,f->video,f->sys));
    f->sys[0x314/4]=XINYI_CPU_HZ==60000000u?70000000u:60000000u;
    assert(!xy_platform_validate_mmio(f->camera,f->video,f->sys));f->sys[0x314/4]=XINYI_CPU_HZ;
    f->sys[0x404/4]=0x2001f;assert(!xy_platform_validate_mmio(f->camera,f->video,f->sys));f->sys[0x404/4]=0x20020;
    f->sys[0x304/4]=0;assert(!xy_platform_validate_mmio(f->camera,f->video,f->sys));f->sys[0x304/4]=1;
    puts("XINYI_PLATFORM_CONTRACT_PASS covering_no_map split_reservations fixed_ranges reject_E8_overlap CPU80_720p_oldHID");
}
static void capture_tests(fixture *f)
{
    xy_platform *p=attach(f);
    xy_platform_event event;
    xy_platform_frame frame;
    uint32_t crc;
    assert(xy_platform_capabilities(p)==XY_PLATFORM_EXCLUSIVE_PREVIEW);
    assert(xy_platform_cpu_hz(p)==XINYI_CPU_HZ && xy_platform_pixels(p,0)==f->gui[0]);
    assert(xy_platform_take_invalidation(p) && !xy_platform_take_invalidation(p));
    assert(xy_platform_present(p,1)==1 && f->video[2]==3);
    f->video[3]|=1u<<3;assert(!xy_platform_present(p,1));f->video[3]&=~(1u<<3);
    f->token=7;assert(xy_platform_capture_start(p,7));
    assert(!xy_platform_capture_start(p,8) && xy_platform_present(p,1)==2);
    event=complete(p);
    assert(event.result==XY_PLATFORM_OK && event.drained && event.display_restored && !event.preview_active);
    assert(f->video[2]==3 && f->stop_count>0 && xy_platform_take_invalidation(p));
    assert(xy_platform_frame_acquire(p,7,&frame) && frame.bytes==XQV_FRAME_BYTES);
    crc=crc32_fast(0xffffffff,f->banks[1],XQV_FRAME_BYTES)^0xffffffff;
    assert(frame.crc32==crc && !memcmp(frame.rgb565,f->banks[1],XQV_FRAME_BYTES) &&
        !memcmp(f->snapshot,f->banks[1],XQV_FRAME_BYTES));
    assert(!xy_platform_capture_start(p,8) && !xy_platform_frame_release(p,6));
    assert(!xy_platform_close(p)); /* Still pinned: no use-after-free. */
    assert(xy_platform_frame_release(p,7));
    f->token=8;f->cancel_copy=1;assert(xy_platform_capture_start(p,8));event=complete(p);
    assert(event.result==XY_PLATFORM_CANCELLED && event.drained && event.display_restored);
    assert(!xy_platform_frame_acquire(p,8,&frame));
    assert(!xy_platform_cancel(p,8));
    f->token=9;assert(xy_platform_preview_start(p,9));event=complete(p);
    assert(event.result==XY_PLATFORM_OK && event.preview_active && !event.drained);
    assert(xy_platform_present(p,0)==2);
    assert(xy_platform_preview_stop(p,10));event=complete(p);
    assert(event.result==XY_PLATFORM_OK && event.drained && event.display_restored && !event.preview_active);
    assert(xy_platform_close(p));
    puts("XINYI_PLATFORM_CAPTURE_PASS async_same_bank_RAM_snapshot_CRC pinning cancel_after_drain GUI_restore preview_exclusive");
}
static void poisoned_test(fixture *f)
{
    xy_platform *p=attach(f);
    xy_platform_event event;
    f->stall_stop=1;f->token=21;f->cancel_copy=1;
    assert(xy_platform_capture_start(p,21));event=complete(p);
    assert(event.result==XY_PLATFORM_UNDRAINED && !event.drained && !event.display_restored);
    assert(!xy_platform_present(p,0) && !xy_platform_capture_start(p,22));
    assert(!xy_platform_close(p));
    f->stall_stop=0; /* Test-only external recovery, never fabricated board ack. */
    assert(xy_platform_close(p));
    puts("XINYI_PLATFORM_DRAIN_PASS undrained_never_ack retain_resources block_present explicit_recovery");
}
static void input_tests(fixture *f)
{
    xy_platform *p=attach(f);
    xy_platform_input input;
    unsigned base=0x400/4;
    int master,slave,flags;
    struct termios original,current;
    f->sys[base+0x0c/4]=(1040u<<11)|1850u;
    f->sys[base+0x28/4]=1;f->sys[base+0x1c/4]=1;
    assert(xy_platform_read_input(p,&input) && input.mouse_y==1040 && input.mouse_x==1850 && input.left_click);
    assert(xy_platform_read_input(p,&input) && !input.left_click);
    f->sys[base+0x14/4]=0x0020002c;f->sys[base+0x18/4]=2;
    assert(xy_platform_read_input(p,&input) && !input.key);
    f->time+=250;assert(xy_platform_read_input(p,&input) && input.key==32);
    f->sys[base+0x14/4]=0x00720015;f->sys[base+0x18/4]=4;
    assert(xy_platform_read_input(p,&input));f->time+=250;
    assert(xy_platform_read_input(p,&input) && !input.key); /* No R page. */
    f->sys[base+0x14/4]=0x001b0029;f->sys[base+0x18/4]=6;
    assert(xy_platform_read_input(p,&input));f->time+=250;
    assert(xy_platform_read_input(p,&input) && input.key==27);
    assert(!openpty(&master,&slave,NULL,NULL,NULL));
    assert(!tcgetattr(slave,&original));flags=fcntl(slave,F_GETFL,0);
    assert(xy_platform_terminal_attach(p,slave));assert(!tcgetattr(slave,&current));
    assert(!(current.c_lflag&(ICANON|ECHO)));
    assert(write(master," \033",2)==2);
    {const struct timespec wait={0,1000000};nanosleep(&wait,NULL);}
    assert(xy_platform_terminal_key(p)==27); /* Esc wins over queued Space. */
    xy_platform_terminal_restore(p);assert(!tcgetattr(slave,&current));
    assert(current.c_lflag==original.c_lflag && current.c_iflag==original.c_iflag && fcntl(slave,F_GETFL,0)==flags);
    close(master);close(slave);assert(xy_platform_close(p));
    puts("XINYI_PLATFORM_INPUT_PASS mouse_11bit_Y press_counts Space_Esc_pair_no_R terminal_restore_Esc_priority");
}
int main(int argc,char **argv)
{
    fixture f;
    assert(argc==2);setup(&f);contract(&f,argv[1]);capture_tests(&f);release(&f);
    setup(&f);poisoned_test(&f);release(&f);
    setup(&f);input_tests(&f);release(&f);
    puts("XINYI_PLATFORM_HOST_PASS synthetic_MMIO_only no_board_acceptance");
    return 0;
}
