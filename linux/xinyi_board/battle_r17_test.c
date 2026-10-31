#include "../xinyi/xinyi_fb.c"
#include "xq_sha256.h"
#include <assert.h>
#include <signal.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];
static int microphone(void *context,int on){(void)context;(void)on;return 1;}

/* Test the real drawing call with a read-only framebuffer. A final memcmp
 * alone cannot distinguish redundant writes from a genuinely quiet update. */
static int hidden_change_writes(unsigned mode,unsigned field)
{
    long page=sysconf(_SC_PAGESIZE);assert(page>0);
    size_t bytes=(VIDEO_FB_FRAME_BYTES+(size_t)page-1)/(size_t)page*(size_t)page;
    uint16_t *pixels=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    assert(pixels!=MAP_FAILED);
    xy_backend backend={.microphone=microphone};xy_app app;xy_app_init(&app,&backend);
    app.page=XY_GAME;app.mode=(xy_mode)mode;xy_feedback_view feedback={0};xy_fb_feedback(&feedback);
    xy_fb_invalidate();xy_fb_render(&app,pixels);
    assert(!mprotect(pixels,bytes,PROT_READ));fflush(NULL);
    pid_t child=fork();assert(child>=0);
    if(!child){
        if(field==0)app.coremark_elapsed_ms++;
        else if(field==1)app.voice_engine_nodes++;
        else if(field==2){app.voice_commands++;app.voice_successes++;}
        else {app.photo.confidence++;app.partial_classes[13]++;}
        xy_fb_render(&app,pixels);
        _exit(0);
    }
    int status=0;assert(waitpid(child,&status,0)==child);
    int wrote=!WIFEXITED(status) || WEXITSTATUS(status)!=0;
    printf("R17_HIDDEN_REAL_RENDER write=%d signal=%d exit=%d mode=%u field=%u\n",wrote,
           WIFSIGNALED(status)?WTERMSIG(status):0,WIFEXITED(status)?WEXITSTATUS(status):-1,mode,field);
    assert(!mprotect(pixels,bytes,PROT_READ|PROT_WRITE));
    assert(!munmap(pixels,bytes));xy_fb_invalidate();return wrote;
}

#if XINYI_BATTLE_R17
static unsigned cases;
static xy_backend backend={.microphone=microphone};
static void fixture(xy_app *a,xy_mode mode)
{
    xy_app_init(a,&backend);a->page=XY_GAME;a->mode=mode;
    a->has_board=a->voice_has_board=1;
    static const unsigned squares[]={0,4,8,19,25,27,31,35,54,58,62,64,70,81,85,89};
    static const uint8_t pieces[]={5,1,5,6,6,7,7,7,15,15,15,14,14,13,9,13};
    for(unsigned n=0;n<sizeof(squares)/sizeof(squares[0]);n++){
        a->photo.board.squares[squares[n]]=pieces[n];a->voice_board.squares[squares[n]]=pieces[n];
    }
    strcpy(a->message,mode==XY_COACH?"空格拍照，每拍独立为红方荐着":mode==XY_VOICE?"请说出您的走法":"红方键鼠操作，黑方AI操作");
}
static void controls(void)
{
    const xy_pointer_event modes[]={XY_ACTION_IMAGE,XY_ACTION_VOICE,XY_ACTION_KEYBOARD};
    for(unsigned mode=0;mode<3;mode++){
        xy_app a;fixture(&a,(xy_mode)mode);xy_pointer_target targets[XY_POINTER_TARGETS];
        unsigned n=xy_pointer_targets(&a,targets,XY_POINTER_TARGETS);assert(n==4);
        unsigned expected_index=0;
        for(unsigned other=0;other<3;other++)if(other!=mode)assert(targets[expected_index++].action==modes[other]);
        assert(targets[2].action==XY_ACTION_RESTART && targets[3].action==XY_ACTION_HOME);
        for(unsigned i=0;i<n;i++){
            xy_pointer_target t=targets[i];assert(t.x==1080+180*i && t.y==856 && t.w==144 && t.h==144);
            unsigned cx=t.x+t.w/2,cy=t.y+t.h/2;
            assert(xy_pointer_action(&a,cx,cy)==t.action);
            assert(xy_pointer_action(&a,t.x+1,cy)==t.action);
            assert(xy_pointer_action(&a,cx,t.y+1)==t.action);
            assert(xy_pointer_action(&a,t.x+t.w-2,cy)==t.action);
            assert(xy_pointer_action(&a,cx,t.y+t.h-2)==t.action);
            assert(xy_pointer_action(&a,t.x,t.y)==XY_ACTION_NONE);
            assert(xy_pointer_action(&a,t.x+5,t.y+5)==XY_ACTION_NONE);
            assert(xy_pointer_action(&a,t.x+t.w-1,t.y+t.h-1)==XY_ACTION_NONE);
            xy_feedback feedback={0};int board=0;
            assert(xy_feedback_step(&feedback,&a,1,cx,cy,1,1,100,&board)==XY_ACTION_NONE);
            assert(feedback.view.pressed==t.action);
            assert(xy_feedback_step(&feedback,&a,1,cx,cy,1,0,500,&board)==XY_ACTION_NONE);
            assert(xy_feedback_step(&feedback,&a,1,cx,cy,0,0,501,&board)==t.action);
            assert(xy_feedback_step(&feedback,&a,1,cx,cy,0,0,502,&board)==XY_ACTION_NONE);
            xy_feedback_reset(&feedback);
            assert(xy_feedback_step(&feedback,&a,1,cx,cy,1,1,600,&board)==XY_ACTION_NONE);
            assert(xy_feedback_step(&feedback,&a,1,t.x+5,t.y+5,0,0,601,&board)==XY_ACTION_NONE);
            xy_feedback_reset(&feedback);
            assert(xy_feedback_step(&feedback,&a,1,cx,cy,1,1,700,&board)==XY_ACTION_NONE);
            assert(xy_feedback_step(&feedback,&a,0,cx,cy,0,0,701,&board)==XY_ACTION_NONE);
            assert(xy_feedback_step(&feedback,&a,1,cx,cy,0,0,702,&board)==XY_ACTION_NONE);
            xy_feedback_reset(&feedback);
            assert(xy_feedback_step(&feedback,&a,1,cx,cy,1,1,800,&board)==XY_ACTION_NONE);
            a.token++;
            assert(xy_feedback_step(&feedback,&a,1,cx,cy,0,0,801,&board)==XY_ACTION_NONE);
        }
        assert(xy_pointer_action(&a,1920,1080)==XY_ACTION_NONE);
        a.cancelling=1;assert(xy_pointer_targets(&a,targets,XY_POINTER_TARGETS)==0);
        a.cancelling=0;a.navigation_pending=1;assert(xy_pointer_targets(&a,targets,XY_POINTER_TARGETS)==0);
    }
    puts("R17_CIRCULAR_TARGETS_IMMEDIATE_RELEASE_HOLD_DRAG_INVALID_STALE_PASS");
}
static void save(const char *dir,const char *name,const uint16_t *pixels)
{
    char path[1200];snprintf(path,sizeof(path),"%s/%s.rgb565",dir,name);
    FILE *f=fopen(path,"wbx");assert(f);
    assert(fwrite(pixels,1,VIDEO_FB_FRAME_BYTES,f)==VIDEO_FB_FRAME_BYTES && !fclose(f));
}
static void frame(const char *dir,const char *name,xy_app *a,uint16_t **banks,uint16_t *reference)
{
    for(unsigned bank=0;bank<2;bank++){
        xy_fb_render(a,banks[bank]);xy_page_cache saved[2];memcpy(saved,xy_page_caches,sizeof(saved));
        memset(reference,0x93,VIDEO_FB_FRAME_BYTES);xy_fb_invalidate();xy_fb_render(a,reference);
        if(memcmp(reference,banks[bank],VIDEO_FB_FRAME_BYTES)){
            unsigned at=0;while(at<VIDEO_FB_FRAME_BYTES/2 && reference[at]==banks[bank][at])at++;
            fprintf(stderr,"R17_PIXEL_MISMATCH name=%s bank=%u x=%u y=%u got=%04x expected=%04x\n",
                    name,bank,at%1920,at/1920,banks[bank][at],reference[at]);fflush(stderr);assert(0);
        }
        memcpy(xy_page_caches,saved,sizeof(saved));
        /* The removed top-left brand and bottom-left permanent messages must
         * leave the actual background, including after returning from home. */
        for(unsigned y=12;y<76;y++)for(unsigned x=96;x<946;x++)assert(banks[bank][y*1920+x]==C_BG);
        for(unsigned y=1040;y<1076;y++)for(unsigned x=96;x<946;x++)assert(banks[bank][y*1920+x]==C_BG);
        /* The status and four discs share one tray. Circle corners must
         * expose that tray, including after hover/press/release restoration. */
        assert(R17_TRAY==0xeef8u && R17_TRAY!=C_CARD);
        /* The resource card ends before y788; leave a visible16px panel
         * gap before the tray at804, across every mode and feedback update. */
        for(unsigned y=788;y<804;y++)for(unsigned x=1080;x<1764;x++){
            if(banks[bank][y*1920+x]!=C_PANEL)
                fprintf(stderr,"R20_RESOURCE_TRAY_OVERFLOW name=%s x=%u y=%u color=%04x\n",name,x,y,banks[bank][y*1920+x]);
            assert(banks[bank][y*1920+x]==C_PANEL);
        }
        assert(banks[bank][846*1920+1056]==R17_TRAY && banks[bank][846*1920+1780]==R17_TRAY);
        for(unsigned i=0;i<4;i++)assert(banks[bank][(856+4)*1920+1080+180*i+4]==R17_TRAY);
        char digest[65];xq_sha256_hex(banks[bank],VIDEO_FB_FRAME_BYTES,digest);
        printf("R17_FRAME %s %u %s\n",name,bank,digest);cases++;
    }
    /* Keep a small synthetic preview set; hashes cover every complete frame. */
    if(!strcmp(name,"mode-0-engine") || !strcmp(name,"mode-1-engine") || !strcmp(name,"mode-2-engine") ||
       !strcmp(name,"mode-0-estimated") || !strcmp(name,"mode-0-cancelling") ||
       !strcmp(name,"mode-2-selected-focus"))save(dir,name,banks[0]);
}
static void home_templates(const char *dir)
{
    uint16_t *banks[2]={malloc(VIDEO_FB_FRAME_BYTES),malloc(VIDEO_FB_FRAME_BYTES)};
    uint16_t *reference=malloc(VIDEO_FB_FRAME_BYTES);assert(banks[0] && banks[1] && reference);
    const xy_page pages[]={XY_HOME,XY_BENCHMARK,XY_HOME,XY_CAMERA_DEBUG,XY_HOME};
    xy_app a;xy_app_init(&a,&backend);xy_feedback_view feedback={0};xy_fb_feedback(&feedback);
    xy_fb_invalidate();
    for(unsigned phase=0;phase<sizeof(pages)/sizeof(pages[0]);phase++){
        if(phase)assert(xy_navigate(&a,pages[phase],XY_COACH));
        for(unsigned bank=0;bank<2;bank++){
            xy_fb_render(&a,banks[bank]);memset(reference,0x93,VIDEO_FB_FRAME_BYTES);reset_clip();
            /* Direct painters deliberately bypass both RLE and pair commands.
             * The separately compiled scalar oracle also bypasses word glyphs. */
            if(a.page==XY_HOME)r13_home(reference,&a);else r13_details(reference,&a);
            if(memcmp(reference,banks[bank],VIDEO_FB_FRAME_BYTES)){
                for(unsigned pixel=0;pixel<VIDEO_FB_FRAME_BYTES/2;pixel++)if(reference[pixel]!=banks[bank][pixel]){
                    fprintf(stderr,"R19_PIXEL_MISMATCH phase=%u bank=%u x=%u y=%u expected=%04x actual=%04x\n",phase,bank,pixel%1920,pixel/1920,reference[pixel],banks[bank][pixel]);break;}
                fflush(stdout);assert(0);
            }
            char digest[65];xq_sha256_hex(banks[bank],VIDEO_FB_FRAME_BYTES,digest);
            printf("R17_HOME_FRAME %u %u %s\n",phase,bank,digest);
            if(!phase && !bank)save(dir,"home",banks[bank]);
        }
    }
    free(reference);free(banks[0]);free(banks[1]);xy_fb_invalidate();
    puts("R17_NEW_HOME_CACHE_DIRECT_RENDER_AND_PAIR_TRANSITIONS_PASS");
}
static void metric_templates(void)
{
    uint16_t *banks[2]={malloc(VIDEO_FB_FRAME_BYTES),malloc(VIDEO_FB_FRAME_BYTES)};
    uint16_t *reference=malloc(VIDEO_FB_FRAME_BYTES);assert(banks[0] && banks[1] && reference);
    xy_app a;xy_app_init(&a,&backend);xy_feedback_view feedback={0};xy_fb_feedback(&feedback);xy_fb_invalidate();
    for(unsigned phase=0;phase<36;phase++){
        if(phase==1){a.coremark_measured=1;a.coremark_cpu_hz=60000000;a.coremark_per_mhz=.22537421625085668;
            strcpy(a.coremark_identity,"e42f5f1be3bc2a1a2e8f99ce428c3f9ed9762bcc685c722b03342ac746b5470b");}
        if(phase==3)a.coremark_per_mhz=.401234567;
        if(phase==4)strcpy(a.coremark_identity,"unmatched");
        if(phase==5)a.coremark_cpu_hz=75000000;
        if(phase==6){a.coremark_measured=0;strcpy(a.message,"CoreMark 后端未就绪");}
        if(phase==7)a.message[0]=0;
        if(phase==8){assert(xy_navigate(&a,XY_BENCHMARK,XY_COACH));a.coremark_measured=1;a.coremark_cpu_hz=60000000;}
        if(phase==9)strcpy(a.message,"CoreMark 实板短测完成");
        if(phase==10)a.coremark_per_mhz=.123456789;
        if(phase==11)a.message[0]=0;
        if(phase==12){memset(a.message,'W',sizeof(a.message)-1);a.message[sizeof(a.message)-1]=0;}
        if(phase==13)assert(xy_navigate(&a,XY_HOME,XY_COACH));
        if(phase==14)assert(xy_navigate(&a,XY_CAMERA_DEBUG,XY_COACH));
        if(phase==15)strcpy(a.message,"摄像头预览失败，可返回后重试");
        if(phase==16)a.message[0]=0;
        if(phase==17)assert(xy_navigate(&a,XY_HOME,XY_VOICE));
        if(phase==18)assert(xy_navigate(&a,XY_BENCHMARK,XY_VOICE));
        if(phase==19)assert(xy_navigate(&a,XY_CAMERA_DEBUG,XY_VOICE));
        if(phase==20)assert(xy_navigate(&a,XY_HOME,XY_KEYBOARD));
        if(phase==21)assert(xy_navigate(&a,XY_BENCHMARK,XY_KEYBOARD));
        if(phase==22)assert(xy_navigate(&a,XY_CAMERA_DEBUG,XY_KEYBOARD));
        if(phase==23)assert(xy_navigate(&a,XY_HOME,XY_COACH));
        if(phase==24){assert(xy_navigate(&a,XY_BENCHMARK,XY_COACH));a.job=XY_COREMARK;a.coremark_progress=0;}
        if(phase==25){a.coremark_progress=22;a.coremark_elapsed_ms=1000;}
        if(phase==26)a.coremark_progress=0;
        if(phase==27){a.coremark_progress=1000;a.coremark_elapsed_ms=48000;}
        if(phase==28)a.cancelling=1;
        if(phase==29){a.cancelling=0;a.job=XY_IDLE;a.coremark_measured=0;strcpy(a.message,"测试未通过校验，预置参考分未更新");}
        if(phase==30){a.job=XY_COREMARK;a.coremark_measured=1;}
        if(phase==31){a.coremark_progress=333;a.coremark_elapsed_ms=13000;a.coremark_per_mhz=.3;}
        if(phase==32){a.job=XY_IDLE;a.coremark_per_mhz=.321;strcpy(a.message,"CoreMark 实板短测完成");}
        if(phase==33)assert(xy_navigate(&a,XY_HOME,XY_COACH));
        if(phase==34)assert(xy_navigate(&a,XY_CAMERA_DEBUG,XY_COACH));
        if(phase==35)assert(xy_navigate(&a,XY_HOME,XY_COACH));
        xy_pointer_target targets[XY_POINTER_TARGETS];unsigned n=xy_pointer_targets(&a,targets,XY_POINTER_TARGETS);
        feedback=(xy_feedback_view){0};if(n)feedback.hover=targets[phase%n].action;
        if(phase%3==1)feedback.pressed=feedback.hover;if(phase%3==2)feedback.released=feedback.hover;
        xy_fb_feedback(&feedback);
        for(unsigned bank=0;bank<2;bank++){
            xy_fb_render(&a,banks[bank]);memset(reference,0x93,VIDEO_FB_FRAME_BYTES);reset_clip();
            if(a.page==XY_HOME)r13_home(reference,&a);else r13_details(reference,&a);
            if(memcmp(reference,banks[bank],VIDEO_FB_FRAME_BYTES)){
                for(unsigned pixel=0;pixel<VIDEO_FB_FRAME_BYTES/2;pixel++)if(reference[pixel]!=banks[bank][pixel]){
                    fprintf(stderr,"R19_METRIC_MISMATCH phase=%u bank=%u x=%u y=%u expected=%04x actual=%04x\n",phase,bank,pixel%1920,pixel/1920,reference[pixel],banks[bank][pixel]);break;}
                fflush(stdout);assert(0);
            }
            char digest[65];xq_sha256_hex(banks[bank],VIDEO_FB_FRAME_BYTES,digest);
            printf("R19_METRIC_FRAME %u %u %s\n",phase,bank,digest);
        }
    }
    free(reference);free(banks[0]);free(banks[1]);xy_fb_invalidate();
    puts("R19_METRIC_MESSAGES_IDENTITIES_REVERSE_PAIRS_FULL_PIXELS_PASS");
}
static void matrix(const char *dir)
{
    const char *copy[]={XY20_IMAGE_MODEL,XY20_IMAGE_ACCELERATOR,XY20_IMAGE_ACCELERATOR_WRAP,
        XY20_VOICE_MODEL,XY20_VOICE_ACCELERATOR,XY20_NNUE_MODEL,XY20_NNUE_ACCELERATOR};
    for(unsigned n=0;n<sizeof(copy)/sizeof(copy[0]);n++){
        const char *line=copy[n];
        while(*line){
            const char *end=strchr(line,'\n');size_t bytes=end?(size_t)(end-line):strlen(line);
            char text[256];assert(bytes<sizeof(text));memcpy(text,line,bytes);text[bytes]=0;
            unsigned width=r13_text_width(text,24),limit=n==1?504u:484u;
            if(width>limit)fprintf(stderr,"R20_COPY_OVERFLOW line=%s width=%u limit=%u\n",text,width,limit);
            assert(width<=limit);
            if(!end)break;
            line=end+1;
        }
    }
    controls();home_templates(dir);metric_templates();uint32_t *guard[2];uint16_t *banks[2],*reference=malloc(VIDEO_FB_FRAME_BYTES);
    assert(reference);
    for(unsigned b=0;b<2;b++){
        guard[b]=malloc(VIDEO_FB_FRAME_BYTES+128);assert(guard[b]);
        for(unsigned i=0;i<(VIDEO_FB_FRAME_BYTES+128)/4;i++)guard[b][i]=0xcafebabe;
        banks[b]=(uint16_t *)(guard[b]+16);
    }
    xy_app a;xy_feedback_view feedback={0};xy_fb_feedback(&feedback);
    /* The actual empty default coach page must not hit the obsolete page-1
     * template. The separate scalar executable disables every page template. */
    for(unsigned mode=0;mode<3;mode++){
        xy_app_init(&a,&backend);assert(xy_navigate(&a,XY_GAME,(xy_mode)mode));
        char label[64];snprintf(label,sizeof(label),"canonical-%u",mode);frame(dir,label,&a,banks,reference);
    }
    for(unsigned mode=0;mode<3;mode++){
        char label[128];fixture(&a,(xy_mode)mode);
#define FRAME(suffix) do{snprintf(label,sizeof(label),"mode-%u-%s",mode,suffix);frame(dir,label,&a,banks,reference);}while(0)
        FRAME("unknown");
        a.has_recommendation=a.current_photo_valid=1;a.recommendation=(xq_search_move_t){19,22};strcpy(a.notation,"炮二平五");
        strcpy(a.voice_heard,"炮二平五");strcpy(a.voice_result,"已走棋");FRAME("result");
        a.image_e2e_valid=a.voice_e2e_valid=1;a.image_e2e_ms=123456;a.voice_e2e_ms=789;FRAME("latency");
        a.voice_engine_stats_valid=1;a.voice_win_rate=623;a.voice_engine_us=172345;FRAME("engine");
        a.voice_win_rate=0;a.voice_engine_us=0;FRAME("engine-zero");
        a.voice_win_rate=1000;a.voice_engine_us=12345678;FRAME("engine-max");
        a.voice_win_rate=UINT32_MAX;a.voice_engine_us=UINT32_MAX;FRAME("engine-unknown");
        a.photo.corrected[19]=a.photo.corrected[25]=1;a.photo.corrected_cells=2;FRAME("corrected");
        a.estimated_position=a.geometry_failed=1;strcpy(a.message,"估计盘面，请核对棋盘");FRAME("estimated");
        a.estimated_position=a.geometry_failed=0;a.photo.corrected[19]=a.photo.corrected[25]=0;a.photo.corrected_cells=0;FRAME("estimated-clear");
        a.voice_selected_valid=1;a.voice_selected=19;a.keyboard_focus_visible=1;a.keyboard_focus=36;FRAME("selected-focus");
        a.voice_selected=25;a.keyboard_focus=45;FRAME("selected-focus-move");
        a.voice_selected_valid=a.keyboard_focus_visible=0;FRAME("selected-focus-clear");
        a.photo.board.squares[19]=a.voice_board.squares[19]=0;
        a.photo.board.squares[22]=a.voice_board.squares[22]=PIECE_C;FRAME("moved");
        for(unsigned i=0;i<4;i++){
            xy_pointer_target targets[XY_POINTER_TARGETS];assert(xy_pointer_targets(&a,targets,XY_POINTER_TARGETS)==4);
            const char *states[]={"hover","pressed","released","clear"};
            for(unsigned state=0;state<4;state++){
                feedback=(xy_feedback_view){0};
                if(!state)feedback.hover=targets[i].action;
                else if(state==1)feedback.hover=feedback.pressed=targets[i].action;
                else if(state==2)feedback.released=targets[i].action;
                xy_fb_feedback(&feedback);
                snprintf(label,sizeof(label),"mode-%u-button-%u-%s",mode,i,states[state]);frame(dir,label,&a,banks,reference);
            }
        }
        strcpy(a.message,"后端出错，请重试");FRAME("error");
        a.geometry_failed=1;FRAME("error-provenance");
        a.geometry_failed=0;FRAME("error-provenance-clear");
        a.cancelling=1;strcpy(a.message,"正在取消，请稍候");FRAME("cancelling");
        a.navigation_pending=1;a.pending_page=XY_HOME;FRAME("navigation-pending");
        a.cancelling=a.navigation_pending=0;
        const xy_job jobs[]={XY_CAPTURE,XY_RECOMMEND,XY_VOICE_COMMAND,XY_ANNOUNCE};
        for(unsigned j=0;j<4;j++){
            a.job=jobs[j];snprintf(label,sizeof(label),"mode-%u-job-%u",mode,j);frame(dir,label,&a,banks,reference);
        }
        a.job=XY_IDLE;a.image_e2e_valid=a.voice_e2e_valid=0;a.current_photo_valid=0;FRAME("next-generation-unknown");
        a.has_board=a.voice_has_board=0;FRAME("empty");
        a.partial_count=4;a.partial_classes[0]=a.partial_classes[4]=2;FRAME("partial");
        a.partial_count=0;
        xy_fb_invalidate();FRAME("invalidation");
#undef FRAME
    }
    for(unsigned from=0;from<3;from++)for(unsigned to=0;to<3;to++){
        fixture(&a,(xy_mode)from);feedback=(xy_feedback_view){0};xy_fb_feedback(&feedback);
        for(unsigned b=0;b<2;b++)xy_fb_render(&a,banks[b]);
        assert(xy_navigate(&a,XY_GAME,(xy_mode)to));char label[64];
        snprintf(label,sizeof(label),"transition-%u-%u",from,to);frame(dir,label,&a,banks,reference);
        assert(xy_navigate(&a,XY_HOME,(xy_mode)to));
        for(unsigned b=0;b<2;b++)xy_fb_render(&a,banks[b]);
        assert(xy_navigate(&a,XY_GAME,(xy_mode)to));
        snprintf(label,sizeof(label),"return-%u-%u",from,to);frame(dir,label,&a,banks,reference);
    }
    for(unsigned b=0;b<2;b++){
        for(unsigned i=0;i<16;i++)assert(guard[b][i]==0xcafebabe && guard[b][16+VIDEO_FB_FRAME_BYTES/4+i]==0xcafebabe);
        free(guard[b]);
    }
    free(reference);printf("R17_BATTLE_THREE_MODES_TWO_BANKS_FULL_PIXELS_GUARDS_PASS records=%u\n",cases);
}
#endif
int main(int argc,char **argv)
{
    assert(argc==2);
    for(unsigned mode=0;mode<(XINYI_BATTLE_R17?3u:1u);mode++)for(unsigned field=0;field<(XINYI_BATTLE_R17?4u:1u);field++){
        int writes=hidden_change_writes(mode,field);fflush(stdout);assert(!writes);
    }
    puts("R17_HIDDEN_REAL_FRAMEBUFFER_QUIET_PASS_NOT_BOARD");
#if XINYI_BATTLE_R17
    matrix(argv[1]);
#else
    (void)argv;
#endif
    return 0;
}
