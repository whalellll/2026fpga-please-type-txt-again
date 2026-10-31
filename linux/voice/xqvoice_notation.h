#ifndef XQVOICE_NOTATION_H
#define XQVOICE_NOTATION_H

#include "xqvoice_protocol.h"
#include "xiangqi_search.h"

/* Returns 1 for one legal match, 0 for no match, and -1 for ambiguity. */
int xqvoice_resolve_move(const xq_search_board_t *board,
                         const xqvoice_command_t *command,
                         xq_search_move_t *move);

#endif
