#define _POSIX_C_SOURCE 200809L
#include "runtime.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>

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
static void tick(xy_runtime *r){(void)xy_runtime_poll(r);assert(!r->fatal);nap();}
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
        assert(!xy_runtime_action(&r,XY_ACTION_RESTART));
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
            limit=now()+4000;while((r.app.cancelling || r.engine_owner) && now()<limit)tick(&r);
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
    assert(r.app.voice_mouse_input && !strcmp(r.app.voice_heard,"a3a4"));
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
}
int main(int argc,char **argv)
{
    assert(argc==5);engine_path=argv[1];speech_path=argv[2];asr_path=argv[3];workdir=argv[4];
    complete_photo_and_geometry();capture_cancel();coach_cancel();engine_cancel_busy();speech_cancel();voice_round_and_cancel();true_score_sorting();
    reaped_coach_cancel_reload();coach_fault_no_reload();live_coremark_dirty();reference_and_log();voice_restart_recovery();mouse_voice_round();
    puts("XINYI_RUNTIME_INTEGRATION_PASS_SYNTHETIC_HOST_OR_QEMU_NOT_BOARD");return 0;
}
