#include "../xinyi/xinyi_fb.c"
#include "xq_sha256.h"
#include <assert.h>
#include <stdlib.h>
volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];
static unsigned cases;
static int ready_microphone(void *p,int enabled){(void)p;(void)enabled;return 1;}
static void event(xy_feedback *f,xy_app *a,int valid,unsigned x,unsigned y,int down,int press,uint64_t now,xy_pointer_event expected)
{int board=0;assert(xy_feedback_step(f,a,valid,x,y,down,press,now,&board)==expected);cases++;}
static void controls(void)
{
    xy_app a;xy_app_init(&a,NULL);xy_feedback f={0};
    const xy_pointer_event expected[]={XY_ACTION_START,XY_ACTION_COREMARK,XY_ACTION_CAMERA,XY_ACTION_EXIT};
    xy_pointer_target t[5];assert(xy_pointer_targets(&a,t,5)==4);
    for(unsigned i=0;i<4;i++){
        assert(t[i].action==expected[i] && t[i].x==760 && t[i].w==400 && t[i].y==340+i*128);
        assert(xy_pointer_action(&a,t[i].x+t[i].w-1,t[i].y+t[i].h-1)==expected[i]);
        assert(!xy_pointer_action(&a,t[i].x+t[i].w,t[i].y));
        xy_feedback_reset(&f);
        event(&f,&a,1,800,t[i].y+20,1,1,100,XY_ACTION_NONE);
        event(&f,&a,1,800,t[i].y+20,1,0,500,XY_ACTION_NONE);
        event(&f,&a,1,800,t[i].y+20,0,0,501,expected[i]); /* Release sample itself acts. */
        event(&f,&a,1,800,t[i].y+20,0,0,502,XY_ACTION_NONE);
        xy_feedback_reset(&f);
        event(&f,&a,1,800,t[i].y+20,0,1,1000,expected[i]); /* Counter-only click acts now too. */
        event(&f,&a,1,800,t[i].y+20,0,0,1040,XY_ACTION_NONE);
        assert(f.view.released==expected[i]);
        event(&f,&a,1,800,t[i].y+20,0,0,1140,XY_ACTION_NONE);
        assert(!f.view.pressed && !f.view.released);
    }
    xy_feedback_reset(&f);event(&f,&a,1,800,360,1,1,2000,XY_ACTION_NONE);
    event(&f,&a,1,1,1,0,0,2001,XY_ACTION_NONE); /* Drag out cancels. */
    xy_feedback_reset(&f);event(&f,&a,1,800,360,1,1,2100,XY_ACTION_NONE);
    event(&f,&a,0,800,360,0,0,2101,XY_ACTION_NONE); /* Invalid pointer is never a release. */
    event(&f,&a,1,800,360,0,0,2102,XY_ACTION_NONE);
    xy_feedback_reset(&f);event(&f,&a,1,800,360,1,1,2200,XY_ACTION_NONE);
    a.token++;event(&f,&a,1,800,360,0,0,2201,XY_ACTION_NONE);
    assert(!r13_measured(&a));a.coremark_measured=1;a.coremark_cpu_hz=XINYI_CPU_HZ;
    a.coremark_per_mhz=.3;assert(r13_measured(&a) && !r13_e42_measurement(&a));
    strcpy(a.coremark_identity,"e42f5f1be3bc2a1a2e8f99ce428c3f9ed9762bcc685c722b03342ac746b5470b");
    assert(r13_e42_measurement(&a)==(XINYI_CPU_HZ==60000000u));
    a.coremark_cpu_hz++;assert(!r13_measured(&a) && !r13_e42_measurement(&a));
    puts("R13_RELEASE_AND_COUNTER_CLICK_IMMEDIATE_ONCE_HOLD_DRAG_STALE_INVALID_METRIC_GUARDS_PASS");
}
static void save(const char *dir,const char *name,const uint16_t *pixels)
{
    char path[1200];snprintf(path,sizeof(path),"%s/%s.rgb565",dir,name);
    FILE *f=fopen(path,"wbx");assert(f && fwrite(pixels,1,VIDEO_FB_FRAME_BYTES,f)==VIDEO_FB_FRAME_BYTES && !fclose(f));
}
static void frame(const char *dir,const char *name,xy_app *a,uint16_t **banks,uint16_t *ref)
{
    char digest[65];
    for(unsigned b=0;b<2;b++){
        xy_fb_render(a,banks[b]);xy_page_cache saved[2];memcpy(saved,xy_page_caches,sizeof(saved));
        xy_fb_invalidate();xy_fb_render(a,ref);assert(!memcmp(ref,banks[b],VIDEO_FB_FRAME_BYTES));
        memcpy(xy_page_caches,saved,sizeof(saved));
        xq_sha256_hex(banks[b],VIDEO_FB_FRAME_BYTES,digest);printf("R13_FRAME %s %u %s\n",name,b,digest);cases++;
    }
    save(dir,name,banks[0]);
}
int main(int argc,char **argv)
{
    assert(argc==2);controls();uint32_t *guard[2];uint16_t *banks[2],*ref=malloc(VIDEO_FB_FRAME_BYTES),*before=malloc(VIDEO_FB_FRAME_BYTES);
    assert(ref && before);
    for(unsigned b=0;b<2;b++){guard[b]=malloc(VIDEO_FB_FRAME_BYTES+128);assert(guard[b]);
        for(unsigned i=0;i<(VIDEO_FB_FRAME_BYTES+128)/4;i++)guard[b][i]=0xcafebabe;banks[b]=(void *)(guard[b]+16);}
    xy_app a;xy_backend backend={.microphone=ready_microphone};xy_app_init(&a,&backend);xy_feedback_view v={0};xy_fb_feedback(&v);
    frame(argv[1],"home",&a,banks,ref);
    strcpy(a.message,"CoreMark 后端未就绪");frame(argv[1],"home-error",&a,banks,ref);
    strcpy(a.message,"欢迎使用芯弈一号");frame(argv[1],"home-return",&a,banks,ref);
    memcpy(before,banks[0],VIDEO_FB_FRAME_BYTES);v.hover=XY_ACTION_START;xy_fb_feedback(&v);
    frame(argv[1],"home-hover",&a,banks,ref);
    unsigned changed=0;for(unsigned i=0;i<1920*1080;i++)if(before[i]!=banks[0][i]){
        unsigned x=i%1920,y=i/1920;assert(x>=760 && x<1160 && y>=340 && y<432);changed++;}
    assert(changed>100);v.pressed=XY_ACTION_START;xy_fb_feedback(&v);frame(argv[1],"home-down",&a,banks,ref);
    v=(xy_feedback_view){.released=XY_ACTION_START};xy_fb_feedback(&v);frame(argv[1],"home-release",&a,banks,ref);
    v=(xy_feedback_view){0};xy_fb_feedback(&v);
    a.page=XY_BENCHMARK;frame(argv[1],"benchmark",&a,banks,ref);
    a.benchmark_reference_visible=1;frame(argv[1],"history",&a,banks,ref);
    a.benchmark_reference_visible=0;a.job=XY_COREMARK;a.coremark_progress=567;a.coremark_elapsed_ms=23456;
    frame(argv[1],"benchmark-running",&a,banks,ref);
    a.coremark_log_visible=1;strcpy(a.coremark_log,"Actual test fixture output\nCRC: pass\n");a.coremark_log_used=strlen(a.coremark_log);
    frame(argv[1],"benchmark-log",&a,banks,ref);
    a.job=XY_IDLE;a.coremark_log_visible=0;a.page=XY_CAMERA_DEBUG;frame(argv[1],"camera",&a,banks,ref);
    a.preview_state=3;frame(argv[1],"camera-draining",&a,banks,ref);a.preview_state=0;
    a.page=XY_GAME;a.mode=XY_COACH;frame(argv[1],"game",&a,banks,ref);
    /* Every canonical transition, with the old feedback painted on both
     * buffers. Compare each complete output against an invalidated buffer. */
    for(unsigned from=0;from<4;from++)for(unsigned to=0;to<4;to++){
        xy_app_init(&a,&backend);assert(xy_navigate(&a,(xy_page)from,XY_COACH));
        xy_pointer_target targets[XY_POINTER_TARGETS];unsigned nt=xy_pointer_targets(&a,targets,XY_POINTER_TARGETS);
        assert(nt);v=(xy_feedback_view){.hover=targets[0].action,.released=targets[nt-1].action};xy_fb_feedback(&v);
        for(unsigned b=0;b<2;b++)xy_fb_render(&a,banks[b]);
        assert(xy_navigate(&a,(xy_page)to,XY_COACH));v=(xy_feedback_view){0};xy_fb_feedback(&v);
        char label[64];snprintf(label,sizeof(label),"transition-%u-%u",from,to);frame(argv[1],label,&a,banks,ref);
    }
    /* A result/error is never replaced by a canonical static page. */
    strcpy(a.message,"CoreMark 后端未就绪");frame(argv[1],"transition-error",&a,banks,ref);
    a.coremark_measured=1;a.coremark_cpu_hz=XINYI_CPU_HZ;a.coremark_per_mhz=.3;
    frame(argv[1],"transition-measured",&a,banks,ref);
    /* Hidden photo/voice state survives navigation, although these three
     * pages display only page controls, messages and CoreMark values. */
    xy_app_init(&a,&backend);a.has_board=1;a.current_photo_valid=1;
    a.photo.board.squares[8]=4;a.photo_latency_ms=277123;a.photo_latency_valid=1;
    a.voice_has_board=1;a.voice_board.squares[0]=4;a.voice_commands=17;a.voice_tail_ms=123;
    a.page=XY_HOME;frame(argv[1],"photo-home",&a,banks,ref);
#if XINYI_GUI_PAIR_DELTAS && defined(XINYI_PAIR_CACHE_TEST_STATS)
    unsigned hits_before=xy16_pair_cache_hits;
#endif
    assert(xy_navigate(&a,XY_BENCHMARK,XY_COACH));frame(argv[1],"photo-benchmark",&a,banks,ref);
#if XINYI_GUI_PAIR_DELTAS && defined(XINYI_PAIR_CACHE_TEST_STATS)
    if(xy16_pairs[2])assert(xy16_pair_cache_hits>=hits_before+2);
#endif
    assert(xy_navigate(&a,XY_HOME,XY_VOICE));frame(argv[1],"voice-home",&a,banks,ref);
    a.coremark_measured=1;a.coremark_cpu_hz=XINYI_CPU_HZ;a.coremark_per_mhz=.31;
    frame(argv[1],"photo-measured-home",&a,banks,ref);
    assert(xy_navigate(&a,XY_CAMERA_DEBUG,XY_COACH));frame(argv[1],"photo-measured-camera",&a,banks,ref);
    a.preview_state=3;frame(argv[1],"photo-measured-camera-drain",&a,banks,ref);
    a.preview_state=0;strcpy(a.message,"预览已停止，按 Esc 或返回按钮回到首页");frame(argv[1],"camera-message",&a,banks,ref);
    /* Pair packing must also match the scalar oracle on odd/clipped glyphs. */
    for(unsigned n=0;n<8;n++){
        reset_clip();fill_screen(banks[0],0xafe5);set_clip(3,1,180,75);
        product_text(banks[0],(int)n-4,-2,32,R13_INK,"中国象棋RISC-V");
        char digest[65];xq_sha256_hex(banks[0],VIDEO_FB_FRAME_BYTES,digest);printf("R13_GLYPH %u %s\n",n,digest);
    }
    for(unsigned b=0;b<2;b++){for(unsigned i=0;i<16;i++)assert(guard[b][i]==0xcafebabe && guard[b][16+VIDEO_FB_FRAME_BYTES/4+i]==0xcafebabe);free(guard[b]);}
    free(ref);free(before);printf("R13_RENDER_FULL_PIXELS_TWO_BANKS_LOCAL_FEEDBACK_GUARDS_PASS cases=%u\n",cases);return 0;
}
