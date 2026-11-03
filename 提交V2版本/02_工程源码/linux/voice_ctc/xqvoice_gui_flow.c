#include "xqvoice_gui_flow.h"
#include "xiangqi_fb_gui.h"
int xqvoice_gui_listen_ready(const xq_search_board_t *board,const xq_mouse_input_t *mouse,int enabled) {
    return enabled && board && !board->side && mouse && mouse->selected_square<0;
}
xq_mouse_action_t xqvoice_gui_input(xqvoice_session *session,xq_search_board_t *board,
    uint32_t revision,xq_mouse_input_t *mouse,int x,int y,uint8_t buttons,
    int enabled,int *voice_committed) {
    xq_mouse_action_t action=XQ_MOUSE_ACTION_NONE;xq_search_move_t move;
    int restart=x>=XQ_FB_RESTART_X && x<XQ_FB_RESTART_X+XQ_FB_RESTART_W &&
                y>=XQ_FB_RESTART_Y && y<XQ_FB_RESTART_Y+XQ_FB_RESTART_H;
    *voice_committed=0;
    if(enabled || restart)action=xq_mouse_input_update(mouse,board,x,y,buttons);
    else mouse->previous_buttons=buttons;
    int listen=action==XQ_MOUSE_ACTION_NONE && xqvoice_gui_listen_ready(board,mouse,enabled);
    if(xqvoice_session_auto_step(session,board,revision,listen,&move)) {
        mouse->selected_square=-1;mouse->event_from=move.from;mouse->event_to=move.to;
        *voice_committed=1;return XQ_MOUSE_ACTION_MOVED;
    }
    return action;
}
