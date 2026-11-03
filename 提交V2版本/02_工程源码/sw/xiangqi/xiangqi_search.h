#ifndef XIANGQI_SEARCH_H
#define XIANGQI_SEARCH_H

#include <stdint.h>

#define XQ_SEARCH_MAX_MOVES 256
#define XQ_SEARCH_MAX_TOP 5
#define XQ_SEARCH_BATCH_MAX 16

enum {
    PIECE_K = 1,
    PIECE_A = 2,
    PIECE_B = 3,
    PIECE_N = 4,
    PIECE_R = 5,
    PIECE_C = 6,
    PIECE_P = 7,
    SIDE_BLACK = 8
};

typedef struct {
    uint8_t squares[90];
    int side;
} xq_search_board_t;

typedef struct {
    uint8_t from;
    uint8_t to;
} xq_search_move_t;

typedef struct {
    int count;
    int depth;
    uint32_t nodes;
    uint32_t mac_cycles;
    uint32_t cpu_cycles;
    uint32_t movegen_cycles;
    uint32_t eval_cycles;
    uint32_t batches;
    xq_search_move_t moves[XQ_SEARCH_MAX_TOP];
    int32_t scores[XQ_SEARCH_MAX_TOP];
} xq_search_result_t;

typedef int (*xq_search_eval_fn)(
    void *context, const xq_search_board_t *board,
    int32_t *score, uint32_t *mac_cycles);
typedef uint32_t (*xq_search_clock_fn)(void *context);
typedef int (*xq_search_eval_batch_fn)(
    void *context, const xq_search_board_t *parent,
    const xq_search_move_t *moves, int count,
    int32_t *scores, uint32_t *mac_cycles);
typedef int (*xq_search_eval_move_fn)(
    void *context, const xq_search_board_t *parent,
    xq_search_move_t move, int new_parent,
    int32_t *score, uint32_t *mac_cycles);

int xq_search_legal_moves(
    const xq_search_board_t *board, xq_search_move_t *moves, int capacity);
int xq_search_is_legal(
    const xq_search_board_t *board, xq_search_move_t move);
void xq_search_move_to_iccs(xq_search_move_t move, char text[5]);
int xq_search_go(
    const xq_search_board_t *board, int depth, int top_n,
    xq_search_eval_fn evaluate, xq_search_eval_move_fn evaluate_move,
    xq_search_eval_batch_fn evaluate_batch,
    xq_search_clock_fn clock,
    void *context, xq_search_result_t *result);

#endif
