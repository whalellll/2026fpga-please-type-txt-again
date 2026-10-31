#define _POSIX_C_SOURCE 200809L
#include "runtime.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

xy_platform *runtime_fixture_reset(void);
void runtime_fixture_busy(int);
void runtime_fixture_exact_scores(int);
void runtime_fixture_geometry_stage(unsigned);
unsigned runtime_fixture_client_opens(void),runtime_fixture_client_closes(void);
void runtime_fixture_reaped_cancel(void),runtime_fixture_worker_ready(void);
int runtime_fixture_pinned(void),runtime_fixture_releases(void);
int runtime_fixture_camera_cancelled(void),runtime_fixture_coach_cancelled(void);
void runtime_fixture_camera_done(int),runtime_fixture_consumed(void),runtime_fixture_coach_done(int);
static const char *engine_path,*speech_path,*asr_path,*workdir;
static uint64_t now(void)
{struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC,&t));return (uint64_t)t.tv_sec*1000+t.tv_nsec/1000000;}
static void nap(void){const struct timespec t={0,1000000};nanosleep(&t,NULL);}
static void tick(xy_runtime *r){(void)xy_runtime_poll(r);assert(!r->fatal);
#if XINYI_BATTLE_R17
    /* Explicit synthetic display consumer; no real renderer/MMIO involved. */
    if(r->app.voice_generation!=r->app.voice_displayed_generation && r->app.mode==XY_VOICE){
        xy_runtime_frame_submitted(r,0,100);(void)xy_runtime_display_ack(r,2,102,now());
    }
#endif
    nap();}
static void ticks(xy_runtime *r,unsigned ms){uint64_t until=now()+ms;while(now()<until)tick(r);}
static void wait_job(xy_runtime *r,xy_job job)
{
    uint64_t limit=now()+4000;
    while(r->app.job!=job && now()<limit)tick(r);
    if(r->app.job!=job)fprintf(stderr,"runtime job=%d expected=%d engine=%d speech=%d fatal=%d\n",r->app.job,job,r->engine.state,r->speech.state,r->fatal);
    assert(r->app.job==job);
}
static void wait_speech(xy_runtime *r)
{uint64_t limit=now()+4000;while(r->speech.state!=XY_SPEECH_RUNNING && now()<limit)tick(r);assert(r->speech.state==XY_SPEECH_RUNNING);}
#if XINYI_BATTLE_R17
static void wait_navigation(xy_runtime *r)
{
    uint64_t limit=now()+4000;xy_page page=r->app.page;xy_mode mode=r->app.mode;
    while((r->navigation_requested || r->app.cancelling || r->app.navigation_pending) && now()<limit){
        if(r->navigation_requested && r->speech.pid>0 && r->speech.closing)
            assert(r->app.page==page && r->app.mode==mode);
        tick(r);
    }
    assert(!r->navigation_requested && !r->app.cancelling && !r->app.navigation_pending);
}
#endif
static void setup(xy_runtime *r,const char *engine_mode,const char *asr_mode)
{
    char model[1024];assert(snprintf(model,sizeof(model),"%s/asr.stub",workdir)>0);
    assert(!setenv("XY_ENGINE_TEST",engine_mode,1) && !setenv("XQVOICE_RUNTIME",asr_path,1));
    assert(!setenv("XQVOICE_MODEL",model,1) && !setenv("XQVOICE_AUDIO_DEVICE",asr_mode,1));
    xy_runtime_config config={"/explicit-test-coach",workdir,engine_path,speech_path,workdir,
        "/explicit-test-coremark","0000000000000000000000000000000000000000000000000000000000000000",128};
    assert(xy_runtime_init(r,runtime_fixture_reset(),&config));
    assert(r->app.page==XY_HOME && r->app.mode==XY_COACH && !r->app.microphone_enabled);
    assert(!r->voice.session.worker_busy && !r->voice.session.need_send);
    assert(xy_runtime_action(r,XY_ACTION_START) && r->app.page==XY_GAME);
}
static void shutdown_runtime(xy_runtime *r)
{
    assert(xy_runtime_shutdown(r));
    errno=0;assert(waitpid(-1,NULL,WNOHANG)==-1 && errno==ECHILD);
}
static void photo_to_coach(xy_runtime *r)
{
    assert(xy_runtime_space(r,0) && r->app.job==XY_CAPTURE && r->camera_active);
    assert(!xy_runtime_space(r,0) && !r->app.microphone_enabled && !r->voice.session.worker_busy);
    runtime_fixture_camera_done(0);tick(r);
    assert(!r->camera_active && r->coach_active && r->frame_pinned && runtime_fixture_pinned());
}
static void valid_photo(xy_runtime *r)
{
    photo_to_coach(r);ticks(r,15);
    assert(r->frame_pinned && runtime_fixture_pinned() && !runtime_fixture_releases());
    runtime_fixture_consumed();tick(r);
    assert(!r->frame_pinned && !runtime_fixture_pinned() && runtime_fixture_releases()==1);
    assert(r->coach_active && r->app.job==XY_CAPTURE);
    runtime_fixture_coach_done(XY_COACH_RESULT);tick(r);
    assert(!r->coach_active && r->app.job==XY_RECOMMEND && r->engine_owner==XY_OWNER_COACH);
    assert(r->app.photo.removed_count==268 && r->app.photo.reason==XY_POSITION_VALID);
    assert(!r->app.photo.board.squares[36] && r->app.photo.corrected[36]);
    assert(r->engine.position.side==0 && !r->app.microphone_enabled && !r->voice.session.worker_busy);
}
static void complete_photo_and_geometry(void)
{
    xy_runtime r;setup(&r,"normal","idle");valid_photo(&r);
    uint32_t token=r.app.token;
    assert(!xy_capture_complete(&r.app,token-1,0,NULL,0,0));
    wait_job(&r,XY_ANNOUNCE);wait_speech(&r);
    assert(r.app.has_recommendation && r.speech_owner==XY_OWNER_COACH && r.engine_owner==XY_OWNER_NONE);
    assert(r.app.recommendation.from==25 && r.app.recommendation.to==22); /* h2e2. */
    assert(!xy_announce_complete(&r.app,token+1,1));
    ticks(&r,35);assert(r.app.job==XY_ANNOUNCE && r.speech_owner==XY_OWNER_COACH);
    wait_job(&r,XY_IDLE);assert(r.speech.cleanup_confirmed && r.speech_owner==XY_OWNER_NONE);
    assert(r.app.has_recommendation && r.app.photo_latency_valid);
    const unsigned geometry_stages[3]={2,5,6};
    for(unsigned i=0;i<3;i++){
        xy_repair_result before=r.app.photo;runtime_fixture_geometry_stage(geometry_stages[i]);
        assert(xy_runtime_space(&r,0));runtime_fixture_camera_done(0);tick(&r);
        assert(r.frame_pinned);runtime_fixture_consumed();runtime_fixture_coach_done(XY_COACH_GEOMETRY_REJECT);tick(&r);
        assert(r.app.job==XY_IDLE && r.app.geometry_failed && r.app.has_board && !r.app.current_photo_valid);
        assert(!memcmp(&before,&r.app.photo,sizeof(before)) && !r.frame_pinned && !r.engine_owner);
        /* Every geometry refusal permits a fresh independent photo through
         * the same resident engine/speech services; no restart or cached fit. */
        assert(xy_runtime_space(&r,0));runtime_fixture_camera_done(0);tick(&r);
        runtime_fixture_consumed();runtime_fixture_coach_done(XY_COACH_RESULT);tick(&r);
        assert(r.app.job==XY_RECOMMEND && !r.app.geometry_failed && r.app.current_photo_valid);
        wait_job(&r,XY_ANNOUNCE);wait_job(&r,XY_IDLE);assert(r.app.has_recommendation);
    }
    assert(xy_runtime_space(&r,0));runtime_fixture_camera_done(0);tick(&r);
    runtime_fixture_consumed();runtime_fixture_coach_done(XY_COACH_PARTIAL);tick(&r);
    assert(r.app.estimated_position && r.app.current_photo_valid && r.app.job==XY_RECOMMEND && r.app.photo.reason==XY_POSITION_VALID);
    wait_job(&r,XY_ANNOUNCE);wait_job(&r,XY_IDLE);assert(r.app.has_recommendation);
    shutdown_runtime(&r);
    puts("RUNTIME_ESTIMATE_SEPARATE_PROTOCOL_RULE_DELETION_LEGAL_RECOMMEND_PASS");
    puts("RUNTIME_SPACE_300_DELETE_ONLY_RED_RECOMMEND_ANNOUNCE_UNTIL_SPEECH_AND_GEOMETRY_KEEP_PASS");
    puts("RUNTIME_NATIVE_GEOMETRY_2_5_6_WIRE5_KEEP_BOARD_AND_NEXT_PHOTO_SUCCESS_PASS");
}
static void capture_cancel(void)
{
    xy_runtime r;setup(&r,"normal","idle");assert(xy_runtime_space(&r,0));
    uint32_t token=r.app.token;assert(xy_runtime_action(&r,XY_ACTION_SWITCH));
    assert(runtime_fixture_camera_cancelled() && r.app.cancelling && r.app.mode==XY_COACH);
    assert(!xy_cancel_complete(&r.app,token+1));ticks(&r,20);
    assert(r.camera_active && r.app.mode==XY_COACH && !r.app.microphone_enabled);
    runtime_fixture_camera_done(1);tick(&r);
#if XINYI_BATTLE_R17
    wait_navigation(&r);
#endif
    assert(r.app.mode==XY_VOICE && !r.app.cancelling && !r.camera_active && r.app.token!=token);
    assert(!xy_capture_complete(&r.app,token,1,NULL,0,0));
    shutdown_runtime(&r);puts("RUNTIME_CAPTURE_CANCEL_NAVIGATION_AFTER_DRAIN_ACK_PASS");
}
static void coach_cancel(void)
{
    xy_runtime r;setup(&r,"normal","idle");photo_to_coach(&r);
    assert(xy_runtime_action(&r,XY_ACTION_SWITCH));
    assert(runtime_fixture_coach_cancelled());ticks(&r,20);
    assert(r.app.cancelling && r.coach_active && r.frame_pinned && r.app.mode==XY_COACH);
    runtime_fixture_consumed();tick(&r);
    assert(!r.frame_pinned && r.coach_active && r.app.cancelling && r.app.mode==XY_COACH);
    runtime_fixture_coach_done(XY_COACH_CANCELLED);tick(&r);
#if XINYI_BATTLE_R17
    wait_navigation(&r);
#endif
    assert(r.app.mode==XY_VOICE && !r.app.cancelling && !r.coach_active);
    assert(runtime_fixture_client_opens()==1 && !runtime_fixture_client_closes());
    shutdown_runtime(&r);puts("RUNTIME_COACH_CANCEL_PIN_UNTIL_CONSUMED_AND_TERMINAL_ACK_PASS");
}
static void engine_cancel_busy(void)
{
    xy_runtime r;setup(&r,"hang","idle");valid_photo(&r);
    uint32_t token=r.app.token;runtime_fixture_busy(1);
    assert(xy_runtime_action(&r,XY_ACTION_SWITCH) && r.app.cancelling);
    uint64_t limit=now()+4000;while(r.engine.pid>0 && now()<limit)tick(&r);
    assert(r.engine.pid<=0 && r.engine_owner==XY_OWNER_COACH && r.app.mode==XY_COACH);
    ticks(&r,25);assert(r.app.cancelling && r.app.mode==XY_COACH && !r.app.microphone_enabled);
    assert(!r.fatal && r.drain_deadline_ms);
    runtime_fixture_busy(0);tick(&r);
#if XINYI_BATTLE_R17
    wait_navigation(&r);
#endif
    assert(r.app.mode==XY_VOICE && !r.app.cancelling && !r.engine_owner && r.app.token!=token);
    xq_search_move_t zero={0};assert(!xy_recommend_complete(&r.app,token,0,zero,"stale"));
    shutdown_runtime(&r);puts("RUNTIME_ENGINE_WAITPID_BUSY1_BLOCKS_MODE_BUSY0_ACK_OLD_TOKEN_REJECT_PASS");
}
static void speech_cancel(void)
{
    xy_runtime r;setup(&r,"normal","idle");valid_photo(&r);wait_job(&r,XY_ANNOUNCE);wait_speech(&r);
    uint32_t token=r.app.token;assert(xy_runtime_action(&r,XY_ACTION_HOME));
    assert(r.app.cancelling && r.app.page==XY_GAME && r.speech.pid>0);
    assert(!xy_speech_task_cancel(&r.speech,token+1,r.speech_revision));
    uint64_t limit=now()+4000;while(r.app.page!=XY_HOME && now()<limit)tick(&r);
    assert(r.app.page==XY_HOME && !r.app.cancelling && r.speech.pid<=0 && r.speech.cleanup_confirmed);
    assert(!xy_announce_complete(&r.app,token,1) && !r.app.microphone_enabled);
    shutdown_runtime(&r);puts("RUNTIME_ANNOUNCE_CANCEL_NAVIGATION_AFTER_SPEECH_BYE_WAITPID_PASS");
}
static void voice_round_and_cancel(void)
{
    xy_runtime r;setup(&r,"normal","one");assert(xy_runtime_action(&r,XY_ACTION_SWITCH));
    assert(r.app.mode==XY_VOICE && r.app.microphone_enabled);
    uint64_t limit=now()+4000;while(r.voice.phase!=XYVB_ENGINE && now()<limit)tick(&r);
    assert(r.voice.phase==XYVB_ENGINE && r.engine_owner==XY_OWNER_VOICE);
    assert(r.app.voice_commands==1 && !r.voice.session.worker_busy && !r.voice.session.need_send);
    assert(!r.camera_active && !r.coach_active && !xy_runtime_space(&r,0));
    uint32_t token=r.voice.token,revision=r.voice.job_revision;
    assert(!xy_voice_bridge_engine_reply(&r.voice,token+1,revision,1,"b9c7","old",500,1,1));
    assert(!setenv("XQVOICE_AUDIO_DEVICE","idle",1));
    limit=now()+4000;while(r.voice.phase!=XYVB_SPEECH && now()<limit)tick(&r);
    assert(r.voice.phase==XYVB_SPEECH && r.speech_owner==XY_OWNER_VOICE && !r.voice.session.worker_busy);
    assert(!xy_voice_bridge_speech_reply(&r.voice,token,r.voice.job_revision+1,1));
    wait_job(&r,XY_IDLE);
    assert(r.app.voice_successes==1 && r.app.voice_tail_ms==470 && !r.voice.board.side);
    assert(r.app.voice_engine_stats_valid && r.speech.cleanup_confirmed);
    /* Start the next microphone request, then leave while its child is busy. */
    limit=now()+4000;while(!r.voice.session.worker_busy && now()<limit)tick(&r);
    assert(r.voice.session.worker_busy && !r.engine_owner && !r.speech_owner);
    xq_search_board_t before=r.voice.board;
    assert(xy_runtime_action(&r,XY_ACTION_SWITCH));
    limit=now()+4000;while(r.app.mode!=XY_COACH && now()<limit)tick(&r);
    assert(r.app.mode==XY_COACH && !r.app.microphone_enabled && !r.voice.session.worker_busy);
    assert(!memcmp(&before,&r.voice.board,sizeof(before)));
    shutdown_runtime(&r);puts("RUNTIME_REAL_VOICE_SESSION_ENGINE_SPEECH_MIC_EXCLUSIVE_LATE_ASR_CANCEL_PASS");
}
static void voice_restart_recovery(void)
{
    for(unsigned busy=0;busy<3;busy++) {
        xy_runtime r;setup(&r,busy?"hang":"exit","one");
        #if !XINYI_BATTLE_R17
        assert(!xy_runtime_action(&r,XY_ACTION_RESTART));
#endif
        assert(xy_runtime_action(&r,XY_ACTION_SWITCH));
        uint64_t limit=now()+4000;
        if(busy) {
            while(r.voice.phase!=XYVB_ENGINE && now()<limit)tick(&r);
            assert(r.voice.phase==XYVB_ENGINE && r.engine_owner==XY_OWNER_VOICE);
        } else {
            while(!r.voice.halted && now()<limit)tick(&r);
            assert(r.voice.halted && r.app.job==XY_IDLE && r.voice.board.side==1);
            assert(strstr(r.app.voice_result,"电脑应着未完成"));
        }
        uint32_t token=r.app.token,revision=r.voice.revision;
        assert(!setenv("XQVOICE_AUDIO_DEVICE","idle",1));
        if(busy)runtime_fixture_busy(1);
        assert(xy_runtime_action(&r,XY_ACTION_RESTART));
        if(busy){ticks(&r,30);assert(r.restart_requested && r.app.cancelling);runtime_fixture_busy(0);}
        if(busy==2) {
            xy_runtime_cancel(&r);assert(!r.restart_requested);
            limit=now()+4000;while((r.app.cancelling || r.engine_owner
#if XINYI_BATTLE_R17
                || r.navigation_requested
#endif
                ) && now()<limit)tick(&r);
            assert(r.app.page==XY_HOME && !r.app.microphone_enabled && !r.restart_requested);
            shutdown_runtime(&r);continue;
        }
        limit=now()+4000;
        while((r.restart_requested || r.navigation_requested || r.app.page!=XY_GAME) && now()<limit)tick(&r);
        assert(!r.restart_requested && !r.navigation_requested && r.app.page==XY_GAME && r.app.mode==XY_VOICE);
        assert(!r.voice.halted && !r.voice.board.side && r.voice.revision!=revision);
        assert(!r.app.voice_commands && !r.app.voice_successes && !r.app.voice_engine_stats_valid);
        assert(!r.app.voice_heard[0] && !r.app.voice_result[0] && r.app.microphone_enabled);
        unsigned pieces=0;for(unsigned i=0;i<90;i++)pieces+=r.voice.board.squares[i]!=0;
        assert(pieces==32 && !xy_voice_bridge_engine_reply(&r.voice,token,revision,1,"b9c7","old",500,128,1));
        shutdown_runtime(&r);
    }
    puts("RUNTIME_VOICE_RESTART_AFTER_ENGINE_FAILURE_OR_BUSY_DRAIN_RESETS32_AND_REJECTS_STALE_PASS");
}
static int mouse_square(xy_runtime *r,unsigned square)
{return xy_runtime_pointer(r,176+(square%9)*88,160+(9-square/9)*88);}
static void mouse_voice_round(void)
{
    xy_runtime r;setup(&r,"normal","idle");
    assert(!mouse_square(&r,27)); /* Image mode never accepts manual board moves. */
    assert(xy_runtime_action(&r,XY_ACTION_SWITCH));
    uint64_t until=now()+4000;while(!r.voice.session.worker_busy && now()<until)tick(&r);
    assert(r.voice.session.worker_busy);
    xq_search_board_t before=r.voice.board;
    assert(!mouse_square(&r,54)); /* Black is not selectable. */
    assert(mouse_square(&r,27) && r.app.voice_selected_valid);
    assert(mouse_square(&r,27) && !r.app.voice_selected_valid);
    assert(mouse_square(&r,27));
    assert(!mouse_square(&r,28) && r.app.voice_selected_valid); /* Pawn sideways. */
    assert(!memcmp(&before,&r.voice.board,sizeof(before)));
    assert(mouse_square(&r,36) && r.voice.mouse_pending && !r.app.voice_selected_valid);
    assert(!memcmp(&before,&r.voice.board,sizeof(before))); /* Wait for actual ASR drain. */
    assert(!mouse_square(&r,29));
    until=now()+4000;while(r.voice.phase!=XYVB_ENGINE && now()<until)tick(&r);
    assert(r.voice.phase==XYVB_ENGINE && !r.voice.session.worker_busy);
    assert(!r.voice.board.squares[27] && r.voice.board.squares[36]==PIECE_P);
    assert(r.voice.board.squares[25]==before.squares[25]); /* Late fake ASR cannon reply discarded. */
#if XINYI_BATTLE_R17
    assert(r.app.voice_mouse_input && !r.app.voice_heard[0]); /* Keyboard is never an ASR transcript. */
#else
    assert(r.app.voice_mouse_input && !strcmp(r.app.voice_heard,"a3a4"));
#endif
    assert(r.app.voice_commands==1 && !mouse_square(&r,29));
    wait_job(&r,XY_IDLE);
    assert(r.app.voice_successes==1 && r.app.voice_tail_ms==UINT32_MAX);
    assert(!r.voice.board.side && !r.voice.board.squares[82] && r.voice.board.squares[65]);
    assert(mouse_square(&r,29) && r.app.voice_selected_valid);
    xy_runtime_cancel(&r);assert(!r.app.voice_selected_valid);
    assert(mouse_square(&r,29));
    assert(mouse_square(&r,38) && r.voice.mouse_pending);
    assert(xy_runtime_action(&r,XY_ACTION_HOME));
    until=now()+4000;while(r.app.page!=XY_HOME && now()<until)tick(&r);
    assert(r.app.page==XY_HOME && !r.voice.mouse_pending && !r.app.microphone_enabled);
    assert(r.voice.board.squares[29]==PIECE_P && !r.voice.board.squares[38]);
    shutdown_runtime(&r);
    puts("RUNTIME_MOUSE_RED_SELECT_RESELECT_LEGAL_MOVE_LATE_ASR_DRAIN_ENGINE_SPEECH_NAVIGATION_CANCEL_PASS");
}
static void true_score_sorting(void)
{
    for(int mode=1;mode<=2;mode++){
        xy_runtime r;setup(&r,"hang","idle");runtime_fixture_exact_scores(mode);
        photo_to_coach(&r);runtime_fixture_consumed();runtime_fixture_coach_done(XY_COACH_RESULT);tick(&r);
        assert(r.app.photo.reason==XY_POSITION_VALID && r.app.job==XY_RECOMMEND);
        assert(r.engine_owner==XY_OWNER_COACH && !r.frame_pinned);
        /* All competing scores have the SAME confidence=875. These board
         * differences prove that runtime forwarded the full float score. */
        if(mode==1){
            assert(!r.app.photo.board.squares[0]);
            assert(r.app.photo.board.squares[36]==PIECE_R && r.app.photo.board.squares[8]==PIECE_R);
            assert(r.app.photo.removed_count==268 && r.app.photo.corrected[0]);
        }else{
            assert(r.app.photo.board.squares[3]==PIECE_K && !r.app.photo.board.squares[4]);
            assert(r.app.photo.removed_count==269 && r.app.photo.corrected[3] && r.app.photo.corrected[4]);
        }
        xy_runtime_cancel(&r);wait_job(&r,XY_IDLE);
        assert(!r.app.cancelling && !r.engine_owner);shutdown_runtime(&r);
    }
    puts("RUNTIME_FLOAT_SCORE_SAME_PERMILLE_THREE_ROOKS_AND_DUPLICATE_DIFFERENT_CLASS_PASS");
}
static void reaped_coach_cancel_reload(void)
{
    xy_runtime r;setup(&r,"normal","idle");photo_to_coach(&r);
    uint32_t old_token=r.app.token;xy_runtime_cancel(&r);
    assert(r.app.cancelling && runtime_fixture_coach_cancelled());
    runtime_fixture_consumed();tick(&r);
    assert(!r.frame_pinned && !runtime_fixture_pinned() && runtime_fixture_releases()==1);
    assert(r.app.cancelling && r.coach_active && runtime_fixture_client_opens()==1);
    runtime_fixture_reaped_cancel();tick(&r);
    assert(!r.app.cancelling && !r.coach_active && r.app.job==XY_IDLE && r.app.token!=old_token);
    assert(!r.fatal && runtime_fixture_client_closes()==1 && runtime_fixture_client_opens()==2);
    assert(!xy_coach_ready(r.coach) && !xy_runtime_space(&r,0));
    assert(!r.camera_active && !r.coach_active && !r.frame_pinned);
    runtime_fixture_worker_ready();tick(&r);
    assert(xy_coach_ready(r.coach) && runtime_fixture_client_closes()==1 && runtime_fixture_client_opens()==2);
    photo_to_coach(&r);runtime_fixture_consumed();runtime_fixture_coach_done(XY_COACH_RESULT);tick(&r);
    assert(r.app.job==XY_RECOMMEND && r.app.photo.reason==XY_POSITION_VALID);
    wait_job(&r,XY_ANNOUNCE);wait_job(&r,XY_IDLE);
    assert(r.app.has_recommendation && runtime_fixture_client_closes()==1 && runtime_fixture_client_opens()==2);
    shutdown_runtime(&r);assert(runtime_fixture_client_closes()==2);
    puts("RUNTIME_REAPED_CANCEL_CONSUMED_PIN_REOPEN_ASYNC_READY_AND_NEXT_SPACE_SUCCESS_PASS");
}
static void coach_fault_no_reload(void)
{
    const int faults[2]={XY_COACH_FATAL,XY_COACH_UNDRAINED};
    for(unsigned i=0;i<2;i++){
        xy_runtime r;setup(&r,"normal","idle");photo_to_coach(&r);
        runtime_fixture_consumed();runtime_fixture_coach_done(faults[i]);
        (void)xy_runtime_poll(&r);
        assert(r.fatal && !r.frame_pinned && !runtime_fixture_pinned());
        assert(runtime_fixture_client_opens()==1 && !runtime_fixture_client_closes());
        assert(!xy_runtime_space(&r,0) && !r.app.microphone_enabled);
        assert(!xy_runtime_shutdown(&r));
        assert(runtime_fixture_client_opens()==1 && runtime_fixture_client_closes()==1);
        errno=0;assert(waitpid(-1,NULL,WNOHANG)==-1 && errno==ECHILD);
    }
    puts("RUNTIME_FATAL_AND_UNDRAINED_NEVER_REOPEN_OR_ACK_AS_RECOVERY_PASS");
}
static void live_coremark_dirty(void)
{
    xy_runtime r;setup(&r,"normal","idle");
    assert(xy_runtime_action(&r,XY_ACTION_HOME));tick(&r);
    r.app.job=XY_COREMARK;r.app.coremark_origin=XY_COREMARK_BOARD;
    r.coremark.token=r.app.token;r.coremark.status=XY_CM_RUNNING;
    strcpy(r.coremark.output,"explicit live output fixture\n");
    r.coremark.output_used=strlen(r.coremark.output);
    r.dirty=0;tick(&r);
    assert(r.dirty && !strcmp(r.app.coremark_log,r.coremark.output));
    r.dirty=0;tick(&r);assert(!r.dirty);
    r.coremark.elapsed_ms=1234;r.coremark.progress=100;
    tick(&r);assert(r.dirty && r.app.coremark_elapsed_ms==1234 && r.app.coremark_progress==100);
    r.dirty=0;tick(&r);assert(!r.dirty);
    r.coremark.elapsed_ms=1300;r.coremark.progress=50;
    tick(&r);assert(!r.dirty && r.app.coremark_elapsed_ms==1234 && r.app.coremark_progress==100);
    r.coremark.status=XY_CM_FAILED;tick(&r);
    assert(r.dirty && r.app.job==XY_IDLE && !r.app.coremark_measured);
    shutdown_runtime(&r);
    puts("RUNTIME_COREMARK_LIVE_LOG_PROGRESS_DIRTY_QUIET_AND_STALE_GUARDS_PASS");
}
static void reference_and_log(void)
{
    xy_runtime r;setup(&r,"normal","idle");
    assert(xy_runtime_action(&r,XY_ACTION_HOME));tick(&r);
#if XINYI_HOME_R13
    double score=r.app.coremark_per_mhz;r.config.bitstream=NULL;
    assert(xy_runtime_action(&r,XY_ACTION_COREMARK) && r.app.page==XY_BENCHMARK);
    assert(!xy_runtime_action(&r,XY_ACTION_CM_RUN) && r.app.job==XY_IDLE);
    assert(xy_runtime_action(&r,XY_ACTION_CM_REFERENCE) && r.app.benchmark_reference_visible);
    assert(r.app.job==XY_IDLE && r.coremark.pid==-1 && !r.app.coremark_measured);
    assert(xy_runtime_action(&r,XY_ACTION_CM_LOG) && r.app.coremark_log_visible);
    assert(!xy_runtime_action(&r,XY_ACTION_START));
    assert(xy_runtime_action(&r,XY_ACTION_CM_LOG_CLOSE));
    assert(xy_runtime_action(&r,XY_ACTION_CM_REFERENCE) && !r.app.benchmark_reference_visible);
    assert(r.app.coremark_per_mhz==score && !r.app.coremark_log_used);
    shutdown_runtime(&r);
    puts("RUNTIME_R13_REFERENCE_DETAIL_NO_CHILD_NO_MEASURED_SCORE_NO_FAKE_OUTPUT_PASS");
#else
    double score=r.app.coremark_per_mhz;
    r.config.bitstream=NULL;
    r.dirty=0;
    assert(!xy_runtime_action(&r,XY_ACTION_COREMARK)); /* real test still requires assignment */
    assert(r.dirty);
    r.dirty=0;
    assert(xy_runtime_action(&r,XY_ACTION_CM_REFERENCE));
    assert(r.dirty);r.dirty=0;
    assert(r.app.job==XY_COREMARK && r.coremark.pid==-1);
    assert(xy_runtime_action(&r,XY_ACTION_CM_LOG) && r.app.coremark_log_visible);
    assert(r.dirty);r.dirty=0;
    assert(!xy_runtime_action(&r,XY_ACTION_START));
    assert(xy_runtime_action(&r,XY_ACTION_CM_LOG_CLOSE));
    assert(r.dirty);r.dirty=0;
    r.reference_started_ms=now()-9990;tick(&r);
    assert(r.app.job==XY_COREMARK && !r.app.coremark_measured);
    r.reference_started_ms=now()-10000;tick(&r);
    assert(r.dirty);
    assert(r.app.job==XY_IDLE && r.app.coremark_reference_shown && !r.app.coremark_measured);
    assert(r.app.coremark_per_mhz==score && r.coremark.pid==-1 && !r.app.coremark_log_used);
    assert(xy_runtime_action(&r,XY_ACTION_CM_REFERENCE));
    xy_runtime_cancel(&r);tick(&r);
    assert(r.app.job==XY_IDLE && !r.app.cancelling && r.app.coremark_per_mhz==score);
    shutdown_runtime(&r);
    puts("RUNTIME_REFERENCE_10S_NO_CHILD_NO_MEASURED_SCORE_NO_FAKE_OUTPUT_CANCEL_PASS");
#endif
}
#if XINYI_HOME_R13
void runtime_fixture_preview_event(xy_platform_operation,xy_platform_result,int,int,int);
static void camera_menu(void)
{
    for(unsigned phase=0;phase<4;phase++){
        xy_runtime r;setup(&r,"normal","idle");
        assert(xy_runtime_action(&r,XY_ACTION_HOME));tick(&r);
        assert(xy_runtime_action(&r,XY_ACTION_CAMERA) && r.app.page==XY_CAMERA_DEBUG);
        assert(xy_runtime_action(&r,XY_ACTION_PREVIEW) && r.app.preview_state==1 && r.camera_active);
        assert(!xy_runtime_space(&r,0) && !xy_runtime_action(&r,XY_ACTION_PREVIEW));
        if(phase==1){
            xy_runtime_cancel(&r);assert(r.navigation_requested && r.app.page==XY_CAMERA_DEBUG);
            runtime_fixture_preview_event(XY_PLATFORM_PREVIEW_STOP,XY_PLATFORM_CANCELLED,1,1,0);tick(&r);
        }else if(phase==2){
            runtime_fixture_preview_event(XY_PLATFORM_PREVIEW_START,XY_PLATFORM_UNDRAINED,0,0,0);
            (void)xy_runtime_poll(&r);assert(r.fatal && r.camera_active && !r.navigation_requested);
            assert(!xy_runtime_shutdown(&r));continue;
        }else{
            if(phase==3){
                runtime_fixture_preview_event(XY_PLATFORM_PREVIEW_START,XY_PLATFORM_FAILED,1,1,0);tick(&r);
                assert(!r.camera_active && !r.app.preview_state && r.app.page==XY_CAMERA_DEBUG);
                assert(xy_runtime_action(&r,XY_ACTION_PREVIEW));
            }
            runtime_fixture_preview_event(XY_PLATFORM_PREVIEW_START,XY_PLATFORM_OK,0,0,1);tick(&r);
            assert(r.app.preview_state==2 && r.camera_active && !r.frame_pinned);
            xy_runtime_cancel(&r);assert(r.app.preview_state==3 && r.app.page==XY_CAMERA_DEBUG);
            runtime_fixture_preview_event(XY_PLATFORM_PREVIEW_STOP,XY_PLATFORM_OK,1,1,0);tick(&r);
        }
        assert(!r.camera_active && !r.app.preview_state && r.app.page==XY_HOME && !r.frame_pinned);
        assert(xy_runtime_action(&r,XY_ACTION_EXIT) && r.exit_requested);
        shutdown_runtime(&r);
    }
    puts("RUNTIME_R13_PREVIEW_EXCLUSIVE_CANCEL_START_DRAIN_FAILURE_RECOVERY_EXIT_PASS");
}
#endif
#if XINYI_BATTLE_R17
static void r17_helper_prestart(void)
{
    char prepared_path[1024],played_path[1024];
    assert(snprintf(prepared_path,sizeof(prepared_path),"%s/audio-prepared",workdir)>0);
    assert(snprintf(played_path,sizeof(played_path),"%s/audio-played",workdir)>0);
    assert(!setenv("XY_AUDIO_PREPARED_MARKER",prepared_path,1) && !setenv("XY_AUDIO_PLAYED_MARKER",played_path,1));
    xy_runtime r;setup(&r,"normal","idle");
    (void)xy_runtime_poll(&r);assert(!r.fatal && r.speech.state==XY_SPEECH_PREPARING && !r.speech.ready);
    uint64_t until=now()+2000;
    while(!r.speech.ready && now()<until)tick(&r);
    /* Actual GUI-runtime -> exec worker must reach READY before a photo/move,
     * without an empty RUN, playback, or an audio/microphone owner. */
    assert(r.speech.pid>0 && r.speech.starts==1 && r.speech.ready);
    assert(!r.speech_owner && r.app.job==XY_IDLE && !r.app.microphone_enabled);
    assert(!r.speech.token && !r.speech.revision && !r.speech.request.count);
    assert(!access(prepared_path,R_OK) && access(played_path,F_OK));
    assert(!xy_speech_task_prepare(&r.speech,"/different-helper",workdir));
    pid_t prepared=r.speech.pid;valid_photo(&r);wait_job(&r,XY_ANNOUNCE);
    assert(r.speech.pid==prepared && r.speech.starts==1);wait_job(&r,XY_IDLE);
    assert(!access(played_path,R_OK));
    assert(xy_runtime_action(&r,XY_ACTION_HOME));until=now()+4000;
    while((r.navigation_requested || r.app.page!=XY_HOME) && now()<until)tick(&r);
    assert(r.app.page==XY_HOME && r.speech.pid<=0 && r.speech.cleanup_confirmed);
    assert(xy_runtime_action(&r,XY_ACTION_KEYBOARD));ticks(&r,30);
    assert(r.app.mode==XY_KEYBOARD && r.speech.starts==1 && r.speech.pid<=0 && !r.app.microphone_enabled);
    assert(xy_runtime_action(&r,XY_ACTION_VOICE));until=now()+2000;
    while(!r.speech.ready && now()<until)tick(&r);
    assert(r.speech.ready && r.speech.starts==2 && !r.speech_owner && r.app.microphone_enabled && r.voice.enabled);
    FILE *played=fopen(played_path,"r");long speaker=0;
    assert(played && fscanf(played,"%ld",&speaker)==1 && speaker>0 && fscanf(played,"%ld",&speaker)==EOF && !fclose(played));
    assert(xy_runtime_action(&r,XY_ACTION_KEYBOARD));wait_navigation(&r);
    assert(r.app.mode==XY_KEYBOARD && !r.app.microphone_enabled && r.speech.pid<=0 && r.speech.starts==2);
    shutdown_runtime(&r);
    assert(!unlink(prepared_path) && !unlink(played_path));
    /* A page switch during deliberately slow preparation must send QUIT,
     * accept its zero-token READY, and wait for BYE/waitpid without playback. */
    assert(!setenv("XY_AUDIO_PREPARE_DELAY_MS","200",1));setup(&r,"normal","idle");
    (void)xy_runtime_poll(&r);assert(!r.fatal && r.speech.state==XY_SPEECH_PREPARING);
    assert(xy_runtime_action(&r,XY_ACTION_HOME) && r.app.page==XY_GAME && r.navigation_requested);
    assert(r.speech.pid>0 && r.speech.closing && !r.speech_owner && !r.speech.request.count);
    until=now()+4000;while(r.navigation_requested && now()<until)tick(&r);
    assert(r.app.page==XY_HOME && r.speech.pid<=0 && r.speech.cleanup_confirmed && access(played_path,F_OK));
    shutdown_runtime(&r);assert(!unsetenv("XY_AUDIO_PREPARE_DELAY_MS"));
    /* Early real results can queue exactly one validated move while READY is
     * still pending. No second fork, empty request, or receive-time timer. */
    setup(&r,"normal","idle");assert(!setenv("XY_AUDIO_PREPARE_DELAY_MS","500",1));
    (void)xy_runtime_poll(&r);prepared=r.speech.pid;valid_photo(&r);wait_job(&r,XY_ANNOUNCE);
    assert(r.speech.pid==prepared && r.speech.starts==1 && r.speech.request.count==4);
    assert(r.speech.state==XY_SPEECH_STARTING && !r.speech.ready);
    wait_job(&r,XY_IDLE);assert(r.speech.pid==prepared && r.speech.starts==1 && r.speech.cleanup_confirmed);
    shutdown_runtime(&r);assert(!unsetenv("XY_AUDIO_PREPARE_DELAY_MS"));
    assert(!unsetenv("XY_AUDIO_PREPARED_MARKER") && !unsetenv("XY_AUDIO_PLAYED_MARKER"));
    /* A crashed preparation has no BYE/cleanup receipt and must stay fatal. */
    setup(&r,"normal","idle");assert(!setenv("XY_AUDIO_PREPARE_CRASH","1",1));
    until=now()+4000;while(!r.fatal && now()<until){(void)xy_runtime_poll(&r);nap();}
    assert(r.fatal && r.speech.state==XY_SPEECH_FAILED && r.speech.pid<=0 && !r.speech.cleanup_confirmed);
    assert(!xy_runtime_shutdown(&r));assert(!unsetenv("XY_AUDIO_PREPARE_CRASH"));
    errno=0;assert(waitpid(-1,NULL,WNOHANG)==-1 && errno==ECHILD);
    /* A preparation deadline still terminates/reaps the actual helper. No
     * missing BYE may be upgraded to a safe-cleanup acknowledgement. */
    setup(&r,"normal","idle");assert(!setenv("XY_AUDIO_PREPARE_DELAY_MS","2000",1));
    (void)xy_runtime_poll(&r);assert(r.speech.pid>0 && r.speech.state==XY_SPEECH_PREPARING);
    r.speech.deadline_ms=now();until=now()+4000;
    while(r.speech.pid>0 && now()<until){(void)xy_runtime_poll(&r);nap();}
    assert(r.speech.pid<=0 && r.speech.protocol_error && r.speech.state==XY_SPEECH_FAILED && !r.speech_owner);
    if(!r.speech.cleanup_confirmed)assert(r.fatal);
    int safe=r.speech.cleanup_confirmed && !r.fatal;assert(xy_runtime_shutdown(&r)==safe);
    assert(!unsetenv("XY_AUDIO_PREPARE_DELAY_MS"));errno=0;assert(waitpid(-1,NULL,WNOHANG)==-1 && errno==ECHILD);
    puts("RUNTIME_R17_PRESTART_READY_NO_EMPTY_RUN_OWNER_OR_RESPAWN_AND_KEYBOARD_CLOSE_PASS");
}
static void r17_keyboard_entry(void)
{
    xy_runtime r;setup(&r,"normal","idle");
    assert(xy_runtime_action(&r,XY_ACTION_KEYBOARD));
    assert(r.app.mode==XY_KEYBOARD && !r.app.microphone_enabled && r.app.voice_has_board);
    xq_search_board_t before=r.voice.board;
    assert(xy_runtime_key(&r,XY_KEY_UP) && r.app.keyboard_focus==13);
    assert(xy_runtime_key(&r,XY_KEY_LEFT) && r.app.keyboard_focus==12);
    r.app.keyboard_focus=27;assert(xy_runtime_key(&r,13) && r.app.voice_selected_valid);
    assert(xy_runtime_key(&r,27) && !r.app.voice_selected_valid);
    assert(xy_runtime_key(&r,13));assert(xy_runtime_key(&r,XY_KEY_UP));assert(xy_runtime_key(&r,13));
    assert(r.voice.mouse_pending);
    wait_job(&r,XY_VOICE_COMMAND);wait_job(&r,XY_IDLE);
    assert(r.app.voice_successes==1 && !r.voice.board.side);
    assert(!r.voice.board.squares[27] && r.voice.board.squares[36]==PIECE_P);
    assert(!r.app.microphone_enabled && !r.voice.session.worker_starts && !r.speech.starts && !r.speech_owner);
    assert(r.app.voice_engine_stats_valid && r.app.voice_win_rate==300);
    xq_search_board_t after=r.voice.board;
    assert(xy_runtime_action(&r,XY_ACTION_HOME));assert(r.app.page==XY_HOME);
    assert(xy_runtime_action(&r,XY_ACTION_KEYBOARD));assert(!memcmp(&after,&r.voice.board,sizeof(after)));
    assert(xy_runtime_action(&r,XY_ACTION_VOICE));assert(r.app.microphone_enabled && !memcmp(&after,&r.voice.board,sizeof(after)));
    assert(xy_runtime_action(&r,XY_ACTION_KEYBOARD));
    uint64_t until=now()+4000;while(r.app.mode!=XY_KEYBOARD && now()<until)tick(&r);
    assert(r.app.mode==XY_KEYBOARD && !r.app.microphone_enabled && !memcmp(&after,&r.voice.board,sizeof(after)));
    assert(xy_runtime_action(&r,XY_ACTION_RESTART));
    until=now()+4000;while(r.restart_requested && now()<until)tick(&r);
    assert(!r.restart_requested && r.app.mode==XY_KEYBOARD && !r.app.microphone_enabled);
    assert(!memcmp(&before,&r.voice.board,sizeof(before)) && !r.app.voice_engine_stats_valid);
    assert(xy_runtime_action(&r,XY_ACTION_IMAGE));
    r.app.has_board=r.app.current_photo_valid=1;r.app.photo.corrected_cells=9;
    assert(xy_runtime_action(&r,XY_ACTION_RESTART));tick(&r);
    assert(r.app.page==XY_GAME && r.app.mode==XY_COACH && !r.app.has_board && !r.app.current_photo_valid && !r.app.photo.corrected_cells);
    assert(!memcmp(&before,&r.voice.board,sizeof(before)));
    shutdown_runtime(&r);
    puts("RUNTIME_R17_KEYBOARD_NAVIGATION_SAFE_ENTRY_PASS");
}
static void r17_display_ack(void)
{
    xy_runtime r;setup(&r,"normal","idle");valid_photo(&r);
    assert(r.app.image_generation && !r.app.image_e2e_valid);
    uint64_t stamp=r.photo_started_ms+900;
    xy_runtime_frame_submitted(&r,1,UINT32_MAX);
    assert(!xy_runtime_display_ack(&r,6,UINT32_MAX,stamp));
    assert(!xy_runtime_display_ack(&r,6,0,stamp));
    assert(!xy_runtime_display_ack(&r,2,1,stamp)); /* Wrong bank. */
    assert(!xy_runtime_display_ack(&r,6|(1u<<5),1,stamp));
    assert(xy_runtime_display_ack(&r,6,1,stamp) && r.app.image_e2e_valid && r.app.image_e2e_ms==900);
    wait_job(&r,XY_ANNOUNCE);wait_job(&r,XY_IDLE);
    assert(r.app.image_e2e_ms==900); /* Recommendation never overwrites it. */
    assert(r.app.speech_e2e_valid && !r.app.speech_e2e_over_budget);
    assert(xy_runtime_space(&r,0));assert(!r.app.image_e2e_valid);
    assert(!xy_runtime_display_ack(&r,6,9,stamp+1000));
    xy_runtime_cancel(&r);runtime_fixture_camera_done(1);tick(&r);
    assert(!r.app.image_e2e_valid);
    shutdown_runtime(&r);
    puts("RUNTIME_R17_SCANOUT_BANK_GENERATION_WRAP_CANCEL_AND_FROZEN_IMAGE_TIME_PASS");
}
static void r17_asr_visible_before_engine(void)
{
    xy_runtime r;setup(&r,"normal","start");assert(xy_runtime_action(&r,XY_ACTION_VOICE));
    uint64_t until=now()+4000;
    while(!r.app.voice_generation && now()<until){(void)xy_runtime_poll(&r);assert(!r.fatal);nap();}
    assert(r.app.voice_generation && r.app.voice_heard[0] && r.voice.phase==XYVB_QUEUED);
    assert(!r.engine_owner && !r.speech_owner && !r.app.voice_e2e_valid && r.app.voice_started_valid);
    ticks(&r,1); /* Synthetic consumer now acknowledges that visible text. */
    assert(r.app.voice_e2e_valid && r.app.voice_e2e_ms>=1000);
    assert(!setenv("XQVOICE_AUDIO_DEVICE","idle",1));
    until=now()+4000;while(r.voice.phase!=XYVB_SPEECH && now()<until)tick(&r);
    assert(r.voice.phase==XYVB_SPEECH && r.speech_owner==XY_OWNER_VOICE);
    wait_job(&r,XY_IDLE);
    assert(r.app.speech_e2e_valid && r.speech.cleanup_confirmed);
    assert(r.app.voice_win_rate==300);
    shutdown_runtime(&r);
    puts("RUNTIME_R17_ASR_VISIBLE_FIRST_OPTIONAL_ONSET_AND_SPEECH_BUDGET_PASS");
}
static void r17_producer_budget(void)
{
    static const char *const modes[]={"queued","legacy","future-ready","old-ready","zero-ready"};
    for(unsigned i=0;i<5;i++){
        xy_runtime r;char ready_path[1400],release_path[1400];
        assert(snprintf(ready_path,sizeof(ready_path),"%s/producer-ready-%u",workdir,i)>0);
        assert(snprintf(release_path,sizeof(release_path),"%s/producer-release-%u",workdir,i)>0);
        assert(!setenv("XY_ENGINE_READY_MARKER",ready_path,1));
        assert(!setenv("XY_ENGINE_RELEASE_MARKER",release_path,1));
        setup(&r,modes[i],"idle");valid_photo(&r);
        if(!i){
            uint64_t until=now()+4000;
            while((r.engine.state!=XY_ENGINE_BUSY || r.engine.pending_bytes) && now()<until)tick(&r);
            assert(r.engine.state==XY_ENGINE_BUSY && !r.engine.pending_bytes);
            FILE *released=fopen(release_path,"w");assert(released);assert(!fclose(released));
            until=now()+4000;while(access(ready_path,R_OK) && now()<until)nap();
            FILE *ready=fopen(ready_path,"r");unsigned long long anchor=0;
            assert(ready && fscanf(ready,"%llu",&anchor)==1 && anchor);assert(!fclose(ready));
            /* The producer has written a complete reply; deliberately stop
             * GUI polling while it waits in the IPC channel. */
            const struct timespec queued={1,100000000};nanosleep(&queued,NULL);
            wait_job(&r,XY_ANNOUNCE);
            assert(r.speech_ready_us==anchor); /* RED for receive-time timing. */
            wait_job(&r,XY_IDLE);
            assert(r.app.speech_e2e_valid && r.app.speech_e2e_over_budget && r.app.speech_e2e_ms>=1100 && r.speech.cleanup_confirmed);
        }else{
            wait_job(&r,XY_ANNOUNCE);wait_job(&r,XY_IDLE);
            assert(r.app.has_recommendation && r.speech.cleanup_confirmed && !r.app.speech_e2e_valid && !r.app.speech_e2e_over_budget);
            assert(!r.speech_ready_us);
        }
        shutdown_runtime(&r);assert(!unsetenv("XY_ENGINE_READY_MARKER"));assert(!unsetenv("XY_ENGINE_RELEASE_MARKER"));
    }
    puts("RUNTIME_R17_PRODUCER_READY_IPC_QUEUE_INCLUDED_LEGACY_FUTURE_OLD_ZERO_TIMERS_UNAVAILABLE_PASS");
}
#endif
int main(int argc,char **argv)
{
    assert(argc==5);engine_path=argv[1];speech_path=argv[2];asr_path=argv[3];workdir=argv[4];
    #if XINYI_BATTLE_R17
    r17_helper_prestart();r17_keyboard_entry();r17_display_ack();r17_asr_visible_before_engine();r17_producer_budget();
#endif
    complete_photo_and_geometry();capture_cancel();coach_cancel();engine_cancel_busy();speech_cancel();voice_round_and_cancel();true_score_sorting();
    reaped_coach_cancel_reload();coach_fault_no_reload();live_coremark_dirty();reference_and_log();voice_restart_recovery();mouse_voice_round();
#if XINYI_HOME_R13
    camera_menu();
#endif
    puts("XINYI_RUNTIME_INTEGRATION_PASS_SYNTHETIC_HOST_OR_QEMU_NOT_BOARD");return 0;
}
