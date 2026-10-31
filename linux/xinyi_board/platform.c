#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include "platform.h"
#include "xq_camera_retry.h"
#include "xq_picture.h"
#include "crc32_fast.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
#if XINYI_GUI_CACHE_R21
#include "gui_cache_r21.h"
#endif

enum { MAP_CAMERA,MAP_VIDEO,MAP_SYS,MAP_CAM0,MAP_CAM1,MAP_SNAPSHOT,MAP_GUI0,MAP_GUI1,MAP_COUNT };
static const uint32_t physical[MAP_COUNT]={0x1fe12000,0x1fe11000,0x1fe00000,
    0x9b200000,0x9b400000,0x9b600000,0x9b800000,0x9bc00000};
static const size_t lengths[MAP_COUNT]={4096,4096,4096,XQV_FRAME_BYTES,
    XQV_FRAME_BYTES,XQV_FRAME_BYTES,XY_PLATFORM_GUI_BYTES,XY_PLATFORM_GUI_BYTES};
struct xy_platform {
    int fd,lock_fd,test_attached;
    void *maps[MAP_COUNT];
#if XINYI_GUI_CACHE_R21
    int gui_cached;
#ifdef XY_PLATFORM_TEST
    void (*test_cache_publish)(void *);
    void *test_cache_context;
#endif
#endif
    xqc_camera camera;
    volatile uint32_t *sys_page;
    uint32_t saved_video_control;
#if XINYI_GUI_DOUBLE_BUFFER
    unsigned gui_pending,gui_page,gui_polls;
    uint32_t gui_frame;
    uint64_t gui_sent_ms;
#endif
    atomic_uint requested_control;
    atomic_int cancel_requested,done,invalidated;
    pthread_t thread;
    int active,preview_active,frame_valid,frame_pinned;
    uint32_t token,frame_token,frame_crc;
    xy_platform_operation operation;
    xy_platform_event event;
    uint32_t *ram;
    xqv_frame frame;
    uint64_t (*test_now)(void *);
    int (*test_poll)(void *,int);
    void *test_context;
    xqp_hid keyboard;
    uint16_t left_count,right_count;
    int terminal_fd,terminal_flags,terminal_saved;
    struct termios terminal;
};
static void fence_io(void)
{
#ifdef __riscv
    __asm__ volatile("fence iorw,iorw":::"memory");
#else
    __sync_synchronize();
#endif
}
static uint64_t now_ms(void *context)
{
    xy_platform *p=context;
    struct timespec t;
    if(p->test_now)return p->test_now(p->test_context);
    if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
    return (uint64_t)t.tv_sec*1000+(unsigned)t.tv_nsec/1000000;
}
static int camera_poll(void *context,int waiting)
{
    xy_platform *p=context;
    int external=0;
    if(p->test_poll)external=p->test_poll(p->test_context,waiting);
    else if(waiting) {const struct timespec t={0,1000000};(void)nanosleep(&t,NULL);}
    return external || atomic_load_explicit(&p->cancel_requested,memory_order_relaxed);
}
static int property(const char *path,unsigned char *out,size_t cap)
{
    ssize_t count;
    int fd=open(path,O_RDONLY|O_CLOEXEC);
    if(fd<0)return -1;
    count=read(fd,out,cap);close(fd);
    return count>=0?(int)count:-1;
}
static uint32_t be32(const unsigned char *b)
{return ((uint32_t)b[0]<<24)|((uint32_t)b[1]<<16)|((uint32_t)b[2]<<8)|b[3];}
static int coverage(const char *root,uint32_t start,uint32_t bytes)
{
    char directory[1024],path[1536];
    unsigned char reg[257],status[16];
    DIR *dir;
    struct dirent *entry;
    int okay=0;
    if(snprintf(directory,sizeof(directory),"%s/reserved-memory",root)>=(int)sizeof(directory))return 0;
    dir=opendir(directory);if(!dir)return 0;
    while((entry=readdir(dir))!=NULL) {
        int n,i;
        if(entry->d_name[0]=='.')continue;
        if(snprintf(path,sizeof(path),"%s/%s/no-map",directory,entry->d_name)>=(int)sizeof(path) ||
           access(path,F_OK))continue;
        (void)snprintf(path,sizeof(path),"%s/%s/status",directory,entry->d_name);
        n=property(path,status,sizeof(status));
        if(n>=0 && !((n==5 && !memcmp(status,"okay",5)) || (n==3 && !memcmp(status,"ok",3))))continue;
        (void)snprintf(path,sizeof(path),"%s/%s/reg",directory,entry->d_name);
        n=property(path,reg,sizeof(reg));
        if(n<=0 || n>256 || n%8)continue;
        for(i=0;i<n;i+=8) {
            uint64_t base=be32(reg+i),length=be32(reg+i+4),end=base+length;
            if(length && end<=0x100000000ULL && base<=start &&
               end>=(uint64_t)start+bytes) {okay=1;break;}
        }
        if(okay)break;
    }
    closedir(dir);return okay;
}
int xy_platform_reservations_cover(const char *root)
{
    unsigned char data[5];
    char path[1024];
    const char *names[]={"#address-cells","#size-cells"};
    unsigned i;
    if(!root)return 0;
    for(i=0;i<2;++i) {
        if(snprintf(path,sizeof(path),"%s/reserved-memory/%s",root,names[i])>=(int)sizeof(path) ||
           property(path,data,sizeof(data))!=4 || be32(data)!=1)return 0;
    }
    (void)snprintf(path,sizeof(path),"%s/reserved-memory/ranges",root);
    if(property(path,data,sizeof(data))!=0)return 0;
    return coverage(root,0x1b200000,0x00200000) && coverage(root,0x1b400000,0x00200000) &&
        coverage(root,0x1b600000,0x00200000) && coverage(root,0x1b800000,0x00400000) &&
        coverage(root,0x1bc00000,0x00400000) && coverage(root,0x02000000,0x00010000);
}
int xy_platform_validate_mmio(const volatile uint32_t *camera,
    const volatile uint32_t *video,const volatile uint32_t *sys)
{
    if(!camera || !video || !sys || camera[0]!=CAMERA_ID_VALUE ||
       camera[1]!=CAMERA_VERSION_VALUE ||
       (camera[CAMERA_REG_CAPABILITIES/4]&CAMERA_CAP_BACKGROUND_CAPTURE) ||
       video[0]!=0x58514642 || video[1]!=0x00010000 || video[4]!=0x1b800000 || video[5]!=0x1bc00000 ||
       video[6]!=3840 || video[7]!=((1080u<<16)|1920u) || video[8]!=4147200 ||
       sys[0x300/4]!=0x53563300 || !(sys[0x304/4]&1u) || (sys[0x30c/4]&31u)!=31u ||
       sys[0x314/4]!=XINYI_CPU_HZ || sys[0x318/4]!=49500000 ||
       sys[0x400/4]!=0x43483935 || sys[0x404/4]<0x00020020)return 0;
    return 1;
}
static xy_platform *allocate(void)
{
    xy_platform *p=calloc(1,sizeof(*p));
    if(!p)return NULL;
    p->fd=p->lock_fd=p->terminal_fd=-1;
    atomic_init(&p->cancel_requested,0);atomic_init(&p->done,0);
    atomic_init(&p->invalidated,1);atomic_init(&p->requested_control,1);
    if(posix_memalign((void **)&p->ram,64,XQV_FRAME_BYTES)) {free(p);errno=ENOMEM;return NULL;}
    return p;
}
static void dispose_maps(xy_platform *p)
{
    unsigned i;
    if(!p->test_attached)for(i=0;i<MAP_COUNT;++i)
        if(p->maps[i])munmap(p->maps[i],lengths[i]);
    if(p->fd>=0)close(p->fd);
    if(p->lock_fd>=0)close(p->lock_fd);
    free(p->ram);free(p);
}
static void setup_camera(xy_platform *p)
{
    p->camera.camera=p->maps[MAP_CAMERA];p->camera.fb=p->maps[MAP_VIDEO];
    p->camera.sys=p->sys_page+0x300/4;
    p->camera.banks[0]=p->maps[MAP_CAM0];p->camera.banks[1]=p->maps[MAP_CAM1];
    p->camera.snapshot=p->maps[MAP_SNAPSHOT];p->camera.background=0;
    p->camera.now_ms=now_ms;p->camera.poll=camera_poll;p->camera.context=p;
    p->saved_video_control=p->camera.fb[2]&3u;
    fence_io();p->camera.fb[2]=p->saved_video_control|(1u<<8);fence_io();
    p->camera.fb[2]=p->saved_video_control;fence_io();
    atomic_store(&p->requested_control,1u|(p->saved_video_control&2u));
    p->preview_active=(p->camera.camera[2]&CAMERA_CONTROL_ENABLE)!=0;
    xy_platform_discard_input(p);
}
#if XINYI_GUI_CACHE_R21
static int gui_cache_probe(int fd)
{
    uint32_t *backup=malloc(XY21_SCRATCH_BYTES);
    if(!backup)return 0;
    void *plain=mmap(NULL,XY21_SCRATCH_BYTES,PROT_READ|PROT_WRITE,MAP_SHARED,fd,
        (off_t)(XY21_SCRATCH_BASE|0x80000000u));
    void *cached=mmap(NULL,XY21_SCRATCH_BYTES,PROT_READ|PROT_WRITE,MAP_SHARED,fd,
        (off_t)XY21_SCRATCH_BASE);
    int okay=plain!=MAP_FAILED && cached!=MAP_FAILED &&
        xy21_cache_check(plain,cached,backup,xy21_cache_publish,NULL);
    if(cached!=MAP_FAILED)munmap(cached,XY21_SCRATCH_BYTES);
    if(plain!=MAP_FAILED)munmap(plain,XY21_SCRATCH_BYTES);
    free(backup);return okay;
}
static void gui_publish(xy_platform *p)
{
    if(!p->gui_cached)return;
#ifdef XY_PLATFORM_TEST
    if(p->test_cache_publish){p->test_cache_publish(p->test_cache_context);return;}
#endif
    xy21_cache_publish(NULL);
}
#endif
xy_platform *xy_platform_open(void)
{
    xy_platform *p;
    unsigned i;
    int saved;
    if(!xy_platform_reservations_cover("/proc/device-tree")) {errno=ENXIO;return NULL;}
    p=allocate();if(!p)return NULL;
    p->lock_fd=open("/run/xq-camera.lock",O_CREAT|O_RDWR|O_CLOEXEC,0600);
    if(p->lock_fd<0 || flock(p->lock_fd,LOCK_EX|LOCK_NB))goto fail;
    p->fd=open("/dev/mem",O_RDWR|O_SYNC|O_CLOEXEC);if(p->fd<0)goto fail;
    /* Map and validate registers first. E8 cannot cause a GUI-bank mapping. */
    for(i=0;i<3;++i) {
        p->maps[i]=mmap(NULL,lengths[i],PROT_READ|PROT_WRITE,MAP_SHARED,p->fd,(off_t)physical[i]);
        if(p->maps[i]==MAP_FAILED) {p->maps[i]=NULL;goto fail;}
    }
    p->sys_page=p->maps[MAP_SYS];
    if(!xy_platform_validate_mmio(p->maps[0],p->maps[1],p->sys_page)) {errno=ENODEV;goto fail;}
#if XINYI_GUI_CACHE_R21
    p->gui_cached=gui_cache_probe(p->fd);
    fprintf(stderr,"XINYI_GUI_CACHE_R21 enabled=%d scratch_restored=1\n",p->gui_cached);
#endif
    for(i=3;i<MAP_COUNT;++i) {
        uint32_t address=physical[i];
#if XINYI_GUI_CACHE_R21
        if(i>=MAP_GUI0 && p->gui_cached)address&=0x7fffffffu;
#endif
        p->maps[i]=mmap(NULL,lengths[i],PROT_READ|PROT_WRITE,MAP_SHARED,p->fd,(off_t)address);
        if(p->maps[i]==MAP_FAILED) {p->maps[i]=NULL;goto fail;}
    }
    setup_camera(p);return p;
fail:
    saved=errno;dispose_maps(p);errno=saved;return NULL;
}
unsigned xy_platform_capabilities(const xy_platform *p)
{return p?XY_PLATFORM_EXCLUSIVE_PREVIEW:0;}
uint32_t xy_platform_cpu_hz(const xy_platform *p)
{return p?p->sys_page[0x314/4]:0;}
volatile uint16_t *xy_platform_pixels(xy_platform *p,unsigned page)
{return p && page<2?(volatile uint16_t *)p->maps[MAP_GUI0+page]:NULL;}
volatile uint32_t *xy_platform_video_regs(xy_platform *p)
{return p?p->camera.fb:NULL;}
#if XINYI_GUI_DOUBLE_BUFFER
int xy_platform_gui_back_page(xy_platform *p,unsigned *page)
{
    if(!p || !page){errno=EINVAL;return 0;}
    if(p->active)return 2;
    if(p->camera.poisoned){errno=EBUSY;return 0;}
    if(p->camera.camera[2]&CAMERA_CONTROL_ENABLE)return 2;
    uint32_t status=p->camera.fb[3];
    if(status&((1u<<3)|(1u<<5))){errno=EIO;return 0;}
    if(p->gui_pending){
        if((status&6u)==(2u|(p->gui_page<<2)) &&
           (uint32_t)(p->camera.fb[9]-p->gui_frame)>=2u){
            p->gui_pending=0;
        }else{
            if(now_ms(p)-p->gui_sent_ms>=500 || ++p->gui_polls>=500){errno=ETIMEDOUT;return 0;}
            return 2;
        }
    }
    *page=((status>>2)&1u)^1u;
    return 1;
}
int xy_platform_gui_initial_idle(xy_platform *p)
{
    if(!p || p->active || p->camera.poisoned || p->gui_pending)return 0;
    uint32_t control=p->camera.fb[2],status=p->camera.fb[3];
    uint32_t camera=p->camera.camera[2],camera_status=p->camera.camera[3];
    return !(control&1u) && !(status&(3u|8u|32u)) && !(camera&1u) &&
        (camera_status&(CAMERA_STATUS_ENABLED|CAMERA_STATUS_WRITER_BUSY|CAMERA_STATUS_STOPPING|CAMERA_STATUS_IDLE))==CAMERA_STATUS_IDLE;
}
#endif
int xy_platform_present(xy_platform *p,unsigned page)
{
    if(!p || page>1) {errno=EINVAL;return 0;}
    atomic_store(&p->requested_control,1u|(page<<1));
    if(p->active)return 2;
    if(p->camera.poisoned) {errno=EBUSY;return 0;}
    if(p->camera.camera[2]&CAMERA_CONTROL_ENABLE)return 2;
#if XINYI_GUI_CACHE_R21
    gui_publish(p);
#endif
#if XINYI_GUI_DOUBLE_BUFFER
    p->gui_frame=p->camera.fb[9];p->gui_sent_ms=now_ms(p);p->gui_polls=0;
#endif
    fence_io();p->camera.fb[2]=1u|(page<<1);fence_io();
#if XINYI_GUI_DOUBLE_BUFFER
    p->gui_page=page;p->gui_pending=1;
#endif
    return (p->camera.fb[3]&((1u<<3)|(1u<<5)))?0:1;
}
int xy_platform_take_invalidation(xy_platform *p)
{return p?atomic_exchange(&p->invalidated,0):0;}
static int restore_display(xy_platform *p)
{
    uint64_t start=now_ms(p);
    uint32_t expected=atomic_load(&p->requested_control),before=p->camera.fb[9];
    unsigned polls=0;
    fence_io();p->camera.fb[2]=expected|(1u<<8);fence_io();
    p->camera.fb[2]=expected;fence_io();
    while((p->camera.fb[3]&6u)!=(2u|(expected&2u?4u:0u)) ||
          (uint32_t)(p->camera.fb[9]-before)<2u) {
        /* Cancellation cannot bypass the transition back to the GUI source. */
        (void)camera_poll(p,1);
        if(now_ms(p)-start>=500 || ++polls>=500)return 0;
    }
    int okay=!(p->camera.fb[3]&((1u<<3)|(1u<<5)));
#if XINYI_GUI_DOUBLE_BUFFER
    if(okay)p->gui_pending=0;
#endif
    return okay;
}
#if XINYI_PREVIEW_RETRY_R19
static void preview_attempt(void *context,unsigned attempt,int result,uint32_t status)
{
    (void)context;
    fprintf(stderr,"XINYI_PREVIEW_ATTEMPT attempt=%u result=%d status=%08x\n",attempt,result,status);
}
#endif
static void *camera_worker(void *context)
{
    xy_platform *p=context;
    int r=XQC_OK,stop=XQC_OK;
#if XINYI_UI_NAV_DIAG
    uint64_t preview_started=now_ms(p);
#endif
    p->event=(xy_platform_event){.token=p->token,.operation=p->operation};
    if(p->operation==XY_PLATFORM_CAPTURE)
        r=xqc_capture_until_ready(&p->camera,p->ram,XQV_FRAME_BYTES,&p->frame,NULL,NULL);
    else if(p->operation==XY_PLATFORM_PREVIEW_START)
#if XINYI_PREVIEW_RETRY_R19
        r=xqc_start_retry(&p->camera,18000,3,preview_attempt,p);
#else
        r=xqc_start(&p->camera,5000);
#endif
    else r=xqc_stop(&p->camera);
#if XINYI_UI_NAV_DIAG
    if(p->operation==XY_PLATFORM_PREVIEW_START)
        fprintf(stderr,"XINYI_PREVIEW_DIAG start_result=%d elapsed_ms=%llu control=%08x status=%08x frames=%u video_status=%08x cancelled=%d\n",
            r,(unsigned long long)(now_ms(p)-preview_started),p->camera.camera[2],p->camera.camera[3],
            p->camera.camera[4],p->camera.fb[3],atomic_load(&p->cancel_requested));
#endif
    if(p->operation==XY_PLATFORM_PREVIEW_START && r==XQC_OK &&
       !atomic_load(&p->cancel_requested)) {
        p->event.preview_active=1;p->event.result=XY_PLATFORM_OK;
        atomic_store_explicit(&p->done,1,memory_order_release);return NULL;
    }
    /* Even cancellation before capture_until_ready's first poll must stop an
     * inherited preview. Never publish/ack until native writes have drained. */
    stop=xqc_stop(&p->camera);
    p->event.camera_result=stop?stop:r;
    p->event.drained=!stop && !p->camera.poisoned;
    if(!p->event.drained) p->event.result=XY_PLATFORM_UNDRAINED;
    else {
        p->event.display_restored=restore_display(p);
        atomic_store(&p->invalidated,1);
        p->event.result=atomic_load(&p->cancel_requested) || r==XQC_CANCELLED?
            XY_PLATFORM_CANCELLED:r?XY_PLATFORM_FAILED:XY_PLATFORM_OK;
        if(!p->event.display_restored && p->event.result==XY_PLATFORM_OK)
            p->event.result=XY_PLATFORM_FAILED;
        if(p->operation==XY_PLATFORM_CAPTURE && p->event.result==XY_PLATFORM_OK) {
            uint32_t crc=0xffffffff;
            size_t offset;
            for(offset=0;offset<XQV_FRAME_BYTES;offset+=4096) {
                size_t chunk=XQV_FRAME_BYTES-offset;
                if(chunk>4096)chunk=4096;
                if(atomic_load(&p->cancel_requested)) {p->event.result=XY_PLATFORM_CANCELLED;break;}
                crc=crc32_fast(crc,(const unsigned char *)p->ram+offset,(uint32_t)chunk);
            }
            if(p->event.result==XY_PLATFORM_OK) {
                p->frame_crc=crc^0xffffffff;p->frame_token=p->token;p->frame_valid=1;
            }
        }
    }
    atomic_store_explicit(&p->done,1,memory_order_release);return NULL;
}
static int begin(xy_platform *p,xy_platform_operation op,uint32_t token,int cancelled)
{
    int r;
    if(!p || !token || p->active || p->camera.poisoned ||
       (op==XY_PLATFORM_CAPTURE && p->frame_pinned)) {errno=EBUSY;return 0;}
    p->operation=op;p->token=token;
    if(op==XY_PLATFORM_CAPTURE) {p->frame_valid=0;memset(&p->frame,0,sizeof(p->frame));}
    atomic_store(&p->cancel_requested,cancelled);atomic_store(&p->done,0);
    p->active=1;
    r=pthread_create(&p->thread,NULL,camera_worker,p);
    if(r) {p->active=0;errno=r;return 0;}
    return 1;
}
int xy_platform_capture_start(xy_platform *p,uint32_t token)
{return begin(p,XY_PLATFORM_CAPTURE,token,0);}
int xy_platform_preview_start(xy_platform *p,uint32_t token)
{return begin(p,XY_PLATFORM_PREVIEW_START,token,0);}
int xy_platform_preview_stop(xy_platform *p,uint32_t token)
{return begin(p,XY_PLATFORM_PREVIEW_STOP,token,0);}
int xy_platform_cancel(xy_platform *p,uint32_t token)
{
    if(!p || !p->active || p->token!=token)return 0;
    atomic_store(&p->cancel_requested,1);return 1;
}
int xy_platform_poll(xy_platform *p,xy_platform_event *event)
{
    if(!p || !event || !p->active || !atomic_load_explicit(&p->done,memory_order_acquire))return 0;
    (void)pthread_join(p->thread,NULL);p->active=0;
    if(atomic_load(&p->cancel_requested) && p->event.preview_active) {
        /* Late cancel of a completed preview-start must drain in a new worker,
         * rather than acknowledge while the camera is still writing. */
        if(begin(p,XY_PLATFORM_PREVIEW_STOP,p->token,1))return 0;
        p->camera.poisoned=1;
        p->event.result=XY_PLATFORM_UNDRAINED;p->event.drained=0;
    } else if(atomic_load(&p->cancel_requested) && p->event.drained) {
        p->event.result=XY_PLATFORM_CANCELLED;
        if(p->operation==XY_PLATFORM_CAPTURE)p->frame_valid=0;
    }
    p->preview_active=p->event.preview_active;
    *event=p->event;return 1;
}
int xy_platform_frame_acquire(xy_platform *p,uint32_t token,xy_platform_frame *out)
{
    if(!p || !out || p->active || !p->frame_valid || p->frame_pinned || p->frame_token!=token)return 0;
    p->frame_pinned=1;
    *out=(xy_platform_frame){token,p->frame.frame_id,p->frame_crc,p->frame.captured_ms,p->ram,p->frame.bytes};
    return 1;
}
int xy_platform_frame_release(xy_platform *p,uint32_t token)
{
    if(!p || !p->frame_pinned || p->frame_token!=token)return 0;
    p->frame_pinned=0;return 1;
}
void xy_platform_discard_input(xy_platform *p)
{
    volatile uint32_t *hid;
    uint32_t counts;
    if(!p || !p->sys_page)return;
    hid=p->sys_page+0x400/4;counts=hid[0x28/4];
    p->left_count=(uint16_t)counts;p->right_count=(uint16_t)(counts>>16);
    xqp_hid_init(&p->keyboard,hid[0x18/4],now_ms(p));
}
#if XINYI_BATTLE_R17
static int battle_hid_key(xqp_hid *h,uint32_t frame,uint32_t packed,uint64_t now)
{
    if(h->pending_reports && now-h->first_ms>=2000u){h->pending_reports=0;h->last_frame=frame;return -1;}
    if(frame!=h->last_frame){
        unsigned usage=packed&255u,modifiers=(packed>>8)&255u,key=0;
        uint32_t delta=frame-h->last_frame;h->last_frame=frame;h->last_report_ms=now;
        if(!modifiers){
            if(usage==0x2c && ((packed>>16)&255u)==32)key=32;
            else if(usage==0x29 && ((packed>>16)&255u)==27)key=27;
            else if(usage==0x28)key=13;
            else if(usage==0x50)key=XY_KEY_LEFT;
            else if(usage==0x4f)key=XY_KEY_RIGHT;
            else if(usage==0x52)key=XY_KEY_UP;
            else if(usage==0x51)key=XY_KEY_DOWN;
        }
        if(!key){h->pending_reports=0;return 0;}
        if(!h->pending_reports){h->first_ms=now;h->key=key;}
        else if(h->key!=key){h->pending_reports=0;return -1;}
        if(delta>2u || h->pending_reports+delta>2u){h->pending_reports=0;return -1;}
        h->pending_reports+=delta;
    }
    if(h->pending_reports==2 && now-h->last_report_ms>=250u){h->pending_reports=0;return(int)h->key;}
    return 0;
}
#endif
int xy_platform_read_input(xy_platform *p,xy_platform_input *out)
{
    volatile uint32_t *hid;
    unsigned tries;
    uint32_t before=0,after=0,packed=0,xy=0,counts=0;
#if XINYI_UI_FEEDBACK
    uint32_t buttons=0;
#endif
    int key;
    if(!p || !out)return 0;
    memset(out,0,sizeof(*out));hid=p->sys_page+0x400/4;
    for(tries=0;tries<4;++tries) {
        before=hid[0x18/4];packed=hid[0x14/4];after=hid[0x18/4];
        if(before==after)break;
    }
    if(tries<4) {
#if XINYI_BATTLE_R17
        key=battle_hid_key(&p->keyboard,after,packed,now_ms(p));
        if(key>0){out->key=key;out->key_first_ms=p->keyboard.first_ms;}
#else
        key=xqp_hid_poll_key(&p->keyboard,after,packed,now_ms(p));
        if(key==32 || key==27) {out->key=key;out->key_first_ms=p->keyboard.first_ms;}
#endif
    }
    for(tries=0;tries<4;++tries) {
        before=hid[0x1c/4];xy=hid[0x0c/4];counts=hid[0x28/4];
#if XINYI_UI_FEEDBACK
        buttons=hid[0x08/4];
#endif
        after=hid[0x1c/4];
        if(before==after)break;
    }
    if(tries<4) {
        out->mouse_x=xy&0x7ff;out->mouse_y=(xy>>11)&0x7ff;
        out->mouse_valid=out->mouse_x<1920 && out->mouse_y<1080;
#if XINYI_UI_FEEDBACK
        out->mouse_sample=1;out->left_down=(buttons&1u)!=0;
        out->mouse_valid=out->mouse_valid && (buttons&16u)!=0;
#endif
        out->left_click=out->mouse_valid && (uint16_t)counts!=p->left_count;
        out->right_click=out->mouse_valid && (uint16_t)(counts>>16)!=p->right_count;
        p->left_count=(uint16_t)counts;p->right_count=(uint16_t)(counts>>16);
    }
    return 1;
}
int xy_platform_terminal_attach(xy_platform *p,int fd)
{
    struct termios raw;
    if(!p || p->terminal_fd>=0 || !isatty(fd))return 0;
    p->terminal_fd=fcntl(fd,F_DUPFD_CLOEXEC,3);
    if(p->terminal_fd<0)return 0;
    p->terminal_flags=fcntl(p->terminal_fd,F_GETFL,0);
    if(p->terminal_flags<0 || tcgetattr(p->terminal_fd,&p->terminal))goto fail;
    p->terminal_saved=1;raw=p->terminal;
    raw.c_lflag&=(tcflag_t)~(ICANON|ECHO);raw.c_cc[VMIN]=0;raw.c_cc[VTIME]=0;
    if(tcsetattr(p->terminal_fd,TCSANOW,&raw) || fcntl(p->terminal_fd,F_SETFL,p->terminal_flags|O_NONBLOCK))goto fail;
    return 1;
fail:
    xy_platform_terminal_restore(p);return 0;
}
int xy_platform_terminal_key(xy_platform *p)
{
    unsigned char bytes[32];ssize_t n,i;
    if(!p || p->terminal_fd<0)return 0;
    n=read(p->terminal_fd,bytes,sizeof(bytes));
#if XINYI_BATTLE_R17
    for(i=0;i+2<n;++i)if(bytes[i]==27 && bytes[i+1]=='['){
        if(bytes[i+2]=='A')return XY_KEY_UP;
        if(bytes[i+2]=='B')return XY_KEY_DOWN;
        if(bytes[i+2]=='C')return XY_KEY_RIGHT;
        if(bytes[i+2]=='D')return XY_KEY_LEFT;
    }
#endif
    for(i=0;i<n;++i)if(bytes[i]==27)return 27;
#if XINYI_BATTLE_R17
    for(i=0;i<n;++i)if(bytes[i]==13 || bytes[i]==10)return 13;
#endif
    for(i=0;i<n;++i)if(bytes[i]==32)return 32;
    return 0;
}
void xy_platform_terminal_restore(xy_platform *p)
{
    if(!p || p->terminal_fd<0)return;
    if(p->terminal_saved)(void)tcsetattr(p->terminal_fd,TCSANOW,&p->terminal);
    if(p->terminal_flags>=0)(void)fcntl(p->terminal_fd,F_SETFL,p->terminal_flags);
    close(p->terminal_fd);p->terminal_fd=-1;p->terminal_saved=0;
}
int xy_platform_close(xy_platform *p)
{
    int r;
    if(!p)return 1;
    xy_platform_terminal_restore(p);
    if(p->frame_pinned) {errno=EBUSY;return 0;}
    if(p->active) {
        (void)xy_platform_cancel(p,p->token);
        (void)pthread_join(p->thread,NULL);p->active=0;
    }
    r=xqc_stop(&p->camera);
    if(r || p->camera.poisoned) {errno=EBUSY;return 0;}
    fence_io();p->camera.fb[2]=p->saved_video_control;fence_io();
    dispose_maps(p);return 1;
}
#ifdef XY_PLATFORM_TEST
xy_platform *xy_platform_test_attach(xqc_camera *camera,volatile uint32_t *sys,
    volatile uint16_t *gui0,volatile uint16_t *gui1)
{
    xy_platform *p=allocate();
    if(!p)return NULL;
    p->test_attached=1;p->sys_page=sys;
    p->maps[MAP_CAMERA]=(void *)camera->camera;p->maps[MAP_VIDEO]=(void *)camera->fb;
    p->maps[MAP_SYS]=(void *)sys;p->maps[MAP_CAM0]=(void *)camera->banks[0];
    p->maps[MAP_CAM1]=(void *)camera->banks[1];p->maps[MAP_SNAPSHOT]=(void *)camera->snapshot;
    p->maps[MAP_GUI0]=(void *)gui0;p->maps[MAP_GUI1]=(void *)gui1;
    p->test_now=camera->now_ms;p->test_poll=camera->poll;p->test_context=camera->context;
    setup_camera(p);return p;
}
void xy_platform_test_set_preview(xy_platform *p,int active) {p->preview_active=active;}
#if XINYI_GUI_CACHE_R21
void xy_platform_test_gui_cache(xy_platform *p,void (*publish)(void *),void *context)
{p->gui_cached=publish!=NULL;p->test_cache_publish=publish;p->test_cache_context=context;}
#endif
#endif
