#ifndef XINYI_PRODUCT_H
#define XINYI_PRODUCT_H

#include <stddef.h>
#include <stdint.h>
#include "xiangqi_search.h"

#define XY_MAX_DETECTIONS 300u
#define XY_TEXT_BYTES 192u
#define XY_CM_LOG_BYTES 16384u
#define XY_CM_LOG_COLUMNS 168u
#define XY_CM_LOG_ROWS 27u
#define XY_POINTER_TARGETS 5u

/* Coordinates match xq_search: file a..i, rank 0 at red's home edge.
 * Classes match XQV: red K,A,B,N,R,C,P, then black in the same order.
 * Input must already have passed immutable frame/protocol/geometry checks.
 * This layer neither fits corners nor changes any numerical vision guard. */
typedef struct {
    uint8_t class_id, file, rank;
    uint16_t confidence;
} xy_detection;
/* Real protocol inputs retain the complete fused float score. Permille is
 * presentation only; two different scores in one permille are not a tie. */
typedef struct {
    uint8_t class_id,file,rank;
    uint16_t confidence;
    float score;
} xy_scored_detection;

typedef enum { XY_HOME, XY_GAME } xy_page;
typedef enum { XY_ACTION_NONE, XY_ACTION_START, XY_ACTION_COREMARK,
               XY_ACTION_CANCEL, XY_ACTION_SWITCH, XY_ACTION_HOME,
               XY_ACTION_CM_LOG, XY_ACTION_CM_LOG_CLOSE, XY_ACTION_CM_LOG_PREV,
               XY_ACTION_CM_LOG_NEXT, XY_ACTION_CM_REFERENCE, XY_ACTION_RESTART } xy_pointer_event;
typedef struct { xy_pointer_event action; unsigned x,y,w,h; } xy_pointer_target;
typedef enum { XY_COACH, XY_VOICE } xy_mode;
typedef enum { XY_IDLE, XY_CAPTURE, XY_RECOMMEND, XY_VOICE_COMMAND,
               XY_COREMARK, XY_ANNOUNCE } xy_job;
typedef enum { XY_COREMARK_NONE, XY_COREMARK_BOARD, XY_COREMARK_MOCK, XY_COREMARK_REFERENCE }
    xy_coremark_origin;
typedef enum { XY_POSITION_VALID, XY_POSITION_BAD_INPUT,
               XY_POSITION_MISSING_KING, XY_POSITION_PIECE_PLACEMENT,
               XY_POSITION_FACING_KINGS, XY_POSITION_BLACK_IN_CHECK,
               XY_POSITION_NO_RED_MOVE } xy_position_reason;

typedef struct {
    xq_search_board_t board;
    uint8_t corrected[90];
    uint16_t confidence;
    unsigned removed_count, corrected_cells;
    xy_position_reason reason;
} xy_repair_result;

/* Nonblocking backend contract: start returns 1 only after accepting the job.
 * Completion must echo the exact token. cancel requests a safe stop; the
 * caller must report xy_cancel_complete only after camera DDR drain / ASR /
 * engine / benchmark stop has finished. Switching/home wait for that ack.
 * microphone(enabled=0) must close recognition input, not merely mute UI.
 * Real CoreMark is an adapter to the board benchmark; this module never
 * simulates a score or converts a host benchmark into a board result. */
typedef struct {
    void *context;
    int (*microphone)(void *, int enabled);
    int (*capture)(void *, uint32_t token);
    int (*recommend)(void *, uint32_t token, const xq_search_board_t *red);
    int (*voice_command)(void *, uint32_t token, const char *text);
    int (*coremark)(void *, uint32_t token, unsigned target_ms);
    void (*cancel)(void *, xy_job, uint32_t token);
    void (*speak)(void *, const char *notation);
} xy_backend;

typedef struct {
    xy_backend backend;
    xy_page page, pending_page;
    xy_mode mode, pending_mode;
    xy_job job;
    uint32_t token;
    int cancelling, navigation_pending, microphone_enabled, microphone_ready;
    int has_board, geometry_failed, has_recommendation;
    int current_photo_valid;
    unsigned partial_count,partial_classes[14]; /* Unmapped candidates, no grid coordinates. */
    int estimated_position; /* Diagnostic provenance; never a strict geometry PASS. */
    xy_repair_result photo;
    xq_search_board_t voice_board;
    int voice_has_board;
    int voice_selected_valid,voice_mouse_input;
    unsigned voice_selected;
    xq_search_move_t recommendation;
    char notation[XY_TEXT_BYTES], message[XY_TEXT_BYTES];
    char voice_heard[XY_TEXT_BYTES], voice_result[XY_TEXT_BYTES];
    unsigned voice_commands, voice_successes, voice_tail_ms;
    uint32_t voice_win_rate, voice_engine_nodes, voice_engine_us;
    int voice_engine_stats_valid;
    unsigned photo_latency_ms;
    int photo_latency_valid;
    xy_coremark_origin coremark_origin;
    unsigned coremark_progress, coremark_elapsed_ms;
    int coremark_measured;
    double coremark_per_mhz;
    uint32_t coremark_cpu_hz;
    char coremark_identity[96];
    int coremark_log_visible,coremark_log_truncated,coremark_reference_shown;
    unsigned coremark_log_page,coremark_reference_index;
    double coremark_reference_per_mhz;
    size_t coremark_log_used;
    char coremark_log[XY_CM_LOG_BYTES];
} xy_app;

int xy_repair(const xy_detection *, unsigned count, xy_repair_result *);
int xy_repair_scored(const xy_scored_detection *,unsigned count,xy_repair_result *);
const char *xy_position_reason_text(xy_position_reason);
void xy_app_init(xy_app *, const xy_backend *);
xy_pointer_event xy_pointer_action(const xy_app *,unsigned x,unsigned y);
int xy_board_square(unsigned x,unsigned y,unsigned *square);
unsigned xy_pointer_targets(const xy_app *,xy_pointer_target *,unsigned capacity);
int xy_navigate(xy_app *, xy_page, xy_mode);
int xy_capture_begin(xy_app *);
int xy_capture_complete(xy_app *, uint32_t token, int geometry_ok,
                        const xy_detection *, unsigned count,
                        unsigned latency_ms);
int xy_capture_partial(xy_app *,uint32_t token,const unsigned classes[14],unsigned count,unsigned latency_ms);
int xy_capture_estimated(xy_app *,uint32_t token,const xy_scored_detection *,unsigned count,unsigned latency_ms);
int xy_capture_complete_scored(xy_app *,uint32_t token,int geometry_ok,
    const xy_scored_detection *,unsigned count,unsigned latency_ms);
int xy_recommend_complete(xy_app *, uint32_t token, int okay,
                          xq_search_move_t, const char *chinese_notation);
/* Speech keeps the job occupied until the exact token completes or its safe
 * cancel ack. A failed announcement keeps the recommendation visible. */
int xy_announce_complete(xy_app *,uint32_t token,int okay);
/* Adapter supplies the elapsed Space-to-terminal time, including engine time
 * for a valid photo. Never synthesize this from a hardware busy counter. */
int xy_photo_elapsed(xy_app *, uint32_t token, unsigned elapsed_ms);
int xy_voice_begin(xy_app *, const char *recognized_text);
int xy_voice_complete(xy_app *, uint32_t token, int okay,
                      const xq_search_board_t *, const char *result,
                      unsigned tail_ms);
int xy_voice_engine_stats(xy_app *, uint32_t token, uint32_t red_win_permille,
                          uint32_t nodes, uint32_t elapsed_us);
int xy_cancel(xy_app *);
int xy_cancel_complete(xy_app *, uint32_t token);
/* Runtime calls this only after ASR/engine/speech cancellation and mic-off. */
int xy_voice_reset_presentation(xy_app *);
int xy_coremark_begin(xy_app *, xy_coremark_origin);
int xy_coremark_progress(xy_app *, uint32_t token, unsigned elapsed_ms,
                         unsigned progress_permille);
int xy_coremark_complete(xy_app *, uint32_t token, int crc_valid,
                         uint64_t iterations, uint64_t timer_ticks,
                         uint32_t timer_hz, uint32_t cpu_hz,
                         const char *bitstream_identity);
int xy_coremark_log_action(xy_app *,xy_pointer_event);
/* A labeled ten-second presentation of an upstream ROM result. Never changes
 * coremark_measured/per_mhz/identity or supplies a fabricated execution log. */
int xy_coremark_reference_complete(xy_app *,uint32_t token);
unsigned xy_coremark_log_lines(const xy_app *);
double xy_coremark_display_score(const xy_app *);

/* Product extension of the existing GUI1080 renderer. Caller owns the active
 * framebuffer and present/ABI checks. All stores remain the imported word-safe
 * primitives; board/piece/font/wood/highlight/coordinates are never replaced.
 * Invalidate after camera use, external drawing or swapping the framebuffer.
 * Render never touches video MMIO or assumes an accepted bitstream identity. */
void xy_fb_render(const xy_app *, volatile uint16_t *rgb565);
void xy_fb_invalidate(void);
size_t xy_state_json(const xy_app *, char *, size_t capacity);

/* Opaque FFI helpers used only by the local synthetic host preview. */
xy_app *xy_host_create(void);
void xy_host_destroy(xy_app *);
int xy_host_event(xy_app *, const char *event);
size_t xy_host_rgb888(xy_app *, unsigned char *, size_t capacity);

#endif
