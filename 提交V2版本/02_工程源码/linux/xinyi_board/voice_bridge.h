#ifndef XINYI_BOARD_VOICE_BRIDGE_H
#define XINYI_BOARD_VOICE_BRIDGE_H
#include "../xinyi/xinyi_product.h"
#include "../voice_ctc/xqvoice_session.h"

/* Single GUI event thread. start callbacks accept an asynchronous task only;
 * never run engine search or synchronous PCM playback in these callbacks.
 * Completion/stopped is reported after the worker has released its resources.
 * Root's voice_command backend calls xy_voice_bridge_command. */
typedef struct {
    void *context;
    int (*engine_start)(void *,uint32_t token,uint32_t revision,const xq_search_board_t *black);
    void (*engine_cancel)(void *,uint32_t token,uint32_t revision);
    int (*speech_start)(void *,uint32_t token,uint32_t revision,
                        const xq_search_board_t *before,const char *iccs);
    void (*speech_cancel)(void *,uint32_t token,uint32_t revision);
} xy_voice_bridge_ops;

enum { XYVB_IDLE,XYVB_QUEUED,XYVB_ENGINE,XYVB_SPEECH };
typedef struct {
    xy_app *app;
    xy_voice_bridge_ops ops;
    xqvoice_session session;
    xq_search_board_t board,engine_before;
    uint32_t revision,job_revision,token,reported_request;
    int initialized,enabled,phase,cancel_pending,external_active,cancel_sent;
    int pending_legal,halted,closing,speech_available,tail_valid;
    unsigned tail_ms;
    int mouse_pending;
    unsigned mouse_from,mouse_to;
    uint32_t mouse_revision;
    char pending_text[64],pending_result[XY_TEXT_BYTES],computer_iccs[5];
} xy_voice_bridge;

/* Init precedes xy_app_init so its microphone(0) hook can call enable(0).
 * ASR paths/backend are the existing XQVOICE_* environment contract. */
void xy_voice_bridge_init(xy_voice_bridge *,xy_app *,const xy_voice_bridge_ops *);
int xy_voice_bridge_enable(xy_voice_bridge *,int enabled);
/* Pause confirms the ASR microphone has closed. If an external engine/speech
 * task remains, it requests cancellation and returns 0 until stopped arrives. */
int xy_voice_bridge_pause(xy_voice_bridge *);
int xy_voice_bridge_poll(xy_voice_bridge *);
/* Accepts only the one transcript staged by poll; never an arbitrary injected
 * command. Called from xy_backend.voice_command, without recursive completion. */
int xy_voice_bridge_command(xy_voice_bridge *,uint32_t token,const char *text);
/* Queue a real legal mouse move; cancel/drain old ASR before committing it. */
int xy_voice_bridge_mouse_move(xy_voice_bridge *,unsigned from,unsigned to);
void xy_voice_bridge_cancel(xy_voice_bridge *,uint32_t token);
int xy_voice_bridge_engine_reply(xy_voice_bridge *,uint32_t token,uint32_t revision,
    int okay,const char *iccs,const char *notation,uint32_t red_win_permille,
    uint32_t nodes,uint32_t elapsed_us);
int xy_voice_bridge_engine_stopped(xy_voice_bridge *,uint32_t token,uint32_t revision);
int xy_voice_bridge_speech_reply(xy_voice_bridge *,uint32_t token,uint32_t revision,int okay);
int xy_voice_bridge_speech_stopped(xy_voice_bridge *,uint32_t token,uint32_t revision);
/* Only after a safe pause; never silently undo a committed human move. */
int xy_voice_bridge_reset(xy_voice_bridge *);
/* Returns 0 while cancellation of an external task awaits its stop receipt. */
int xy_voice_bridge_close(xy_voice_bridge *);
#endif
