#define _POSIX_C_SOURCE 200809L
#include "voice_bridge.h"
#include "xiangqi_pikafish_link.h"
#include <limits.h>
#include <stdio.h>
#include <string.h>

static void copy_text(char *out,size_t bytes,const char *text)
{(void)snprintf(out,bytes,"%s",text?text:"");}
static void next_revision(xy_voice_bridge *v)
{if(!++v->revision)++v->revision;}
static void initial_board(xq_search_board_t *b)
{
    static const uint8_t back[9]={PIECE_R,PIECE_N,PIECE_B,PIECE_A,PIECE_K,PIECE_A,PIECE_B,PIECE_N,PIECE_R};
    memset(b,0,sizeof(*b));
    for(unsigned i=0;i<9;i++){b->squares[i]=back[i];b->squares[81+i]=back[i]|SIDE_BLACK;}
    for(unsigned i=0;i<9;i+=2){b->squares[27+i]=PIECE_P;b->squares[54+i]=PIECE_P|SIDE_BLACK;}
    b->squares[19]=b->squares[25]=PIECE_C;b->squares[64]=b->squares[70]=PIECE_C|SIDE_BLACK;
}
static int app_ready(const xy_voice_bridge *v)
{
    const xy_app *a=v->app;
#if XINYI_BATTLE_R17
    return !v->closing && !v->halted && a && a->page==XY_GAME &&
        ((a->mode==XY_VOICE && v->enabled && a->microphone_enabled) ||
         (a->mode==XY_KEYBOARD && !a->microphone_enabled)) && !a->cancelling;
#else
    return v->enabled && !v->closing && !v->halted && a && a->page==XY_GAME &&
        a->mode==XY_VOICE && a->microphone_enabled && !a->cancelling;
#endif
}
static int current_job(const xy_voice_bridge *v,uint32_t token,uint32_t revision,int phase)
{
    return v && v->initialized && v->external_active && v->phase==phase &&
        v->token==token && v->job_revision==revision;
}
static int live_job(const xy_voice_bridge *v)
{
    return app_ready(v) && !v->cancel_pending && v->app->job==XY_VOICE_COMMAND &&
        v->app->token==v->token && v->revision==v->job_revision;
}
static void abandon_stale(xy_voice_bridge *v)
{
    if(!v->cancel_pending && !v->closing){
        v->phase=XYVB_IDLE;v->token=0;if(v->board.side)v->halted=1;
    }
}
static void visible_board(xy_voice_bridge *v)
{v->app->voice_board=v->board;v->app->voice_has_board=1;v->app->voice_selected_valid=0;}
static void finish(xy_voice_bridge *v,int okay,const char *result)
{
    uint32_t token=v->token;
    v->phase=XYVB_IDLE;v->external_active=v->cancel_sent=0;v->token=0;
    (void)xy_voice_complete(v->app,token,okay,okay?&v->board:NULL,result,
                            v->tail_valid?v->tail_ms:UINT_MAX);
    xqvoice_session_defer(&v->session,250);
}
static void request_external_cancel(xy_voice_bridge *v)
{
    if(!v->external_active || v->cancel_sent)return;
    v->cancel_sent=1;
    if(v->phase==XYVB_ENGINE && v->ops.engine_cancel)
        v->ops.engine_cancel(v->ops.context,v->token,v->job_revision);
    else if(v->phase==XYVB_SPEECH && v->ops.speech_cancel)
        v->ops.speech_cancel(v->ops.context,v->token,v->job_revision);
}
void xy_voice_bridge_init(xy_voice_bridge *v,xy_app *a,const xy_voice_bridge_ops *ops)
{
    if(!v)return;
    memset(v,0,sizeof(*v));v->app=a;if(ops)v->ops=*ops;
    xqvoice_session_init(&v->session);initial_board(&v->board);
    v->revision=1;v->initialized=1;v->tail_ms=UINT_MAX;
    v->speech_available=v->ops.speech_start!=NULL;
}
int xy_voice_bridge_pause(xy_voice_bridge *v)
{
    if(!v || !v->initialized)return 0;
    v->mouse_pending=0;
    if(v->enabled){v->enabled=0;next_revision(v);}
    if(!xqvoice_session_pause(&v->session))return 0;
    request_external_cancel(v);
    return !v->external_active;
}
int xy_voice_bridge_enable(xy_voice_bridge *v,int enabled)
{
    if(!v || !v->initialized || !v->app || v->closing)return 0;
    if(!enabled)return xy_voice_bridge_pause(v);
    if(v->external_active || v->cancel_pending || v->phase!=XYVB_IDLE)return 0;
    if(!v->enabled){next_revision(v);v->enabled=1;}
    visible_board(v);v->app->voice_tail_ms=v->tail_valid?v->tail_ms:UINT_MAX;
    return 1;
}
int xy_voice_bridge_command(xy_voice_bridge *v,uint32_t token,const char *text)
{
    if(!v || !app_ready(v) || !token || !text || v->phase!=XYVB_QUEUED || v->token ||
       strcmp(text,v->pending_text) || v->app->token!=token || v->app->job!=XY_VOICE_COMMAND)return 0;
    v->token=token;v->job_revision=v->revision;return 1;
}
static int mouse_position(xy_voice_bridge *v,unsigned from,unsigned to,xq_search_board_t *next,char iccs[5])
{
    if(from>=90 || to>=90 || from==to)return 0;
    iccs[0]=(char)('a'+from%9);iccs[1]=(char)('0'+from/9);
    iccs[2]=(char)('a'+to%9);iccs[3]=(char)('0'+to/9);iccs[4]=0;
    *next=v->board;
    return xq_pikafish_apply_move(next,iccs,NULL);
}
int xy_voice_bridge_mouse_move(xy_voice_bridge *v,unsigned from,unsigned to)
{
    xq_search_board_t next;char iccs[5];
    if(!v || !app_ready(v) || v->halted || v->mouse_pending || v->phase!=XYVB_IDLE ||
       v->external_active || v->cancel_pending || v->app->job!=XY_IDLE || v->board.side ||
       !mouse_position(v,from,to,&next,iccs))return 0;
    v->mouse_from=from;v->mouse_to=to;v->mouse_revision=v->revision;v->mouse_pending=1;
    xqvoice_session_cancel(&v->session);return 1;
}
void xy_voice_bridge_cancel(xy_voice_bridge *v,uint32_t token)
{
    if(!v || !v->initialized || !token || token!=v->token || v->phase==XYVB_IDLE)return;
    if(!v->cancel_pending){v->cancel_pending=1;next_revision(v);}
    (void)xqvoice_session_pause(&v->session);request_external_cancel(v);
}
static int stopped(xy_voice_bridge *v,uint32_t token,uint32_t revision,int phase)
{
    if(!current_job(v,token,revision,phase))return 0;
    v->external_active=0;
    if(!v->cancel_pending && !v->closing && live_job(v)) {
        if(phase==XYVB_ENGINE){v->halted=1;finish(v,0,"电脑应着未完成，请重新开始");}
        else {v->speech_available=0;finish(v,1,"已走棋；电脑已应着，播报未完成");}
    }
    return 1;
}
int xy_voice_bridge_engine_stopped(xy_voice_bridge *v,uint32_t token,uint32_t revision)
{return stopped(v,token,revision,XYVB_ENGINE);}
int xy_voice_bridge_speech_stopped(xy_voice_bridge *v,uint32_t token,uint32_t revision)
{return stopped(v,token,revision,XYVB_SPEECH);}
int xy_voice_bridge_engine_reply(xy_voice_bridge *v,uint32_t token,uint32_t revision,
    int okay,const char *iccs,const char *notation,uint32_t rate,uint32_t nodes,uint32_t elapsed_us)
{
    xq_search_board_t next;
    if(!current_job(v,token,revision,XYVB_ENGINE))return 0;
    v->external_active=0;
    if(!live_job(v)){abandon_stale(v);return 0;}
    next=v->board;
    if(!okay || next.side!=1 || memcmp(&next,&v->engine_before,sizeof(next)) ||
       !iccs || strlen(iccs)!=4 || !xq_pikafish_apply_move(&next,iccs,NULL)) {
        v->halted=1;finish(v,0,"电脑未能返回合法应着，请重新开始");return 1;
    }
    v->board=next;visible_board(v);next_revision(v);v->job_revision=v->revision;
    (void)xy_voice_engine_stats(v->app,token,rate,nodes,elapsed_us);
    copy_text(v->computer_iccs,sizeof(v->computer_iccs),iccs);
    (void)snprintf(v->pending_result,sizeof(v->pending_result),"已走棋；电脑%s",
                   notation && *notation?notation:iccs);
#if XINYI_BATTLE_R17
    if(v->app->mode==XY_KEYBOARD){finish(v,1,v->pending_result);return 1;}
#endif
    v->phase=XYVB_SPEECH;v->external_active=1;v->cancel_sent=0;
    if(!v->ops.speech_start || !v->ops.speech_start(v->ops.context,token,v->job_revision,
                                                   &v->engine_before,v->computer_iccs)) {
        v->external_active=0;v->speech_available=0;
        copy_text(v->pending_result,sizeof(v->pending_result),"已走棋；电脑已应着，播报未就绪");
        finish(v,1,v->pending_result);
    }
    return 1;
}
int xy_voice_bridge_speech_reply(xy_voice_bridge *v,uint32_t token,uint32_t revision,int okay)
{
    if(!current_job(v,token,revision,XYVB_SPEECH))return 0;
    v->external_active=0;
    if(!live_job(v)){abandon_stale(v);return 0;}
    v->speech_available=okay!=0;
    if(!okay)copy_text(v->pending_result,sizeof(v->pending_result),"已走棋；电脑已应着，播报失败");
    finish(v,1,v->pending_result);return 1;
}
int xy_voice_bridge_poll(xy_voice_bridge *v)
{
    xy_app *a;xq_search_move_t move;int committed;
    if(!v || !v->initialized || !(a=v->app))return 0;
    if(v->cancel_pending) {
        if(!xqvoice_session_pause(&v->session) || v->external_active)return 0;
        uint32_t token=v->token;
        v->phase=XYVB_IDLE;v->token=0;v->cancel_pending=v->cancel_sent=0;
        if(v->board.side)v->halted=1;
        int changed=xy_cancel_complete(a,token);
#if XINYI_BATTLE_R17
        if(changed && v->halted && a->page==XY_GAME && !a->navigation_pending)
            copy_text(a->message,sizeof(a->message),"电脑应着已取消，请重新开始");
#endif
        return changed;
    }
    if(v->mouse_pending) {
        xq_search_board_t next;char iccs[5];
        if(!app_ready(v) || v->halted || a->job!=XY_IDLE || v->board.side || v->mouse_revision!=v->revision) {
            v->mouse_pending=0;return 1;
        }
        /* Never let a late transcript for the previous board race this move. */
        (void)xqvoice_session_poll(&v->session,NULL,0,0);
        if(v->session.worker_busy || v->session.need_send || v->session.state==XQV_CANCELLING)return 0;
        v->mouse_pending=0;
        if(!mouse_position(v,v->mouse_from,v->mouse_to,&next,iccs))return 1;
        v->board=next;visible_board(v);next_revision(v);
        v->reported_request=v->session.timing_request;
        v->pending_legal=1;v->tail_valid=0;v->tail_ms=UINT_MAX;
        copy_text(v->pending_text,sizeof(v->pending_text),iccs);
        copy_text(v->pending_result,sizeof(v->pending_result),"已走棋");
        v->phase=XYVB_QUEUED;v->token=0;
#if XINYI_BATTLE_R17
        char previous_heard[XY_TEXT_BYTES];memcpy(previous_heard,a->voice_heard,sizeof(previous_heard));
#endif
        if(!xy_voice_begin(a,v->pending_text)){v->phase=XYVB_IDLE;v->halted=1;}
        else a->voice_mouse_input=1;
#if XINYI_BATTLE_R17
        memcpy(a->voice_heard,previous_heard,sizeof(a->voice_heard));
#endif
        return 1;
    }
    if(v->phase==XYVB_QUEUED && v->token) {
        if(!live_job(v))return 0;
#if XINYI_BATTLE_R17
        /* A recognized command is visible before AI/speech. The real main
         * acknowledges its generation after the corresponding bank scans. */
        if(v->pending_legal && !a->voice_mouse_input && a->mode==XY_VOICE &&
           a->voice_generation!=a->voice_displayed_generation)return 0;
#endif
        if(!xqvoice_session_pause(&v->session))return 0;
        if(!v->pending_legal){finish(v,0,v->pending_result);return 1;}
        v->engine_before=v->board;v->phase=XYVB_ENGINE;v->external_active=1;v->cancel_sent=0;
        if(!v->ops.engine_start || !v->ops.engine_start(v->ops.context,v->token,v->job_revision,&v->engine_before)) {
            v->external_active=0;v->halted=1;finish(v,0,"电脑应着服务未就绪，请重新开始");
        }
        return 1;
    }
    if(v->phase!=XYVB_IDLE || !app_ready(v) || a->job!=XY_IDLE || v->board.side)return 0;
#if XINYI_BATTLE_R17
    if(a->mode==XY_KEYBOARD)return 0; /* Never arm ASR in keyboard mode. */
#endif
    committed=xqvoice_session_auto_step(&v->session,&v->board,v->revision,1,&move);
    if(committed){visible_board(v);next_revision(v);}
    if((v->session.state==XQV_COMMITTED || v->session.state==XQV_ERROR) &&
       v->session.timing_request && v->session.timing_request!=v->reported_request &&
       !v->session.worker_busy && !v->session.need_send) {
        v->reported_request=v->session.timing_request;
        if(v->session.result==XQV_RESULT_UNAVAILABLE) {
            copy_text(a->voice_result,sizeof(a->voice_result),v->session.result_text);
#if XINYI_BATTLE_R17
            copy_text(a->message,sizeof(a->message),v->session.result_text);
#endif
            a->voice_tail_ms=UINT_MAX;return 1;
        }
        v->pending_legal=committed!=0;
        copy_text(v->pending_text,sizeof(v->pending_text),v->session.heard_text[0]?
            v->session.heard_text:"未识别到文字");
        copy_text(v->pending_result,sizeof(v->pending_result),v->session.result_text);
        v->tail_valid=v->session.timing.valid!=0;
        uint64_t ms=v->session.timing.last_voice_to_result_us/1000u;
        v->tail_ms=v->tail_valid && ms<UINT_MAX?(unsigned)ms:UINT_MAX;
        if(v->tail_ms==UINT_MAX)v->tail_valid=0;
        v->phase=XYVB_QUEUED;v->token=0;
        if(!xy_voice_begin(a,v->pending_text)) {
            v->phase=XYVB_IDLE;
            if(committed)v->halted=1;
        }
#if XINYI_BATTLE_R17
        else {
            if(!++a->voice_generation)++a->voice_generation;
            a->voice_result_token=a->token;
            a->voice_e2e_valid=0;a->voice_e2e_ms=0;
            a->voice_started_valid=v->session.timing.utterance_valid!=0;
            a->voice_started_ms=v->session.timing.utterance_start_us/1000u;
        }
#endif
        return 1;
    }
    return 0;
}
int xy_voice_bridge_reset(xy_voice_bridge *v)
{
    if(!v || !v->initialized || v->enabled || v->external_active || v->cancel_pending || v->phase!=XYVB_IDLE)return 0;
    next_revision(v);initial_board(&v->board);v->halted=0;v->reported_request=0;
    v->tail_valid=0;v->tail_ms=UINT_MAX;
    v->session.result=XQV_RESULT_NONE;v->session.heard_text[0]=v->session.result_text[0]=0;
    if(v->app){visible_board(v);v->app->voice_tail_ms=UINT_MAX;}
    return 1;
}
int xy_voice_bridge_close(xy_voice_bridge *v)
{
    if(!v || !v->initialized)return 1;
    v->closing=1;
    if(!xy_voice_bridge_pause(v))return 0;
    xqvoice_session_close(&v->session);v->initialized=0;return 1;
}
