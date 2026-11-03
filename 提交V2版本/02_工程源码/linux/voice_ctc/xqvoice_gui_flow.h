#ifndef XQVOICE_GUI_FLOW_H
#define XQVOICE_GUI_FLOW_H
#include "xqvoice_session.h"
#include "xiangqi_mouse_input.h"
/* Mouse actions take precedence. A MOVED return has already changed board,
   regardless of whether mouse or voice originated it. */
xq_mouse_action_t xqvoice_gui_input(xqvoice_session *session,xq_search_board_t *board,
    uint32_t revision,xq_mouse_input_t *mouse,int x,int y,uint8_t buttons,
    int enabled,int *voice_committed);
int xqvoice_gui_listen_ready(const xq_search_board_t *board,const xq_mouse_input_t *mouse,int enabled);
#endif
