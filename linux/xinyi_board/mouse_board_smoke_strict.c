/* Real-board diagnostic using the product's real platform/runtime and workers.
 * Coordinates are injected at the production pointer API. This does not test
 * physical mouse transport, microphone accuracy, or HDMI appearance. */
#define _POSIX_C_SOURCE 200809L
#include "runtime.h"
#include "../xinyi/xinyi_layout.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static unsigned long long now(void)
{struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;return (unsigned long long)t.tv_sec*1000+t.tv_nsec/1000000;}
static void tick(xy_runtime *r)
{const struct timespec t={0,5000000};(void)xy_runtime_poll(r);nanosleep(&t,NULL);}
static int square(xy_runtime *r,unsigned s)
{return xy_runtime_pointer(r,XY_BOARD_X+s%9*XY_BOARD_CELL,XY_BOARD_Y+(9-s/9)*XY_BOARD_CELL);}
#define CHECK(x) do {if(!(x)){printf("MOUSE_BOARD_FAIL line=%u expr=%s\n",__LINE__,#x);goto cleanup;}} while(0)
int main(void)
{
    xy_runtime r;xy_runtime_config c={0};xy_platform *p=NULL;int initialized=0,okay=0;
    unsigned long long limit; xq_search_board_t initial;
    setvbuf(stdout,NULL,_IOLBF,0);
    c.coach_worker=getenv("XINYI_COACH_WORKER");c.models=getenv("XINYI_MODELS");
    c.engine=getenv("XINYI_ENGINE");c.speech_worker=getenv("XINYI_SPEECH_WORKER");
    c.pcm=getenv("XINYI_PCM");c.coremark=getenv("XINYI_COREMARK");c.search_nodes=512;
    CHECK(c.coach_worker && c.models && c.engine && c.speech_worker && c.pcm && c.coremark);
    p=xy_platform_open();CHECK(p && xy_platform_cpu_hz(p)==75000000u);
    initialized=1;CHECK(xy_runtime_init(&r,p,&c));
    initial=r.voice.board;
    CHECK(xy_runtime_action(&r,XY_ACTION_SWITCH));
    limit=now()+180000;
    while((r.app.page!=XY_GAME || r.app.mode!=XY_VOICE || !r.voice.session.worker_busy) && now()<limit && !r.fatal)tick(&r);
    CHECK(!r.fatal && r.app.page==XY_GAME && r.app.mode==XY_VOICE && r.voice.session.worker_busy);
    CHECK(!square(&r,54));
    CHECK(square(&r,27) && r.app.voice_selected_valid);
    CHECK(square(&r,27) && !r.app.voice_selected_valid);
    CHECK(square(&r,27));
    CHECK(!square(&r,28) && r.app.voice_selected_valid && !memcmp(&initial,&r.voice.board,sizeof(initial)));
    CHECK(square(&r,36) && r.voice.mouse_pending && !r.app.voice_selected_valid);
    CHECK(!square(&r,29));
    puts("MOUSE_BOARD_LEGAL_INPUT_QUEUED_WAITING_REAL_ASR_DRAIN_ENGINE_SPEECH");
    limit=now()+360000;
    while((r.app.voice_successes!=1 || r.app.job!=XY_IDLE) && now()<limit && !r.fatal)tick(&r);
    CHECK(!r.fatal && r.app.job==XY_IDLE && r.app.voice_successes==1 && r.app.voice_commands==1);
    CHECK(!r.voice.board.side && !r.voice.board.squares[27] && r.voice.board.squares[36]==PIECE_P);
    CHECK(r.app.voice_mouse_input && !strcmp(r.app.voice_heard,"a3a4") && r.app.voice_tail_ms==UINT32_MAX);
    CHECK(r.app.voice_engine_stats_valid && r.app.voice_engine_nodes>0 && r.speech.starts>0);
    CHECK(r.speech.state==XY_SPEECH_DONE && r.speech.result_received && r.speech.cleanup_confirmed && !r.speech.result_status && !r.speech.underflows);
    printf("MOUSE_BOARD_REAL_ENGINE_SPEECH_PASS nodes=%u engine_us=%u speech_starts=%u\n",r.app.voice_engine_nodes,r.app.voice_engine_us,r.speech.starts);
    CHECK(xy_runtime_action(&r,XY_ACTION_RESTART));
    limit=now()+30000;
    while((r.restart_requested || r.navigation_requested || r.app.page!=XY_GAME || r.app.mode!=XY_VOICE) && now()<limit && !r.fatal)tick(&r);
    CHECK(!r.fatal && !r.restart_requested && !r.navigation_requested && r.app.voice_commands==0);
    CHECK(!memcmp(&initial,&r.voice.board,sizeof(initial)));
    CHECK(square(&r,27) && square(&r,36) && r.voice.mouse_pending);
    CHECK(xy_runtime_action(&r,XY_ACTION_HOME));
    limit=now()+30000;
    while((r.app.page!=XY_HOME || r.navigation_requested) && now()<limit && !r.fatal)tick(&r);
    CHECK(!r.fatal && r.app.page==XY_HOME && !r.voice.mouse_pending && !r.app.microphone_enabled);
    CHECK(!memcmp(&initial,&r.voice.board,sizeof(initial)));
    okay=1;
cleanup:
    if(initialized && !xy_runtime_shutdown(&r))okay=0;
    if(p && !xy_platform_close(p))okay=0;
    if(okay)puts("MOUSE_BOARD_REAL_RUNTIME_LEGAL_MOVE_ASR_DRAIN_PIKAFISH_SPEECH_RESTART_HOME_AUDIO_ACK_NO_UNDERFLOW_PASS_PHYSICAL_TRANSPORT_UNTESTED");
    return okay?0:2;
}
