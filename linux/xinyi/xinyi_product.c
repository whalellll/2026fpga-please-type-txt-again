#include "xinyi_product.h"
#include "xinyi_layout.h"
#include "coremark/reference.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static unsigned type_of(uint8_t p) { return p & 7u; }
static unsigned side_of(uint8_t p) { return (p & SIDE_BLACK) != 0; }
static int absolute(int x) { return x < 0 ? -x : x; }
static void text_copy(char *out, size_t bytes, const char *in)
{
    if (bytes) (void)snprintf(out, bytes, "%s", in ? in : "");
}
static unsigned next_token(xy_app *a)
{
    if (++a->token == 0) ++a->token;
    return a->token;
}
unsigned xy_pointer_targets(const xy_app *a,xy_pointer_target *out,unsigned cap)
{
    xy_pointer_event actions[XY_POINTER_TARGETS];
    xy_rect rects[XY_POINTER_TARGETS];
    unsigned n=0,i;
    if(!a || !out || !cap || a->cancelling || a->navigation_pending)return 0;
    if((a->page==XY_HOME
#if XINYI_HOME_R13
        || a->page==XY_BENCHMARK
#endif
       ) && a->coremark_log_visible) {
        actions[n]=XY_ACTION_CM_LOG_PREV;rects[n++]=xy_layout_cm_log_prev;
        actions[n]=XY_ACTION_CM_LOG_NEXT;rects[n++]=xy_layout_cm_log_next;
        actions[n]=XY_ACTION_CM_LOG_CLOSE;rects[n++]=xy_layout_cm_log_close;
        if(a->job==XY_COREMARK){actions[n]=XY_ACTION_CANCEL;rects[n++]=xy_layout_coremark_cancel;}
    }
#if XINYI_HOME_R13
    else if(a->page==XY_HOME && a->job==XY_IDLE){
        actions[n]=XY_ACTION_START;rects[n++]=xy_layout_home_start;
        actions[n]=XY_ACTION_COREMARK;rects[n++]=xy_layout_home_coremark;
        actions[n]=XY_ACTION_CAMERA;rects[n++]=xy_layout_home_camera;
        actions[n]=XY_ACTION_EXIT;rects[n++]=xy_layout_home_exit;
    } else if(a->page==XY_BENCHMARK){
        if(a->job==XY_IDLE){
            actions[n]=XY_ACTION_CM_RUN;rects[n++]=xy_layout_cm_run;
            actions[n]=XY_ACTION_CM_REFERENCE;rects[n++]=xy_layout_home_cm_reference;
        }else if(a->job==XY_COREMARK){actions[n]=XY_ACTION_CANCEL;rects[n++]=xy_layout_coremark_cancel;}
        actions[n]=XY_ACTION_CM_LOG;rects[n++]=xy_layout_home_cm_log;
        actions[n]=XY_ACTION_HOME;rects[n++]=xy_layout_detail_home;
    } else if(a->page==XY_CAMERA_DEBUG && !a->preview_state){
        actions[n]=XY_ACTION_PREVIEW;rects[n++]=xy_layout_preview_start;
        actions[n]=XY_ACTION_HOME;rects[n++]=xy_layout_detail_home;
    }
#else
    else if(a->page==XY_HOME) {
        if(a->job==XY_COREMARK) {
            actions[n]=XY_ACTION_CANCEL;rects[n++]=xy_layout_coremark_cancel;
        } else if(a->job==XY_IDLE) {
            actions[n]=XY_ACTION_START;rects[n++]=xy_layout_home_start;
            actions[n]=XY_ACTION_COREMARK;rects[n++]=xy_layout_home_coremark;
            actions[n]=XY_ACTION_CM_REFERENCE;rects[n++]=xy_layout_home_cm_reference;
        }
        actions[n]=XY_ACTION_CM_LOG;rects[n++]=xy_layout_home_cm_log;
    }
#endif
    else if(a->page==XY_GAME) {
#if XINYI_BATTLE_R17
        static const xy_pointer_event modes[3]={XY_ACTION_IMAGE,XY_ACTION_VOICE,XY_ACTION_KEYBOARD};
        for(unsigned mode=0;mode<3;mode++)if(mode!=(unsigned)a->mode){actions[n]=modes[mode];rects[n]=xy_layout_battle_nav[n];n++;}
        actions[n]=XY_ACTION_RESTART;rects[n]=xy_layout_battle_nav[n];n++;
        actions[n]=XY_ACTION_HOME;rects[n]=xy_layout_battle_nav[n];n++;
#else
        actions[n]=XY_ACTION_SWITCH;rects[n++]=xy_layout_mode_switch;
        actions[n]=XY_ACTION_HOME;rects[n++]=xy_layout_game_home;
        if(a->mode==XY_VOICE){actions[n]=XY_ACTION_RESTART;rects[n++]=xy_layout_voice_restart;}
#endif
    }
    if(n>cap)n=cap;
    for(i=0;i<n;++i)out[i]=(xy_pointer_target){actions[i],rects[i].x,rects[i].y,rects[i].w,rects[i].h};
    return n;
}
xy_pointer_event xy_pointer_action(const xy_app *a,unsigned x,unsigned y)
{
    xy_pointer_target target[XY_POINTER_TARGETS];
    unsigned i,n;
    if(x>=1920 || y>=1080)return XY_ACTION_NONE;
    n=xy_pointer_targets(a,target,XY_POINTER_TARGETS);
    for(i=0;i<n;++i)if(x>=target[i].x && x-target[i].x<target[i].w &&
        y>=target[i].y && y-target[i].y<target[i].h){
#if XINYI_BATTLE_R17
        if(a->page==XY_GAME){
            int dx=(int)x-(int)(target[i].x+target[i].w/2),dy=(int)y-(int)(target[i].y+target[i].h/2);
            if(dx*dx+dy*dy>(int)(target[i].w/2)*(int)(target[i].w/2))continue;
        }
#endif
        return target[i].action;
    }
    return XY_ACTION_NONE;
}
int xy_board_square(unsigned x,unsigned y,unsigned *square)
{
    const unsigned left=XY_BOARD_X-XY_BOARD_CELL/2,top=XY_BOARD_Y-XY_BOARD_CELL/2;
    if(!square || x<left || y<top || x>=left+9*XY_BOARD_CELL || y>=top+10*XY_BOARD_CELL)return 0;
    *square=(9-(y-top)/XY_BOARD_CELL)*9+(x-left)/XY_BOARD_CELL;
    return 1;
}
static int placement(unsigned type, unsigned side, unsigned file, unsigned rank)
{
    unsigned r = side ? 9u - rank : rank;
    if (type == PIECE_K) return file >= 3 && file <= 5 && r <= 2;
    if (type == PIECE_A)
        return (r == 0 || r == 2) ? (file == 3 || file == 5) :
               (r == 1 && file == 4);
    if (type == PIECE_B)
        return ((r == 0 || r == 4) && (file == 2 || file == 6)) ||
               (r == 2 && (file == 0 || file == 4 || file == 8));
    if (type == PIECE_P) return r >= 3 && (r >= 5 || file % 2 == 0);
    return 1;
}
static int attacks(const xq_search_board_t *b, unsigned from, unsigned to)
{
    unsigned p = b->squares[from], type = type_of((uint8_t)p);
    int fx = (int)(from % 9), fy = (int)(from / 9);
    int tx = (int)(to % 9), ty = (int)(to / 9);
    int dx = tx - fx, dy = ty - fy, ax = absolute(dx), ay = absolute(dy);
    int step, at, occupied = 0;
    if (type == PIECE_R || type == PIECE_C || type == PIECE_K) {
        if (dx && dy) return 0;
        step = dx ? (dx > 0 ? 1 : -1) : (dy > 0 ? 9 : -9);
        for (at = (int)from + step; at != (int)to; at += step)
            occupied += b->squares[at] != 0;
        if (type == PIECE_R) return occupied == 0;
        if (type == PIECE_C) return occupied == 1;
        return occupied == 0 && (ax + ay == 1 || dx == 0);
    }
    if (type == PIECE_N) {
        int leg = (int)from;
        if (ax == 2 && ay == 1) leg += dx > 0 ? 1 : -1;
        else if (ax == 1 && ay == 2) leg += dy > 0 ? 9 : -9;
        else return 0;
        return b->squares[leg] == 0;
    }
    if (type == PIECE_P) {
        int forward = side_of((uint8_t)p) ? -1 : 1;
        int crossed = side_of((uint8_t)p) ? fy <= 4 : fy >= 5;
        return (dx == 0 && dy == forward) || (crossed && dy == 0 && ax == 1);
    }
    /* Kings are in different palaces, outside the reach of A/B. */
    return 0;
}
static xy_position_reason position_reason(const xq_search_board_t *b)
{
    int king[2] = {-1, -1};
    unsigned square;
    xq_search_move_t moves[XQ_SEARCH_MAX_MOVES];
    for (square = 0; square < 90; ++square) {
        uint8_t p = b->squares[square];
        unsigned side = side_of(p), type = type_of(p);
        if (!p) continue;
        if (type == PIECE_K) king[side] = (int)square;
        if (!placement(type, side, square % 9, square / 9))
            return XY_POSITION_PIECE_PLACEMENT;
    }
    if (king[0] < 0 || king[1] < 0) return XY_POSITION_MISSING_KING;
    if (king[0] % 9 == king[1] % 9 && attacks(b, (unsigned)king[0],
                                             (unsigned)king[1]))
        return XY_POSITION_FACING_KINGS;
    /* A red-to-move engine position cannot already have black in check.
     * Keep the photo on screen, without inventing a turn or deleting pieces. */
    for (square = 0; square < 90; ++square)
        if (b->squares[square] && !side_of(b->squares[square]) &&
            attacks(b, square, (unsigned)king[1]))
            return XY_POSITION_BLACK_IN_CHECK;
    if (xq_search_legal_moves(b, moves, XQ_SEARCH_MAX_MOVES) <= 0)
        return XY_POSITION_NO_RED_MOVE;
    return XY_POSITION_VALID;
}

static float confidence_at(const xy_detection *in,const float *scores,unsigned i)
{return scores?scores[i]:(float)in[i].confidence;}
static int repair_impl(const xy_detection *in,const float *scores,unsigned count,xy_repair_result *out)
{
    static const unsigned limits[7] = {1, 2, 2, 2, 2, 2, 5};
    int winner[90];
    unsigned i, c;
    xy_repair_result r;
    if (!out) return 0;
    memset(&r, 0, sizeof(r));
    r.reason = XY_POSITION_BAD_INPUT;
    if (count > XY_MAX_DETECTIONS || (count && !in)) { *out = r; return 0; }
    for (i = 0; i < 90; ++i) winner[i] = -1;
    /* Validate all inputs before accepting any deletion or board update. */
    for (i = 0; i < count; ++i)
        if (in[i].class_id >= 14 || in[i].file >= 9 || in[i].rank >= 10 ||
            in[i].confidence > 1000 || (scores && (!isfinite(scores[i]) ||
            scores[i]<.05f || scores[i]>1.f ||
            (unsigned)floor((double)scores[i]*1000.)!=in[i].confidence))) { *out = r; return 0; }
    for (i = 0; i < count; ++i) {
        unsigned square = in[i].rank * 9u + in[i].file;
        if(!placement(in[i].class_id%7u+1u,in[i].class_id>=7u,in[i].file,in[i].rank)) {
            ++r.removed_count;r.corrected[square]=1;continue;
        }
        int old = winner[square];
        if (old < 0) winner[square] = (int)i;
        else {
            ++r.removed_count;
            r.corrected[square] = 1;
            if (confidence_at(in,scores,i) > confidence_at(in,scores,(unsigned)old)) winner[square] = (int)i;
        }
    }
    for (c = 0; c < 14; ++c) {
        unsigned n = 0;
        for (i = 0; i < 90; ++i)
            n += winner[i] >= 0 && in[winner[i]].class_id == c;
        while (n > limits[c % 7]) {
            int worst = -1;
            for (i = 0; i < 90; ++i)
                if (winner[i] >= 0 && in[winner[i]].class_id == c &&
                    (worst < 0 || confidence_at(in,scores,(unsigned)winner[i]) <
                     confidence_at(in,scores,(unsigned)winner[worst]) ||
                     (confidence_at(in,scores,(unsigned)winner[i]) == confidence_at(in,scores,(unsigned)winner[worst]) &&
                      winner[i] > winner[worst]))) worst = (int)i;
            winner[worst] = -1;
            ++r.removed_count;
            r.corrected[worst] = 1;
            --n;
        }
    }
    /* Minimum retained piece fused score in permille; not board accuracy. */
    r.confidence = count ? 1000 : 0;
    for (i = 0; i < 90; ++i) {
        r.corrected_cells += r.corrected[i] != 0;
        if (winner[i] >= 0) {
            const xy_detection *d = &in[winner[i]];
            r.board.squares[i] = (uint8_t)(d->class_id % 7u + 1u +
                                           (d->class_id >= 7u ? SIDE_BLACK : 0));
            if (r.confidence > d->confidence) r.confidence = d->confidence;
        }
    }
    r.board.side = 0; /* Stateless red coach, every capture independently. */
    r.reason = position_reason(&r.board);
    *out = r;
    return 1;
}
int xy_repair(const xy_detection *in,unsigned count,xy_repair_result *out)
{return repair_impl(in,NULL,count,out);}
static int scored_copy(const xy_scored_detection *in,unsigned count,xy_detection *pieces,float *scores)
{
    if(count>XY_MAX_DETECTIONS || (count && !in))return 0;
    for(unsigned i=0;i<count;++i){pieces[i]=(xy_detection){in[i].class_id,in[i].file,in[i].rank,in[i].confidence};scores[i]=in[i].score;}
    return 1;
}
int xy_repair_scored(const xy_scored_detection *in,unsigned count,xy_repair_result *out)
{
    xy_detection pieces[XY_MAX_DETECTIONS];float scores[XY_MAX_DETECTIONS];
    if(!scored_copy(in,count,pieces,scores))return repair_impl(NULL,NULL,1,out);
    return repair_impl(pieces,scores,count,out);
}

const char *xy_position_reason_text(xy_position_reason reason)
{
    switch (reason) {
    case XY_POSITION_VALID: return "局面有效";
    case XY_POSITION_BAD_INPUT: return "识别数据校验失败";
    case XY_POSITION_MISSING_KING: return "缺少帅或将";
    case XY_POSITION_PIECE_PLACEMENT: return "棋子位置异常";
    case XY_POSITION_FACING_KINGS: return "将帅照面";
    case XY_POSITION_BLACK_IN_CHECK: return "红方荐着局面异常：黑方已被将军";
    case XY_POSITION_NO_RED_MOVE: return "红方无合法走法";
    }
    return "局面异常";
}
static int microphone(xy_app *a, int enabled)
{
    if (a->microphone_ready && a->microphone_enabled == enabled) return 1;
    if (!a->backend.microphone || !a->backend.microphone(a->backend.context, enabled)) {
        text_copy(a->message, sizeof(a->message), "音频输入切换失败");
        return 0;
    }
    a->microphone_enabled = enabled;
    a->microphone_ready = 1;
    return 1;
}
void xy_app_init(xy_app *a, const xy_backend *backend)
{
    memset(a, 0, sizeof(*a));
    if (backend) a->backend = *backend;
    a->page = XY_HOME;
    a->mode = XY_COACH;
    a->voice_win_rate = a->voice_engine_us = UINT32_MAX;
    a->voice_tail_ms = UINT32_MAX;
#if XINYI_BATTLE_R17
    a->keyboard_focus=4;
#endif
    a->coremark_per_mhz = XY_CM_REFERENCE_MEAN;
    a->coremark_cpu_hz = 60000000;
    text_copy(a->coremark_identity, sizeof(a->coremark_identity),
              "main P3 ROM BRAM 6565ad37 reference; not current Linux measurement");
    text_copy(a->message, sizeof(a->message), "欢迎使用芯弈一号");
    /* The adapter must initialize the physical microphone to closed before
     * mounting this screen, and prove the off transition through this hook. */
    if (!microphone(a, 0))
        text_copy(a->message, sizeof(a->message), "麦克风关闭未确认，硬件入口未就绪");
}
static int apply_navigation(xy_app *a, xy_page page, xy_mode mode)
{
    if (!microphone(a, page == XY_GAME && mode == XY_VOICE)) return 0;
    a->voice_selected_valid=0;
    a->page = page;
    a->mode = mode;
#if XINYI_BATTLE_R17
    a->keyboard_focus_visible=0;
#endif
    a->has_recommendation = 0;
    text_copy(a->notation, sizeof(a->notation), "");
    text_copy(a->message, sizeof(a->message), page == XY_HOME ? "欢迎使用芯弈一号" :
               mode == XY_COACH ? "空格拍照，每拍独立为红方荐着" :
#if XINYI_BATTLE_R17
               mode==XY_KEYBOARD?"点击棋子后点落点，或方向键与回车走棋":
#endif
               "请说出您的走法");
    return 1;
}
int xy_navigate(xy_app *a, xy_page page, xy_mode mode)
{
    if (!a || (unsigned)page >
#if XINYI_HOME_R13
        XY_CAMERA_DEBUG
#else
        XY_GAME
#endif
        || (unsigned)mode >
#if XINYI_BATTLE_R17
        XY_KEYBOARD ||
#else
        XY_VOICE ||
#endif
        a->navigation_pending || a->cancelling) return 0;
    if (a->job != XY_IDLE) {
        a->pending_page = page;
        a->pending_mode = mode;
        a->navigation_pending = 1;
        return xy_cancel(a);
    }
    return apply_navigation(a, page, mode);
}
int xy_capture_begin(xy_app *a)
{
    if (!a || a->page != XY_GAME || a->mode != XY_COACH || a->job != XY_IDLE ||
        a->cancelling || !a->backend.capture || !microphone(a, 0)) return 0;
    next_token(a);
    a->job = XY_CAPTURE;
    a->has_recommendation = 0;
    a->geometry_failed = 0;
    a->photo_latency_valid = 0;
#if XINYI_BATTLE_R17
    a->image_e2e_valid=0;a->image_e2e_ms=0;
#endif
    a->current_photo_valid = 0;
    a->partial_count=0;memset(a->partial_classes,0,sizeof(a->partial_classes));
    a->estimated_position=0;
    text_copy(a->notation, sizeof(a->notation), "");
    text_copy(a->message, sizeof(a->message), "正在识别，请稍后，请勿重复按键");
    if (!a->backend.capture(a->backend.context, a->token)) {
        a->job = XY_IDLE;
        text_copy(a->message, sizeof(a->message), "相机任务未启动，请重拍");
        return 0;
    }
    return 1;
}
static int capture_complete_impl(xy_app *a, uint32_t token, int geometry_ok,
                        const xy_detection *pieces, unsigned count,
                        const float *scores,unsigned latency_ms)
{
    xy_repair_result r;
    if (!a || token != a->token || a->job != XY_CAPTURE || a->cancelling) return 0;
    a->photo_latency_ms = latency_ms;
    a->photo_latency_valid = 1;
    a->job = XY_IDLE;
    if (!geometry_ok || !repair_impl(pieces,scores,count,&r)) {
        a->geometry_failed = 1;
        text_copy(a->message, sizeof(a->message), "识别失败请重拍");
        return 1;
    }
    a->photo = r;
    a->has_board = 1;
    a->current_photo_valid = 1;
    a->geometry_failed = 0;
#if XINYI_BATTLE_R17
    if(!++a->image_generation)++a->image_generation;
#endif
    if (r.reason != XY_POSITION_VALID) {
        text_copy(a->message, sizeof(a->message), "局面异常未能荐着，请重拍");
        return 1;
    }
    a->job = XY_RECOMMEND;
    text_copy(a->message, sizeof(a->message), "盘面已更新，正在为红方荐着");
    if (!a->backend.recommend || !a->backend.recommend(a->backend.context,
                                                     token, &a->photo.board)) {
        a->job = XY_IDLE;
        text_copy(a->message, sizeof(a->message), "荐着服务未就绪，请重试");
    }
    return 1;
}
int xy_capture_partial(xy_app *a,uint32_t token,const unsigned classes[14],unsigned count,unsigned latency_ms)
{
    unsigned total=0;
    if(!a || !classes || !count || count>XY_MAX_DETECTIONS || token!=a->token || a->job!=XY_CAPTURE || a->cancelling)return 0;
    for(unsigned i=0;i<14;i++){if(classes[i]>count)return 0;total+=classes[i];}
    if(total!=count || !capture_complete_impl(a,token,0,NULL,0,NULL,latency_ms))return 0;
    a->partial_count=count;memcpy(a->partial_classes,classes,sizeof(a->partial_classes));
    text_copy(a->message,sizeof(a->message),"已显示部分棋子候选；棋盘定位未通过，请摆正后重拍");return 1;
}
int xy_capture_complete(xy_app *a,uint32_t token,int geometry_ok,
    const xy_detection *pieces,unsigned count,unsigned latency_ms)
{return capture_complete_impl(a,token,geometry_ok,pieces,count,NULL,latency_ms);}
int xy_capture_complete_scored(xy_app *a,uint32_t token,int geometry_ok,
    const xy_scored_detection *in,unsigned count,unsigned latency_ms)
{
    xy_detection pieces[XY_MAX_DETECTIONS];float scores[XY_MAX_DETECTIONS];
    if(!scored_copy(in,count,pieces,scores))return capture_complete_impl(a,token,0,NULL,0,NULL,latency_ms);
    return capture_complete_impl(a,token,geometry_ok,pieces,count,scores,latency_ms);
}
int xy_capture_estimated(xy_app *a,uint32_t token,const xy_scored_detection *in,unsigned count,unsigned latency_ms)
{
    if(!a || token!=a->token || a->job!=XY_CAPTURE || a->cancelling)return 0;
    a->estimated_position=1;
    return xy_capture_complete_scored(a,token,1,in,count,latency_ms);
}
int xy_recommend_complete(xy_app *a, uint32_t token, int okay,
                          xq_search_move_t move, const char *notation)
{
    if (!a || token != a->token || a->job != XY_RECOMMEND || a->cancelling) return 0;
    a->job = XY_IDLE;
    if (!okay || !notation || !notation[0] ||
        !xq_search_is_legal(&a->photo.board, move)) {
        text_copy(a->message, sizeof(a->message), "未能取得合法红方荐着，请重拍");
        return 1;
    }
    a->recommendation = move;
    a->has_recommendation = 1;
    text_copy(a->notation, sizeof(a->notation), notation);
    text_copy(a->message, sizeof(a->message), "红方教练荐着");
    if (a->backend.speak) {
        a->job = XY_ANNOUNCE;
        a->backend.speak(a->backend.context, a->notation);
    }
    return 1;
}
int xy_announce_complete(xy_app *a,uint32_t token,int okay)
{
    if (!a || token!=a->token || a->job!=XY_ANNOUNCE || a->cancelling) return 0;
    a->job=XY_IDLE;
    text_copy(a->message,sizeof(a->message),okay?"红方教练荐着":"荐着已显示，语音播报失败");
    return 1;
}
int xy_voice_begin(xy_app *a, const char *text)
{
    if (!a || !text || !*text || a->page != XY_GAME ||
#if XINYI_BATTLE_R17
        (a->mode!=XY_VOICE && a->mode!=XY_KEYBOARD) ||
        (a->mode==XY_VOICE && !a->microphone_enabled) ||
#else
        a->mode != XY_VOICE || !a->microphone_enabled ||
#endif
        a->job != XY_IDLE || !a->backend.voice_command)
        return 0;
    next_token(a);
    a->job = XY_VOICE_COMMAND;
    a->voice_selected_valid=a->voice_mouse_input=0;
    text_copy(a->voice_heard, sizeof(a->voice_heard), text);
    text_copy(a->message, sizeof(a->message), "正在处理语音走法");
    if (!a->backend.voice_command(a->backend.context, a->token, text)) {
        a->job = XY_IDLE;
        text_copy(a->message, sizeof(a->message), "语音任务未启动");
        return 0;
    }
    ++a->voice_commands;
    return 1;
}
int xy_photo_elapsed(xy_app *a, uint32_t token, unsigned elapsed_ms)
{
    if (!a || token != a->token || a->page != XY_GAME || a->mode != XY_COACH ||
        a->cancelling || (a->job != XY_IDLE && a->job != XY_RECOMMEND && a->job != XY_ANNOUNCE) ||
        (a->photo_latency_valid && elapsed_ms < a->photo_latency_ms)) return 0;
    a->photo_latency_ms = elapsed_ms;
    a->photo_latency_valid = 1;
    return 1;
}
int xy_voice_complete(xy_app *a, uint32_t token, int okay,
                      const xq_search_board_t *board, const char *result,
                      unsigned tail_ms)
{
    if (!a || token != a->token || a->job != XY_VOICE_COMMAND || a->cancelling)
        return 0;
    a->job = XY_IDLE;
    a->voice_successes += okay != 0;
    a->voice_tail_ms = tail_ms;
    text_copy(a->voice_result, sizeof(a->voice_result), result);
    text_copy(a->message, sizeof(a->message), okay ? "走法已执行，请继续" : "未能执行，请重说");
    /* voice_2 adapter owns the human-move/engine-reply game semantics. */
    if (okay && board) {
        a->voice_board = *board;
        a->voice_has_board = 1;
    }
    return 1;
}
int xy_cancel(xy_app *a)
{
    if (!a || a->job == XY_IDLE || a->cancelling) return 0;
    a->cancelling = 1;
    text_copy(a->message, sizeof(a->message), "正在安全停止，请稍后");
    if (a->backend.cancel) a->backend.cancel(a->backend.context, a->job, a->token);
    return 1;
}
int xy_voice_engine_stats(xy_app *a, uint32_t token, uint32_t rate,
                          uint32_t nodes, uint32_t elapsed_us)
{
    if (!a || token != a->token || a->page != XY_GAME ||
#if XINYI_BATTLE_R17
        (a->mode!=XY_VOICE && a->mode!=XY_KEYBOARD) ||
#else
        a->mode != XY_VOICE ||
#endif
        a->cancelling || (rate > 1000 && rate != UINT32_MAX)) return 0;
    a->voice_win_rate = rate;
    a->voice_engine_nodes = nodes;
    a->voice_engine_us = elapsed_us;
    a->voice_engine_stats_valid = 1;
    return 1;
}
int xy_cancel_complete(xy_app *a, uint32_t token)
{
    int pending;
    if (!a || token != a->token || !a->cancelling) return 0;
    a->job = XY_IDLE;
    a->cancelling = 0;
    a->has_recommendation = 0;
    (void)next_token(a); /* All late callbacks, including telemetry, expire. */
    pending = a->navigation_pending;
    a->navigation_pending = 0;
    if (pending) return apply_navigation(a, a->pending_page, a->pending_mode);
    text_copy(a->message, sizeof(a->message), "已取消，可以重试");
    return 1;
}
int xy_voice_reset_presentation(xy_app *a)
{
    if(!a || a->page!=XY_HOME || a->job!=XY_IDLE || a->microphone_enabled ||
       a->cancelling || a->navigation_pending)return 0;
    a->voice_heard[0]=a->voice_result[0]=0;
    a->voice_selected_valid=a->voice_mouse_input=0;
    a->voice_commands=a->voice_successes=a->voice_engine_nodes=0;
    a->voice_tail_ms=a->voice_win_rate=a->voice_engine_us=UINT32_MAX;
    a->voice_engine_stats_valid=0;
#if XINYI_BATTLE_R17
    a->voice_e2e_valid=a->voice_started_valid=0;a->voice_e2e_ms=0;
    a->voice_generation=a->voice_displayed_generation=0;
    a->keyboard_focus=4;a->keyboard_focus_visible=0;
    a->speech_e2e_valid=a->speech_e2e_over_budget=0;
#endif
    return 1;
}
#if XINYI_BATTLE_R17
int xy_image_reset_presentation(xy_app *a)
{
    if(!a || a->page!=XY_HOME || a->job!=XY_IDLE || a->microphone_enabled || a->cancelling || a->navigation_pending)return 0;
    (void)next_token(a);
    a->has_board=a->current_photo_valid=a->geometry_failed=a->has_recommendation=0;
    a->estimated_position=0;a->partial_count=0;
    memset(&a->photo,0,sizeof(a->photo));memset(a->partial_classes,0,sizeof(a->partial_classes));
    a->notation[0]=0;a->photo_latency_valid=a->image_e2e_valid=0;
    a->photo_latency_ms=a->image_e2e_ms=0;a->speech_e2e_valid=a->speech_e2e_over_budget=0;
    return 1;
}
#endif
int xy_coremark_begin(xy_app *a, xy_coremark_origin origin)
{
    if (!a || (a->page != XY_HOME
#if XINYI_HOME_R13
               && a->page != XY_BENCHMARK
#endif
              ) || a->job != XY_IDLE || !a->backend.coremark ||
        (origin != XY_COREMARK_BOARD && origin != XY_COREMARK_MOCK && origin != XY_COREMARK_REFERENCE) ||
        a->coremark_log_visible ||
        !microphone(a, 0)) return 0;
    next_token(a);
    a->job = XY_COREMARK;
    a->coremark_origin = origin;
    a->coremark_progress = a->coremark_elapsed_ms = 0;
    text_copy(a->message, sizeof(a->message), origin == XY_COREMARK_BOARD ?
               "CoreMark 实板短测约 30–60 秒" : origin==XY_COREMARK_REFERENCE ?
               "参考成绩演示，十秒后显示历史成绩" : "模拟进度演示，不产生板测成绩");
    if(origin==XY_COREMARK_BOARD){a->coremark_log[0]=0;a->coremark_log_used=0;
        a->coremark_log_truncated=0;a->coremark_log_page=0;}
    if (!a->backend.coremark(a->backend.context, a->token, origin==XY_COREMARK_REFERENCE?10000:45000)) {
        a->job = XY_IDLE;
        text_copy(a->message, sizeof(a->message), "CoreMark 后端未就绪");
        return 0;
    }
    return 1;
}
int xy_coremark_progress(xy_app *a, uint32_t token, unsigned elapsed,
                         unsigned permille)
{
    if (!a || token != a->token || a->job != XY_COREMARK || a->cancelling ||
        permille > 1000 || permille < a->coremark_progress ||
        elapsed < a->coremark_elapsed_ms) return 0;
    a->coremark_progress = permille;
    a->coremark_elapsed_ms = elapsed;
    return 1;
}
int xy_coremark_complete(xy_app *a, uint32_t token, int crc_valid,
                         uint64_t iterations, uint64_t ticks,
                         uint32_t timer_hz, uint32_t cpu_hz,
                         const char *identity)
{
    double elapsed, value;
    if (!a || token != a->token || a->job != XY_COREMARK || a->cancelling) return 0;
    a->job = XY_IDLE;
    a->coremark_progress = 1000;
    if(a->coremark_origin==XY_COREMARK_REFERENCE) {
        a->job=XY_COREMARK;return 0; /* Only the elapsed-time presentation path completes it. */
    }
    if (a->coremark_origin == XY_COREMARK_MOCK) {
        text_copy(a->message, sizeof(a->message), "模拟结束，预置参考分未更新");
        return 1;
    }
    elapsed = timer_hz ? (double)ticks / timer_hz : 0;
    value = ticks && cpu_hz ? (double)iterations * timer_hz * 1000000.0 /
                                   ((double)ticks * cpu_hz) : 0;
    if (!crc_valid || !iterations || elapsed < 10.0 || elapsed > 120.0 ||
        cpu_hz == 0 || !identity || !identity[0] || !isfinite(value) || value <= 0) {
        text_copy(a->message, sizeof(a->message), "测试未通过校验，预置参考分未更新");
        return 1;
    }
    a->coremark_measured = 1;
    a->coremark_reference_shown=0;
    a->coremark_per_mhz = value;
    a->coremark_cpu_hz = cpu_hz;
    a->coremark_elapsed_ms = (unsigned)(elapsed * 1000.0);
    text_copy(a->coremark_identity, sizeof(a->coremark_identity), identity);
    text_copy(a->message, sizeof(a->message), "CoreMark 实板短测完成");
    return 1;
}
double xy_coremark_display_score(const xy_app *a)
{return a->coremark_reference_shown?a->coremark_reference_per_mhz:a->coremark_per_mhz;}
int xy_coremark_reference_complete(xy_app *a,uint32_t token)
{
    if(!a || a->token!=token || a->job!=XY_COREMARK || a->cancelling ||
       a->coremark_origin!=XY_COREMARK_REFERENCE || a->coremark_elapsed_ms<10000)return 0;
    a->coremark_reference_per_mhz=xy_cm_reference_scores[a->coremark_reference_index++%6];
    a->coremark_reference_shown=1;a->job=XY_IDLE;a->coremark_progress=1000;
    text_copy(a->message,sizeof(a->message),"参考成绩演示完成，非本次实测");
    return 1;
}
unsigned xy_coremark_log_lines(const xy_app *a)
{
    unsigned rows=0,col=0;
    if(!a)return 0;
    for(size_t i=0;i<a->coremark_log_used && i<XY_CM_LOG_BYTES-1;i++){
        if(a->coremark_log[i]=='\n'){rows++;col=0;}
        else {if(col==XY_CM_LOG_COLUMNS){rows++;col=0;}col++;}
    }
    return rows+(col!=0);
}
int xy_coremark_log_action(xy_app *a,xy_pointer_event action)
{
    if(!a || (a->page!=XY_HOME
#if XINYI_HOME_R13
              && a->page!=XY_BENCHMARK
#endif
             ) || a->cancelling || a->navigation_pending)return 0;
    if(action==XY_ACTION_CM_LOG){a->coremark_log_visible=1;return 1;}
    if(!a->coremark_log_visible)return 0;
    if(action==XY_ACTION_CM_LOG_CLOSE){a->coremark_log_visible=0;return 1;}
    if(action==XY_ACTION_CM_LOG_PREV){if(a->coremark_log_page)a->coremark_log_page--;return 1;}
    if(action==XY_ACTION_CM_LOG_NEXT){
        if((a->coremark_log_page+1)*XY_CM_LOG_ROWS<xy_coremark_log_lines(a))a->coremark_log_page++;
        return 1;
    }
    return 0;
}
