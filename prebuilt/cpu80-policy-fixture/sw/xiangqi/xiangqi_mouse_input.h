#ifndef XIANGQI_MOUSE_INPUT_H
#define XIANGQI_MOUSE_INPUT_H

#include <stdint.h>

#include "xiangqi_search.h"

#define XQ_MOUSE_BUTTON_LEFT  0x01u
#define XQ_MOUSE_BUTTON_RIGHT 0x02u

typedef enum {
    XQ_MOUSE_ACTION_NONE = 0,
    XQ_MOUSE_ACTION_SELECTED,
    XQ_MOUSE_ACTION_RESELECTED,
    XQ_MOUSE_ACTION_CANCELLED,
    XQ_MOUSE_ACTION_MOVED,
    XQ_MOUSE_ACTION_ILLEGAL,
    XQ_MOUSE_ACTION_SELECT_OWN,
    XQ_MOUSE_ACTION_RESTART
} xq_mouse_action_t;

typedef struct {
    int selected_square;
    int event_from;
    int event_to;
    uint8_t previous_buttons;
} xq_mouse_input_t;

void xq_mouse_input_init(xq_mouse_input_t *input, uint8_t buttons);
int xq_mouse_screen_to_square(int x, int y);
xq_mouse_action_t xq_mouse_input_update(
    xq_mouse_input_t *input, xq_search_board_t *board,
    int x, int y, uint8_t buttons);

#endif
