#ifndef XQ_PICTURE_H
#define XQ_PICTURE_H
#include "xq_vision.h"

typedef enum { XQP_RED, XQP_ENGINE, XQP_BLACK, XQP_MANUAL,
               XQP_RESTART, XQP_FINISHED } xqp_phase;
typedef enum { XQP_RETAKE, XQP_MISMATCH, XQP_EDIT, XQP_SEARCH,
               XQP_ACCEPTED, XQP_NEWGAME_REQUIRED, XQP_BAD_RESULT } xqp_event;
typedef struct {
    xqp_phase phase, resume_phase;
    xq_search_board_t confirmed, expected, observed;
    uint16_t threshold;
    unsigned failures;
    char red_move[5], black_move[5];
} xqp_game;
void xqp_init(xqp_game *, const xq_search_board_t *, uint16_t threshold);
xqp_event xqp_observe(xqp_game *, const xqv_result *, uint32_t frame);
xqp_event xqp_confirm_manual(xqp_game *);
int xqp_edit(xqp_game *, unsigned square, int direction);
int xqp_engine_move(xqp_game *, const xq_search_board_t *, const char *move);
/* Restricted HID contract: start with keys released, one supported key alone, complete
 * press/release within 2 seconds, no lost/reordered reports. Hardware exposes
 * last ASCII/usage, not current key-down state. Require exactly two reports
 * and 250 ms quiet; ambiguous bursts are discarded, never queued as moves. */
typedef struct {
    uint32_t last_frame, pending_reports;
    uint64_t first_ms, last_report_ms;
    unsigned key;
} xqp_hid;
void xqp_hid_init(xqp_hid *, uint32_t frame, uint64_t now_ms);
/* Returns 1: one complete pair; 0: wait; -1: incomplete/ambiguous input. */
int xqp_hid_poll(xqp_hid *, uint32_t frame, uint32_t packed_report, uint64_t now_ms);
/* Same bounded report-pair policy; returns ASCII Space/Esc/r/c, or -1. */
int xqp_hid_poll_key(xqp_hid *, uint32_t frame, uint32_t packed_report, uint64_t now_ms);
#endif
