#define _POSIX_C_SOURCE 200809L
#include "runtime.h"
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

static uint64_t milliseconds(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
    return (uint64_t)t.tv_sec*1000u+(unsigned)t.tv_nsec/1000000u;
}
#if XINYI_BATTLE_R17
static uint64_t microseconds(void)
{
    struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
    return(uint64_t)t.tv_sec*1000000u+(unsigned)t.tv_nsec/1000u;
}
#endif
static unsigned photo_elapsed(const xy_runtime *r)
{
    uint64_t now=milliseconds(),ms=now>=r->photo_started_ms?now-r->photo_started_ms:0;
    return ms<UINT_MAX?(unsigned)ms:UINT_MAX;
}
static void fatal(xy_runtime *r)
{
    r->fatal=1;r->dirty=1;
    (void)snprintf(r->app.message,sizeof(r->app.message),"安全停止未完成，请联系工作人员");
    (void)xy_voice_bridge_pause(&r->voice);
}
static int drained(void *context)
{return xy_accelerator_idle(&((xy_runtime *)context)->accelerator);}
static xy_coach_task *open_coach(xy_runtime *r)
{
    xy_coach_config config={r->config.coach_worker,r->config.models,180000,7200000,
                            10000,2000,10000,drained,r};
    return xy_coach_open(&config);
}
static int microphone(void *context,int enabled)
{
    xy_runtime *r=context;
    if(enabled && (r->fatal || r->camera_active || r->coach_active ||
                   r->engine_owner || r->speech_owner || !drained(r)))return 0;
    return xy_voice_bridge_enable(&r->voice,enabled);
}
static int capture(void *context,uint32_t token)
{
    xy_runtime *r=context;
    if(r->fatal || r->camera_active || r->coach_active || r->frame_pinned ||
       r->engine_owner || r->speech_owner || !xy_coach_ready(r->coach) || !drained(r))return 0;
    if(!xy_platform_capture_start(r->platform,token))return 0;
    r->camera_active=1;r->camera_token=token;r->photo_started_ms=milliseconds();
#if XINYI_BATTLE_R17
    r->image_token=token;
#endif
    return 1;
}
static int engine_start(xy_runtime *r,int owner,uint32_t token,uint32_t revision,
                         const xq_search_board_t *position)
{
    if(r->fatal || r->engine_owner || r->camera_active || r->coach_active ||
       r->speech_owner || !drained(r))return 0;
    if(!xy_engine_start(&r->engine,r->config.engine,token,revision,position,
                         r->config.search_nodes)){
        if(r->engine.pid>0)fatal(r);
        return 0;
    }
    r->engine_owner=owner;r->engine_token=token;r->engine_revision=revision;
#if XINYI_BATTLE_R17
    r->speech_ready_ms=r->speech_ready_us=0;r->app.speech_e2e_valid=r->app.speech_e2e_over_budget=0;
    if(r->app.mode!=XY_KEYBOARD)(void)xy_speech_task_prepare(&r->speech,
        r->config.speech_worker,r->config.pcm);
#endif
    r->drain_deadline_ms=0;return 1;
}
static int recommend(void *context,uint32_t token,const xq_search_board_t *position)
{
    xy_runtime *r=context;
    r->recommendation_board=*position;
    return engine_start(r,XY_OWNER_COACH,token,token,position);
}
static int voice_engine_start(void *context,uint32_t token,uint32_t revision,
                              const xq_search_board_t *position)
{return engine_start(context,XY_OWNER_VOICE,token,revision,position);}
static void voice_engine_cancel(void *context,uint32_t token,uint32_t revision)
{
    xy_runtime *r=context;
    if(r->engine_owner==XY_OWNER_VOICE && r->engine_token==token &&
       r->engine_revision==revision)(void)xy_engine_cancel(&r->engine);
}
static int speech_start(xy_runtime *r,int owner,uint32_t token,uint32_t revision,
                         const xq_search_board_t *before,const char *iccs)
{
#if XINYI_BATTLE_R17
    if(r->app.mode==XY_KEYBOARD)return 0;
#endif
    if(r->fatal || r->speech_owner || r->engine_owner || r->camera_active || r->coach_active)return 0;
    int started;
#if XINYI_COACH_MOVE_AUDIO
    if(owner==XY_OWNER_COACH
#if XINYI_BATTLE_R17
       || owner==XY_OWNER_VOICE
#endif
      )started=xy_speech_task_start_move(&r->speech,r->config.speech_worker,
        r->config.pcm,token,revision,before,iccs);
    else
#endif
    started=xy_speech_task_start(&r->speech,r->config.speech_worker,r->config.pcm,
                            token,revision,before,iccs);
    if(!started){
        if(r->speech.pid>0 || (r->speech.starts && !r->speech.cleanup_confirmed))fatal(r);
        return 0;
    }
    r->speech_owner=owner;r->speech_token=token;r->speech_revision=revision;return 1;
}
static int voice_speech_start(void *context,uint32_t token,uint32_t revision,
                              const xq_search_board_t *before,const char *iccs)
{return speech_start(context,XY_OWNER_VOICE,token,revision,before,iccs);}
static void voice_speech_cancel(void *context,uint32_t token,uint32_t revision)
{
    xy_runtime *r=context;
    if(r->speech_owner==XY_OWNER_VOICE && r->speech_token==token &&
       r->speech_revision==revision)(void)xy_speech_task_cancel(&r->speech,token,revision);
}
static void speak(void *context,const char *notation)
{
    xy_runtime *r=context;
    (void)notation; /* Playback uses the very same validated engine move. */
    if(!speech_start(r,XY_OWNER_COACH,r->app.token,r->app.token,
                     &r->recommendation_board,r->recommendation_iccs))
        (void)xy_announce_complete(&r->app,r->app.token,0);
}
static int voice_command(void *context,uint32_t token,const char *text)
{xy_runtime *r=context;return xy_voice_bridge_command(&r->voice,token,text);}
static int coremark(void *context,uint32_t token,unsigned target_ms)
{
    xy_runtime *r=context;
    if(r->fatal || r->engine_owner || r->speech_owner || r->camera_active || r->coach_active || !drained(r))return 0;
    if(r->app.coremark_origin==XY_COREMARK_REFERENCE){
        r->reference_started_ms=milliseconds();return 1;
    }
    if(!r->config.bitstream || strlen(r->config.bitstream)!=64)return 0;
    return xy_cm_process_start(&r->coremark,r->config.coremark,token,target_ms,
                               xy_platform_cpu_hz(r->platform),r->config.bitstream);
}
static void cancel(void *context,xy_job job,uint32_t token)
{
    xy_runtime *r=context;
    if(job==XY_CAPTURE){
        if(r->camera_active)(void)xy_platform_cancel(r->platform,token);
        if(r->coach_active)(void)xy_coach_cancel(r->coach,token);
    }else if(job==XY_RECOMMEND){
        if(r->engine_owner==XY_OWNER_COACH)(void)xy_engine_cancel(&r->engine);
    }else if(job==XY_ANNOUNCE){
        if(r->speech_owner==XY_OWNER_COACH)
            (void)xy_speech_task_cancel(&r->speech,token,r->speech_revision);
    }else if(job==XY_VOICE_COMMAND)xy_voice_bridge_cancel(&r->voice,token);
    else if(job==XY_COREMARK && r->app.coremark_origin!=XY_COREMARK_REFERENCE)
        (void)xy_cm_process_cancel(&r->coremark);
#if XINYI_BATTLE_R17
    if(!r->speech_owner && r->speech.pid>0)(void)xy_speech_task_close(&r->speech);
#endif
}
int xy_runtime_init(xy_runtime *r,xy_platform *platform,const xy_runtime_config *config)
{
    if(!r || !platform || !config)return 0;
    memset(r,0,sizeof(*r));r->platform=platform;r->config=*config;
    r->accelerator.fd=-1;
    xy_engine_init(&r->engine);xy_speech_task_init(&r->speech);xy_cm_process_init(&r->coremark);
    xy_voice_bridge_ops ops={r,voice_engine_start,voice_engine_cancel,voice_speech_start,voice_speech_cancel};
    xy_voice_bridge_init(&r->voice,&r->app,&ops);
    xy_backend backend={r,microphone,capture,recommend,voice_command,coremark,cancel,speak};
    xy_app_init(&r->app,&backend);r->dirty=1;
    if(!xy_accelerator_open(&r->accelerator)){fatal(r);return 0;}
    r->coach=open_coach(r);
    if(!r->coach){fatal(r);return 0;}
    return 1;
}
static void release_frame(xy_runtime *r)
{
    if(r->frame_pinned && xy_coach_consumed(r->coach,r->frame_token)){
        if(!xy_platform_frame_release(r->platform,r->frame_token)){fatal(r);return;}
        r->frame_pinned=0;
    }
}
static int poll_camera(xy_runtime *r)
{
    xy_platform_event e;xy_platform_frame frame;
    if(!xy_platform_poll(r->platform,&e))return 0;
#if XINYI_HOME_R13
    if(r->app.preview_state){
        if(!r->camera_active || e.token!=r->camera_token || e.result==XY_PLATFORM_UNDRAINED){fatal(r);return 1;}
        if(e.operation==XY_PLATFORM_PREVIEW_START && e.result==XY_PLATFORM_OK && e.preview_active){
            /* A live preview intentionally has no drain acknowledgement. */
            r->app.preview_state=2;
            if(r->navigation_requested){
                if(!xy_platform_preview_stop(r->platform,r->camera_token)){fatal(r);return 1;}
                r->app.preview_state=3;
            }
            return 1;
        }
        if(!e.drained || !e.display_restored || e.preview_active ||
           (e.operation!=XY_PLATFORM_PREVIEW_START && e.operation!=XY_PLATFORM_PREVIEW_STOP)){
            fatal(r);return 1;
        }
        r->camera_active=0;r->app.preview_state=0;
        (void)snprintf(r->app.message,sizeof(r->app.message),e.result==XY_PLATFORM_FAILED?
#if XINYI_PREVIEW_RETRY_R19
            "摄像头启动失败，请再点一次预览":
#else
            "摄像头预览失败，可返回后重试":
#endif
            "预览已停止，按 Esc 或返回按钮回到首页");
        return 1;
    }
#endif
    if(!r->camera_active || e.token!=r->camera_token || !e.drained ||
       e.result==XY_PLATFORM_UNDRAINED){fatal(r);return 1;}
    r->camera_active=0;
    if(r->app.cancelling){(void)xy_cancel_complete(&r->app,e.token);return 1;}
    if(e.result!=XY_PLATFORM_OK || !e.display_restored ||
       !xy_platform_frame_acquire(r->platform,e.token,&frame)){
        (void)xy_capture_complete(&r->app,e.token,0,NULL,0,photo_elapsed(r));return 1;
    }
    r->frame_pinned=1;r->frame_token=e.token;
    if(!xy_coach_start(r->coach,e.token,&frame)){
        (void)xy_platform_frame_release(r->platform,e.token);r->frame_pinned=0;
        (void)xy_capture_complete(&r->app,e.token,0,NULL,0,photo_elapsed(r));return 1;
    }
    r->coach_active=1;return 1;
}
static int poll_coach(xy_runtime *r)
{
    xy_coach_event e;xqcoach_result result;
    int have=xy_coach_poll(r->coach,&e,&result);
    release_frame(r);
    if(!have)return 0;
    if(e.type==XY_COACH_READY)return 1;
    if(e.type==XY_COACH_UNDRAINED || !e.drained){fatal(r);return 1;}
    if(e.type==XY_COACH_FATAL){fatal(r);return 1;}
    if(!r->coach_active || e.token!=r->app.token){fatal(r);return 1;}
    r->coach_active=0;
    if(r->frame_pinned){fatal(r);return 1;}
    if(e.type==XY_COACH_CANCELLED && !e.resident_ready){
        /* Cancel before request publication can require reaping the resident.
         * Its old frame is consumed and all DMA drained before replacing it.
         * This user-requested cancellation is recoverable; faults stay fatal. */
        if(!e.worker_reaped || !xy_coach_close(r->coach)){fatal(r);return 1;}
        r->coach=open_coach(r);
        if(!r->coach){fatal(r);return 1;}
    }
    if(r->app.cancelling){(void)xy_cancel_complete(&r->app,e.token);return 1;}
    if(e.type==XY_COACH_PARTIAL){
        unsigned classes[14]={0};
        xy_scored_detection mapped[XY_MAX_DETECTIONS];unsigned nmapped=0;
        if(result.status!=5 || !result.count || result.count>XY_MAX_DETECTIONS){fatal(r);return 1;}
        for(unsigned i=0;i<result.count;i++){
            const xqcoach_candidate *p=result.candidates+i;
            if(p->class_id>=14){fatal(r);return 1;}
            classes[p->class_id]++;
            if(result.estimated && p->file<9 && p->rank<10)
                mapped[nmapped++]=(xy_scored_detection){p->class_id,p->file,p->rank,p->confidence,p->score};
            else if(p->file!=255 || p->rank!=255){fatal(r);return 1;}
        }
        if(nmapped){
            if(!xy_capture_estimated(&r->app,e.token,mapped,nmapped,photo_elapsed(r)))fatal(r);
            printf("XINYI_COACH_PRODUCT estimated=1 candidates=%u mapped=%u removed=%u legal=%u\n",
                result.count,nmapped,r->app.photo.removed_count,r->app.photo.reason==XY_POSITION_VALID);
        }else if(!xy_capture_partial(&r->app,e.token,classes,result.count,photo_elapsed(r)))fatal(r);
        return 1;
    }
    if(e.type!=XY_COACH_RESULT){
        (void)xy_capture_complete(&r->app,e.token,0,NULL,0,photo_elapsed(r));return 1;
    }
    if(result.count>XY_MAX_DETECTIONS){fatal(r);return 1;}
    xy_scored_detection pieces[XY_MAX_DETECTIONS];
    for(unsigned i=0;i<result.count;i++){
        const xqcoach_candidate *p=result.candidates+i;
        pieces[i]=(xy_scored_detection){p->class_id,p->file,p->rank,p->confidence,p->score};
    }
    (void)xy_capture_complete_scored(&r->app,e.token,1,pieces,result.count,photo_elapsed(r));
    return 1;
}
static int poll_engine(xy_runtime *r)
{
    xy_engine_state state=xy_engine_poll(&r->engine);xy_engine_reply reply;
    int owner=r->engine_owner;
    if(!owner)return 0;
    if(state==XY_ENGINE_DONE){
        if(!drained(r)){fatal(r);return 1;}
        if(!xy_engine_take(&r->engine,&reply)){fatal(r);return 1;}
        r->engine_owner=XY_OWNER_NONE;
#if XINYI_BATTLE_R17
        /* A receive timestamp omits IPC/GUI scheduling. Only an identity-checked
         * producer anchor from this exact reply can support the full budget. */
        r->speech_ready_us=reply.producer_ready_valid?reply.producer_ready_us:0;
        r->speech_ready_ms=r->speech_ready_us/1000u;
#endif
        if(owner==XY_OWNER_COACH){
            memcpy(r->recommendation_iccs,reply.iccs,5);
            (void)xy_recommend_complete(&r->app,reply.token,reply.okay,reply.move,reply.notation);
            (void)xy_photo_elapsed(&r->app,reply.token,photo_elapsed(r));
        }else (void)xy_voice_bridge_engine_reply(&r->voice,reply.token,reply.revision,
                reply.okay,reply.iccs,reply.notation,reply.red_win_permille,reply.nodes,reply.elapsed_us);
        return 1;
    }
    if((state==XY_ENGINE_STOPPED || state==XY_ENGINE_FAILED) && r->engine.pid<=0){
        if(!drained(r)){
            if(!r->drain_deadline_ms)r->drain_deadline_ms=milliseconds()+10000;
            if(milliseconds()>=r->drain_deadline_ms)fatal(r);
            return 0;
        }
#if XINYI_BATTLE_R17
        /* Cancellation must also reap a helper which was only preparing.
         * It owns no speech job, so the ordinary owner gate cannot cover it. */
        if(r->app.cancelling && !r->speech_owner && r->speech.pid>0){
            (void)xy_speech_task_close(&r->speech);return 0;
        }
#endif
        r->engine_owner=XY_OWNER_NONE;r->drain_deadline_ms=0;
        if(owner==XY_OWNER_VOICE)
            (void)xy_voice_bridge_engine_stopped(&r->voice,r->engine_token,r->engine_revision);
        else if(r->app.cancelling)(void)xy_cancel_complete(&r->app,r->engine_token);
        else {
            const xq_search_move_t zero={0};
            (void)xy_recommend_complete(&r->app,r->engine_token,0,zero,"");
            (void)xy_photo_elapsed(&r->app,r->engine_token,photo_elapsed(r));
        }
        return 1;
    }
    return 0;
}
static int poll_speech(xy_runtime *r)
{
    (void)xy_speech_task_poll(&r->speech);
    int state=r->speech.state,owner=r->speech_owner;
    if(!owner){
#if XINYI_BATTLE_R17
        if(state==XY_SPEECH_FAILED && r->speech.starts && !r->speech.cleanup_confirmed){fatal(r);return 1;}
#endif
        return 0;
    }
    if(state==XY_SPEECH_STOPPED || state==XY_SPEECH_FAILED){
        if(!r->speech.cleanup_confirmed || (state==XY_SPEECH_STOPPED && r->speech.pid>0)){
            fatal(r);return 1;
        }
    }
    if(state==XY_SPEECH_STOPPED){
        r->speech_owner=XY_OWNER_NONE;
        if(owner==XY_OWNER_VOICE)
            (void)xy_voice_bridge_speech_stopped(&r->voice,r->speech_token,r->speech_revision);
        else if(r->app.cancelling)(void)xy_cancel_complete(&r->app,r->speech_token);
        else (void)xy_announce_complete(&r->app,r->speech_token,0);
        return 1;
    }
    if(state==XY_SPEECH_DONE || state==XY_SPEECH_FAILED){
        if(r->app.cancelling){
            (void)xy_speech_task_cancel(&r->speech,r->speech_token,r->speech_revision);return 0;
        }
        r->speech_owner=XY_OWNER_NONE;
#if XINYI_BATTLE_R17
        uint64_t ended=microseconds();
        if(state==XY_SPEECH_DONE && r->speech_ready_us && ended>=r->speech_ready_us && ended-r->speech_ready_us<=7200000000ull){
            uint64_t elapsed=ended-r->speech_ready_us;
            r->app.speech_e2e_ms=(unsigned)((elapsed+999u)/1000u);
            r->app.speech_e2e_valid=1;
            r->app.speech_e2e_over_budget=elapsed>1000000u;
        }
#endif
        if(owner==XY_OWNER_VOICE)(void)xy_voice_bridge_speech_reply(&r->voice,r->speech_token,
                                                 r->speech_revision,state==XY_SPEECH_DONE);
        else (void)xy_announce_complete(&r->app,r->speech_token,state==XY_SPEECH_DONE);
        return 1;
    }
    return 0;
}
static int navigation(xy_runtime *r)
{
    if(!r->navigation_requested || r->app.navigation_pending || r->app.cancelling)return 0;
#if XINYI_HOME_R13
    if(r->app.preview_state)return 0;
#endif
#if XINYI_BATTLE_R17
    /* Keep pending navigation in the runtime until every independent helper
     * is reaped. Product cancel completion must not apply the destination
     * early while a preparation-only child has no speech_owner. */
    if(r->app.job!=XY_IDLE){
        int changed=xy_cancel(&r->app);
        if(!r->speech_owner && r->speech.pid>0)(void)xy_speech_task_close(&r->speech);
        return changed;
    }
    /* Freeze pending manual/ASR input before waiting for helper shutdown.
     * Otherwise a queued red move could commit while the old page remains
     * visible during an otherwise harmless preparation-only close. */
    if(!xy_voice_bridge_pause(&r->voice))return 0;
    r->app.microphone_enabled=0;r->app.microphone_ready=1;
    r->app.voice_selected_valid=0;
    if(!r->speech_owner && r->speech.pid>0){
        (void)xy_speech_task_close(&r->speech);
        if(strcmp(r->app.message,"正在安全停止，请稍后")){
            (void)snprintf(r->app.message,sizeof(r->app.message),"正在安全停止，请稍后");return 1;
        }
        return 0;
    }
#endif
    if(xy_navigate(&r->app,r->destination_page,r->destination_mode)){
#if XINYI_BATTLE_R17
        if(r->app.page==XY_GAME && r->app.mode==XY_KEYBOARD){
            r->app.voice_board=r->voice.board;r->app.voice_has_board=1;
        }
#endif
        r->navigation_requested=0;return 1;
    }
    return 0; /* microphone pause is asynchronous; retain the one user click. */
}
int xy_runtime_poll(xy_runtime *r)
{
    int changed=0;
    if(!r || r->fatal)return 0;
    changed|=poll_camera(r);if(r->fatal)return 1;
    changed|=poll_coach(r);if(r->fatal)return 1;
    changed|=poll_engine(r);if(r->fatal)return 1;
    changed|=poll_speech(r);if(r->fatal)return 1;
    if(r->app.job==XY_COREMARK && r->app.coremark_origin==XY_COREMARK_REFERENCE){
        if(r->app.cancelling){changed|=xy_cancel_complete(&r->app,r->app.token);}
        else {
            uint64_t now=milliseconds(),ms=now>=r->reference_started_ms?now-r->reference_started_ms:0;
            unsigned elapsed=(unsigned)(ms>10000?10000:ms);
            changed|=xy_coremark_progress(&r->app,r->app.token,elapsed,elapsed/10);
            if(elapsed>=10000)changed|=xy_coremark_reference_complete(&r->app,r->app.token);
        }
    }else{
        (void)xy_cm_process_poll(&r->coremark);
        changed|=xy_cm_process_apply(&r->coremark,&r->app);
    }
    changed|=xy_voice_bridge_poll(&r->voice);
    changed|=navigation(r);
    if(r->restart_requested && !r->navigation_requested && r->app.page==XY_HOME &&
       !r->app.cancelling && !r->app.navigation_pending && !r->engine_owner &&
       !r->speech_owner &&
#if XINYI_BATTLE_R17
       (r->restart_mode==XY_COACH || xy_voice_bridge_reset(&r->voice))) {
        if(r->restart_mode==XY_COACH){
            if(!xy_image_reset_presentation(&r->app)){fatal(r);return 1;}
        }else if(!xy_voice_reset_presentation(&r->app)){fatal(r);return 1;}
        memset(r->displayed,0,sizeof(r->displayed));
        r->restart_requested=0;r->destination_page=XY_GAME;r->destination_mode=r->restart_mode;
#else
       xy_voice_bridge_reset(&r->voice)) {
        if(!xy_voice_reset_presentation(&r->app)){fatal(r);return 1;}
        r->restart_requested=0;r->destination_page=XY_GAME;r->destination_mode=XY_VOICE;
#endif
        r->navigation_requested=1;changed=1;changed|=navigation(r);
    }
#if XINYI_BATTLE_R17
    /* Prepare on the event thread, never inside the result-to-play path.
     * READY does not claim speech_owner or touch the ASR microphone. */
    if(r->app.page==XY_GAME && r->app.mode!=XY_KEYBOARD &&
       !r->navigation_requested && !r->app.navigation_pending && !r->app.cancelling &&
       !r->speech_owner && (r->speech.state==XY_SPEECH_IDLE || r->speech.state==XY_SPEECH_STOPPED))
        (void)xy_speech_task_prepare(&r->speech,r->config.speech_worker,r->config.pcm);
#endif
    r->dirty|=changed;return changed;
}
int xy_runtime_action(xy_runtime *r,xy_pointer_event action)
{
    if(!r || r->fatal || r->navigation_requested || r->restart_requested)return 0;
#if XINYI_HOME_R13
    if(action==XY_ACTION_CM_REFERENCE && r->app.page==XY_BENCHMARK && r->app.job==XY_IDLE){
        r->app.benchmark_reference_visible=!r->app.benchmark_reference_visible;r->dirty=1;return 1;
    }
    if(action==XY_ACTION_EXIT){
        if(r->app.page!=XY_HOME || r->app.job!=XY_IDLE || r->camera_active)return 0;
        r->exit_requested=1;return 1;
    }
    if(action==XY_ACTION_PREVIEW){
        if(r->app.page!=XY_CAMERA_DEBUG || r->app.job!=XY_IDLE || r->app.preview_state ||
           r->camera_active || r->coach_active || r->frame_pinned || r->engine_owner ||
           r->speech_owner || r->app.microphone_enabled || !drained(r))return 0;
        if(++r->app.token==0)++r->app.token;
        if(!xy_platform_preview_start(r->platform,r->app.token)){
            (void)snprintf(r->app.message,sizeof(r->app.message),"摄像头预览未启动，请重试");r->dirty=1;return 0;
        }
        r->camera_active=1;r->camera_token=r->app.token;r->app.preview_state=1;r->dirty=1;return 1;
    }
    if(action==XY_ACTION_HOME && r->app.preview_state){
        r->destination_page=XY_HOME;r->destination_mode=XY_COACH;r->navigation_requested=1;
        if(r->app.preview_state==1){
            if(!xy_platform_cancel(r->platform,r->camera_token)){fatal(r);return 0;}
        }else if(r->app.preview_state==2){
            if(!xy_platform_preview_stop(r->platform,r->camera_token)){fatal(r);return 0;}
            r->app.preview_state=3;
        }
        r->dirty=1;return 1;
    }
    if(action==XY_ACTION_COREMARK && r->app.page==XY_HOME){
        r->destination_page=XY_BENCHMARK;r->destination_mode=XY_COACH;
        r->navigation_requested=1;(void)navigation(r);r->dirty=1;return 1;
    }
    if(action==XY_ACTION_CAMERA && r->app.page==XY_HOME){
        r->destination_page=XY_CAMERA_DEBUG;r->destination_mode=XY_COACH;
        r->navigation_requested=1;(void)navigation(r);r->dirty=1;return 1;
    }
#endif
    if(action==XY_ACTION_RESTART){
#if XINYI_BATTLE_R17
        if(r->app.page!=XY_GAME)return 0;
        r->restart_mode=r->app.mode;
        r->restart_requested=1;r->navigation_requested=1;
        r->destination_page=XY_HOME;r->destination_mode=r->app.mode;
#else
        if(r->app.page!=XY_GAME || r->app.mode!=XY_VOICE)return 0;
        r->restart_requested=1;r->navigation_requested=1;
        r->destination_page=XY_HOME;r->destination_mode=XY_VOICE;
#endif
        (void)navigation(r);r->dirty=1;return 1;
    }
    if(xy_coremark_log_action(&r->app,action)){r->dirty=1;return 1;}
    if(action==XY_ACTION_CANCEL){xy_runtime_cancel(r);return 1;}
    if(action==XY_ACTION_COREMARK || action==XY_ACTION_CM_REFERENCE
#if XINYI_HOME_R13
       || action==XY_ACTION_CM_RUN
#endif
      ){
#if XINYI_HOME_R13
        r->app.benchmark_reference_visible=0;
#endif
        int okay=xy_coremark_begin(&r->app,action==XY_ACTION_CM_REFERENCE?XY_COREMARK_REFERENCE:XY_COREMARK_BOARD);
        /* A rejected backend can still publish an error message/new token. */
        r->dirty|=1;return okay;
    }
    if(r->app.coremark_log_visible)return 0;
    if(action==XY_ACTION_START){r->destination_page=XY_GAME;r->destination_mode=XY_COACH;}
#if XINYI_BATTLE_R17
    else if(action==XY_ACTION_IMAGE || action==XY_ACTION_VOICE || action==XY_ACTION_KEYBOARD){
        r->destination_page=XY_GAME;
        r->destination_mode=action==XY_ACTION_IMAGE?XY_COACH:action==XY_ACTION_VOICE?XY_VOICE:XY_KEYBOARD;
    }
#endif
    else if(action==XY_ACTION_SWITCH){r->destination_page=XY_GAME;r->destination_mode=r->app.mode==XY_COACH?XY_VOICE:XY_COACH;}
    else if(action==XY_ACTION_HOME){r->destination_page=XY_HOME;r->destination_mode=r->app.mode;}
    else return 0;
    r->navigation_requested=1;(void)navigation(r);r->dirty=1;return 1;
}
int xy_runtime_pointer(xy_runtime *r,unsigned x,unsigned y)
{
    unsigned square;xy_pointer_event action;
    if(!r)return 0;
    action=xy_pointer_action(&r->app,x,y);
    if(action!=XY_ACTION_NONE)return xy_runtime_action(r,action);
    if(r->fatal || r->navigation_requested || r->restart_requested || r->app.page!=XY_GAME ||
       (r->app.mode!=XY_VOICE
#if XINYI_BATTLE_R17
        && r->app.mode!=XY_KEYBOARD
#endif
       ) || r->app.job!=XY_IDLE || r->app.cancelling ||
       r->voice.halted || r->voice.phase!=XYVB_IDLE || r->voice.mouse_pending ||
       r->voice.board.side || !xy_board_square(x,y,&square))return 0;
    unsigned piece=r->voice.board.squares[square];
#if XINYI_BATTLE_R17
    if(r->app.mode==XY_KEYBOARD){r->app.keyboard_focus=square;r->app.keyboard_focus_visible=1;}
#endif
    if(piece && !(piece&SIDE_BLACK)) {
        r->app.voice_selected_valid=!(r->app.voice_selected_valid && r->app.voice_selected==square);
        r->app.voice_selected=square;r->dirty=1;return 1;
    }
    if(!r->app.voice_selected_valid)return 0;
    if(!xy_voice_bridge_mouse_move(&r->voice,r->app.voice_selected,square)) {
        (void)snprintf(r->app.message,sizeof(r->app.message),"Illegal move");r->dirty=1;return 0;
    }
    r->app.voice_selected_valid=0;r->dirty=1;return 1;
}
int xy_runtime_space(xy_runtime *r,uint64_t pressed_ms)
{
    if(!r || r->fatal || r->navigation_requested)return 0;
    int okay=xy_capture_begin(&r->app);
    uint64_t now=milliseconds();
    if(okay && pressed_ms && pressed_ms<=now)r->photo_started_ms=pressed_ms;
    r->dirty=1;return okay;
}
void xy_runtime_cancel(xy_runtime *r)
{
#if XINYI_HOME_R13
    if(r && !r->fatal && r->app.page==XY_CAMERA_DEBUG){
        (void)xy_runtime_action(r,XY_ACTION_HOME);return;
    }
#endif
    if(r && !r->fatal){
#if XINYI_BATTLE_R17
        int retain_navigation=r->navigation_requested && r->app.cancelling;
        r->restart_requested=0;r->navigation_requested=retain_navigation;
#else
        r->restart_requested=r->navigation_requested=0;
#endif
        r->voice.mouse_pending=0;r->app.voice_selected_valid=0;r->app.coremark_log_visible=0;(void)xy_cancel(&r->app);
#if XINYI_BATTLE_R17
        if(!r->speech_owner && r->speech.pid>0)(void)xy_speech_task_close(&r->speech);
#endif
        r->dirty=1;
    }
}
#if XINYI_BATTLE_R17
int xy_runtime_key(xy_runtime *r,int key)
{
    if(!r || r->fatal)return 0;
    if(key==27){xy_runtime_cancel(r);return 1;}
    if(r->app.page!=XY_GAME || r->app.mode!=XY_KEYBOARD || r->app.job!=XY_IDLE ||
       r->app.cancelling || r->navigation_requested || r->restart_requested ||
       r->voice.halted || r->voice.board.side || r->voice.mouse_pending)return 0;
    unsigned square=r->app.keyboard_focus<90?r->app.keyboard_focus:4;
    if(key==XY_KEY_LEFT){if(square%9)square--;}
    else if(key==XY_KEY_RIGHT){if(square%9<8)square++;}
    else if(key==XY_KEY_UP){if(square<81)square+=9;}
    else if(key==XY_KEY_DOWN){if(square>=9)square-=9;}
    else if(key==13)return xy_runtime_pointer(r,176+(square%9)*88,160+(9-square/9)*88);
    else return 0;
    r->app.keyboard_focus=square;r->app.keyboard_focus_visible=1;r->dirty=1;return 1;
}
void xy_runtime_frame_submitted(xy_runtime *r,unsigned page,uint32_t frame)
{
    if(!r || page>1)return;
    r->displayed[page].pending=0;
    if(r->app.page!=XY_GAME || r->app.cancelling)return;
    uint32_t image=r->app.mode==XY_COACH && r->app.current_photo_valid && r->app.token==r->image_token?r->app.image_generation:0;
    uint32_t voice=r->app.mode==XY_VOICE && r->app.voice_result_token==r->app.token?r->app.voice_generation:0;
    if(!image && !voice)return;
    r->displayed[page].token=r->app.token;r->displayed[page].frame=frame;
    r->displayed[page].image_generation=image;r->displayed[page].voice_generation=voice;
    r->displayed[page].pending=1;
}
int xy_runtime_display_ack(xy_runtime *r,uint32_t status,uint32_t frame,uint64_t now)
{
    if(!r || r->fatal || r->app.cancelling || r->app.page!=XY_GAME ||
       (status&((1u<<3)|(1u<<5))) || !(status&2u))return 0;
    unsigned page=(status>>2)&1u;
    uint32_t elapsed_frames=frame-r->displayed[page].frame;
    if(!r->displayed[page].pending || elapsed_frames<2u || elapsed_frames>0x7fffffffu)return 0;
    r->displayed[page].pending=0;
    if(r->displayed[page].token!=r->app.token)return 0;
    int changed=0;
    if(r->app.mode==XY_COACH && r->app.current_photo_valid && !r->app.image_e2e_valid &&
       r->displayed[page].image_generation && r->displayed[page].image_generation==r->app.image_generation &&
       r->photo_started_ms && now>=r->photo_started_ms && now-r->photo_started_ms<=7200000u){
        r->app.image_e2e_ms=(unsigned)(now-r->photo_started_ms);r->app.image_e2e_valid=1;changed=1;
    }
    if(r->app.mode==XY_VOICE && r->displayed[page].voice_generation &&
       r->displayed[page].voice_generation==r->app.voice_generation){
        if(r->app.voice_displayed_generation!=r->app.voice_generation){r->app.voice_displayed_generation=r->app.voice_generation;changed=1;}
        if(!r->app.voice_e2e_valid && r->app.voice_started_valid && r->app.voice_started_ms &&
           now>=r->app.voice_started_ms && now-r->app.voice_started_ms<=7200000u){
            r->app.voice_e2e_ms=(unsigned)(now-r->app.voice_started_ms);r->app.voice_e2e_valid=1;changed=1;
        }
    }
    r->dirty|=changed;return changed;
}
#endif
int xy_runtime_shutdown(xy_runtime *r)
{
    if(!r)return 1;
    xy_runtime_cancel(r);
    uint64_t deadline=milliseconds()+15000;
    while(!r->fatal && (r->app.cancelling || r->engine_owner || r->speech_owner ||
                        r->camera_active || r->coach_active) && milliseconds()<deadline){
        (void)xy_runtime_poll(r);const struct timespec t={0,5000000};nanosleep(&t,NULL);
    }
    int okay=xy_voice_bridge_close(&r->voice);
    if(!okay){
        /* Even a quarantined external task must not leave ASR listening. No
         * mode-switch ack is issued by this emergency shutdown path. */
        xqvoice_session_close(&r->voice.session);
    }
    okay=xy_engine_dispose(&r->engine) && okay;
    (void)xy_speech_task_close(&r->speech);
    deadline=milliseconds()+6500;
    while(r->speech.pid>0 && milliseconds()<deadline){
        (void)xy_speech_task_poll(&r->speech);const struct timespec t={0,5000000};nanosleep(&t,NULL);
    }
    if(r->speech.pid>0 || (!r->speech.cleanup_confirmed && r->speech.starts))okay=0;
    xy_cm_process_dispose(&r->coremark);
    if(r->coach){
        if(!xy_coach_close(r->coach))okay=0;
        else {
            r->coach=NULL;
            if(r->frame_pinned){
                if(xy_platform_frame_release(r->platform,r->frame_token))r->frame_pinned=0;
                else okay=0;
            }
        }
    }
    if(r->frame_pinned || !drained(r) || r->fatal
#if XINYI_HOME_R13
       || r->camera_active
#endif
      )okay=0;
    /* Caller retains platform mappings on unsafe camera drain. */
    xy_accelerator_close(&r->accelerator);return okay;
}
