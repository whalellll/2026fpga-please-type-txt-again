/* Exact CPU60 canonical pages. Other states retain the original renderer. */
#ifndef XINYI_PAGE_DELTA_H
#define XINYI_PAGE_DELTA_H
#include "xinyi_page_templates.h"
#if XINYI_BATTLE_R17
#include "xinyi_battle_home_template_r17.h"
#if XINYI_GUI_FAST_NAV_R21 && !defined(XINYI_SCALAR_GLYPH_ORACLE)
#include "xinyi_game_templates_r21.h"
#if XINYI_GUI_PALETTE_R21
#include "xinyi_game_palette_r21.h"
#endif
#if XINYI_GUI_COMMANDS_R21
#include "xinyi_game_commands_r21.h"
#endif
#endif
/* The legacy page0 includes historical labels and pending ratios. Keep those
 * immutable bytes for flag0; every r17 pair and delta uses its own source-bound
 * scalar home pixels. The board-only old page1 rectangle remains unchanged. */
static const xy15_run *const xy17_pages[4]={xy17_home_page,xy15_page_1,xy20_detail_page_2,xy20_detail_page_3};
#define xy15_pages xy17_pages
#define xy15_page_0 xy17_home_page
#define xy15_page_2 xy20_detail_page_2
#define xy15_page_3 xy20_detail_page_3
#endif
#if XINYI_GUI_PAIR_DELTAS
#include "xinyi_pair_cache.h"
static int xy16_pair_enabled(void)
{
#if XINYI_UI_NAV_DIAG
    return xy_pair_delta_enabled;
#else
    return 1;
#endif
}
#endif
static int xy15_template_microphone(void *context,int enabled)
{(void)context;(void)enabled;return 1;}
static void xy15_template_string_tail(char *s,size_t bytes)
{size_t n=0;while(n<bytes && s[n])n++;if(n<bytes)memset(s+n,0,bytes-n);}
static void xy15_template_normalize(xy_app *a)
{
    memset(&a->backend,0,sizeof(a->backend));a->token=0;
    a->pending_page=XY_HOME;a->pending_mode=XY_COACH;
    a->microphone_ready=0;
    xy15_template_string_tail(a->message,sizeof(a->message));
    xy15_template_string_tail(a->notation,sizeof(a->notation));
}
static int xy15_template_key(const xy_app *app)
{
#if XINYI_BATTLE_R17
    /* page1 contains the historical game layout; never paint it into r17. */
    if(app->page==XY_GAME)return -1;
#endif
    if((unsigned)app->page>=4 || app->mode!=XY_COACH)return -1;
    /* Compare the complete app including result/error/cancellation fields.
     * Only backend identity and non-rendered ownership counters are omitted. */
    xy_backend backend={.microphone=xy15_template_microphone};xy_app actual=*app,expected;
    xy_app_init(&expected,&backend);
    if(app->page && !xy_navigate(&expected,app->page,XY_COACH))return -1;
    xy15_template_normalize(&actual);xy15_template_normalize(&expected);
    return memcmp(&actual,&expected,sizeof(actual))?-1:(int)app->page;
}
#if XINYI_GUI_PAIR_DELTAS
static int xy16_template_key(const xy_app *app)
{
    if(!xy16_pair_enabled() || app->page==XY_GAME)return xy15_template_key(app);
#if XINYI_GUI_METRIC_DELTAS
    if(app->page==XY_BENCHMARK && app->job==XY_COREMARK && !app->coremark_log_visible &&
       !app->benchmark_reference_visible && !app->navigation_pending)return 2;
#endif
    if(app->job!=XY_IDLE || app->cancelling || app->navigation_pending || app->coremark_log_visible)return -1;
#if XINYI_GUI_METRIC_DELTAS
    /* These idle pages have fixed geometry; only the bounded metric/message
     * rectangles below differ from their canonical pixels. */
    if(app->page==XY_HOME)return 0;
    if(app->page==XY_BENCHMARK)return !app->benchmark_reference_visible?2:-1;
    if(app->page==XY_CAMERA_DEBUG)return !app->preview_state?3:-1;
    return -1;
#else
    /* These painters do not read photo/voice results. Test the controls,
     * displayed metrics and footer instead of copying the complete app. */
    if(app->page==XY_HOME){
        return !r13_measured(app) && (!app->message[0] || !strcmp(app->message,"欢迎使用芯弈一号"))?0:-1;
    }
    if(strcmp(app->message,"空格拍照，每拍独立为红方荐着"))return -1;
    if(app->page==XY_BENCHMARK)return !r13_measured(app) && !app->benchmark_reference_visible?2:-1;
    if(app->page==XY_CAMERA_DEBUG)return !app->preview_state?3:-1;
    return -1;
#endif
}
#endif
static void xy15_template_fill(volatile uint32_t *out,unsigned count,uint32_t value)
{
    while(count>=8){out[0]=value;out[1]=value;out[2]=value;out[3]=value;
        out[4]=value;out[5]=value;out[6]=value;out[7]=value;out+=8;count-=8;}
    while(count--)*out++=value;
}
#if XINYI_GUI_LOAD8_R21
/* Command data is immutable ordinary RAM/ROM and cannot overlap the writable
 * GUI bank. Stage eight aligned reads before stores to avoid interleaving the
 * SoC load/store path. Volatile reads retain that ordering in all producers. */
static inline void xy21_copy8(volatile uint32_t *out,const volatile uint32_t *source)
{
    uint32_t v0=source[0],v1=source[1],v2=source[2],v3=source[3];
    uint32_t v4=source[4],v5=source[5],v6=source[6],v7=source[7];
    out[0]=v0;out[1]=v1;out[2]=v2;out[3]=v3;
    out[4]=v4;out[5]=v5;out[6]=v6;out[7]=v7;
}
#endif
#if XINYI_GUI_FAST_NAV_R21 && !defined(XINYI_SCALAR_GLYPH_ORACLE)
#if XINYI_GUI_LINEAR_R21
#include <stdlib.h>
static uint32_t *xy21_linear[4];
static unsigned xy21_linear_attempted;
static void xy21_linear_prepare(void)
{
    if(xy21_linear_attempted)return;
    xy21_linear_attempted=1;
#ifdef XINYI_GAME_LINEAR_TEST_OOM
    uint32_t *data=NULL;
#else
    uint32_t *data=malloc(8303040u);
#endif
    if(!data)return;
    const xy15_run *parts[4]={xy21_game_left,xy21_game_right_0,xy21_game_right_1,xy21_game_right_2};
    for(unsigned part=0;part<4;part++){
        const xy15_run *run=parts[part];unsigned words=(part?481u:479u)*1080u,at=0;
        xy21_linear[part]=data;
        while(at<words){unsigned count=run->count;
            for(unsigned i=0;i<count;i++)data[at+i]=run->value;
            at+=count;run++;
        }
        data+=words;
    }
}
static void xy21_linear_copy(volatile uint32_t *out,const uint32_t *source,unsigned count)
{
    while(count>=8){
        out[0]=source[0];out[1]=source[1];out[2]=source[2];out[3]=source[3];
        out[4]=source[4];out[5]=source[5];out[6]=source[6];out[7]=source[7];
        source+=8;out+=8;count-=8;
    }
    while(count--)*out++=*source++;
}
static void xy21_linear_paint(volatile uint16_t *fb,unsigned mode)
{
    volatile uint32_t *out=(volatile uint32_t *)(uintptr_t)fb;
    const uint32_t *left=xy21_linear[0],*right=xy21_linear[mode+1];
    for(unsigned row=0;row<1080;row++){
        xy21_linear_copy(out,left,479);xy21_linear_copy(out+479,right,481);
        out+=960;left+=479;right+=481;
    }
}
#endif
static void xy21_game_rect(volatile uint16_t *fb,const xy15_run *run,unsigned first,unsigned width)
{
    volatile uint32_t *out=(volatile uint32_t *)(uintptr_t)fb;unsigned left=0,value=0;
    for(unsigned row=0;row<1080;row++){
        unsigned at=row*960u+first,end=at+width;
        while(at<end){
            if(!left){left=run->count;value=run->value;run++;}
            unsigned count=left<end-at?left:end-at;
            xy15_template_fill(out+at,count,value);at+=count;left-=count;
        }
    }
}
#if XINYI_GUI_SPANS_R21
#include <stdlib.h>
typedef struct {uint32_t bounds,value;} xy21_span;
static xy21_span *xy21_spans[4];
static unsigned xy21_singles[4],xy21_repeats[4],xy21_span_attempted;
static void xy21_spans_prepare(void)
{
    if(xy21_span_attempted)return;
    xy21_span_attempted=1;
    const xy15_run *parts[4]={xy21_game_left,xy21_game_right_0,xy21_game_right_1,xy21_game_right_2};
    for(unsigned pass=0;pass<2;pass++){
        size_t total=0;
        for(unsigned part=0;part<4;part++){
            const xy15_run *run=parts[part];unsigned left=0,value=0,one=0,many=0;
            for(unsigned row=0;row<1080;row++){
                unsigned at=row*960u+(part?479u:0u),end=at+(part?481u:479u);
                while(at<end){
                    if(!left){left=run->count;value=run->value;run++;}
                    unsigned count=left<end-at?left:end-at;
                    if(pass){xy21_span item={at|((count-1u)<<20),value};
                        if(count==1)xy21_spans[part][one++]=item;
                        else xy21_spans[part][xy21_singles[part]+many++]=item;
                    }else if(count==1)one++;else many++;
                    at+=count;left-=count;
                }
            }
            if(!pass){xy21_singles[part]=one;xy21_repeats[part]=many;total+=(size_t)one+many;}
        }
        if(!pass){
#ifdef XINYI_GAME_SPANS_TEST_OOM
            xy21_span *data=NULL;
#else
            xy21_span *data=malloc(total*sizeof(*data));
#endif
            if(!data)return;
            for(unsigned part=0;part<4;part++){
                xy21_spans[part]=data;data+=xy21_singles[part]+xy21_repeats[part];
            }
        }
    }
}
static void xy21_spans_paint(volatile uint16_t *fb,unsigned part)
{
    volatile uint32_t *out=(volatile uint32_t *)(uintptr_t)fb;
    const xy21_span *p=xy21_spans[part];unsigned n=xy21_singles[part];
    while(n>=4){
        out[p[0].bounds]=p[0].value;out[p[1].bounds]=p[1].value;
        out[p[2].bounds]=p[2].value;out[p[3].bounds]=p[3].value;p+=4;n-=4;
    }
    while(n--){out[p->bounds]=p->value;p++;}
    for(n=0;n<xy21_repeats[part];n++,p++)
        xy15_template_fill(out+(p->bounds&0xfffffu),(p->bounds>>20)+1u,p->value);
}
#endif
#if XINYI_GUI_ROW_NAV_R22
#if XINYI_GUI_ROW_SCALAR_R23
#include "xinyi_game_row_scalar_r23.h"
#else
#include "xinyi_game_row_r22.h"
#endif
#endif
static void xy21_game_base(volatile uint16_t *fb,unsigned mode)
{
#if XINYI_GUI_ROW_NAV_R22
#if XINYI_GUI_ROW_SCALAR_R23
    xy23_game_rows(fb,mode);return;
#else
    xy22_game_rows(fb,mode);return;
#endif
#endif
#if XINYI_GUI_PALETTE_R21
    volatile uint32_t *palette_out=(volatile uint32_t *)(uintptr_t)fb;
    for(unsigned part=0;part<2;part++){
        unsigned key=part?mode+1:0;
        const uint16_t *code=xy21_codes[key];const uint32_t *palette=xy21_palettes[key];
        for(unsigned row=0;row<1080;row++){
            unsigned at=row*960u+(part?479u:0u),end=row*960u+(part?960u:479u);
            while(at<end){
                uint32_t packed=*code++,count=packed>>12,value=palette[packed&4095u];
                if(!count)count=*code++;
                xy15_template_fill(palette_out+at,count,value);at+=count;
            }
        }
    }
    return;
#endif
#if XINYI_GUI_COMMANDS_R21
    volatile uint32_t *out=(volatile uint32_t *)(uintptr_t)fb;
    for(unsigned part=0;part<2;part++){
      const uint32_t *commands=xy21_commands[part?mode+1:0];
      while(*commands!=UINT32_MAX){
        unsigned offset=*commands++,kind=*commands++,count=kind&0x7fffffffu;
        volatile uint32_t *destination=out+offset;
        if(kind&0x80000000u)xy15_template_fill(destination,count,*commands++);
        else{
            while(count>=8){
#if XINYI_GUI_LOAD8_R21
                xy21_copy8(destination,commands);
#else
                destination[0]=commands[0];destination[1]=commands[1];destination[2]=commands[2];destination[3]=commands[3];
                destination[4]=commands[4];destination[5]=commands[5];destination[6]=commands[6];destination[7]=commands[7];
#endif
                destination+=8;commands+=8;count-=8;
            }
            while(count--)*destination++=*commands++;
        }
      }
    }
    return;
#endif
#if XINYI_GUI_LINEAR_R21
    if(xy21_linear[0]){xy21_linear_paint(fb,mode);return;}
#endif
#if XINYI_GUI_SPANS_R21
    if(xy21_spans[0]){xy21_spans_paint(fb,0);xy21_spans_paint(fb,mode+1);return;}
#endif
    xy21_game_rect(fb,xy21_game_left,0,479);
    xy21_game_rect(fb,xy21_game_right[mode],479,481);
}
static const xy_app *xy21_game_canonical(unsigned mode)
{
    static xy_app canonical[3];static unsigned ready;
    if(!(ready&(1u<<mode))){
        xy_backend backend={.microphone=xy15_template_microphone};
        xy_app_init(canonical+mode,&backend);
        (void)xy_navigate(canonical+mode,XY_GAME,(xy_mode)mode);
        canonical[mode].has_board=canonical[mode].voice_has_board=0;
        ready|=1u<<mode;
    }
    return canonical+mode;
}
#endif
#if XINYI_GUI_METRIC_DELTAS
_Static_assert(XINYI_BATTLE_R17 && XINYI_GUI_PAIR_DELTAS,"Metric deltas require battle/pair cache");
static void xy19_restore(volatile uint16_t *fb,int key,unsigned x,unsigned y,unsigned w,unsigned h)
{
    volatile uint32_t *out=(volatile uint32_t *)(uintptr_t)fb;
    const xy15_run *run=xy19_rows[key][y].run;
    unsigned at=xy19_rows[key][y].word,limit=(y+h)*960u;
    while(at<limit){
        unsigned end=at+run->count,begin=at<y*960u?y*960u:at;
        if(end>limit)end=limit;
        for(unsigned row=begin/960u;row*960u<end;row++){
            unsigned left=row*960u+x/2u,right=row*960u+(x+w)/2u;
            if(left<begin){left=begin;}if(right>end){right=end;}
            if(left<right)xy15_template_fill(out+left,right-left,run->value);
        }
        at+=run->count;run++;
    }
}
static void xy19_restore_dynamic(volatile uint16_t *fb,int key,const xy_app *old)
{
    if(key==2 && old->job==XY_COREMARK){
        xy19_restore(fb,2,320,612,1280,96);
        xy19_restore(fb,2,248,832,1426,68);
        xy19_restore(fb,2,1430,980,370,58);
    }
    if(r13_measured(old)){
        if(key==2)xy19_restore(fb,2,320,408,1280,48);
    }
    const char *base=key==0?"欢迎使用芯弈一号":"空格拍照，每拍独立为红方荐着";
    if(strcmp(old->message,base))xy19_restore(fb,key,key==0?672:0,940,key==0?576:1920,32);
}
static int xy19_dynamic_changed(const xy_app *a,const xy_app *old)
{
    return a->coremark_measured!=old->coremark_measured ||
        a->coremark_per_mhz!=old->coremark_per_mhz || a->coremark_cpu_hz!=old->coremark_cpu_hz ||
        strcmp(a->coremark_identity,old->coremark_identity) || strcmp(a->message,old->message) ||
        (a->page==XY_BENCHMARK && (a->job!=old->job || a->cancelling!=old->cancelling ||
         a->coremark_progress!=old->coremark_progress || a->coremark_elapsed_ms!=old->coremark_elapsed_ms));
}
static void xy19_overlay(volatile uint16_t *fb,int key,const xy_app *a)
{
    if(key==2 && r13_measured(a)){
        char text[160];fill_rect(fb,320,408,1280,48,R13_PAPER);
        (void)snprintf(text,sizeof(text),"CoreMark/MHz    %.6f",a->coremark_per_mhz);
        product_text(fb,320,408,32,R13_INK,text);
    }
    if(key==2 && a->job==XY_COREMARK){
        char text[160];rounded_rect(fb,320,612,1280,24,10,R13_LINE);
        if(a->coremark_progress)rounded_rect(fb,320,612,(int)(1280u*a->coremark_progress/1000u),24,10,R13_GOLD);
        (void)snprintf(text,sizeof(text),"%u%%    %us",a->coremark_progress/10,a->coremark_elapsed_ms/1000);
        product_text(fb,320,660,24,R13_INK,text);
        r19_background_region(fb,248,832,1426,68);
        r19_background_region(fb,1430,980,370,58);
        xy_pointer_target targets[XY_POINTER_TARGETS];unsigned n=xy_pointer_targets(a,targets,XY_POINTER_TARGETS);
        for(unsigned i=0;i<n;i++)feedback_button(fb,a,targets[i].action);
    }
    /* The taller home AI cards now cross this row. Restore the home message
     * only in its center column; detail pages use the original art background. */
#if XINYI_GUI_FAST_NAV_R21
    const char *canonical_message=key==0?"欢迎使用芯弈一号":"空格拍照，每拍独立为红方荐着";
    if(!strcmp(a->message,canonical_message))return;
#endif
    if(key==0)xy19_restore(fb,0,672,940,576,32);
    else r19_background_region(fb,0,940,1920,32);
    if(key==0){
        if(a->message[0] && strcmp(a->message,"欢迎使用芯弈一号")){
            set_clip(672,940,576,32);
            r13_center(fb,960,940,24,R13_RED,a->message);
            reset_clip();
        }
    }else product_text(fb,248,942,24,R13_MUTED,a->message);
}
#endif
#if XINYI_BATTLE_R17 && !defined(XINYI_SCALAR_GLYPH_ORACLE)
static void xy17_board_base(volatile uint16_t *fb)
{
    /* Reuse only the unchanged empty-board rectangle from the immutable
     * scalar page data. Top branding, footer and the entire old panel are
     * outside this region. The r17 panel is always rendered independently.
     * Each background word is written once, instead of overpainting three
     * overlapping wooden rectangles after a full-screen clear. */
    fill_rect(fb,958,0,962,1080,C_BG);
    fill_rect(fb,0,0,958,88,C_BG);
    fill_rect(fb,0,1038,958,42,C_BG);
    volatile uint32_t *out=(volatile uint32_t *)(uintptr_t)fb;
    const xy15_run *run=xy15_page_1;unsigned at=0;
    while(at<1038u*960u){
        unsigned end=at+run->count;
        unsigned begin=at<88u*960u?88u*960u:at;
        unsigned limit=end<1038u*960u?end:1038u*960u;
        for(unsigned row=begin/960u;row*960u<limit;row++){
            unsigned left=row*960u,right=left+479u;
            if(left<begin)left=begin;
            if(right>limit)right=limit;
            if(left<right)xy15_template_fill(out+left,right-left,run->value);
        }
        at=end;run++;
    }
}
#endif
static void xy15_template_restore_feedback(volatile uint32_t *out,int key,const xy_app *app,const xy_feedback_view *feedback)
{
    xy_pointer_target targets[XY_POINTER_TARGETS];unsigned n=xy_pointer_targets(app,targets,XY_POINTER_TARGETS);
    unsigned x0=960,x1=0,y0=1080,y1=0;
    for(unsigned i=0;i<n;i++){
        unsigned action=targets[i].action;
        if(action!=feedback->hover && action!=feedback->pressed && action!=feedback->released)continue;
        unsigned left=targets[i].x/2,right=(targets[i].x+targets[i].w+1)/2;
        if(left<x0)x0=left;
        if(right>x1)x1=right;
        if(targets[i].y<y0)y0=targets[i].y;
        if(targets[i].y+targets[i].h>y1)y1=targets[i].y+targets[i].h;
    }
    if(x0>=x1 || y0>=y1)return;
    const xy15_run *run=xy15_pages[key];unsigned at=0;
    while(at<y1*960){
        unsigned end=at+run->count,begin=at<y0*960?y0*960:at;
        if(end>y1*960)end=y1*960;
        for(unsigned row=begin/960;row*960<end;row++){
            unsigned left=row*960+x0,right=row*960+x1;
            if(left<begin)left=begin;
            if(right>end)right=end;
            if(left<right)xy15_template_fill(out+left,right-left,run->value);
        }
        at+=run->count;run++;
    }
}
static void xy15_template_paint(volatile uint16_t *fb,int key,int old_key,const xy_app *old_app,const xy_feedback_view *feedback)
{
    volatile uint32_t *out=(volatile uint32_t *)(uintptr_t)fb;
#if XINYI_UI_NAV_DIAG
    uint64_t phase_started=xy_nav_clock();
#endif
    if(old_key>=0)xy15_template_restore_feedback(out,old_key,old_app,feedback);
#if XINYI_UI_NAV_DIAG
    xy_nav_cost_finish(0,phase_started);phase_started=xy_nav_clock();
#endif
#if XINYI_GUI_METRIC_DELTAS
    if(old_key>=0)xy19_restore_dynamic(fb,old_key,old_app);
#if XINYI_UI_NAV_DIAG
    xy_nav_cost_finish(1,phase_started);phase_started=xy_nav_clock();
#endif
    if(old_key==key)return;
#endif
#if XINYI_GUI_PAIR_DELTAS
    const uint32_t *commands=old_key>=0?xy16_pairs[(unsigned)old_key*4u+(unsigned)key]:NULL;
    if(commands && xy16_pair_enabled()){
#ifdef XINYI_PAIR_CACHE_TEST_STATS
        xy16_pair_cache_hits++;
#endif
        while(*commands!=UINT32_MAX){
            unsigned offset=*commands++,kind=*commands++,count=kind&0x7fffffffu;
            volatile uint32_t *destination=out+offset;
            if(kind&0x80000000u)xy15_template_fill(destination,count,*commands++);
            else{
                while(count>=8){
#if XINYI_GUI_LOAD8_R21
                    xy21_copy8(destination,commands);
#else
                    destination[0]=commands[0];destination[1]=commands[1];destination[2]=commands[2];destination[3]=commands[3];
                    destination[4]=commands[4];destination[5]=commands[5];destination[6]=commands[6];destination[7]=commands[7];
#endif
                    destination+=8;commands+=8;count-=8;
                }
                while(count--)*destination++=*commands++;
            }
        }
#if XINYI_UI_NAV_DIAG
        xy_nav_cost_finish(2,phase_started);
#endif
        return;
    }
#endif
    const xy15_run *next=xy15_pages[key],*old=old_key>=0?xy15_pages[old_key]:NULL;
    unsigned at=0,left=next->count,old_left=old?old->count:VIDEO_FB_FRAME_BYTES/4;
    while(at<VIDEO_FB_FRAME_BYTES/4){
        unsigned count=left<old_left?left:old_left;
        if(!old || next->value!=old->value)xy15_template_fill(out+at,count,next->value);
        at+=count;left-=count;old_left-=count;
        if(!left && at<VIDEO_FB_FRAME_BYTES/4){next++;left=next->count;}
        if(old && !old_left && at<VIDEO_FB_FRAME_BYTES/4){old++;old_left=old->count;}
    }
#if XINYI_UI_NAV_DIAG
    xy_nav_cost_finish(2,phase_started);
#endif
}
#endif
