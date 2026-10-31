#ifndef XINYI_BOARD_RUNTIME_H
#define XINYI_BOARD_RUNTIME_H
#include "../xinyi/xinyi_product.h"
#include "../xinyi/coremark/process.h"
#include "platform.h"
#include "voice_bridge.h"
#include "engine_bridge.h"
#include "speech_task.h"
#include "coach_task.h"
#include "accelerator_idle.h"
typedef struct {
    const char *coach_worker,*models,*engine,*speech_worker,*pcm,*coremark,*bitstream;
    unsigned search_nodes;
} xy_runtime_config;
enum { XY_OWNER_NONE,XY_OWNER_COACH,XY_OWNER_VOICE };
typedef struct {
    xy_app app;
    xy_runtime_config config;
    xy_platform *platform;
    xy_accelerator accelerator;
    xy_voice_bridge voice;
    xy_engine engine;
    xy_speech_task speech;
    xy_coach_task *coach;
    xy_cm_process coremark;
    int engine_owner,speech_owner,camera_active,coach_active,frame_pinned;
    int fatal,exit_requested,dirty,navigation_requested,restart_requested;
    xy_page destination_page;
    xy_mode destination_mode;
    uint32_t camera_token,frame_token,engine_token,engine_revision,speech_token,speech_revision;
    uint64_t photo_started_ms,drain_deadline_ms,reference_started_ms;
    xq_search_board_t recommendation_board;
    char recommendation_iccs[5];
#if XINYI_BATTLE_R17
    xy_mode restart_mode;
    uint32_t image_token;
    uint64_t speech_ready_ms;
    uint64_t speech_ready_us;
    struct { uint32_t token,image_generation,voice_generation,frame; int pending; } displayed[2];
#endif
} xy_runtime;
/* No mock backends in this entry point. Hardware/source checks precede init. */
int xy_runtime_init(xy_runtime *,xy_platform *,const xy_runtime_config *);
int xy_runtime_poll(xy_runtime *);
int xy_runtime_action(xy_runtime *,xy_pointer_event);
int xy_runtime_pointer(xy_runtime *,unsigned x,unsigned y);
int xy_runtime_space(xy_runtime *,uint64_t physical_press_ms);
void xy_runtime_cancel(xy_runtime *);
int xy_runtime_shutdown(xy_runtime *);
#if XINYI_BATTLE_R17
int xy_runtime_key(xy_runtime *,int key);
void xy_runtime_frame_submitted(xy_runtime *,unsigned page,uint32_t video_frame);
/* status is the real video source/bank/error register, not a requested bank. */
int xy_runtime_display_ack(xy_runtime *,uint32_t video_status,uint32_t video_frame,uint64_t now_ms);
#endif
#endif
