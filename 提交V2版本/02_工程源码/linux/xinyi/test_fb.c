#include "xinyi_fb.c"
#include <assert.h>
#include <stdlib.h>

volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];

static void save_ppm(const char *dir,const char *name,const uint16_t *pixels)
{
    char path[1024];
    FILE *out;
    unsigned i;
    (void)snprintf(path,sizeof(path),"%s/%s.ppm",dir,name);
    out=fopen(path,"wb"); assert(out);
    fprintf(out,"P6\n1920 1080\n255\n");
    for(i=0;i<1920*1080;++i) {
        unsigned p=pixels[i];
        unsigned char rgb[3]={(unsigned char)(((p>>11)*255+15)/31),
            (unsigned char)((((p>>5)&63)*255+31)/63),(unsigned char)(((p&31)*255+15)/31)};
        assert(fwrite(rgb,1,3,out)==3);
    }
    assert(!fclose(out));
}
static int ready_mic(void *ctx,int enabled) { (void)ctx; (void)enabled; return 1; }
static void compare_full(xy_app *a,uint16_t *actual,uint16_t *reference)
{
    xy_app saved=previous_app;
    volatile uint16_t *old_pixels=previous_pixels;
    int valid=xy_valid;
    xy_fb_invalidate(); xy_fb_render(a,reference);
    assert(!memcmp(actual,reference,VIDEO_FB_FRAME_BYTES));
    previous_app=saved; previous_pixels=old_pixels; xy_valid=valid;
}
int main(int argc,char **argv)
{
    xy_app a;
    xy_backend backend={0};
    uint32_t *guarded=malloc(VIDEO_FB_FRAME_BYTES+128);
    uint16_t *pixels,*reference=calloc(1920*1080,2),*baseline=calloc(1920*1080,2);
    xy_detection d[]={{0,4,0,990},{7,4,9,990},{6,4,3,964},
                       {4,0,0,900},{4,8,0,900},{4,0,4,100}};
    unsigned i,r;
    assert(argc==2 && guarded && reference && baseline);
    for(i=0;i<(VIDEO_FB_FRAME_BYTES+128)/4;++i)guarded[i]=0xcafebabe;
    pixels=(uint16_t *)(guarded+16);
    backend.microphone=ready_mic;
    xy_app_init(&a,&backend);
    xy_fb_render(&a,pixels); compare_full(&a,pixels,reference);
    save_ppm(argv[1],"home",pixels);
    a.job=XY_COREMARK;
    for(i=0;i<12;++i) {
        a.coremark_progress=i*83;
        xy_fb_render(&a,pixels);compare_full(&a,pixels,reference);
    }
    a.job=XY_IDLE;assert(xy_coremark_log_action(&a,XY_ACTION_CM_LOG));
    for(i=0;i<100;i++)a.coremark_log_used+=(size_t)snprintf(a.coremark_log+a.coremark_log_used,
        sizeof(a.coremark_log)-a.coremark_log_used,"fixture row %03u: not measured time; compiler/seed/CRC output sample\n",i);
    xy_fb_render(&a,pixels);compare_full(&a,pixels,reference);save_ppm(argv[1],"coremark-output",pixels);
    assert(xy_coremark_log_action(&a,XY_ACTION_CM_LOG_NEXT));
    xy_fb_render(&a,pixels);compare_full(&a,pixels,reference);
    assert(xy_coremark_log_action(&a,XY_ACTION_CM_LOG_CLOSE));
    a.coremark_reference_shown=1;a.coremark_reference_per_mhz=5.278868675096502;
    xy_fb_render(&a,pixels);compare_full(&a,pixels,reference);save_ppm(argv[1],"coremark-reference",pixels);
    a.job=XY_IDLE;
    a.page=XY_GAME; a.mode=XY_COACH;
    assert(xy_repair(d,6,&a.photo)); a.has_board=1;a.current_photo_valid=1;
    a.has_recommendation=1; a.recommendation=(xq_search_move_t){31,40};
    strcpy(a.notation,"兵五进一"); strcpy(a.message,"红方教练荐着");
    xy_fb_render(&a,pixels); compare_full(&a,pixels,reference);
    save_ppm(argv[1],"coach-repaired",pixels);
    /* All unmarked board pixels must match the original warm-wood renderer,
     * including 48x48 AA pieces, river, coordinate letters and highlights. */
    reset_clip(); fill_screen(baseline,C_BG); draw_board(baseline);
    draw_position(baseline,&a.photo.board,31,40);
    draw_ring(baseline,BOARD_X+4*CELL,BOARD_Y+5*CELL,42,3,C_GREEN);
    for(r=88;r<1034;++r) for(i=96;i<948;++i) {
        int badge=i>=140 && i<212 && r>=618 && r<642;
        if(!badge)assert(pixels[r*1920+i]==baseline[r*1920+i]);
    }
    for(i=0;i<48;++i) {
        unsigned square=27+(i%5)*2;
        a.photo.board.squares[square]=i&1?PIECE_P:0;
        a.photo.corrected[square]=(uint8_t)(i%3==0);
        a.geometry_failed=(i%7==0);
        a.has_recommendation=(i%4==0);
        a.recommendation.from=(uint8_t)square; a.recommendation.to=(uint8_t)(square+9);
        a.photo_latency_ms=100+i;
        xy_fb_render(&a,pixels); compare_full(&a,pixels,reference);
    }
    a.geometry_failed=1; xy_fb_render(&a,pixels); save_ppm(argv[1],"geometry-failure",pixels);
    a.job=XY_CAPTURE;a.token=100;a.has_recommendation=0;
    unsigned classes[14]={0};classes[0]=classes[6]=classes[7]=1;
    assert(xy_capture_partial(&a,100,classes,3,1000));
    xy_fb_render(&a,pixels);compare_full(&a,pixels,reference);save_ppm(argv[1],"partial-candidates-synthetic",pixels);
    xy_scored_detection estimate[]={{0,4,0,750,.75f},{7,4,9,750,.75f},{6,4,3,750,.75f},{2,4,7,750,.75f}};
    a.job=XY_CAPTURE;a.partial_count=0;
    assert(xy_capture_estimated(&a,100,estimate,4,1000));
    xy_fb_render(&a,pixels);compare_full(&a,pixels,reference);save_ppm(argv[1],"estimated-board-synthetic",pixels);
    assert(!a.geometry_failed && a.current_photo_valid && a.photo.removed_count==1);
    a.mode=XY_VOICE; a.voice_board=a.photo.board; a.voice_has_board=1;
    strcpy(a.voice_heard,"炮二平五"); strcpy(a.voice_result,"已执行，电脑马八进七（合成）");
    xy_fb_render(&a,pixels); compare_full(&a,pixels,reference); save_ppm(argv[1],"voice",pixels);
    for(i=0;i<90;i++){
        a.voice_selected_valid=1;a.voice_selected=i;
        xy_fb_render(&a,pixels);compare_full(&a,pixels,reference);
        a.voice_selected_valid=0;
        xy_fb_render(&a,pixels);compare_full(&a,pixels,reference);
    }
    a.voice_mouse_input=1;strcpy(a.voice_heard,"a3a4");
    xy_fb_render(&a,pixels);compare_full(&a,pixels,reference);save_ppm(argv[1],"mouse-voice",pixels);
    for(i=0;i<16;++i)assert(guarded[i]==0xcafebabe && guarded[16+VIDEO_FB_FRAME_BYTES/4+i]==0xcafebabe);
    free(guarded);free(reference);free(baseline);
    puts("XINYI_FRAMEBUFFER_PASS original_wood_AA_pixels 48_dirty_vs_full 12_progress_dirty_vs_full output_pagination_reference bounds_guards real_RGB565 no_MMIO");
    return 0;
}
