/* Native 1080p pages, using the existing clipped word-store primitives. */
#ifndef XINYI_HOME_R13_RENDER_H
#define XINYI_HOME_R13_RENDER_H
#if XINYI_BATTLE_R17
#include "xinyi_battle_speedups_r17.h"
#include "xinyi_home_metrics_r19.h"
#include "xinyi_ui_copy_r20.h"
#endif
#define R13_RGB(r,g,b) ((((r)>>3)<<11)|(((g)>>2)<<5)|((b)>>3))
enum { R13_INK=R13_RGB(38,56,49),R13_MUTED=R13_RGB(104,118,108),
       R13_RED=R13_RGB(165,61,53),R13_GOLD=R13_RGB(186,145,88),
       R13_PAPER=R13_RGB(252,250,245),R13_LINE=R13_RGB(223,216,203) };
#undef R13_RGB
static unsigned r13_text_width(const char *s,unsigned size)
{
    const unsigned char *p=(const unsigned char *)s;unsigned width=0;
    while(*p){unsigned c=utf8_next(&p);
        if(c>=32 && c<=126){unsigned scale=size>=48?5:size>=32?3:size>=24?2:1;
            width+=ascii_glyph((char)c,(int)scale)->advance;}
        else width+=size>=64?64:size>=32?32:24;
    }
    return width;
}
static void r13_center(volatile uint16_t *fb,int center,int y,unsigned size,uint16_t color,const char *s)
{product_text(fb,center-(int)r13_text_width(s,size)/2,y,size,color,s);}
static void r13_background(volatile uint16_t *fb)
{
    uint32_t row[960];volatile uint32_t *words=(volatile uint32_t *)(uintptr_t)fb;
#if XINYI_HOME_R15
    for(unsigned y=0;y<XY15_ART_HEIGHT;y++){
        unsigned at=0;
        for(unsigned i=xy15_art_offsets[y];i<xy15_art_offsets[y+1];i++){
            uint32_t run=xy15_art_runs[i],pair=(run&65535u)*0x10001u;
            for(unsigned n=0;n<(run>>16);n++)row[at++]=pair;
        }
        for(unsigned dy=0;dy<2;dy++){
            volatile uint32_t *destination=words+(y*2+dy)*960;
            for(unsigned x=0;x<960;x+=4){destination[x]=row[x];destination[x+1]=row[x+1];
                destination[x+2]=row[x+2];destination[x+3]=row[x+3];}
        }
    }
#else
    for(unsigned y=0;y<135;y++){
        unsigned at=0;
        for(unsigned i=xy_home_row_offsets[y];i<xy_home_row_offsets[y+1];i++){
            uint32_t run=xy_home_runs[i],pair=(run&0xffffu)*0x10001u;
            for(unsigned n=0;n<(run>>16)*4;n++)row[at++]=pair;
        }
        for(unsigned dy=0;dy<8;dy++){
            volatile uint32_t *destination=words+(y*8+dy)*960;
            for(unsigned x=0;x<960;x+=4){destination[x]=row[x];destination[x+1]=row[x+1];
                destination[x+2]=row[x+2];destination[x+3]=row[x+3];}
        }
    }
#endif
}
#if XINYI_HOME_R15
#if XINYI_GUI_METRIC_DELTAS
static void r19_background_region(volatile uint16_t *fb,unsigned x,unsigned y,unsigned w,unsigned h)
{
    uint32_t pixels[960];volatile uint32_t *words=(volatile uint32_t *)(uintptr_t)fb;
    for(unsigned source=y/2;source<(y+h+1)/2;source++){
        unsigned at=0;
        for(unsigned i=xy15_art_offsets[source];i<xy15_art_offsets[source+1];i++){
            uint32_t run=xy15_art_runs[i],pair=(run&65535u)*0x10001u;
            for(unsigned n=0;n<(run>>16);n++)pixels[at++]=pair;
        }
        for(unsigned row=source*2;row<source*2+2;row++)if(row>=y && row<y+h){
            volatile uint32_t *out=words+row*960;
            for(unsigned column=x/2;column<(x+w)/2;column++)out[column]=pixels[column];
        }
    }
}
#endif
static void r15_title(volatile uint16_t *fb)
{
    unsigned x=((1920u-XY15_TITLE_WIDTH)/2u)&~1u;
    volatile uint32_t *words=(volatile uint32_t *)(uintptr_t)fb;
#ifdef XINYI_SCALAR_GLYPH_ORACLE
    for(unsigned row=0;row<XY15_TITLE_HEIGHT;row++)for(unsigned col=0;col<XY15_TITLE_WIDTH;col++){
        unsigned packed=xy15_title_alpha[(row*XY15_TITLE_WIDTH+col)/2];
        unsigned alpha=(packed>>((1u-(col&1u))*4u))&15u;if(!alpha)continue;
        size_t pixel=(size_t)(52+row)*1920+x+col;unsigned shift=(pixel&1u)*16u;
        uint32_t old=words[pixel/2];uint16_t color=xy_blend(R13_INK,(uint16_t)(old>>shift),alpha);
        words[pixel/2]=(old&~(65535u<<shift))|((uint32_t)color<<shift);
    }
#else
    for(unsigned row=0;row<XY15_TITLE_HEIGHT;row++)for(unsigned col=0;col<XY15_TITLE_WIDTH;col+=2){
        unsigned a=xy15_title_alpha[(row*XY15_TITLE_WIDTH+col)/2];if(!a)continue;
        size_t at=(size_t)(52+row)*960+(x+col)/2;uint32_t old=words[at];
        unsigned lo=a>>4,hi=a&15u;
        uint16_t left=lo?xy_blend(R13_INK,(uint16_t)old,lo):(uint16_t)old;
        uint16_t right=hi?xy_blend(R13_INK,(uint16_t)(old>>16),hi):(uint16_t)(old>>16);
        words[at]=left|((uint32_t)right<<16);
    }
#endif
}
#endif
static void r13_card(volatile uint16_t *fb,int x,int y,int w,int h)
{
    rounded_rect(fb,x,y,w,h,20,R13_LINE);
    rounded_rect(fb,x+1,y+1,w-2,h-2,19,R13_PAPER);
}
static void r13_header(volatile uint16_t *fb,const char *title,const char *subtitle)
{
    r13_background(fb);
#if XINYI_HOME_R15
    if(!strcmp(title,"中国象棋RISC-V对弈平台"))r15_title(fb);
    else
#endif
    r13_center(fb,960,66,64,R13_INK,title);
    r13_center(fb,960,166,32,R13_MUTED,subtitle);
}
static int r13_button(volatile uint16_t *fb,const xy_app *a,xy_pointer_event action)
{
    xy_rect r;const char *label=NULL;unsigned size=24;uint16_t ink=R13_INK;
    if(a->page==XY_HOME){
        size=32;
        if(action==XY_ACTION_START){r=xy_layout_home_start;label="开始游戏";}
        else if(action==XY_ACTION_COREMARK){r=xy_layout_home_coremark;label="coremark";}
        else if(action==XY_ACTION_CAMERA){r=xy_layout_home_camera;label="摄像头调试";}
        else if(action==XY_ACTION_EXIT){r=xy_layout_home_exit;label="退出";ink=R13_RED;}
    }else if(a->page==XY_BENCHMARK && !a->coremark_log_visible){
        if(action==XY_ACTION_CM_RUN){r=xy_layout_cm_run;label="运行测试";}
        else if(action==XY_ACTION_CM_LOG){r=xy_layout_home_cm_log;label="查看输出";}
        else if(action==XY_ACTION_CM_REFERENCE){r=xy_layout_home_cm_reference;
            label=a->benchmark_reference_visible?"返回测试":"历史参考";}
        else if(action==XY_ACTION_HOME){r=xy_layout_detail_home;label="返回首页";}
    }else if(a->page==XY_CAMERA_DEBUG){
        if(action==XY_ACTION_PREVIEW){r=xy_layout_preview_start;label="进入全屏预览";size=32;}
        else if(action==XY_ACTION_HOME){r=xy_layout_detail_home;label="返回首页";}
    }
    if(!label)return 0;
    int down=xy_feedback_requested.pressed==action;
    int active=down || xy_feedback_requested.hover==action || xy_feedback_requested.released==action;
    rounded_rect(fb,r.x,r.y,r.w,r.h,18,active?R13_GOLD:R13_LINE);
    rounded_rect(fb,r.x+2,r.y+2,r.w-4,r.h-4,16,down?0xeefbu:R13_PAPER);
    int x=(int)r.x+((int)r.w-(int)r13_text_width(label,size))/2;
    int y=(int)r.y+((int)r.h-(int)size)/2+(down?1:0);
    product_text(fb,x,y,size,ink,label);return 1;
}
static int r13_measured(const xy_app *a)
{return a->coremark_measured && a->coremark_cpu_hz==XINYI_CPU_HZ &&
    isfinite(a->coremark_per_mhz) && a->coremark_per_mhz>0;}
#if !XINYI_BATTLE_R17
static int r13_e42_measurement(const xy_app *a)
{return XINYI_CPU_HZ==60000000u && r13_measured(a) &&
    !strcmp(a->coremark_identity,"e42f5f1be3bc2a1a2e8f99ce428c3f9ed9762bcc685c722b03342ac746b5470b");}
#endif
static void r13_cpu(volatile uint16_t *fb,const xy_app *a)
{
#if XINYI_BATTLE_R17
    (void)a;
    product_text(fb,96,266,32,R13_INK,"乱序CPU性能指标");
    r13_card(fb,96,314,560,610);
    product_text(fb,128,350,24,R13_MUTED,"coremark/MHz");
    product_text(fb,128,388,48,R13_INK,XY20_CM_PER_MHZ);
    hline(fb,128,624,458,1,R13_LINE);
    product_text(fb,128,484,24,R13_MUTED,"cpu 主频");
    product_text(fb,128,522,48,R13_INK,XY20_CPU_FREQUENCY);
    hline(fb,128,624,590,1,R13_LINE);
    product_text(fb,128,616,24,R13_MUTED,"coremark/LUTs");
    product_text(fb,128,654,32,R13_INK,XY20_CM_PER_LUT);
    product_text(fb,128,708,24,R13_MUTED,"分支方向正确率  " XY19_BRANCH_RANGE);
    product_text(fb,128,742,24,R13_MUTED,"I-Cache 命中率  " XY19_ICACHE_RANGE);
    product_text(fb,128,776,24,R13_MUTED,"D-Cache 命中率  " XY19_DCACHE_RANGE);
    product_text(fb,128,810,24,R13_MUTED,"双提交周期占比  " XY19_DUAL_RETIRE_RANGE);
#else

    char s[96];product_text(fb,96,266,32,R13_INK,"乱序CPU性能指标");
#if XINYI_BATTLE_R17
    int archive=XINYI_CPU_HZ==60000000u && XY19_CM_ARCHIVE_VALID;
#endif
    r13_card(fb,96,314,560,610);
    product_text(fb,128,350,24,R13_MUTED,"coremark/MHz");
    if(r13_measured(a))(void)snprintf(s,sizeof(s),"%.4f",a->coremark_per_mhz);
#if XINYI_BATTLE_R17
    else if(archive)(void)snprintf(s,sizeof(s),"%.4f",XY19_CM_ARCHIVE_PER_MHZ);
#endif
    else strcpy(s,"--");
    product_text(fb,128,388,48,R13_INK,s);
    hline(fb,128,624,458,1,R13_LINE);
    product_text(fb,128,484,24,R13_MUTED,"cpu 主频");
    (void)snprintf(s,sizeof(s),"%u MHz",XINYI_CPU_HZ/1000000u);product_text(fb,128,522,48,R13_INK,s);
    hline(fb,128,624,590,1,R13_LINE);
    product_text(fb,128,616,24,R13_MUTED,"coremark/LUTs");
    if(r13_e42_measurement(a))(void)snprintf(s,sizeof(s),"%.6f",a->coremark_per_mhz*60./20125.);
#if XINYI_BATTLE_R17
    else if(archive && !r13_measured(a))(void)snprintf(s,sizeof(s),"%.6f",XY19_CM_ARCHIVE_PER_MHZ*60./20125.);
#endif
    else strcpy(s,"--");
    product_text(fb,128,654,32,R13_INK,s);
#if XINYI_BATTLE_R17
    if(XINYI_CPU_HZ==60000000u){
        product_text(fb,128,708,24,R13_MUTED,"分支方向正确率  " XY19_BRANCH_RANGE);
        product_text(fb,128,742,24,R13_MUTED,"I-Cache 命中率  " XY19_ICACHE_RANGE);
        product_text(fb,128,776,24,R13_MUTED,"D-Cache 命中率  " XY19_DCACHE_RANGE);
        product_text(fb,128,810,24,R13_MUTED,"双提交周期占比  " XY19_DUAL_RETIRE_RANGE);
    }else{
#endif
    product_text(fb,128,714,24,R13_MUTED,"分支预测准确率     -- 待测");
    product_text(fb,128,754,24,R13_MUTED,"cache 命中率       -- 待测");
    product_text(fb,128,794,24,R13_MUTED,"双发率             -- 待测");
#if XINYI_BATTLE_R17
    }
#endif
    hline(fb,128,624,840,1,R13_LINE);
    product_text(fb,128,862,24,R13_MUTED,r13_measured(a)?
#if XINYI_BATTLE_R17
        "本次有效 Linux 实测":
        archive?"Linux 实测存档 · " XY19_CM_ARCHIVE_DATE:
#else
        "最近有效 Linux 实测":
#endif
        "性能指标等待本机测试");
    product_text(fb,128,894,24,R13_MUTED,XINYI_CPU_HZ==60000000u?"配置主频 · CPU内核 20,125 LUT":"配置主频 · CPU资源待绑定");
#endif
}
#if XINYI_BATTLE_R17
/* Fixed copy uses explicit lines and spacing, shared with the game cards. */
static int r20_lines(volatile uint16_t *fb,int x,int y,int pitch,uint16_t ink,const char *text)
{
    const char *line=text;
    while(*line){
        const char *end=strchr(line,'\n');size_t count=end?(size_t)(end-line):strlen(line);
        char buffer[256];if(count>=sizeof(buffer))count=sizeof(buffer)-1;
        memcpy(buffer,line,count);buffer[count]=0;
        product_text(fb,x,y,24,ink,buffer);y+=pitch;
        if(!end)break;
        line=end+1;
    }
    return y;
}
static void r17_home_ai(volatile uint16_t *fb,int y,int height,const char *name,const char *model,
    const char *accelerator,const char *luts,const char *ratio,const char *scope)
{
    r13_card(fb,1264,y,560,height);
    product_text(fb,1292,y+18,24,R13_INK,name);
    int row=r20_lines(fb,1292,y+50,28,R13_MUTED,model);
    row=r20_lines(fb,1292,row,28,R13_INK,accelerator);
    product_text(fb,1292,row,24,R13_MUTED,luts);row+=28;
    product_text(fb,1292,row,24,R13_MUTED,"加速比");
    product_text(fb,1400,row,24,R13_MUTED,scope);
    r13_center(fb,1740,row,24,R13_INK,ratio);
}
#else
static void r13_ai(volatile uint16_t *fb,int y,const char *name,const char *model,const char *accelerator,const char *luts)
{
    r13_card(fb,1264,y,560,190);
    product_text(fb,1292,y+18,24,R13_INK,name);
    product_text(fb,1292,y+56,24,R13_MUTED,model);
    product_text(fb,1292,y+88,24,R13_MUTED,accelerator);
    product_text(fb,1292,y+120,24,R13_MUTED,luts);
    product_text(fb,1292,y+152,24,R13_MUTED,"加速比：待测");
}
#endif
static void r13_home(volatile uint16_t *fb,const xy_app *a)
{
    r13_header(fb,"中国象棋RISC-V对弈平台","盘古676 100Pro+开发板");
    r13_cpu(fb,a);
    product_text(fb,1264,266,32,R13_INK,"AI加速指标");
#if XINYI_BATTLE_R17
    r17_home_ai(fb,314,222,"图像识别",XY20_IMAGE_MODEL,XY20_IMAGE_ACCELERATOR,
        "LUT：5,762，含 LUTRAM",XY17_IMAGE_SPEEDUP,XY17_IMAGE_SPEEDUP_SCOPE);
    r17_home_ai(fb,552,194,"语音识别",XY20_VOICE_MODEL,XY20_VOICE_ACCELERATOR,
        "LUT：2,458，含 LUTRAM",XY17_ACTIVE_VOICE_SPEEDUP,XY17_VOICE_SPEEDUP_SCOPE);
    r17_home_ai(fb,762,252,"棋盘推理",XY20_NNUE_MODEL,XY20_NNUE_ACCELERATOR,
        "LUT：3,462，含 LUTRAM",XY17_NNUE_SPEEDUP,XY17_NNUE_SPEEDUP_SCOPE);
#else
    r13_ai(fb,314,"图像识别","模型：定位192 / YOLOv5n640 / 分类32","加速器：vision32 / 32PE",
        XINYI_CPU_HZ==60000000u?"LUT：5,762，含 LUTRAM":"LUT：待绑定");
    r13_ai(fb,524,"语音识别","模型：CNN + CTC","加速器：voice_accel",
        XINYI_CPU_HZ==60000000u?"LUT：2,458，含 LUTRAM":"LUT：待绑定");
    r13_ai(fb,734,"棋盘推理","模型：Pikafish PFF1 NNUE","加速器：Stage A + NNUE MLP",
        XINYI_CPU_HZ==60000000u?"LUT：3,462，含 LUTRAM":"LUT：待绑定");
#endif
    const xy_pointer_event actions[]={XY_ACTION_START,XY_ACTION_COREMARK,XY_ACTION_CAMERA,XY_ACTION_EXIT};
    for(unsigned i=0;i<4;i++)(void)r13_button(fb,a,actions[i]);
#if !XINYI_HOME_R15
    r13_center(fb,960,866,24,R13_MUTED,"点击进入 · 松开即响应");
#endif
    if(a->message[0] && strcmp(a->message,"欢迎使用芯弈一号")){
#if XINYI_BATTLE_R17
        set_clip(672,940,576,32);
#endif
        r13_center(fb,960,940,24,R13_RED,a->message);
        reset_clip();
    }
    r13_center(fb,960,
#if XINYI_HOME_R15
        1032,
#else
        982,
#endif
#if XINYI_BATTLE_R17
        24,R13_MUTED,XY20_CPU_NOTE);
#else
        24,R13_MUTED,XINYI_CPU_HZ==60000000u?
        "资源：E42 综合子树参考，含 LUTRAM；加速比与微架构百分比待实测":
        "主频为构建配置；综合资源待匹配版本，加速比与微架构百分比待实测");
#endif
}
static void r13_details(volatile uint16_t *fb,const xy_app *a)
{
    char s[160];r13_header(fb,a->page==XY_BENCHMARK?"CoreMark 性能测试":"摄像头调试",
        a->page==XY_BENCHMARK?"实测输出与历史参考分别展示":"全屏实时预览 · Esc 停止并返回首页");
    r13_card(fb,248,288,1426,490);
    if(a->page==XY_CAMERA_DEBUG){
        product_text(fb,320,350,32,R13_INK,"预览期间相机独占 HDMI");
        product_text(fb,320,420,24,R13_MUTED,"画面为 1280 × 720，居中显示，四周黑边。");
        product_text(fb,320,474,24,R13_MUTED,"按 Esc 停止预览，排空完成后返回首页。");
        product_text(fb,320,528,24,R13_MUTED,"此入口只预览，不进行识别或保存照片。");
        if(!a->preview_state)(void)r13_button(fb,a,XY_ACTION_PREVIEW);
        else product_text(fb,320,650,32,R13_INK,a->preview_state==3?"正在停止预览":"正在进入预览");
    }else if(a->benchmark_reference_visible){
        product_text(fb,320,340,32,R13_INK,"历史参考 · P3 / CPU60 ROM");
        (void)snprintf(s,sizeof(s),"CoreMark/MHz    %.9f",XY_CM_REFERENCE_MEAN);product_text(fb,320,408,32,R13_INK,s);
        product_text(fb,320,476,24,R13_MUTED,"六次裸机 ROM BRAM 参考均值，来源 main P3。");
        product_text(fb,320,524,24,R13_MUTED,"与本机 Linux 测试的环境、版本不同，不作为本次成绩。");
    }else{
        product_text(fb,320,340,32,R13_INK,"最近有效 Linux 实测");
        if(r13_measured(a))(void)snprintf(s,sizeof(s),"CoreMark/MHz    %.6f",a->coremark_per_mhz);
        else strcpy(s,"CoreMark/MHz    --");
        product_text(fb,320,408,32,R13_INK,s);
        product_text(fb,320,480,24,R13_MUTED,"运行测试约 30–60 秒；可查看真实输出或取消。");
        product_text(fb,320,526,24,R13_MUTED,"测试通过校验后更新成绩，历史参考不覆盖实测。");
        if(a->job==XY_COREMARK){
            rounded_rect(fb,320,612,1280,24,10,R13_LINE);
            if(a->coremark_progress)rounded_rect(fb,320,612,(int)(1280u*a->coremark_progress/1000u),24,10,R13_GOLD);
            (void)snprintf(s,sizeof(s),"%u%%    %us",a->coremark_progress/10,a->coremark_elapsed_ms/1000);
            product_text(fb,320,660,24,R13_INK,s);
        }
    }
    xy_pointer_target targets[XY_POINTER_TARGETS];unsigned n=xy_pointer_targets(a,targets,XY_POINTER_TARGETS);
    for(unsigned i=0;i<n;i++)feedback_button(fb,a,targets[i].action);
    product_text(fb,248,942,24,R13_MUTED,a->message);
}
#endif
