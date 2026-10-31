#ifndef XQVOICE_SESSION_H
#define XQVOICE_SESSION_H
#include <stdint.h>
#include <sys/types.h>
#include "xqvoice_notation.h"
enum {XQV_IDLE=0,XQV_RECORDING,XQV_READY,XQV_ERROR,XQV_CANCELLING,XQV_COMMITTED};
enum {XQV_RESULT_NONE=0,XQV_RESULT_COMMAND,XQV_RESULT_ILLEGAL,XQV_RESULT_UNRECOGNIZED,
      XQV_RESULT_UNAVAILABLE,XQV_RESULT_TOO_LONG};
enum {XQV_PHASE_CAPTURE=0,XQV_PHASE_INFER=1,XQV_PHASE_LISTEN=2};
enum {XQV_BUTTON_START=1,XQV_BUTTON_CONFIRM,XQV_BUTTON_RETRY,XQV_BUTTON_CANCEL};
#define XQV_BUTTON_Y 650
#define XQV_BUTTON_H 32
typedef struct {
    uint64_t request_us,cnn_us,decode_us;
    uint64_t endpoint_to_result_us,last_voice_to_result_us,feature_tail_us;
    unsigned valid;
#if XINYI_BATTLE_R17
    uint64_t utterance_start_us,utterance_to_result_us;
    unsigned utterance_valid;
#endif
} xqvoice_timing;
typedef struct {
    int state,fd,retry,phase,stop_requested,stop_delivered;
    pid_t pid;
    uint32_t next_request,request,revision;
    uint64_t deadline_ms, cancel_deadline_ms;
    uint64_t request_started_ms;
    uint32_t timing_request;
    xq_search_board_t snapshot;
    xqvoice_command_t command;
    char output[2048];size_t output_bytes;
    const char *error;
    int result,listening_ready;
    uint32_t result_generation;
    char result_text[64],heard_text[32],pending_phrase[13];
    uint32_t quiet_rejections;
    xqvoice_command_t displayed_command;
    uint64_t next_start_ms;
    int command_fd,worker_ready,worker_busy,need_send,reply_received,reply_code;
    uint32_t worker_request,worker_starts;
    char reply_text[32],input_path[1024],input_kind;
    char transmit[2200];size_t transmit_used,transmit_sent;
    /* Valid only for a completed live utterance of this revision. request_us
       includes waiting/listening; last_voice tail includes VAD silence. */
    xqvoice_timing timing,reply_timing;
} xqvoice_session;
void xqvoice_session_init(xqvoice_session *s);
int xqvoice_session_start(xqvoice_session *s,const xq_search_board_t *board,uint32_t revision,int ready);
void xqvoice_session_cancel(xqvoice_session *s);
int xqvoice_session_stop_recording(xqvoice_session *s);
void xqvoice_session_retry(xqvoice_session *s,const xq_search_board_t *board,uint32_t revision,int ready);
int xqvoice_session_poll(xqvoice_session *s,const xq_search_board_t *board,uint32_t revision,int ready);
int xqvoice_session_apply(xqvoice_session *s,xq_search_board_t *board,uint32_t revision,int ready,xq_search_move_t *move);
/* Poll, commit a legal result once, or arm the next utterance. No user confirmation. */
int xqvoice_session_auto_step(xqvoice_session *s,xq_search_board_t *board,uint32_t revision,int ready,xq_search_move_t *move);
void xqvoice_session_defer(xqvoice_session *s,unsigned milliseconds);
void xqvoice_session_close(xqvoice_session *s);
/* Stop this utterance and await microphone release, preserving the loaded worker. */
int xqvoice_session_pause(xqvoice_session *s);
int xqvoice_phrase(const char *utf8,xqvoice_command_t *command);
int xqvoice_button_at(int x,int y);
/* Implemented by the Linux renderer; old hardware/shared renderer untouched. */
void xq_fb_gui_set_voice_session(const xqvoice_session *s,int available);
#endif
