#ifndef XIANGQI_PIKAFISH_LINK_H
#define XIANGQI_PIKAFISH_LINK_H

#include <stdint.h>

#include "xiangqi_search.h"

#define XQ_PIKAFISH_FEN_CAPACITY 128

int xq_pikafish_board_to_fen(const xq_search_board_t *board,
                             char *fen, uint32_t capacity);
int xq_pikafish_parse_move(const char *text, xq_search_move_t *move);
int xq_pikafish_apply_move(xq_search_board_t *board, const char *text,
                           xq_search_move_t *move_out);
int xq_pikafish_parse_wdl(const char *line, uint32_t *wins,
                          uint32_t *draws, uint32_t *losses);

#endif
