#ifndef XIANGQI_FB_GUI_H
#define XIANGQI_FB_GUI_H

#include <stdint.h>
#include "xiangqi_search.h"

#ifdef XQ_GUI_1080
#define XQ_FB_BOARD_X 176
#define XQ_FB_BOARD_Y 160
#define XQ_FB_CELL    88
#define XQ_FB_RESTART_X 1052
#define XQ_FB_RESTART_Y 906
#define XQ_FB_RESTART_W 740
#define XQ_FB_RESTART_H 64
#else
#define XQ_FB_BOARD_X 96
#define XQ_FB_BOARD_Y 72
#define XQ_FB_CELL    64
#define XQ_FB_RESTART_X 966
#define XQ_FB_RESTART_Y 594
#define XQ_FB_RESTART_W 204
#define XQ_FB_RESTART_H 48
#endif
#define XQ_FB_TIME_UNAVAILABLE 0xffffffffu
#define XQ_FB_WIN_RATE_UNAVAILABLE 0xffffffffu

typedef enum {
    XQ_FB_STATE_READY = 0,
    XQ_FB_STATE_SELECTED,
    XQ_FB_STATE_RESELECTED,
    XQ_FB_STATE_CANCELLED,
    XQ_FB_STATE_ILLEGAL,
    XQ_FB_STATE_SELECT_OWN,
    XQ_FB_STATE_MOUSE_MOVE,
    XQ_FB_STATE_EVAL_ERROR,
    XQ_FB_STATE_BLACK_THINK,
    XQ_FB_STATE_SEARCH_ERROR,
    XQ_FB_STATE_RED_WINS,
    XQ_FB_STATE_BLACK_MOVE,
    XQ_FB_STATE_EVALUATED,
    XQ_FB_STATE_NO_MOVE,
    XQ_FB_STATE_BEST_MOVE,
    XQ_FB_STATE_RESTARTED
} xq_fb_state_t;

int xq_fb_gui_init(void);
void xq_fb_gui_set_red_win_rate(uint32_t permille);
void xq_fb_gui_set_voice_feedback(const char *text);
int xq_fb_gui_show(const xq_search_board_t *board,
                   int selected_from, int selected_to,
                   int32_t score, uint32_t nodes,
                   uint32_t inference_ticks, xq_fb_state_t state);
uint32_t xq_fb_gui_status(void);

#endif
