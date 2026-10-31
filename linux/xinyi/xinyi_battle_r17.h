/* Native battle pages. Drawing stays on the caller's inactive framebuffer.
 * Compare rendered values, not ownership/telemetry bytes in the whole app. */
#ifndef XINYI_BATTLE_R17_RENDER_H
#define XINYI_BATTLE_R17_RENDER_H
#include "xinyi_battle_metrics_r17.h"
#include "xinyi_battle_speedups_r17.h"
#define R17_TRAY ((uint16_t)((((235u>>3)<<11)|((220u>>2)<<5)|(199u>>3))))
#if XINYI_GUI_PAGE_DELTAS && !defined(XINYI_SCALAR_GLYPH_ORACLE)
static void xy17_board_base(volatile uint16_t *);
#endif

static const char *r17_mode_name(xy_mode mode)
{return mode==XY_COACH?"图像识别辅助对弈":mode==XY_VOICE?"语音对战":"键鼠对战";}
static int r17_button(volatile uint16_t *fb,const xy_app *a,xy_pointer_event action)
{
    if(a->page!=XY_GAME)return 0;
    xy_pointer_event choices[4];unsigned count=0;
    if(a->mode!=XY_COACH)choices[count++]=XY_ACTION_IMAGE;
    if(a->mode!=XY_VOICE)choices[count++]=XY_ACTION_VOICE;
    if(a->mode!=XY_KEYBOARD)choices[count++]=XY_ACTION_KEYBOARD;
    choices[count++]=XY_ACTION_RESTART;choices[count++]=XY_ACTION_HOME;
    for(unsigned i=0;i<count;i++)if(choices[i]==action){
        xy_rect r=xy_layout_battle_nav[i];
        const char *label=action==XY_ACTION_IMAGE?"图像识别":action==XY_ACTION_VOICE?"语音对战":
            action==XY_ACTION_KEYBOARD?"键鼠对战":action==XY_ACTION_RESTART?"重新开始":"返回首页";
        int enabled=xy_pointer_action(a,r.x+r.w/2,r.y+r.h/2)==action;
        int down=enabled && xy_feedback_requested.pressed==action;
        int active=enabled && (xy_feedback_requested.hover==action ||
            xy_feedback_requested.released==action);
        uint16_t face=down?xy_blend(C_GOLD,C_PIECE,3):active?R13_PAPER:C_PIECE;
        uint16_t ink=enabled?C_TEXT:R13_MUTED;
        int x=(int)r.x+72,y=(int)r.y+72;
        /* Restore the complete bounded footprint, including the old shadow. */
        fill_rect(fb,r.x,r.y,r.w,r.h+4,R17_TRAY);
        draw_disc(fb,x,y+3,71,C_SHADOW);
        draw_disc(fb,x,y,71,face);
        draw_ring(fb,x,y,70,2,down?C_GOLD:C_BORDER);
        draw_ring(fb,x,y,64,1,active?C_GOLD:C_TEXT);
        r13_center(fb,x+(down?1:0),y-12+(down?2:0),24,ink,label);
        return 1;
    }
    return 0;
}

static void r17_status(const xy_app *a,char out[XY_TEXT_BYTES])
{
    const char *message=a->message;
    if(a->cancelling){(void)snprintf(out,XY_TEXT_BYTES,"正在安全停止，请稍后");return;}
    if(!strcmp(message,"红方教练荐着"))message="荐着已就绪";
    else if(!strcmp(message,"正在处理语音走法"))message="正在处理走法";
    else if(!strcmp(message,"空格拍照，每拍独立为红方荐着"))message="空格拍照 · Esc 取消识别";
    else if(a->mode==XY_KEYBOARD &&
       (strstr(message,"方向键移动") || strstr(message,"鼠标点选")))message="等待红方走棋";
    if(a->mode==XY_COACH && a->estimated_position){
        (void)snprintf(out,XY_TEXT_BYTES,"估计盘面，请核对 · %.144s",message);return;
    }
    if(a->speech_e2e_over_budget){
        (void)snprintf(out,XY_TEXT_BYTES,"播报用时超过1秒 · %.144s",message);return;
    }
    (void)snprintf(out,XY_TEXT_BYTES,"%s",message);
}
static void r17_value_column(volatile uint16_t *fb,int x,int y,int width,unsigned ms,int valid)
{
    char text[48];
    if(valid)(void)snprintf(text,sizeof(text),"%u.%03u s",ms/1000,ms%1000);
    else (void)snprintf(text,sizeof(text),"-- s");
    fill_rect(fb,x,y,width,40,C_CARD);
    product_text(fb,x,y+4,32,C_GOLD,text);
}
static void r17_value(volatile uint16_t *fb,int y,unsigned ms,int valid)
{r17_value_column(fb,1080,y,684,ms,valid);}
static uint16_t r17_status_ink(const xy_app *a)
{return a->cancelling || a->speech_e2e_over_budget ||
    (a->mode==XY_COACH && (a->estimated_position || a->geometry_failed))?C_GOLD:C_GREEN;}
static void r17_model_speedup(volatile uint16_t *fb,int top,int height,
    const char *value,const char *scope)
{
    /* One bounded area shows one operator ratio. The scope is always visible,
     * including while a new hardware/software pairing is still unmeasured. */
    fill_rect(fb,1564,top,1,height,C_DIVIDER);
    r13_center(fb,1668,top,24,C_GREEN,"加速比");
    r13_center(fb,1668,top+32,32,C_GOLD,value);
    r13_center(fb,1668,top+72,24,C_GREEN,scope);
}
static void r17_probability(volatile uint16_t *fb,const xy_app *a)
{
    int keyboard=a->mode==XY_KEYBOARD;
    int top=keyboard?232:460,bar=keyboard?300:524;
    char text[40];int valid=a->voice_engine_stats_valid && a->voice_win_rate<=1000u;
    if(valid)(void)snprintf(text,sizeof(text),"%u.%u%%",a->voice_win_rate/10,a->voice_win_rate%10);
    else (void)snprintf(text,sizeof(text),"--");
    fill_rect(fb,1456,top+16,300,48,C_CARD);
    product_text(fb,1456,top+20,32,C_GOLD,text);
    rounded_rect(fb,1080,bar,684,14,6,C_DIVIDER);
    if(valid && a->voice_win_rate){
        set_clip(1080,bar,(int)(684u*a->voice_win_rate/1000u),14);
        rounded_rect(fb,1080,bar,684,14,6,C_RED);reset_clip();
    }
}
static void r17_panel_static(volatile uint16_t *fb,const xy_app *a)
{
    rounded_rect(fb,1016,88,812,930,22,C_SHADOW);
    rounded_rect(fb,1012,84,812,930,22,C_PANEL);
    product_text(fb,1052,112,32,C_TEXT,r17_mode_name(a->mode));
    product_text(fb,1052,166,24,C_GREEN,a->mode==XY_COACH?
        "拍摄实际棋盘，辅助红方下一步走棋":a->mode==XY_VOICE?
        "红方语音操作，黑方AI操作":"红方键鼠操作，黑方AI操作");
    hline(fb,1052,1792,214,1,C_DIVIDER);
    if(a->mode==XY_COACH){
        product_card(fb,1052,232,740,100,"红方推荐下一步走法");
        product_card(fb,1052,348,740,100,"图像识别端到端延迟");
        product_card(fb,1052,464,740,56,"");
        product_card(fb,1052,536,740,252,"模型与加速器");
        int row=r20_lines(fb,1080,590,28,C_TEXT,XY20_IMAGE_MODEL);
        row=r20_lines(fb,1080,row,28,C_TEXT,XY20_IMAGE_ACCELERATOR_WRAP);
        product_text(fb,1080,row,24,C_TEXT,XY17_IMAGE_PARAMETERS);
        product_text(fb,1080,row+28,24,C_TEXT,"LUT：5,762，含 LUTRAM");
        r17_model_speedup(fb,634,140,XY17_IMAGE_SPEEDUP,XY17_IMAGE_SPEEDUP_SCOPE);
    }else if(a->mode==XY_VOICE){
        product_card(fb,1052,232,740,84,"语音识别结果");
        product_card(fb,1052,332,740,112,"语音识别端到端延迟");
        product_text(fb,1440,352,24,C_GREEN,"黑方AI推理用时");
        fill_rect(fb,1408,350,1,76,C_DIVIDER);
        product_card(fb,1052,460,740,92,"红方胜率");
        product_card(fb,1052,568,740,220,"模型与加速器");
        int row=r20_lines(fb,1080,624,32,C_TEXT,XY20_VOICE_MODEL);
        row=r20_lines(fb,1080,row,32,C_TEXT,XY20_VOICE_ACCELERATOR);
        product_text(fb,1080,row,24,C_TEXT,"参数量：11,782");
        product_text(fb,1080,row+32,24,C_TEXT,"LUT：2,458，含 LUTRAM");
        r17_model_speedup(fb,632,132,XY17_ACTIVE_VOICE_SPEEDUP,XY17_VOICE_SPEEDUP_SCOPE);
    }else{
        product_card(fb,1052,232,740,104,"红方胜率");
        product_card(fb,1052,390,740,126,"黑方AI推理用时");
        product_card(fb,1052,536,740,252,"模型与加速器");
        int row=r20_lines(fb,1080,590,28,C_TEXT,XY20_NNUE_MODEL);
        row=r20_lines(fb,1080,row,28,C_TEXT,XY20_NNUE_ACCELERATOR);
        product_text(fb,1080,row,24,C_TEXT,XY17_PIKAFISH_PARAMETERS);
        product_text(fb,1080,row+28,24,C_TEXT,"LUT：3,462，含 LUTRAM");
        r17_model_speedup(fb,634,140,XY17_NNUE_SPEEDUP,XY17_NNUE_SPEEDUP_SCOPE);
    }
    /* One shared tray holds the short status and all four chess discs. */
    rounded_rect(fb,1052,804,740,204,24,C_BORDER);
    rounded_rect(fb,1054,806,736,200,22,R17_TRAY);
    hline(fb,1080,1764,850,1,C_DIVIDER);
    const xy_pointer_event actions[]={XY_ACTION_IMAGE,XY_ACTION_VOICE,
        XY_ACTION_KEYBOARD,XY_ACTION_RESTART,XY_ACTION_HOME};
    for(unsigned i=0;i<sizeof(actions)/sizeof(actions[0]);i++)(void)r17_button(fb,a,actions[i]);
}
static void r17_panel(volatile uint16_t *fb,const xy_app *a,const xy_app *old,int full)
{
    char text[XY_TEXT_BYTES],previous[XY_TEXT_BYTES];
    int all=full || a->mode!=old->mode;
    if(all)r17_panel_static(fb,a);
    if(a->mode==XY_COACH){
        if(all || a->has_recommendation!=old->has_recommendation || strcmp(a->notation,old->notation)){
            fill_rect(fb,1080,282,684,44,C_CARD);
            set_clip(1080,282,684,44);
            product_text(fb,1080,288,32,C_GOLD,a->has_recommendation?a->notation:"--");reset_clip();
        }
        if(all || a->image_e2e_valid!=old->image_e2e_valid || a->image_e2e_ms!=old->image_e2e_ms)
            r17_value(fb,400,a->image_e2e_ms,a->image_e2e_valid);
        if(all || a->current_photo_valid!=old->current_photo_valid || a->photo.corrected_cells!=old->photo.corrected_cells){
            if(a->current_photo_valid)(void)snprintf(text,sizeof(text),"本拍自动纠错 %u 处",a->photo.corrected_cells);
            else (void)snprintf(text,sizeof(text),"本拍自动纠错 -- 处");
            fill_rect(fb,1080,480,684,32,C_CARD);product_text(fb,1080,484,24,C_TEXT,text);
        }
    }else{
        if(a->mode==XY_VOICE){
            if(all || strcmp(a->voice_heard,old->voice_heard)){
                fill_rect(fb,1080,280,684,36,C_CARD);set_clip(1080,280,684,36);
                product_text(fb,1080,282,32,C_GOLD,a->voice_heard[0]?a->voice_heard:"--");reset_clip();
            }
            if(all || a->voice_e2e_valid!=old->voice_e2e_valid || a->voice_e2e_ms!=old->voice_e2e_ms)
                r17_value_column(fb,1080,386,300,a->voice_e2e_ms,a->voice_e2e_valid);
        }
        if(all || a->voice_engine_stats_valid!=old->voice_engine_stats_valid || a->voice_win_rate!=old->voice_win_rate)
            r17_probability(fb,a);
        if(all || a->voice_engine_stats_valid!=old->voice_engine_stats_valid || a->voice_engine_us!=old->voice_engine_us){
            unsigned us=a->voice_engine_us;int valid=a->voice_engine_stats_valid && us!=UINT32_MAX;
            if(valid)(void)snprintf(text,sizeof(text),"%u.%03u s",us/1000000u,(us/1000u)%1000u);
            else (void)snprintf(text,sizeof(text),"-- s");
            int y=a->mode==XY_KEYBOARD?448:386,x=a->mode==XY_KEYBOARD?1080:1440;
            fill_rect(fb,x,y,a->mode==XY_KEYBOARD?684:324,40,C_CARD);product_text(fb,x,y+4,32,C_GOLD,text);
        }
    }
    r17_status(a,text);r17_status(old,previous);
    if(all || strcmp(text,previous) || r17_status_ink(a)!=r17_status_ink(old)){
        fill_rect(fb,1080,816,684,30,R17_TRAY);set_clip(1080,816,684,30);
        product_text(fb,1080,820,24,r17_status_ink(a),text);
        reset_clip();
    }
    /* A job/cancel transition can change enabled navigation feedback without
     * changing its geometric footprint or forcing the other panel fields. */
    if(!all && (a->cancelling!=old->cancelling || a->navigation_pending!=old->navigation_pending)){
        const xy_pointer_event actions[]={XY_ACTION_IMAGE,XY_ACTION_VOICE,XY_ACTION_KEYBOARD,XY_ACTION_RESTART,XY_ACTION_HOME};
        for(unsigned i=0;i<sizeof(actions)/sizeof(actions[0]);i++)(void)r17_button(fb,a,actions[i]);
    }
}
static int r17_from(const xy_app *a)
{return a->mode==XY_COACH?(a->has_recommendation?(int)a->recommendation.from:-1):
    a->voice_selected_valid?(int)a->voice_selected:-1;}
static int r17_to(const xy_app *a)
{return a->mode==XY_COACH && a->has_recommendation?(int)a->recommendation.to:-1;}
static int r17_focus(const xy_app *a)
{return a->mode==XY_KEYBOARD && a->keyboard_focus_visible?(int)a->keyboard_focus:-1;}
static int r17_corrected(const xy_app *a,unsigned square)
{return a->mode==XY_COACH && a->has_board && a->photo.corrected[square];}
static void r17_board_marks(volatile uint16_t *fb,const xy_app *a,unsigned square)
{
    int x=BOARD_X+(int)(square%9)*CELL,y=BOARD_Y+(9-(int)(square/9))*CELL;
    if(r17_to(a)==(int)square && !a->photo.board.squares[square])draw_ring(fb,x,y,42,3,C_GREEN);
    if(r17_corrected(a,square)){
        rounded_rect(fb,x-36,y+18,72,24,4,C_GREEN);product_text(fb,x-36,y+18,24,C_BG,"已修正");
    }
    if(r17_focus(a)==(int)square){
        for(unsigned edge=0;edge<2;edge++){
            int left=x-42+(int)edge*72;
            fill_rect(fb,left,y-42,12,2,C_GOLD);fill_rect(fb,left,y+40,12,2,C_GOLD);
            fill_rect(fb,x-42+(int)edge*82,y-42,2,12,C_GOLD);
            fill_rect(fb,x-42+(int)edge*82,y+30,2,12,C_GOLD);
        }
    }
}
#if XINYI_GUI_FAST_NAV_R21 && !defined(XINYI_SCALAR_GLYPH_ORACLE)
static void xy21_game_base(volatile uint16_t *,unsigned);
static const xy_app *xy21_game_canonical(unsigned);
#endif
static void r17_game(volatile uint16_t *fb,const xy_app *a,const xy_app *old,int full)
{
#if XINYI_UI_NAV_DIAG
    uint64_t game_started=xy_nav_clock();
#endif
    static const xq_search_board_t empty={{0},0};
    const xq_search_board_t *b=a->mode==XY_COACH?(a->has_board?&a->photo.board:&empty):
        (a->voice_has_board?&a->voice_board:&empty);
    const xq_search_board_t *previous=old->mode==XY_COACH?(old->has_board?&old->photo.board:&empty):
        (old->voice_has_board?&old->voice_board:&empty);
    int from=r17_from(a),to=r17_to(a),old_from=r17_from(old),old_to=r17_to(old);
    int focus=r17_focus(a),old_focus=r17_focus(old);
#if XINYI_GUI_FAST_NAV_R21 && !defined(XINYI_SCALAR_GLYPH_ORACLE)
    int cached=full && (unsigned)a->mode<3 && a->job==XY_IDLE &&
        !a->cancelling && !a->navigation_pending;
#endif
    if(full){
#if XINYI_GUI_FAST_NAV_R21 && !defined(XINYI_SCALAR_GLYPH_ORACLE)
        if(cached)xy21_game_base(fb,(unsigned)a->mode);
        else
#endif
#if XINYI_GUI_PAGE_DELTAS && !defined(XINYI_SCALAR_GLYPH_ORACLE)
        xy17_board_base(fb);
#else
        fill_screen(fb,C_BG);draw_board(fb);
#endif
        draw_position(fb,b,from,to);
    }
    for(unsigned square=0;square<90;square++){
        int changed=full || b->squares[square]!=previous->squares[square] ||
            (from!=old_from && ((int)square==from || (int)square==old_from)) ||
            (to!=old_to && ((int)square==to || (int)square==old_to)) ||
            (focus!=old_focus && ((int)square==focus || (int)square==old_focus)) ||
            r17_corrected(a,square)!=r17_corrected(old,square);
        if(changed){
            if(!full)redraw_square(fb,b,from,to,(int)square);
            r17_board_marks(fb,a,square);
        }
    }
#if XINYI_UI_NAV_DIAG
    xy_nav_cost_finish(2,game_started);game_started=xy_nav_clock();
#endif
#if XINYI_GUI_FAST_NAV_R21 && !defined(XINYI_SCALAR_GLYPH_ORACLE)
    if(cached){
        r17_panel(fb,a,xy21_game_canonical((unsigned)a->mode),0);
        const xy_pointer_event actions[]={XY_ACTION_IMAGE,XY_ACTION_VOICE,XY_ACTION_KEYBOARD,XY_ACTION_RESTART,XY_ACTION_HOME};
        for(unsigned i=0;i<sizeof(actions)/sizeof(actions[0]);i++)
            if(actions[i]==xy_feedback_requested.hover || actions[i]==xy_feedback_requested.pressed ||
               actions[i]==xy_feedback_requested.released)(void)r17_button(fb,a,actions[i]);
    }
    else
#endif
    r17_panel(fb,a,old,full);
#if XINYI_UI_NAV_DIAG
    xy_nav_cost_finish(3,game_started);
#endif
}
#endif
