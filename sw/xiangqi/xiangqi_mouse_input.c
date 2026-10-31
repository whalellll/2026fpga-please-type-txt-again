#include "xiangqi_fb_gui.h"
#include "xiangqi_mouse_input.h"

#ifdef XQ_GUI_1080
#define XQ_MOUSE_HIT_RADIUS 38
#else
#define XQ_MOUSE_HIT_RADIUS 28
#endif

static int piece_side(uint8_t piece)
{
    return (piece & SIDE_BLACK) != 0u;
}

void xq_mouse_input_init(xq_mouse_input_t *input, uint8_t buttons)
{
    input->selected_square = -1;
    input->event_from = -1;
    input->event_to = -1;
    input->previous_buttons = buttons;
}

int xq_mouse_screen_to_square(int x, int y)
{
    int file;
    int screen_rank;
    int grid_x;
    int grid_y;

    if (x < XQ_FB_BOARD_X - XQ_MOUSE_HIT_RADIUS ||
        x > XQ_FB_BOARD_X + 8 * XQ_FB_CELL + XQ_MOUSE_HIT_RADIUS ||
        y < XQ_FB_BOARD_Y - XQ_MOUSE_HIT_RADIUS ||
        y > XQ_FB_BOARD_Y + 9 * XQ_FB_CELL + XQ_MOUSE_HIT_RADIUS)
        return -1;

    file = (x - XQ_FB_BOARD_X + XQ_FB_CELL / 2) / XQ_FB_CELL;
    screen_rank = (y - XQ_FB_BOARD_Y + XQ_FB_CELL / 2) / XQ_FB_CELL;
    if (file < 0 || file > 8 || screen_rank < 0 || screen_rank > 9)
        return -1;

    grid_x = XQ_FB_BOARD_X + file * XQ_FB_CELL;
    grid_y = XQ_FB_BOARD_Y + screen_rank * XQ_FB_CELL;
    if (x < grid_x - XQ_MOUSE_HIT_RADIUS ||
        x > grid_x + XQ_MOUSE_HIT_RADIUS ||
        y < grid_y - XQ_MOUSE_HIT_RADIUS ||
        y > grid_y + XQ_MOUSE_HIT_RADIUS)
        return -1;

    return (9 - screen_rank) * 9 + file;
}

xq_mouse_action_t xq_mouse_input_update(
    xq_mouse_input_t *input, xq_search_board_t *board,
    int x, int y, uint8_t buttons)
{
    uint8_t pressed = (uint8_t)(buttons & ~input->previous_buttons);
    int square;
    uint8_t piece;

    input->previous_buttons = buttons;
    input->event_from = -1;
    input->event_to = -1;

    if ((pressed & XQ_MOUSE_BUTTON_RIGHT) != 0u) {
        if (input->selected_square < 0)
            return XQ_MOUSE_ACTION_NONE;
        input->event_from = input->selected_square;
        input->selected_square = -1;
        return XQ_MOUSE_ACTION_CANCELLED;
    }
    if ((pressed & XQ_MOUSE_BUTTON_LEFT) == 0u)
        return XQ_MOUSE_ACTION_NONE;

    if (x >= XQ_FB_RESTART_X && x < XQ_FB_RESTART_X + XQ_FB_RESTART_W &&
        y >= XQ_FB_RESTART_Y && y < XQ_FB_RESTART_Y + XQ_FB_RESTART_H) {
        input->event_from = input->selected_square;
        input->selected_square = -1;
        return XQ_MOUSE_ACTION_RESTART;
    }

    square = xq_mouse_screen_to_square(x, y);
    if (square < 0)
        return XQ_MOUSE_ACTION_NONE;
    piece = board->squares[square];

    if (input->selected_square < 0) {
        input->event_to = square;
        if (piece == 0u || piece_side(piece) != board->side)
            return XQ_MOUSE_ACTION_SELECT_OWN;
        input->selected_square = square;
        return XQ_MOUSE_ACTION_SELECTED;
    }

    if (square == input->selected_square) {
        input->event_from = square;
        input->selected_square = -1;
        return XQ_MOUSE_ACTION_CANCELLED;
    }
    if (piece != 0u && piece_side(piece) == board->side) {
        input->event_from = input->selected_square;
        input->event_to = square;
        input->selected_square = square;
        return XQ_MOUSE_ACTION_RESELECTED;
    }

    input->event_from = input->selected_square;
    input->event_to = square;
    {
        xq_search_move_t move;
        move.from = (uint8_t)input->selected_square;
        move.to = (uint8_t)square;
        if (!xq_search_is_legal(board, move))
            return XQ_MOUSE_ACTION_ILLEGAL;
    }

    board->squares[square] = board->squares[input->selected_square];
    board->squares[input->selected_square] = 0u;
    board->side ^= 1;
    input->selected_square = -1;
    return XQ_MOUSE_ACTION_MOVED;
}
