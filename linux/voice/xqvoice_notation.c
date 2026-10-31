#include "xqvoice_notation.h"

static int piece_matches(uint8_t board_piece, xqvoice_piece_t spoken)
{
    switch (board_piece & 7u) {
    case PIECE_K:
        return spoken == XQVOICE_PIECE_SHUAI ||
               spoken == XQVOICE_PIECE_JIANG;
    case PIECE_A:
        return spoken == XQVOICE_PIECE_SHI;
    case PIECE_B:
        return spoken == XQVOICE_PIECE_XIANG;
    case PIECE_N:
        return spoken == XQVOICE_PIECE_MA;
    case PIECE_R:
        return spoken == XQVOICE_PIECE_JU;
    case PIECE_C:
        return spoken == XQVOICE_PIECE_PAO;
    case PIECE_P:
        return spoken == XQVOICE_PIECE_BING ||
               spoken == XQVOICE_PIECE_ZU;
    default:
        return 0;
    }
}

static int notation_file(int side, int file)
{
    return side ? 9 - file : file + 1;
}

static int move_matches(const xq_search_board_t *board,
                        const xqvoice_command_t *command,
                        xq_search_move_t move)
{
    uint8_t piece = board->squares[move.from];
    int side = (piece & SIDE_BLACK) != 0u;
    int type = piece & 7u;
    int from_file = move.from % 9;
    int from_rank = move.from / 9;
    int to_file = move.to % 9;
    int to_rank = move.to / 9;
    int forward_delta = side ? from_rank - to_rank : to_rank - from_rank;
    xqvoice_action_t action;
    int target;

    if (!piece_matches(piece, command->piece) ||
        notation_file(side, from_file) != command->source_file)
        return 0;
    if (from_rank == to_rank) {
        action = XQVOICE_ACTION_PING;
        target = notation_file(side, to_file);
    } else {
        action = forward_delta > 0 ? XQVOICE_ACTION_JIN : XQVOICE_ACTION_TUI;
        if (type == PIECE_N || type == PIECE_B || type == PIECE_A)
            target = notation_file(side, to_file);
        else
            target = forward_delta < 0 ? -forward_delta : forward_delta;
    }
    return action == command->action && target == command->target;
}

int xqvoice_resolve_move(const xq_search_board_t *board,
                         const xqvoice_command_t *command,
                         xq_search_move_t *move)
{
    xq_search_move_t legal[XQ_SEARCH_MAX_MOVES];
    int count;
    int matches = 0;
    int index;

    if (!board || !command || !move || command->type != XQVOICE_COMMAND_MOVE)
        return 0;
    count = xq_search_legal_moves(board, legal, XQ_SEARCH_MAX_MOVES);
    for (index = 0; index < count; ++index) {
        if (move_matches(board, command, legal[index])) {
            *move = legal[index];
            ++matches;
        }
    }
    return matches == 1 ? 1 : (matches ? -1 : 0);
}
