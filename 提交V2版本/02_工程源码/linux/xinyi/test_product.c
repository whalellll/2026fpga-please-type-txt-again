#include "xinyi_product.h"
#include "xinyi_layout.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

typedef struct { int mic, mic_fail, camera, engine, voice, cancel, speech, coremark; } fake;
static int microphone(void *p, int enabled)
{ fake *f=p; if (f->mic_fail) return 0; f->mic=enabled; return 1; }
static int capture(void *p, uint32_t token)
{ fake *f=p; assert(!f->mic && token); ++f->camera; return 1; }
static int engine(void *p, uint32_t token, const xq_search_board_t *b)
{ fake *f=p; assert(!f->mic && token && b->side==0); ++f->engine; return 1; }
static int voice(void *p, uint32_t token, const char *text)
{ fake *f=p; assert(f->mic && token && text[0]); ++f->voice; return 1; }
static void cancel(void *p, xy_job job, uint32_t token)
{ fake *f=p; assert(job!=XY_IDLE && token); ++f->cancel; }
static void speak(void *p, const char *text)
{ fake *f=p; assert(text[0]); ++f->speech; }
static int benchmark(void *p, uint32_t token, unsigned ms)
{ fake *f=p; assert(token && (ms==45000 || ms==10000) && !f->mic); ++f->coremark; return 1; }
static xy_backend backend(fake *f)
{
    xy_backend b={f,microphone,capture,engine,voice,benchmark,cancel,speak};
    return b;
}
static unsigned minimum(xy_detection *d)
{
    d[0]=(xy_detection){0,4,0,999};
    d[1]=(xy_detection){7,4,9,998};
    d[2]=(xy_detection){6,4,3,950};
    return 3;
}
static void repair_tests(void)
{
    xy_detection d[XY_MAX_DETECTIONS], before[XY_MAX_DETECTIONS];
    xy_repair_result r;
    unsigned n=minimum(d), i, j;
    assert(xy_repair(d,n,&r) && r.reason==XY_POSITION_VALID);
    assert(r.board.side==0 && r.confidence==950 && !r.removed_count);
    /* 55 generated confidence patterns, not CAMERA_v2 / game photos. */
    for (i=0; i<55; ++i) {
        n=minimum(d);
        d[n++]=(xy_detection){4,0,0,(uint16_t)(800+i)};
        d[n++]=(xy_detection){4,8,0,900};
        d[n++]=(xy_detection){4,0,4,(uint16_t)(100+i)};
        memcpy(before,d,sizeof(d));
        assert(xy_repair(d,n,&r) && r.reason==XY_POSITION_VALID);
        assert(!memcmp(d,before,sizeof(d)) && r.removed_count==1 && r.corrected_cells==1);
        assert(!r.board.squares[36] && r.corrected[36]);
        for(j=0;j<90;++j) if(r.board.squares[j]) {
            unsigned k;
            for(k=0;k<n;++k) if(d[k].file==j%9 && d[k].rank==j/9 &&
                r.board.squares[j]==d[k].class_id%7+1+(d[k].class_id>=7?SIDE_BLACK:0)) break;
            assert(k<n); /* Every output piece came from input. */
        }
    }
    n=minimum(d);
    d[n++]=(xy_detection){4,0,0,800};
    d[n++]=(xy_detection){5,0,0,801};
    assert(xy_repair(d,n,&r) && r.board.squares[0]==PIECE_C && r.removed_count==1);
    d[n++]=(xy_detection){4,0,0,801};
    assert(xy_repair(d,n,&r) && r.board.squares[0]==PIECE_C && r.removed_count==2 && r.corrected_cells==1);
    n=minimum(d);
    d[n++]=(xy_detection){4,0,0,900}; d[n++]=(xy_detection){4,8,0,900};
    d[n++]=(xy_detection){4,0,4,900};
    assert(xy_repair(d,n,&r) && !r.board.squares[36]); /* Stable confidence tie. */
    assert(xy_repair(d,1,&r) && r.reason==XY_POSITION_MISSING_KING);
    n=minimum(d); d[2].class_id=99;
    assert(!xy_repair(d,n,&r) && r.reason==XY_POSITION_BAD_INPUT);
    d[2].class_id=6; d[2].confidence=1001; assert(!xy_repair(d,n,&r));
    assert(!xy_repair(d,XY_MAX_DETECTIONS+1,&r));
    n=minimum(d);
    for(i=n;i<XY_MAX_DETECTIONS;++i)d[i]=(xy_detection){6,4,3,(uint16_t)(700+i%201)};
    assert(xy_repair(d,200,&r) && r.reason==XY_POSITION_VALID && r.removed_count==197);
    assert(xy_repair(d,XY_MAX_DETECTIONS,&r) && r.reason==XY_POSITION_VALID &&
        r.removed_count==297 && r.corrected_cells==1 && r.board.squares[31]==PIECE_P);
    n=minimum(d); d[2].rank=1;
    assert(xy_repair(d,n,&r) && r.reason==XY_POSITION_FACING_KINGS && r.removed_count==1 && !r.board.squares[13]);
    n=minimum(d);d[n++]=(xy_detection){2,4,7,999}; /* Impossible red elephant. */
    assert(xy_repair(d,n,&r) && r.reason==XY_POSITION_VALID && r.removed_count==1 && !r.board.squares[67]);
    d[n++]=(xy_detection){4,4,7,900}; /* Illegal class cannot suppress a valid lower-score rook. */
    assert(xy_repair(d,n,&r) && r.board.squares[67]==PIECE_R && r.removed_count==1);
    n=minimum(d); assert(xy_repair(d,n-1,&r) && r.reason==XY_POSITION_FACING_KINGS);
    n=minimum(d); d[n++]=(xy_detection){4,4,8,950};
    assert(xy_repair(d,n,&r) && r.reason==XY_POSITION_BLACK_IN_CHECK);
    puts("XINYI_REPAIR_PASS 55_synthetic_third_rooks 300_candidates_no_truncation delete_only stable_ties unique_badges strict_rejects");
}
static void controller_tests(void)
{
    xy_app a;
    fake f={0}; xy_backend b=backend(&f);
    xy_detection d[8]; unsigned n=minimum(d), token;
    xq_search_board_t previous;
    xy_app_init(&a,&b);
    assert(a.page==XY_HOME && a.voice_tail_ms==UINT32_MAX && !f.mic && !xy_capture_begin(&a));
    assert(xy_navigate(&a,XY_GAME,XY_COACH) && xy_capture_begin(&a));
    token=a.token;
    assert(!xy_capture_begin(&a));
    assert(xy_capture_complete(&a,token,1,d,n,42) && a.job==XY_RECOMMEND && f.engine==1);
    assert(xy_recommend_complete(&a,token,1,(xq_search_move_t){31,40},"兵五进一"));
    assert(a.has_recommendation && f.speech==1 && a.job==XY_ANNOUNCE);
    assert(!xy_capture_begin(&a) && !xy_voice_begin(&a,"炮二平五"));
    assert(xy_photo_elapsed(&a,token,100));
    assert(!xy_announce_complete(&a,token-1,1));
    assert(xy_announce_complete(&a,token,0) && a.has_recommendation && a.job==XY_IDLE);
    assert(strstr(a.message,"播报失败"));
    previous=a.photo.board;
    assert(xy_capture_begin(&a)); token=a.token;
    assert(!xy_recommend_complete(&a,token-1,1,(xq_search_move_t){31,40},"过期"));
    assert(xy_capture_complete(&a,token,0,NULL,0,43) && a.geometry_failed);
    assert(!memcmp(&previous,&a.photo.board,sizeof(previous)) && f.engine==1 && !a.has_recommendation);
    assert(xy_capture_begin(&a)); token=a.token;
    assert(xy_capture_complete(&a,token,1,d,1,44) && a.has_board && !a.has_recommendation && f.engine==1);
    assert(a.photo.reason==XY_POSITION_MISSING_KING);
    assert(xy_capture_begin(&a)); token=a.token;
    assert(xy_navigate(&a,XY_GAME,XY_VOICE) && a.cancelling && !f.mic);
    assert(!xy_capture_complete(&a,token,1,d,n,45));
    assert(!xy_cancel_complete(&a,token-1) && !f.mic);
    assert(xy_cancel_complete(&a,token) && a.mode==XY_VOICE && f.mic);
    assert(!xy_voice_engine_stats(&a,token,700,1,20));
    assert(!xy_photo_elapsed(&a,token,999));
    assert(!xy_capture_begin(&a) && xy_voice_begin(&a,"炮二平五")); token=a.token;
    previous=a.photo.board;
    assert(xy_voice_complete(&a,token,1,&previous,"电脑已应着",99));
    assert(a.voice_commands==1 && a.voice_successes==1 && a.voice_has_board);
    assert(xy_navigate(&a,XY_GAME,XY_COACH) && !f.mic && !xy_voice_begin(&a,"不能输入"));
    assert(!memcmp(&previous,&a.photo.board,sizeof(previous)));
    assert(xy_capture_begin(&a)); token=a.token;
    assert(xy_capture_complete(&a,token,1,d,n,46));
    assert(xy_recommend_complete(&a,token,1,(xq_search_move_t){85,76},"黑方走法"));
    assert(!a.has_recommendation && f.speech==1);
    assert(xy_capture_begin(&a)); token=a.token;
    assert(xy_capture_complete(&a,token,1,d,n,46));
    assert(xy_recommend_complete(&a,token,1,(xq_search_move_t){31,40},"兵五进一"));
    assert(a.job==XY_ANNOUNCE && xy_navigate(&a,XY_GAME,XY_VOICE));
    assert(a.cancelling && a.job==XY_ANNOUNCE && !f.mic);
    assert(!xy_announce_complete(&a,token,1) && !xy_capture_begin(&a));
    assert(xy_cancel_complete(&a,token) && f.mic && a.mode==XY_VOICE);
    assert(!xy_announce_complete(&a,token,1));
    assert(xy_navigate(&a,XY_GAME,XY_COACH));
    f.mic_fail=1;
    assert(!xy_navigate(&a,XY_GAME,XY_VOICE) && a.mode==XY_COACH);
    xy_app_init(&a,&b);
    assert(!a.microphone_ready && !xy_navigate(&a,XY_GAME,XY_COACH));
    puts("XINYI_CONTROLLER_PASS red_always stale_results geometry_preserves_board cancellation_drain mic_exclusive invalid_no_engine");
    puts("XINYI_ANNOUNCE_PASS busy_capture_mic_exclusion failed_speech_visible navigation_safe_ack stale_token");
}
static void scored_tests(void)
{
    xy_scored_detection d[6]={{0,4,0,875,.875f},{7,4,9,875,.875f},{6,4,3,875,.875f},
        {4,0,0,900,.9001f},{4,8,0,900,.9005f},{4,0,4,900,.9009f}};
    xy_scored_detection reversed[6];xy_repair_result r,s;
    assert(xy_repair_scored(d,6,&r) && r.reason==XY_POSITION_VALID);
    assert(!r.board.squares[0] && r.board.squares[8]==PIECE_R && r.board.squares[36]==PIECE_R);
    assert(r.corrected[0] && r.removed_count==1);
    for(unsigned i=0;i<6;++i)reversed[i]=d[5-i];
    assert(xy_repair_scored(reversed,6,&s) && !memcmp(&r.board,&s.board,sizeof(r.board)));
    /* Different classes in the same cell still compare the complete score. */
    d[4]=(xy_scored_detection){5,0,0,900,.9009f};
    assert(xy_repair_scored(d,5,&r) && r.board.squares[0]==PIECE_C && r.removed_count==1);
    d[3].score=.9009f;
    assert(xy_repair_scored(d,5,&r) && r.board.squares[0]==PIECE_R); /* Exact tie is stable. */
    d[3].score=NAN;assert(!xy_repair_scored(d,5,&r) && r.reason==XY_POSITION_BAD_INPUT);
    d[3].score=1.001f;assert(!xy_repair_scored(d,5,&r));
    d[3].score=.049f;assert(!xy_repair_scored(d,5,&r));
    d[3].score=.9001f;d[3].confidence=901;assert(!xy_repair_scored(d,5,&r));
    d[3].confidence=900;d[4]=(xy_scored_detection){4,8,0,900,.9005f};
    fake f={0};xy_backend b=backend(&f);xy_app a;xy_app_init(&a,&b);
    assert(xy_navigate(&a,XY_GAME,XY_COACH) && xy_capture_begin(&a));
    assert(xy_capture_complete_scored(&a,a.token,1,d,6,99) && a.job==XY_RECOMMEND && f.engine==1);
    assert(!a.photo.board.squares[0] && a.photo.board.squares[36]==PIECE_R);
    puts("XINYI_SCORED_REPAIR_PASS full_float_same_permille reversed_input same_cell_different_class excess_rook finite_floor_guards capture_api");
}
static void benchmark_tests(void)
{
    xy_app a;
    fake f={0}; xy_backend b=backend(&f);
    double original; unsigned token;
    char json[8192], tiny[4];
    xy_app_init(&a,&b); original=a.coremark_per_mhz;
    assert(xy_coremark_begin(&a,XY_COREMARK_MOCK)); token=a.token;
    assert(xy_coremark_progress(&a,token,1000,500));
    assert(!xy_coremark_progress(&a,token,999,600));
    assert(!xy_coremark_progress(&a,token,1001,499));
    assert(xy_coremark_complete(&a,token,1,10000,45000000,1000000,60000000,"synthetic"));
    assert(!a.coremark_measured && a.coremark_per_mhz==original);
    assert(xy_coremark_begin(&a,XY_COREMARK_BOARD)); token=a.token;
    assert(xy_coremark_complete(&a,token,0,10000,45000000,1000000,60000000,"unit-test-only"));
    assert(!a.coremark_measured && a.coremark_per_mhz==original);
    assert(xy_coremark_begin(&a,XY_COREMARK_BOARD)); token=a.token;
    assert(xy_coremark_complete(&a,token,1,10000,45000000,1000000,60000000,"unit-test-only"));
    assert(a.coremark_measured && a.coremark_cpu_hz==60000000);
    assert(xy_coremark_begin(&a,XY_COREMARK_BOARD)); token=a.token;
    assert(xy_cancel(&a) && !xy_coremark_complete(&a,token,1,1,1,1,1,"late"));
    assert(xy_cancel_complete(&a,token));
    double measured=a.coremark_per_mhz;
    char identity[96];strcpy(identity,a.coremark_identity);
    for(unsigned i=0;i<7;i++) {
        assert(xy_coremark_begin(&a,XY_COREMARK_REFERENCE));token=a.token;
        assert(!xy_coremark_reference_complete(&a,token));
        assert(xy_coremark_progress(&a,token,9999,999));
        assert(!xy_coremark_reference_complete(&a,token));
        assert(xy_coremark_progress(&a,token,10000,1000));
        assert(xy_coremark_reference_complete(&a,token));
        assert(a.coremark_measured && a.coremark_per_mhz==measured);
        assert(!strcmp(a.coremark_identity,identity) && a.coremark_reference_shown);
        assert(xy_coremark_display_score(&a)>5.27 && xy_coremark_display_score(&a)<5.29);
    }
    assert(xy_coremark_begin(&a,XY_COREMARK_REFERENCE));token=a.token;
    assert(xy_cancel(&a) && xy_cancel_complete(&a,token));
    assert(!xy_coremark_reference_complete(&a,token));
    strcpy(a.coremark_log,"Compiler version : test fixture\nseedcrc : 0xe9f5\n");
    a.coremark_log_used=strlen(a.coremark_log);
    assert(xy_coremark_log_lines(&a)==2);
    assert(xy_coremark_log_action(&a,XY_ACTION_CM_LOG) && a.coremark_log_visible);
    assert(xy_pointer_action(&a,xy_layout_home_start.x,xy_layout_home_start.y)==XY_ACTION_NONE);
    assert(xy_coremark_log_action(&a,XY_ACTION_CM_LOG_NEXT) && !a.coremark_log_page);
    memset(a.coremark_log,'X',XY_CM_LOG_COLUMNS*28);a.coremark_log[XY_CM_LOG_COLUMNS*28]=0;
    a.coremark_log_used=XY_CM_LOG_COLUMNS*28;
    assert(xy_coremark_log_lines(&a)==28);
    assert(xy_coremark_log_action(&a,XY_ACTION_CM_LOG_NEXT) && a.coremark_log_page==1);
    assert(xy_coremark_log_action(&a,XY_ACTION_CM_LOG_PREV) && !a.coremark_log_page);
    assert(xy_coremark_log_action(&a,XY_ACTION_CM_LOG_CLOSE) && !a.coremark_log_visible);
    strcpy(a.message,"quote \" slash \\ newline\n");
    assert(xy_state_json(&a,json,sizeof(json)) && strstr(json,"\\\"") && strstr(json,"\\u000a"));
    assert(!xy_state_json(&a,tiny,sizeof(tiny)) && tiny[0]==0);
    puts("XINYI_COREMARK_PASS mock_never_scores crc_ticks_identity_required cancellation_preserves_result reference_10s_real_score_separate output_pages json_bounded");
}
static void pointer_tests(void)
{
    xy_app a={0};
    const xy_rect rects[]={xy_layout_home_start,xy_layout_home_coremark,xy_layout_coremark_cancel,
        xy_layout_mode_switch,xy_layout_game_home};
    const xy_pointer_event actions[]={XY_ACTION_START,XY_ACTION_COREMARK,XY_ACTION_CANCEL,
        XY_ACTION_SWITCH,XY_ACTION_HOME};
    unsigned i;
    for(i=0;i<5;++i) {
        a.page=i<3?XY_HOME:XY_GAME;a.job=i==2?XY_COREMARK:XY_IDLE;
        assert(xy_pointer_action(&a,rects[i].x,rects[i].y)==actions[i]);
        assert(xy_pointer_action(&a,rects[i].x+rects[i].w-1,rects[i].y+rects[i].h-1)==actions[i]);
        assert(xy_pointer_action(&a,rects[i].x+rects[i].w,rects[i].y+rects[i].h)==XY_ACTION_NONE);
        assert(xy_pointer_action(&a,rects[i].x-1,rects[i].y-1)==XY_ACTION_NONE);
    }
    a.page=XY_HOME;a.job=XY_COREMARK;
    assert(xy_pointer_action(&a,xy_layout_home_start.x,xy_layout_home_start.y)==XY_ACTION_NONE);
    assert(xy_pointer_action(&a,xy_layout_home_coremark.x,xy_layout_home_coremark.y)==XY_ACTION_NONE);
    a.cancelling=1;
    assert(xy_pointer_action(&a,xy_layout_coremark_cancel.x,xy_layout_coremark_cancel.y)==XY_ACTION_NONE);
    a.cancelling=0;a.page=XY_GAME;a.job=XY_CAPTURE;
    assert(xy_pointer_action(&a,xy_layout_mode_switch.x,xy_layout_mode_switch.y)==XY_ACTION_SWITCH);
    a.mode=XY_COACH;
    assert(xy_pointer_action(&a,xy_layout_voice_restart.x,xy_layout_voice_restart.y)==XY_ACTION_NONE);
    a.mode=XY_VOICE;a.job=XY_VOICE_COMMAND;
    assert(xy_pointer_action(&a,xy_layout_voice_restart.x,xy_layout_voice_restart.y)==XY_ACTION_RESTART);
    assert(xy_pointer_action(&a,xy_layout_voice_restart.x+xy_layout_voice_restart.w-1,
        xy_layout_voice_restart.y+xy_layout_voice_restart.h-1)==XY_ACTION_RESTART);
    a.cancelling=1;
    assert(xy_pointer_action(&a,xy_layout_voice_restart.x,xy_layout_voice_restart.y)==XY_ACTION_NONE);
    a.cancelling=0;
    assert(xy_pointer_action(&a,1920,0)==XY_ACTION_NONE && xy_pointer_action(&a,0,1080)==XY_ACTION_NONE);
    assert(xy_pointer_action(&a,0,0)==XY_ACTION_NONE && xy_pointer_action(NULL,112,336)==XY_ACTION_NONE);
    puts("XINYI_POINTER_PASS shared_native_layout edges home_start CoreMark_busy_cancel mode_home no_retired_entries");
}
int main(void)
{
    unsigned square;
    for(unsigned s=0;s<90;s++){
        assert(xy_board_square(176+(s%9)*88,160+(9-s/9)*88,&square) && square==s);
    }
    assert(xy_board_square(132,116,&square) && square==81);
    assert(xy_board_square(923,995,&square) && square==8);
    assert(!xy_board_square(131,160,&square) && !xy_board_square(176,115,&square));
    assert(!xy_board_square(924,160,&square) && !xy_board_square(176,996,&square));
    assert(!xy_board_square(UINT32_MAX,UINT32_MAX,&square) && !xy_board_square(176,160,NULL));
    repair_tests(); scored_tests(); controller_tests(); benchmark_tests(); pointer_tests();
    puts("XINYI_HOST_TEST_PASS (synthetic functional tests; no board measurements)");
    return 0;
}
