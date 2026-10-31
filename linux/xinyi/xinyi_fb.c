/* Extend the imported GUI1080 layer in the same translation unit so its
 * private word-safe, clipped AA and dirty-square primitives remain the single
 * implementation. The host fixture compiles this against byte-exact git blobs.
 * The board integration compiles against the imported files in linux/pikafish.
 * Do not also link xiangqi_fb_gui_1080.o into that executable. */
#include <xiangqi_fb_gui_1080.c>
#include "xinyi_product.h"
#include "xinyi_layout.h"
#include "xinyi_font.h"
#if XINYI_BATTLE_R17
#include "xinyi_battle_font_r17.h"
#endif
#include "../xinyi_board/clock_contract.h"
#include "../xinyi_board/gui_options.h"
#include <stdio.h>
#include <string.h>
#if XINYI_GUI_PAIR_DELTAS && XINYI_UI_NAV_DIAG
static int xy_pair_delta_enabled=1;
#endif
#if XINYI_GUI_PAGE_DELTAS && XINYI_UI_NAV_DIAG
static int xy_page_delta_enabled=1;
#endif
#if XINYI_UI_NAV_DIAG
#include <time.h>
static unsigned xy_ram_copy_ms;
#if XINYI_GUI_RAM_RENDER
static uint64_t xy_ram_clock_ms(void)
{struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;return(uint64_t)t.tv_sec*1000u+t.tv_nsec/1000000u;}
#endif
#endif
#if XINYI_UI_NAV_DIAG
static unsigned xy_nav_cost[5];
static uint64_t xy_nav_clock(void)
{struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;return(uint64_t)t.tv_sec*1000u+(unsigned)t.tv_nsec/1000000u;}
static void xy_nav_cost_finish(unsigned field,uint64_t start)
{uint64_t end=xy_nav_clock();xy_nav_cost[field]+=(unsigned)(end>=start?end-start:0);}
unsigned xy_fb_nav_cost_ms(unsigned field){return field<5?xy_nav_cost[field]:0;}
#endif
#if XINYI_GUI_RAM_RENDER
/* Ordinary private process RAM, never a DMA/MMIO buffer. Only completed full
 * frames use this carrier; existing incremental draws retain their history. */
static uint32_t xy_ram_frame[VIDEO_FB_FRAME_BYTES/4];
#if XINYI_UI_NAV_DIAG
static int xy_ram_enabled=1;
#endif
#endif
#if XINYI_UI_NAV_DIAG
int xy_fb_ram_diag_mode(void)
{
#if XINYI_GUI_PAIR_DELTAS
    return xy_pair_delta_enabled;
#elif XINYI_GUI_RAM_RENDER
    return xy_ram_enabled;
#elif XINYI_GUI_PAGE_DELTAS
    return xy_page_delta_enabled;
#else
    return 0;
#endif
}
void xy_fb_ram_diag_mode_set(int enabled)
{
#if XINYI_GUI_PAIR_DELTAS
    xy_pair_delta_enabled=enabled!=0;
#elif XINYI_GUI_RAM_RENDER
    xy_ram_enabled=enabled!=0;
#elif XINYI_GUI_PAGE_DELTAS
    xy_page_delta_enabled=enabled!=0;
#else
    (void)enabled;
#endif
}
unsigned xy_fb_ram_diag_publish_ms(void){return xy_ram_copy_ms;}
#endif
static inline volatile uint16_t *xy_ram_begin(volatile uint16_t *destination)
{
#if XINYI_GUI_RAM_RENDER
#if XINYI_UI_NAV_DIAG
    if(!xy_ram_enabled)return destination;
#else
    (void)destination;
#endif
    return (volatile uint16_t *)(void *)xy_ram_frame;
#else
    return destination;
#endif
}
static inline void xy_ram_publish(volatile uint16_t *destination,volatile uint16_t *painted)
{
#if XINYI_GUI_RAM_RENDER
    if(destination==painted)return;
    volatile uint32_t *out=(volatile uint32_t *)(uintptr_t)destination;
    const uint32_t *in=xy_ram_frame;unsigned i;
    _Static_assert(VIDEO_FB_FRAME_BYTES%32==0,"Full frame has complete eight-word groups");
#if XINYI_UI_NAV_DIAG
    uint64_t start=xy_ram_clock_ms();
#endif
    for(i=0;i<VIDEO_FB_FRAME_BYTES/4;i+=8){
        out[i]=in[i];out[i+1]=in[i+1];out[i+2]=in[i+2];out[i+3]=in[i+3];
        out[i+4]=in[i+4];out[i+5]=in[i+5];out[i+6]=in[i+6];out[i+7]=in[i+7];
    }
#if XINYI_UI_NAV_DIAG
    xy_ram_copy_ms=(unsigned)(xy_ram_clock_ms()-start);
#endif
#else
    (void)destination;(void)painted;
#endif
}
#if XINYI_HOME_R13
#include "xinyi_home_background.h"
#if XINYI_HOME_R15
#include "xinyi_home_art.h"
#endif
#include <math.h>
#endif
#if XINYI_UI_FEEDBACK
 #if XINYI_BATTLE_R17
static int r17_button(volatile uint16_t *,const xy_app *,xy_pointer_event);
 #endif
#include "../xinyi_board/ui_feedback.h"
static xy_feedback_view xy_feedback_requested;
void xy_fb_feedback(const xy_feedback_view *v)
{xy_feedback_requested=v?*v:(xy_feedback_view){0};}
#endif
_Static_assert(BOARD_X==XY_BOARD_X && BOARD_Y==XY_BOARD_Y && CELL==XY_BOARD_CELL,"Mouse/draw board geometry must match");

#if XINYI_GUI_DOUBLE_BUFFER
typedef struct {xy_app app;volatile uint16_t *pixels;int valid;
#if XINYI_UI_FEEDBACK
    xy_feedback_view feedback;
#endif
} xy_page_cache;
static xy_page_cache xy_page_caches[2];
static xy_page_cache *xy_page_state(volatile uint16_t *fb)
{
    for(unsigned i=0;i<2;i++)if(xy_page_caches[i].pixels==fb)return &xy_page_caches[i];
    for(unsigned i=0;i<2;i++)if(!xy_page_caches[i].pixels){
        xy_page_caches[i].pixels=fb;return &xy_page_caches[i];
    }
    /* Production owns exactly two banks. An extra off-board target starts
     * cold instead of inheriting another buffer's dirty-render history. */
    xy_page_caches[0].pixels=fb;xy_page_caches[0].valid=0;return &xy_page_caches[0];
}
#else
static xy_app previous_app;
static volatile uint16_t *previous_pixels;
static int xy_valid;
#if XINYI_UI_FEEDBACK
static xy_feedback_view previous_feedback;
#endif
#endif
static uint16_t xy_blend(uint16_t foreground, uint16_t background, unsigned alpha)
{
    return (uint16_t)(((((foreground >> 11)*alpha + (background >> 11)*(15-alpha)+7)/15)<<11) |
        (((((foreground >> 5)&63)*alpha + ((background >> 5)&63)*(15-alpha)+7)/15)<<5) |
        (((foreground&31)*alpha + (background&31)*(15-alpha)+7)/15));
}
static uint32_t utf8_next(const unsigned char **text)
{
    const unsigned char *p=*text;
    uint32_t c=*p++;
    if (c>=0xc2 && c<=0xdf && p[0]>=0x80 && p[0]<=0xbf) {
        c=((c&31)<<6)|(p[0]&63); ++p;
    } else if (c>=0xe0 && c<=0xef && p[0]>=0x80 && p[0]<=0xbf &&
               p[1]>=0x80 && p[1]<=0xbf) {
        c=((c&15)<<12)|((p[0]&63)<<6)|(p[1]&63); p+=2;
    } else if (c>=128) c='?';
    *text=p;
    return c;
}
static int product_glyph(volatile uint16_t *fb, int x, int y, unsigned code,
                          unsigned size, uint16_t color)
{
    unsigned i,row,col;
    const xy_font_glyph *g=NULL;
#if XINYI_HOME_R13
    unsigned lo=0,hi=XY_FONT_GLYPHS;
    while(lo<hi){
        unsigned middle=lo+(hi-lo)/2;const xy_font_glyph *p=xy_font_glyphs+middle;
        if(p->size<size || (p->size==size && p->codepoint<code))lo=middle+1;else hi=middle;
    }
    if(lo<XY_FONT_GLYPHS && xy_font_glyphs[lo].size==size && xy_font_glyphs[lo].codepoint==code)g=xy_font_glyphs+lo;
    (void)i;
#else
    for(i=0;i<XY_FONT_GLYPHS;++i)
        if(xy_font_glyphs[i].codepoint==code && xy_font_glyphs[i].size==size) {
            g=&xy_font_glyphs[i]; break;
        }
#endif
#if XINYI_BATTLE_R17
    const uint8_t *bitmap=xy_font_alpha;
    if(!g){
        unsigned low=0,high=sizeof(xy17_font_glyphs)/sizeof(xy17_font_glyphs[0]);
        while(low<high){
            unsigned mid=low+(high-low)/2;const xy_font_glyph *p=xy17_font_glyphs+mid;
            if(p->size<size || (p->size==size && p->codepoint<code))low=mid+1;else high=mid;
        }
        if(low<sizeof(xy17_font_glyphs)/sizeof(xy17_font_glyphs[0]) &&
           xy17_font_glyphs[low].size==size && xy17_font_glyphs[low].codepoint==code){
            g=xy17_font_glyphs+low;bitmap=xy17_font_alpha;
        }
    }
#endif
    if(!g) { draw_text(fb,x,y,"?",2,C_GOLD); return (int)size; }
#if XINYI_BATTLE_R17
    /* The imported square glyphs center ink, including low punctuation.
     * Restore its baseline position without moving quotes or other glyphs. */
    if(code==0xff0cu || code==0x3001u || code==0x3002u)y+=(int)(size*7u/24u);
#endif
#if XINYI_HOME_R13 && !defined(XINYI_SCALAR_GLYPH_ORACLE)
    if(!(x&1) && !(g->width&1)){
        volatile uint32_t *words=(volatile uint32_t *)(uintptr_t)fb;
        for(row=0;row<g->height;row++){
            int yy=y+(int)row;if(yy<clip_y0 || yy>=clip_y1)continue;
            for(col=0;col<g->width;col+=2){
                int xx=x+(int)col;
#if XINYI_BATTLE_R17
                unsigned packed=bitmap[g->offset+(row*g->width+col)/2];
#else
                unsigned packed=xy_font_alpha[g->offset+(row*g->width+col)/2];
#endif
                unsigned alpha0=xx>=clip_x0 && xx<clip_x1?packed>>4:0;
                unsigned alpha1=xx+1>=clip_x0 && xx+1<clip_x1?packed&15:0;
                if(!alpha0 && !alpha1)continue;
                unsigned at=((unsigned)yy*VIDEO_FB_WIDTH+(unsigned)xx)>>1;
                uint32_t pair=words[at];
                if(alpha0){uint16_t p=alpha0==15?color:xy_blend(color,(uint16_t)pair,alpha0);pair=(pair&0xffff0000u)|p;}
                if(alpha1){uint16_t p=alpha1==15?color:xy_blend(color,(uint16_t)(pair>>16),alpha1);pair=(pair&0xffffu)|((uint32_t)p<<16);}
                words[at]=pair;
            }
        }
        return g->advance;
    }
#endif
    for(row=0;row<g->height;++row) for(col=0;col<g->width;++col) {
        unsigned index=row*g->width+col;
#if XINYI_BATTLE_R17
        unsigned packed=bitmap[g->offset+index/2];
#else
        unsigned packed=xy_font_alpha[g->offset+index/2];
#endif
        unsigned alpha=index&1 ? packed&15 : packed>>4;
        int xx=x+(int)col, yy=y+(int)row;
        if(alpha && xx>=clip_x0 && xx<clip_x1 && yy>=clip_y0 && yy<clip_y1) {
            unsigned pixel=(unsigned)yy*VIDEO_FB_WIDTH+(unsigned)xx;
            volatile uint32_t *words=(volatile uint32_t *)(uintptr_t)fb;
            uint32_t pair=words[pixel>>1];
            uint16_t background=(uint16_t)(pair>>((pixel&1)*16));
            put_pixel(fb,xx,yy,alpha==15?color:xy_blend(color,background,alpha));
        }
    }
    return g->advance;
}
static void product_text(volatile uint16_t *fb,int x,int y,unsigned size,
                          uint16_t color,const char *s)
{
    const unsigned char *p=(const unsigned char *)s;
    int start=x;
    while(*p) {
        unsigned c=utf8_next(&p);
        if(c=='\n') {x=start; y+=(int)size+8; continue;}
        if(c>=32 && c<=126) {
            unsigned scale=size>=48?5:size>=32?3:size>=24?2:1;
            const xq_ui_glyph_t *g=ascii_glyph((char)c,(int)scale);
            draw_ui_glyph(fb,x,y+(int)size-(scale==5?48:scale==3?30:scale==2?22:16),g,color);
            x+=g->advance;
        } else x+=product_glyph(fb,x,y,c,size>=64?64:size>=32?32:24,color);
    }
}
static void product_card(volatile uint16_t *fb,int x,int y,int w,int h,
                          const char *heading)
{
    card(fb,x,y,w,h);
    product_text(fb,x+28,y+20,24,C_GREEN,heading);
}
#if XINYI_UI_FEEDBACK
 #if XINYI_HOME_R13
static int r13_button(volatile uint16_t *,const xy_app *,xy_pointer_event);
 #endif
static void feedback_button(volatile uint16_t *fb,const xy_app *a,xy_pointer_event action)
{
#if XINYI_BATTLE_R17
    if(r17_button(fb,a,action))return;
#endif
#if XINYI_HOME_R13
    if(r13_button(fb,a,action))return;
#endif
    xy_rect r;const char *label;uint16_t color=C_GREEN;unsigned size=24;
    int dx=20,dy=16,radius=10,down=0;
    switch(action){
    case XY_ACTION_START:r=xy_layout_home_start;label="开始游戏";color=C_GOLD;size=32;dx=72;dy=20;radius=14;break;
    case XY_ACTION_COREMARK:r=xy_layout_home_coremark;label="CoreMark 测试";size=32;dx=36;dy=20;radius=14;break;
    case XY_ACTION_CM_LOG:r=xy_layout_home_cm_log;label="CoreMark 打印信息";break;
    case XY_ACTION_CM_REFERENCE:r=xy_layout_home_cm_reference;label="参考成绩演示 (10s)";break;
    case XY_ACTION_CM_LOG_PREV:r=xy_layout_cm_log_prev;label="上一页";break;
    case XY_ACTION_CM_LOG_NEXT:r=xy_layout_cm_log_next;label="下一页";break;
    case XY_ACTION_CM_LOG_CLOSE:r=xy_layout_cm_log_close;label="返回";break;
    case XY_ACTION_CANCEL:r=xy_layout_coremark_cancel;label="取消测试 / Esc";
        if(!a->coremark_log_visible){color=C_GOLD;dy=12;}break;
    case XY_ACTION_SWITCH:r=xy_layout_mode_switch;label=a->mode==XY_COACH?"切换语音对战":"切换图像指导";dx=28;dy=12;break;
    case XY_ACTION_HOME:r=xy_layout_game_home;label="返回首页";color=C_GOLD;dx=24;dy=12;break;
    case XY_ACTION_RESTART:r=xy_layout_voice_restart;label="重新开始";color=C_GOLD;dx=28;dy=12;break;
    default:return;
    }
    int enabled=xy_pointer_action(a,r.x+r.w/2,r.y+r.h/2)==action;
    int hover=enabled && xy_feedback_requested.hover==action;
    down=enabled && xy_feedback_requested.pressed==action;
    int released=enabled && xy_feedback_requested.released==action;
    /* Repaint the original footprint before moving the inner face. All
     * feedback uses clipped 32-bit framebuffer primitives, never a full frame. */
    rounded_rect(fb,r.x,r.y,r.w,r.h,radius,color);
    if(hover || down || released){
        uint16_t edge=down?xy_blend(0,color,8):C_PIECE;
        uint16_t face=down?xy_blend(0,color,4):xy_blend(C_PIECE,color,released?2:1);
        rounded_rect(fb,r.x,r.y,r.w,r.h,radius,edge);
        rounded_rect(fb,r.x+3,r.y+3,r.w-6,r.h-6,radius-2,face);
        if(down)fill_rect(fb,r.x+radius,r.y+4,r.w-2*radius,4,edge);
    }
    product_text(fb,r.x+dx+(down?2:0),r.y+dy+(down?3:0),size,C_BG,label);
}
#endif
static void benchmark_progress(volatile uint16_t *fb,const xy_app *a)
{
    fill_rect(fb,112,994,1696,84,C_BG);
    rounded_rect(fb,112,1010,1280,14,6,C_DIVIDER);
    if(a->coremark_progress)fill_rect(fb,112,1010,(int)(1280*a->coremark_progress/1000),14,C_GREEN);
#if XINYI_UI_FEEDBACK
    feedback_button(fb,a,XY_ACTION_CANCEL);
#else
    rounded_rect(fb,xy_layout_coremark_cancel.x,xy_layout_coremark_cancel.y,
        xy_layout_coremark_cancel.w,xy_layout_coremark_cancel.h,10,C_GOLD);
    product_text(fb,xy_layout_coremark_cancel.x+20,xy_layout_coremark_cancel.y+12,24,C_BG,"取消测试 / Esc");
#endif
    product_text(fb,112,1046,24,C_GREEN,a->message);
}
static void benchmark_update(volatile uint16_t *fb,const xy_app *a,const xy_app *old)
{
    /* Keep cancel/text static. The old path repainted ~142k pixels plus
     * antialiased text every progress update through uncached DDR. */
    rounded_rect(fb,112,1010,1280,14,6,C_DIVIDER);
    if(a->coremark_progress)fill_rect(fb,112,1010,(int)(1280*a->coremark_progress/1000),14,C_GREEN);
    if(strcmp(a->message,old->message)){
        fill_rect(fb,112,1046,1696,28,C_BG);
        product_text(fb,112,1046,24,C_GREEN,a->message);
    }
}
#if !XINYI_UI_FEEDBACK
static void log_button(volatile uint16_t *fb,xy_rect r,const char *label)
{
    rounded_rect(fb,r.x,r.y,r.w,r.h,10,C_GREEN);
    product_text(fb,r.x+20,r.y+16,24,C_BG,label);
}
#endif
static void benchmark_output(volatile uint16_t *fb,const xy_app *a)
{
    char text[180],line[XY_CM_LOG_COLUMNS+1];
    unsigned row=0,col=0,first=a->coremark_log_page*XY_CM_LOG_ROWS;
    unsigned pages=(xy_coremark_log_lines(a)+XY_CM_LOG_ROWS-1)/XY_CM_LOG_ROWS;
    fill_screen(fb,C_BG);
    product_text(fb,112,72,32,C_TEXT,"CoreMark 打印信息");
    product_text(fb,112,132,24,C_GREEN,"Actual Linux stdout/stderr. Reference demo creates no execution log.");
    for(size_t i=0;i<=a->coremark_log_used && i<XY_CM_LOG_BYTES;i++){
        int end=i==a->coremark_log_used;
        char ch=end?'\n':a->coremark_log[i];
        if(ch=='\n' || col==XY_CM_LOG_COLUMNS){
            line[col]=0;
            if(row>=first && row<first+XY_CM_LOG_ROWS)
                product_text(fb,112,200+(row-first)*26,16,C_TEXT,line);
            row++;col=0;
            if(row>=first+XY_CM_LOG_ROWS)break;
            if(ch=='\n')continue;
        }
        if(!end)line[col++]=ch;
    }
    if(!a->coremark_log_used)product_text(fb,112,240,24,C_GOLD,"尚无实际测试输出");
    (void)snprintf(text,sizeof(text),"Page %u/%u   %u bytes%s",a->coremark_log_page+1,
        pages?pages:1,
        (unsigned)a->coremark_log_used,a->coremark_log_truncated?" [output truncated]":"");
    product_text(fb,112,916,24,C_GREEN,text);
#if XINYI_UI_FEEDBACK
    feedback_button(fb,a,XY_ACTION_CM_LOG_PREV);
#else
    log_button(fb,xy_layout_cm_log_prev,"上一页");
#endif
#if XINYI_UI_FEEDBACK
    feedback_button(fb,a,XY_ACTION_CM_LOG_NEXT);
#else
    log_button(fb,xy_layout_cm_log_next,"下一页");
#endif
#if XINYI_UI_FEEDBACK
    feedback_button(fb,a,XY_ACTION_CM_LOG_CLOSE);
#else
    log_button(fb,xy_layout_cm_log_close,"返回");
#endif
#if XINYI_UI_FEEDBACK
    if(a->job==XY_COREMARK)feedback_button(fb,a,XY_ACTION_CANCEL);
#else
    if(a->job==XY_COREMARK)log_button(fb,xy_layout_coremark_cancel,"取消测试 / Esc");
#endif
}
static void home(volatile uint16_t *fb,const xy_app *a)
{
    char text[160];
    fill_screen(fb,C_BG);
    product_text(fb,112,114,64,C_TEXT,"芯弈一号");
    product_text(fb,116,206,32,C_GREEN,"单芯片 FPGA 象棋 AI 一体机");
    product_text(fb,116,266,24,C_GOLD,"一片 FPGA · 视觉三模型 / 语音 ASR / 引擎 NNUE");
#if XINYI_UI_FEEDBACK
    feedback_button(fb,a,XY_ACTION_START);
#else
    rounded_rect(fb,xy_layout_home_start.x,xy_layout_home_start.y,
        xy_layout_home_start.w,xy_layout_home_start.h,14,C_GOLD);
    product_text(fb,184,356,32,C_BG,"开始游戏");
#endif
#if XINYI_UI_FEEDBACK
    feedback_button(fb,a,XY_ACTION_COREMARK);
#else
    rounded_rect(fb,xy_layout_home_coremark.x,xy_layout_home_coremark.y,
        xy_layout_home_coremark.w,xy_layout_home_coremark.h,14,C_GREEN);
    product_text(fb,476,356,32,C_BG,"CoreMark 测试");
#endif
#if XINYI_UI_FEEDBACK
    feedback_button(fb,a,XY_ACTION_CM_LOG);
#else
    log_button(fb,xy_layout_home_cm_log,"CoreMark 打印信息");
#endif
#if XINYI_UI_FEEDBACK
    feedback_button(fb,a,XY_ACTION_CM_REFERENCE);
#else
    log_button(fb,xy_layout_home_cm_reference,"参考成绩演示 (10s)");
#endif
    product_card(fb,112,466,544,170,"CPU 性能 · CoreMark/MHz");
    (void)snprintf(text,sizeof(text),"%.6f",xy_coremark_display_score(a));
    product_text(fb,140,516,48,C_GOLD,text);
    product_text(fb,140,586,24,C_GREEN,a->coremark_reference_shown?"参考成绩演示，非本次实测":
        a->coremark_measured?"本次 Linux 实板短测":"main CPU60 ROM 参考，非本次实测");
    product_card(fb,688,466,544,170,"自研 RV32 SoC");
    (void)snprintf(text,sizeof(text),"%uMHz · Linux · 1080p",XINYI_CPU_HZ/1000000u);
    product_text(fb,716,522,32,C_TEXT,text);
    product_text(fb,716,586,24,C_GREEN,"目标集成配置，待实板验收");
    product_card(fb,1264,466,544,170,"单 FPGA 三项 AI");
    product_text(fb,1292,522,32,C_TEXT,"46,365 / 66,000 LUT");
    product_text(fb,1292,586,24,C_GREEN,"main P3 集成资源参考");
    product_card(fb,112,668,1696,270,"量级对比 · 不同配置与工作负载结果可不同");
    product_text(fb,140,722,24,C_GREEN,"方案                  算力载体        功耗量级          三项 AI 能力             独显与散热");
    hline(fb,140,1780,758,1,C_DIVIDER);
    product_text(fb,140,774,24,C_GOLD,"芯弈一号           单颗 FPGA       瓦级目标        视觉 / 语音 / 引擎       无外置 GPU");
    product_text(fb,140,828,24,C_TEXT,"PC + GPU          CPU 与独显      随配置           可部署三项 AI            通常需主动散热");
    product_text(fb,140,882,24,C_TEXT,"普通 MCU           MCU              随器件与负载   受模型和内存约束         通常无独显");
    product_text(fb,118,960,24,C_GREEN,"视觉模型参考 2.1GMAC/拍；功耗为量级描述，非本轮测量");
    if(a->job==XY_COREMARK) {
        benchmark_progress(fb,a);
    } else product_text(fb,118,1012,24,C_GREEN,a->message);
}
static void panel(volatile uint16_t *fb,const xy_app *a)
{
    char text[200];
    rounded_rect(fb,1016,88,812,930,22,C_SHADOW);
    rounded_rect(fb,1012,84,812,930,22,C_PANEL);
    product_text(fb,1052,112,32,C_TEXT,a->mode==XY_COACH?"图像指导 · 红方教练":"语音对战");
    product_text(fb,1052,166,24,C_GREEN,a->mode==XY_COACH?
        "每拍独立为红方荐着 · 麦克风关闭":"人说话走棋，引擎自动应着 · 相机只预览");
    hline(fb,1052,1792,214,1,C_DIVIDER);
    product_card(fb,1052,238,740,a->mode==XY_COACH?140:104,a->mode==XY_COACH?"红方荐着":a->voice_mouse_input?"走法":"听到的原文");
    product_text(fb,1080,290,32,C_GOLD,a->mode==XY_COACH?
        (a->has_recommendation?a->notation:"等待识别与合法红方荐着"):
        (a->voice_heard[0]?a->voice_heard:"等待语音"));
    if(a->mode==XY_COACH) {
        product_card(fb,1052,400,740,160,"图像识别 · 最低单子得分");
        (void)snprintf(text,sizeof(text),"%s    %s",a->current_photo_valid?
            "本拍最低单子得分":"上一拍最低单子得分",a->has_board?"":"--");
        product_text(fb,1080,454,24,C_TEXT,text);
        if(a->has_board) {
            (void)snprintf(text,sizeof(text),"%u.%u%%",a->photo.confidence/10,a->photo.confidence%10);
            product_text(fb,1560,448,32,C_GOLD,text);
        }
        product_text(fb,1080,514,24,C_GREEN,"保留棋子的最低得分，非全盘正确率");
        product_card(fb,1052,582,740,244,"模型资源 · 无外置 GPU");
        if(a->partial_count) {
            const unsigned *p=a->partial_classes;
            product_card(fb,1052,582,740,244,"部分识别 · 尚未定位到棋盘格");
            (void)snprintf(text,sizeof(text),"红：帅%u 仕%u 相%u 马%u 车%u 炮%u 兵%u",p[0],p[1],p[2],p[3],p[4],p[5],p[6]);
            product_text(fb,1080,636,24,C_PIECE,text);
            (void)snprintf(text,sizeof(text),"黑：将%u 士%u 象%u 马%u 车%u 炮%u 卒%u",p[7],p[8],p[9],p[10],p[11],p[12],p[13]);
            product_text(fb,1080,678,24,C_TEXT,text);
            (void)snprintf(text,sizeof(text),"共 %u 个候选；可能有漏识别或误识别",a->partial_count);
            product_text(fb,1080,720,24,C_GOLD,text);
            product_text(fb,1080,766,24,C_GOLD,"请摆正后重拍，暂不生成荐着");
        } else {
        product_text(fb,1080,636,24,C_TEXT,"YOLOv5n · W8A8 · 2.1GMAC/拍");
        product_text(fb,1080,678,24,C_TEXT,"三模型约 2.3MB · main 模型测试参考");
        product_text(fb,1080,720,24,C_TEXT,"NNUE 热态 16.9ms；130.7→16.9ms 约 7.75×");
        product_text(fb,1080,766,24,C_GREEN,"main P3 参考，非本轮实测");
        }
        product_card(fb,1052,848,740,96,"实时");
        (void)snprintf(text,sizeof(text),"本拍自动纠错 %u 处    本拍延迟 %u.%03us",
            a->current_photo_valid?a->photo.corrected_cells:0,a->photo_latency_ms/1000,a->photo_latency_ms%1000);
        product_text(fb,1080,896,24,C_GOLD,a->photo_latency_valid?text:"本拍自动纠错 -- 处    本拍延迟 --");
    } else {
        uint32_t us=a->voice_engine_us;
        char tail[32];
        /* Retain the exact existing win bar, node card and time glyphs.
         * Durations enter as microseconds, never assume the old 27MHz timer
         * is the current CPU/SYS clock. The legacy helper's scale is internal. */
        draw_panel_score(fb,0,1,a->voice_win_rate);
        draw_panel_nodes(fb,a->voice_engine_nodes);
        draw_panel_time_value(fb,us==UINT32_MAX || us>UINT32_MAX/CLINT_TICKS_PER_US?
            XQ_FB_TIME_UNAVAILABLE:us*CLINT_TICKS_PER_US);
        if(!a->voice_engine_stats_valid) {
            fill_rect(fb,1080,574,140,42,C_CARD);
            draw_text(fb,1080,580,"--",3,C_GOLD);
        }
        product_card(fb,1052,646,740,112,"处理结果");
        product_text(fb,1080,702,24,C_TEXT,a->voice_result[0]?a->voice_result:"等待合法命令");
        product_card(fb,1052,780,740,164,"语音会话 · balanced24 / int8 / CTC8");
        if(a->voice_tail_ms==UINT32_MAX || !a->voice_commands)
            (void)snprintf(tail,sizeof(tail),"--");
        else (void)snprintf(tail,sizeof(tail),"%ums",a->voice_tail_ms);
        (void)snprintf(text,sizeof(text),"累计命令成功 %u/%u    尾部延迟 %s",
            a->voice_successes,a->voice_commands,tail);
        product_text(fb,1080,834,24,C_GOLD,text);
        product_text(fb,1080,890,24,C_GREEN,"仅显示实际后端提供的引擎统计");
    }
#if XINYI_UI_FEEDBACK
    feedback_button(fb,a,XY_ACTION_SWITCH);
#else
    rounded_rect(fb,xy_layout_mode_switch.x,xy_layout_mode_switch.y,
        xy_layout_mode_switch.w,xy_layout_mode_switch.h,10,C_GREEN);
    product_text(fb,1080,974,24,C_BG,a->mode==XY_COACH?"切换语音对战":"切换图像指导");
#endif
#if XINYI_UI_FEEDBACK
    feedback_button(fb,a,XY_ACTION_HOME);
#else
    rounded_rect(fb,xy_layout_game_home.x,xy_layout_game_home.y,
        xy_layout_game_home.w,xy_layout_game_home.h,10,C_GOLD);
    product_text(fb,1592,974,24,C_BG,"返回首页");
#endif
    if(a->mode==XY_VOICE) {
#if XINYI_UI_FEEDBACK
    feedback_button(fb,a,XY_ACTION_RESTART);
#else
        rounded_rect(fb,xy_layout_voice_restart.x,xy_layout_voice_restart.y,
            xy_layout_voice_restart.w,xy_layout_voice_restart.h,10,C_GOLD);
        product_text(fb,1380,974,24,C_BG,"重新开始");
#endif
    }
}
#if XINYI_HOME_R13
#include "coremark/reference.h"
#include "xinyi_home_r13.h"
#endif
#if XINYI_BATTLE_R17
_Static_assert(XINYI_HOME_R15 && XINYI_GUI_DOUBLE_BUFFER && XINYI_UI_FEEDBACK && XINYI_COACH_MOVE_AUDIO,
               "Battle pages require r15, two bank histories, feedback and move audio");
#include "xinyi_battle_r17.h"
#endif
#if XINYI_GUI_PAGE_DELTAS
_Static_assert(XINYI_HOME_R15 && XINYI_GUI_DOUBLE_BUFFER && XINYI_UI_FEEDBACK && XINYI_CPU_HZ==60000000u && !XINYI_GUI_RAM_RENDER,"Exact CPU60 page template contract");
#include "xinyi_page_delta.h"
#endif
void xy_fb_invalidate(void)
{
#if XINYI_GUI_DOUBLE_BUFFER
    for(unsigned i=0;i<2;i++)xy_page_caches[i].valid=0;
#else
    xy_valid=0;
#endif
}
void xy_fb_render(const xy_app *a,volatile uint16_t *fb)
{
    volatile uint16_t *destination=fb;
#if XINYI_UI_NAV_DIAG
    uint64_t feedback_started;
    xy_ram_copy_ms=0;memset(xy_nav_cost,0,sizeof(xy_nav_cost));
#endif
 #if !XINYI_BATTLE_R17
    static const xq_search_board_t empty={{0},0};
    const xq_search_board_t *b,*old;
    int selected_from,selected_to,old_from,old_to,square;
 #endif
    int full;
    if(!a || !fb) return;
#if XINYI_GUI_PAIR_DELTAS
    xy16_pair_prepare();
#endif
#if XINYI_GUI_SPANS_R21 && XINYI_GUI_FAST_NAV_R21 && !defined(XINYI_SCALAR_GLYPH_ORACLE)
    xy21_spans_prepare();
#endif
#if XINYI_GUI_LINEAR_R21 && XINYI_GUI_FAST_NAV_R21 && !defined(XINYI_SCALAR_GLYPH_ORACLE)
    xy21_linear_prepare();
#endif
#if XINYI_HOME_R13
    (void)home;(void)benchmark_update;
#endif
#if XINYI_BATTLE_R17
    (void)panel;
#endif
#if XINYI_GUI_DOUBLE_BUFFER
    xy_page_cache *state=xy_page_state(fb);
#define previous_app (state->app)
#define previous_pixels (state->pixels)
#define xy_valid (state->valid)
#if XINYI_UI_FEEDBACK
#define previous_feedback (state->feedback)
#endif
#endif
    full=!xy_valid || fb!=previous_pixels || a->page!=previous_app.page ||
        a->coremark_log_visible!=previous_app.coremark_log_visible;
    reset_clip();
#if XINYI_GUI_PAGE_DELTAS
    int template_painted=0;
#if XINYI_GUI_PAIR_DELTAS
    if(!xy16_pair_enabled() || full || XINYI_GUI_METRIC_DELTAS)
#endif
#if XINYI_UI_NAV_DIAG
    if(xy_page_delta_enabled)
#endif
    {
#if XINYI_GUI_PAIR_DELTAS
        int key=xy16_template_key(a);
        int old_key=xy_valid && fb==previous_pixels?xy16_template_key(&previous_app):-1;
#else
        int key=xy15_template_key(a);
        int old_key=xy_valid && fb==previous_pixels?xy15_template_key(&previous_app):-1;
#endif
        if(key>=0 && (full || old_key!=key
#if XINYI_GUI_METRIC_DELTAS
            || xy19_dynamic_changed(a,&previous_app)
#endif
           )){
            xy15_template_paint(fb,key,old_key,&previous_app,&previous_feedback);
#if XINYI_GUI_METRIC_DELTAS
#if XINYI_UI_NAV_DIAG
            uint64_t overlay_started=xy_nav_clock();
#endif
            xy19_overlay(fb,key,a);
#if XINYI_UI_NAV_DIAG
            xy_nav_cost_finish(3,overlay_started);
#endif
#endif
            template_painted=1;goto frame_feedback;
        }
    }
#endif
    if((a->page==XY_HOME
#if XINYI_HOME_R13
        || a->page==XY_BENCHMARK
#endif
       ) && a->coremark_log_visible) {
        if(full || a->coremark_log_page!=previous_app.coremark_log_page ||
           a->coremark_log_used!=previous_app.coremark_log_used || a->job!=previous_app.job ||
           a->coremark_log_truncated!=previous_app.coremark_log_truncated)
            {fb=xy_ram_begin(destination);benchmark_output(fb,a);}
    } else if(a->page==XY_HOME) {
#if XINYI_HOME_R13
        if(full || a->coremark_measured!=previous_app.coremark_measured ||
           a->coremark_per_mhz!=previous_app.coremark_per_mhz ||
           a->coremark_cpu_hz!=previous_app.coremark_cpu_hz ||
           strcmp(a->coremark_identity,previous_app.coremark_identity) ||
           strcmp(a->message,previous_app.message)){fb=xy_ram_begin(destination);r13_home(fb,a);}
    } else if(a->page==XY_BENCHMARK || a->page==XY_CAMERA_DEBUG){
        if(full || a->job!=previous_app.job || a->coremark_progress!=previous_app.coremark_progress ||
           a->coremark_elapsed_ms!=previous_app.coremark_elapsed_ms ||
           a->coremark_per_mhz!=previous_app.coremark_per_mhz ||
           a->coremark_measured!=previous_app.coremark_measured ||
           a->benchmark_reference_visible!=previous_app.benchmark_reference_visible ||
           a->preview_state!=previous_app.preview_state || strcmp(a->message,previous_app.message)){
            fb=xy_ram_begin(destination);r13_details(fb,a);
        }
#else
        if(full || memcmp(a,&previous_app,sizeof(*a))) {
            if(!full && a->job==XY_COREMARK && previous_app.job==XY_IDLE &&
                a->coremark_per_mhz==previous_app.coremark_per_mhz &&
                a->coremark_reference_shown==previous_app.coremark_reference_shown)
                benchmark_progress(fb,a);
            else if(!full && a->job==XY_COREMARK && previous_app.job==XY_COREMARK &&
                a->coremark_per_mhz==previous_app.coremark_per_mhz &&
                a->coremark_measured==previous_app.coremark_measured)
                benchmark_update(fb,a,&previous_app);
            else {fb=xy_ram_begin(destination);home(fb,a);}
        }
 #endif
    } else {
#if XINYI_BATTLE_R17
        r17_game(fb,a,&previous_app,full);
#else
        b=a->mode==XY_COACH?(a->has_board?&a->photo.board:&empty):
            (a->voice_has_board?&a->voice_board:&empty);
        old=previous_app.mode==XY_COACH?(previous_app.has_board?&previous_app.photo.board:&empty):
            (previous_app.voice_has_board?&previous_app.voice_board:&empty);
        selected_from=a->mode==XY_COACH && a->has_recommendation?a->recommendation.from:-1;
        selected_to=a->mode==XY_COACH && a->has_recommendation?a->recommendation.to:-1;
        old_from=previous_app.mode==XY_COACH && previous_app.has_recommendation?previous_app.recommendation.from:-1;
        old_to=previous_app.mode==XY_COACH && previous_app.has_recommendation?previous_app.recommendation.to:-1;
        if(a->mode==XY_VOICE && a->voice_selected_valid)selected_from=(int)a->voice_selected;
        if(previous_app.mode==XY_VOICE && previous_app.voice_selected_valid)old_from=(int)previous_app.voice_selected;
        if(full) {
            fb=xy_ram_begin(destination);
            fill_screen(fb,C_BG);
            draw_board(fb);
            draw_position(fb,b,selected_from,selected_to);
        } else for(square=0;square<90;++square)
            if(b->squares[square]!=old->squares[square] || square==selected_from ||
                square==selected_to || square==old_from || square==old_to ||
                a->mode!=previous_app.mode || a->photo.corrected[square]!=previous_app.photo.corrected[square])
                redraw_square(fb,b,selected_from,selected_to,square);
        if(selected_to>=0 && !b->squares[selected_to]) {
            int x=BOARD_X+(selected_to%9)*CELL,y=BOARD_Y+(9-selected_to/9)*CELL;
            draw_ring(fb,x,y,42,3,C_GREEN);
        }
        if(a->mode==XY_COACH) for(square=0;square<90;++square)
            if(a->has_board && a->photo.corrected[square]) {
                int x=BOARD_X+(square%9)*CELL,y=BOARD_Y+(9-square/9)*CELL;
                rounded_rect(fb,x-36,y+18,72,24,4,C_GREEN);
                product_text(fb,x-36,y+18,24,C_BG,"已修正");
            }
        if(full || memcmp(a,&previous_app,sizeof(*a))) {
            fill_rect(fb,96,12,850,64,C_BG);
            product_text(fb,96,28,32,C_TEXT,"芯弈一号");
            panel(fb,a);
            fill_rect(fb,96,1040,1728,36,C_BG);
            product_text(fb,96,1042,24,C_GOLD,a->message);
        }
        if(a->mode==XY_COACH && a->geometry_failed) {
            rounded_rect(fb,558,98,368,44,8,C_RED);
            product_text(fb,574,108,24,C_PIECE,"识别失败请重拍");
        } else if(previous_app.geometry_failed && !full) {
            /* Restore the exact textured rectangle after removing the badge. */
            set_clip(550,90,390,56); draw_board(fb); draw_position(fb,b,selected_from,selected_to); reset_clip();
        }
#endif
    }
#if XINYI_GUI_PAGE_DELTAS
frame_feedback:
#endif
#if XINYI_UI_NAV_DIAG
    feedback_started=xy_nav_clock();
#endif
#ifdef XINYI_HOST_PREVIEW
    fill_rect(fb,1160,16,650,48,C_BG);
    product_text(fb,1160,28,24,C_GOLD,"HOST 合成预览 · 无实板测量");
#endif
#if XINYI_UI_FEEDBACK
    if(
#if XINYI_GUI_PAGE_DELTAS
       template_painted ||
#endif
       memcmp(&previous_feedback,&xy_feedback_requested,sizeof(previous_feedback))){
        xy_pointer_target targets[XY_POINTER_TARGETS];unsigned n=xy_pointer_targets(a,targets,XY_POINTER_TARGETS);
        for(unsigned i=0;i<n;i++){
            xy_pointer_event t=targets[i].action;
            if(t==previous_feedback.hover || t==previous_feedback.pressed || t==previous_feedback.released ||
               t==xy_feedback_requested.hover || t==xy_feedback_requested.pressed || t==xy_feedback_requested.released)
                feedback_button(fb,a,t);
        }
    }
#if XINYI_UI_NAV_DIAG
    xy_nav_cost_finish(4,feedback_started);
#endif
    previous_feedback=xy_feedback_requested;
#endif
    xy_ram_publish(destination,fb);
    previous_app=*a; previous_pixels=destination; xy_valid=1;
#if XINYI_GUI_DOUBLE_BUFFER
#if XINYI_UI_FEEDBACK
#undef previous_feedback
#endif
#undef previous_app
#undef previous_pixels
#undef xy_valid
#endif
}
