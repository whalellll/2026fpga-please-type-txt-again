#include "xiangqi_search.h"

#define FILE_N 9
#define RANK_N 10
#define SQ_N 90
#define SQ(file, rank) ((rank) * FILE_N + (file))
#define SQ_FILE(square) ((square) % FILE_N)
#define SQ_RANK(square) ((square) / FILE_N)
#define PIECE_TYPE(piece) ((piece) & 7)
#define PIECE_SIDE(piece) (((piece) & SIDE_BLACK) != 0)
#define SEARCH_INF 32000
#define SEARCH_MATE 30000

static int in_palace(int file, int rank, int side)
{
    if (file < 3 || file > 5)
        return 0;
    return side == 0 ? rank >= 0 && rank <= 2 : rank >= 7 && rank <= 9;
}

static int same_side(uint8_t left, uint8_t right)
{
    return left != 0u && right != 0u && PIECE_SIDE(left) == PIECE_SIDE(right);
}

static int find_king(const xq_search_board_t *board, int side)
{
    uint8_t king = (uint8_t)(PIECE_K | (side != 0 ? SIDE_BLACK : 0));
    int square;
    for (square = 0; square < SQ_N; ++square) {
        if (board->squares[square] == king)
            return square;
    }
    return -1;
}

static int count_between(
    const xq_search_board_t *board, int from, int to)
{
    int from_file = SQ_FILE(from);
    int from_rank = SQ_RANK(from);
    int to_file = SQ_FILE(to);
    int to_rank = SQ_RANK(to);
    int file_step = (to_file > from_file) - (to_file < from_file);
    int rank_step = (to_rank > from_rank) - (to_rank < from_rank);
    int file;
    int rank;
    int count = 0;
    if ((file_step != 0 && rank_step != 0) ||
        (file_step == 0 && rank_step == 0))
        return -1;
    file = from_file + file_step;
    rank = from_rank + rank_step;
    while (file != to_file || rank != to_rank) {
        if (board->squares[SQ(file, rank)] != 0u)
            ++count;
        file += file_step;
        rank += rank_step;
    }
    return count;
}

static int can_move_piece(
    const xq_search_board_t *board, int from, int to)
{
    uint8_t piece;
    uint8_t destination;
    int side;
    int from_file;
    int from_rank;
    int to_file;
    int to_rank;
    int file_delta;
    int rank_delta;
    int abs_file;
    int abs_rank;
    if (from == to || from < 0 || from >= SQ_N || to < 0 || to >= SQ_N)
        return 0;
    piece = board->squares[from];
    destination = board->squares[to];
    if (piece == 0u || same_side(piece, destination))
        return 0;
    side = PIECE_SIDE(piece);
    from_file = SQ_FILE(from);
    from_rank = SQ_RANK(from);
    to_file = SQ_FILE(to);
    to_rank = SQ_RANK(to);
    file_delta = to_file - from_file;
    rank_delta = to_rank - from_rank;
    abs_file = file_delta < 0 ? -file_delta : file_delta;
    abs_rank = rank_delta < 0 ? -rank_delta : rank_delta;

    switch (PIECE_TYPE(piece)) {
    case PIECE_K:
        return in_palace(to_file, to_rank, side) && abs_file + abs_rank == 1;
    case PIECE_A:
        return in_palace(to_file, to_rank, side) &&
               abs_file == 1 && abs_rank == 1;
    case PIECE_B:
        if (abs_file != 2 || abs_rank != 2)
            return 0;
        if ((side == 0 && to_rank > 4) || (side != 0 && to_rank < 5))
            return 0;
        return board->squares[SQ(from_file + file_delta / 2,
                                 from_rank + rank_delta / 2)] == 0u;
    case PIECE_N: {
        int block_file = from_file;
        int block_rank = from_rank;
        if (!((abs_file == 1 && abs_rank == 2) ||
              (abs_file == 2 && abs_rank == 1)))
            return 0;
        if (abs_file == 2)
            block_file += file_delta > 0 ? 1 : -1;
        else
            block_rank += rank_delta > 0 ? 1 : -1;
        return board->squares[SQ(block_file, block_rank)] == 0u;
    }
    case PIECE_R:
        return count_between(board, from, to) == 0;
    case PIECE_C: {
        int between = count_between(board, from, to);
        if (between < 0)
            return 0;
        return destination == 0u ? between == 0 : between == 1;
    }
    case PIECE_P: {
        int forward = side == 0 ? 1 : -1;
        int crossed = side == 0 ? from_rank >= 5 : from_rank <= 4;
        if (file_delta == 0 && rank_delta == forward)
            return 1;
        return crossed && abs_rank == 0 && abs_file == 1;
    }
    default:
        return 0;
    }
}

static void apply_move(
    xq_search_board_t *board, xq_search_move_t move, uint8_t *captured)
{
    *captured = board->squares[move.to];
    board->squares[move.to] = board->squares[move.from];
    board->squares[move.from] = 0u;
    board->side ^= 1;
}

static void undo_move(
    xq_search_board_t *board, xq_search_move_t move, uint8_t captured)
{
    board->side ^= 1;
    board->squares[move.from] = board->squares[move.to];
    board->squares[move.to] = captured;
}

static int in_board(int file, int rank)
{
    return file >= 0 && file < FILE_N && rank >= 0 && rank < RANK_N;
}

static void add_target(
    const xq_search_board_t *board, uint8_t piece,
    int file, int rank, uint32_t targets[3])
{
    int square;
    if (!in_board(file, rank))
        return;
    square = SQ(file, rank);
    if (!same_side(piece, board->squares[square]))
        targets[square >> 5] |= 1u << (square & 31);
}

/*
 * Generate only geometrically reachable destinations for one piece.  The old
 * implementation tried all 90 destinations and rejected almost all of them.
 * Keeping the final destination scan in ascending square order preserves the
 * search's deterministic move ordering.
 */
static void generate_piece_targets(
    const xq_search_board_t *board, int from, uint32_t targets[3])
{
    static const int8_t orthogonal[4][2] = {
        {-1, 0}, {1, 0}, {0, -1}, {0, 1}
    };
    static const int8_t diagonal[4][2] = {
        {-1, -1}, {-1, 1}, {1, -1}, {1, 1}
    };
    static const int8_t horse[8][2] = {
        {-2, -1}, {-2, 1}, {-1, -2}, {-1, 2},
        {1, -2}, {1, 2}, {2, -1}, {2, 1}
    };
    uint8_t piece = board->squares[from];
    int side = PIECE_SIDE(piece);
    int file = SQ_FILE(from);
    int rank = SQ_RANK(from);
    int index;
    targets[0] = 0u;
    targets[1] = 0u;
    targets[2] = 0u;

    switch (PIECE_TYPE(piece)) {
    case PIECE_K:
        for (index = 0; index < 4; ++index) {
            int to_file = file + orthogonal[index][0];
            int to_rank = rank + orthogonal[index][1];
            if (in_palace(to_file, to_rank, side))
                add_target(board, piece, to_file, to_rank, targets);
        }
        break;
    case PIECE_A:
        for (index = 0; index < 4; ++index) {
            int to_file = file + diagonal[index][0];
            int to_rank = rank + diagonal[index][1];
            if (in_palace(to_file, to_rank, side))
                add_target(board, piece, to_file, to_rank, targets);
        }
        break;
    case PIECE_B:
        for (index = 0; index < 4; ++index) {
            int to_file = file + 2 * diagonal[index][0];
            int to_rank = rank + 2 * diagonal[index][1];
            int eye_file = file + diagonal[index][0];
            int eye_rank = rank + diagonal[index][1];
            if (!in_board(to_file, to_rank) ||
                (side == 0 ? to_rank > 4 : to_rank < 5) ||
                board->squares[SQ(eye_file, eye_rank)] != 0u)
                continue;
            add_target(board, piece, to_file, to_rank, targets);
        }
        break;
    case PIECE_N:
        for (index = 0; index < 8; ++index) {
            int file_delta = horse[index][0];
            int rank_delta = horse[index][1];
            int leg_file = file + (file_delta < -1 ? -1 :
                                   file_delta > 1 ? 1 : 0);
            int leg_rank = rank + (rank_delta < -1 ? -1 :
                                   rank_delta > 1 ? 1 : 0);
            if (!in_board(file + file_delta, rank + rank_delta) ||
                board->squares[SQ(leg_file, leg_rank)] != 0u)
                continue;
            add_target(board, piece, file + file_delta, rank + rank_delta,
                       targets);
        }
        break;
    case PIECE_R:
        for (index = 0; index < 4; ++index) {
            int to_file = file + orthogonal[index][0];
            int to_rank = rank + orthogonal[index][1];
            while (in_board(to_file, to_rank)) {
                uint8_t destination = board->squares[SQ(to_file, to_rank)];
                if (destination == 0u) {
                    add_target(board, piece, to_file, to_rank, targets);
                } else {
                    if (!same_side(piece, destination))
                        add_target(board, piece, to_file, to_rank, targets);
                    break;
                }
                to_file += orthogonal[index][0];
                to_rank += orthogonal[index][1];
            }
        }
        break;
    case PIECE_C:
        for (index = 0; index < 4; ++index) {
            int to_file = file + orthogonal[index][0];
            int to_rank = rank + orthogonal[index][1];
            int found_screen = 0;
            while (in_board(to_file, to_rank)) {
                uint8_t destination = board->squares[SQ(to_file, to_rank)];
                if (!found_screen) {
                    if (destination == 0u)
                        add_target(board, piece, to_file, to_rank, targets);
                    else
                        found_screen = 1;
                } else if (destination != 0u) {
                    if (!same_side(piece, destination))
                        add_target(board, piece, to_file, to_rank, targets);
                    break;
                }
                to_file += orthogonal[index][0];
                to_rank += orthogonal[index][1];
            }
        }
        break;
    case PIECE_P: {
        int forward = side == 0 ? 1 : -1;
        int crossed = side == 0 ? rank >= 5 : rank <= 4;
        add_target(board, piece, file, rank + forward, targets);
        if (crossed) {
            add_target(board, piece, file - 1, rank, targets);
            add_target(board, piece, file + 1, rank, targets);
        }
        break;
    }
    default:
        break;
    }
}

static int attacker_at(
    const xq_search_board_t *board, int file, int rank,
    int king, int enemy_side, int type)
{
    int square;
    uint8_t piece;
    if (!in_board(file, rank))
        return 0;
    square = SQ(file, rank);
    piece = board->squares[square];
    return piece != 0u && PIECE_SIDE(piece) == enemy_side &&
           PIECE_TYPE(piece) == type && can_move_piece(board, square, king);
}

/* Test attacks from the few squares that can reach the king, not all 90. */
static int square_attacked(
    const xq_search_board_t *board, int king, int side)
{
    static const int8_t orthogonal[4][2] = {
        {-1, 0}, {1, 0}, {0, -1}, {0, 1}
    };
    static const int8_t diagonal[4][2] = {
        {-1, -1}, {-1, 1}, {1, -1}, {1, 1}
    };
    static const int8_t horse[8][2] = {
        {-2, -1}, {-2, 1}, {-1, -2}, {-1, 2},
        {1, -2}, {1, 2}, {2, -1}, {2, 1}
    };
    int enemy_side = side ^ 1;
    int file;
    int rank;
    int index;
    if (king < 0 || king >= SQ_N)
        return 1;
    file = SQ_FILE(king);
    rank = SQ_RANK(king);

    for (index = 0; index < 4; ++index) {
        int scan_file = file + orthogonal[index][0];
        int scan_rank = rank + orthogonal[index][1];
        int found_screen = 0;
        while (in_board(scan_file, scan_rank)) {
            uint8_t piece = board->squares[SQ(scan_file, scan_rank)];
            if (piece != 0u) {
                if (!found_screen) {
                    if (PIECE_SIDE(piece) == enemy_side &&
                        (PIECE_TYPE(piece) == PIECE_R ||
                         (orthogonal[index][0] == 0 &&
                          PIECE_TYPE(piece) == PIECE_K)))
                        return 1;
                    found_screen = 1;
                } else {
                    if (PIECE_SIDE(piece) == enemy_side &&
                        PIECE_TYPE(piece) == PIECE_C)
                        return 1;
                    break;
                }
            }
            scan_file += orthogonal[index][0];
            scan_rank += orthogonal[index][1];
        }
    }
    for (index = 0; index < 8; ++index) {
        if (attacker_at(board, file + horse[index][0],
                        rank + horse[index][1], king,
                        enemy_side, PIECE_N))
            return 1;
    }
    for (index = 0; index < 4; ++index) {
        if (attacker_at(board, file + orthogonal[index][0],
                        rank + orthogonal[index][1], king,
                        enemy_side, PIECE_P) ||
            attacker_at(board, file + orthogonal[index][0],
                        rank + orthogonal[index][1], king,
                        enemy_side, PIECE_K) ||
            attacker_at(board, file + diagonal[index][0],
                        rank + diagonal[index][1], king,
                        enemy_side, PIECE_A) ||
            attacker_at(board, file + 2 * diagonal[index][0],
                        rank + 2 * diagonal[index][1], king,
                        enemy_side, PIECE_B))
            return 1;
    }
    return 0;
}

int xq_search_is_legal(
    const xq_search_board_t *board, xq_search_move_t move)
{
    xq_search_board_t next;
    uint8_t captured;
    uint8_t piece;
    if (move.from >= SQ_N || move.to >= SQ_N)
        return 0;
    piece = board->squares[move.from];
    if (piece == 0u || PIECE_SIDE(piece) != board->side ||
        !can_move_piece(board, move.from, move.to))
        return 0;
    next = *board;
    apply_move(&next, move, &captured);
    (void)captured;
    return !square_attacked(
        &next, PIECE_TYPE(piece) == PIECE_K ? move.to :
        find_king(&next, board->side), board->side);
}

int xq_search_legal_moves(
    const xq_search_board_t *board, xq_search_move_t *moves, int capacity)
{
    xq_search_board_t work;
    int count = 0;
    int king;
    int from;
    int to;
    if (board == 0 || moves == 0 || capacity <= 0)
        return 0;
    king = find_king(board, board->side);
    if (king < 0)
        return 0;
    work = *board;
    for (from = 0; from < SQ_N; ++from) {
        uint32_t targets[3];
        uint8_t piece = board->squares[from];
        if (piece == 0u || PIECE_SIDE(piece) != board->side)
            continue;
        generate_piece_targets(board, from, targets);
        for (to = 0; to < SQ_N; ++to) {
            xq_search_move_t move;
            uint8_t captured;
            int next_king;
            if ((targets[to >> 5] & (1u << (to & 31))) == 0u)
                continue;
            move.from = (uint8_t)from;
            move.to = (uint8_t)to;
            apply_move(&work, move, &captured);
            next_king = PIECE_TYPE(piece) == PIECE_K ? to : king;
            if (square_attacked(&work, next_king, board->side)) {
                undo_move(&work, move, captured);
                continue;
            }
            if (count < capacity)
                moves[count] = move;
            ++count;
            undo_move(&work, move, captured);
        }
    }
    return count < capacity ? count : capacity;
}

void xq_search_move_to_iccs(xq_search_move_t move, char text[5])
{
    text[0] = (char)('a' + SQ_FILE(move.from));
    text[1] = (char)('0' + SQ_RANK(move.from));
    text[2] = (char)('a' + SQ_FILE(move.to));
    text[3] = (char)('0' + SQ_RANK(move.to));
    text[4] = '\0';
}

static int32_t negamax(
    xq_search_board_t *board, int depth, int ply,
    int32_t alpha, int32_t beta, xq_search_eval_fn evaluate, void *context,
    xq_search_eval_move_fn evaluate_move,
    xq_search_eval_batch_fn evaluate_batch, xq_search_clock_fn clock,
    uint32_t *nodes, uint32_t *cycles, uint32_t *movegen_cycles,
    uint32_t *eval_cycles, uint32_t *batches, int *ok)
{
    xq_search_move_t moves[XQ_SEARCH_MAX_MOVES];
    int move_count;
    int index;
    int32_t best = -SEARCH_INF;
    if (find_king(board, board->side) < 0)
        return -SEARCH_MATE + ply;
    if (depth == 0) {
        int32_t score;
        uint32_t mac_eval_cycles;
        uint32_t started = clock != 0 ? clock(context) : 0u;
        if (!evaluate(context, board, &score, &mac_eval_cycles)) {
            *ok = 0;
            return 0;
        }
        if (clock != 0)
            *eval_cycles += clock(context) - started;
        ++*nodes;
        *cycles += mac_eval_cycles;
        return score;
    }
    if (clock != 0) {
        uint32_t started = clock(context);
        move_count = xq_search_legal_moves(board, moves, XQ_SEARCH_MAX_MOVES);
        *movegen_cycles += clock(context) - started;
    } else {
        move_count = xq_search_legal_moves(board, moves, XQ_SEARCH_MAX_MOVES);
    }
    if (move_count == 0)
        return -SEARCH_MATE + ply;
    if (depth == 1 && evaluate_move != 0) {
        int parent_ready = 0;
        for (index = 0; index < move_count; ++index) {
            uint8_t captured = board->squares[moves[index].to];
            int32_t leaf_score;
            int32_t score;
            uint32_t mac_eval_cycles = 0u;
            uint32_t started;
            if (captured != 0u && PIECE_TYPE(captured) == PIECE_K) {
                leaf_score = -SEARCH_MATE + ply + 1;
            } else {
                started = clock != 0 ? clock(context) : 0u;
                if (!evaluate_move(context, board, moves[index],
                                   !parent_ready, &leaf_score,
                                   &mac_eval_cycles)) {
                    *ok = 0;
                    return 0;
                }
                parent_ready = 1;
                if (clock != 0)
                    *eval_cycles += clock(context) - started;
                ++*nodes;
                *cycles += mac_eval_cycles;
            }
            score = -leaf_score;
            if (score > best)
                best = score;
            if (score > alpha)
                alpha = score;
            if (alpha >= beta)
                break;
        }
        return best;
    }
    if (depth == 1 && evaluate_batch != 0) {
        for (index = 0; index < move_count; index += XQ_SEARCH_BATCH_MAX) {
            xq_search_move_t batch_moves[XQ_SEARCH_BATCH_MAX];
            int batch_map[XQ_SEARCH_BATCH_MAX];
            int32_t batch_scores[XQ_SEARCH_BATCH_MAX];
            int32_t leaf_scores[XQ_SEARCH_BATCH_MAX];
            int chunk = move_count - index;
            int batch_count = 0;
            int offset;
            uint32_t batch_mac_cycles = 0u;
            uint32_t started;
            if (chunk > XQ_SEARCH_BATCH_MAX)
                chunk = XQ_SEARCH_BATCH_MAX;
            for (offset = 0; offset < chunk; ++offset) {
                xq_search_move_t move = moves[index + offset];
                uint8_t captured = board->squares[move.to];
                if (captured != 0u && PIECE_TYPE(captured) == PIECE_K) {
                    leaf_scores[offset] = -SEARCH_MATE + ply + 1;
                } else {
                    batch_moves[batch_count] = move;
                    batch_map[batch_count] = offset;
                    ++batch_count;
                }
            }
            if (batch_count != 0) {
                started = clock != 0 ? clock(context) : 0u;
                if (!evaluate_batch(context, board, batch_moves, batch_count,
                                    batch_scores, &batch_mac_cycles)) {
                    *ok = 0;
                    return 0;
                }
                if (clock != 0)
                    *eval_cycles += clock(context) - started;
                *nodes += (uint32_t)batch_count;
                *cycles += batch_mac_cycles;
                ++*batches;
                for (offset = 0; offset < batch_count; ++offset)
                    leaf_scores[batch_map[offset]] = batch_scores[offset];
            }
            for (offset = 0; offset < chunk; ++offset) {
                int32_t score = -leaf_scores[offset];
                if (score > best)
                    best = score;
                if (score > alpha)
                    alpha = score;
                if (alpha >= beta)
                    return best;
            }
        }
        return best;
    }
    for (index = 0; index < move_count; ++index) {
        uint8_t captured;
        int32_t score;
        apply_move(board, moves[index], &captured);
        score = -negamax(board, depth - 1, ply + 1, -beta, -alpha,
                         evaluate, context, evaluate_move, evaluate_batch,
                         clock, nodes,
                         cycles, movegen_cycles, eval_cycles, batches, ok);
        board->side ^= 1;
        board->squares[moves[index].from] = board->squares[moves[index].to];
        board->squares[moves[index].to] = captured;
        if (!*ok)
            return 0;
        if (score > best)
            best = score;
        if (score > alpha)
            alpha = score;
        if (alpha >= beta)
            break;
    }
    return best;
}

static void insert_candidate(
    xq_search_result_t *result, int top_n,
    xq_search_move_t move, int32_t score)
{
    int position = result->count;
    int index;
    if (position > top_n)
        position = top_n;
    for (index = 0; index < result->count; ++index) {
        if (score > result->scores[index]) {
            position = index;
            break;
        }
    }
    if (position >= top_n)
        return;
    if (result->count < top_n)
        ++result->count;
    for (index = result->count - 1; index > position; --index) {
        result->moves[index] = result->moves[index - 1];
        result->scores[index] = result->scores[index - 1];
    }
    result->moves[position] = move;
    result->scores[position] = score;
}

int xq_search_go(
    const xq_search_board_t *board, int depth, int top_n,
    xq_search_eval_fn evaluate, xq_search_eval_move_fn evaluate_move,
    xq_search_eval_batch_fn evaluate_batch,
    xq_search_clock_fn clock,
    void *context, xq_search_result_t *result)
{
    xq_search_move_t moves[XQ_SEARCH_MAX_MOVES];
    xq_search_board_t work;
    int move_count;
    int index;
    int ok = 1;
    int32_t root_alpha = -SEARCH_INF;
    uint32_t search_started;
    if (board == 0 || evaluate == 0 || result == 0)
        return 0;
    if (depth < 1)
        depth = 1;
    if (depth > 2)
        depth = 2;
    if (top_n < 1)
        top_n = 1;
    if (top_n > XQ_SEARCH_MAX_TOP)
        top_n = XQ_SEARCH_MAX_TOP;
    result->count = 0;
    result->depth = depth;
    result->nodes = 0u;
    result->mac_cycles = 0u;
    result->cpu_cycles = 0u;
    result->movegen_cycles = 0u;
    result->eval_cycles = 0u;
    result->batches = 0u;
    work = *board;
    search_started = clock != 0 ? clock(context) : 0u;
    if (clock != 0) {
        uint32_t started = clock(context);
        move_count = xq_search_legal_moves(&work, moves, XQ_SEARCH_MAX_MOVES);
        result->movegen_cycles += clock(context) - started;
    } else {
        move_count = xq_search_legal_moves(&work, moves, XQ_SEARCH_MAX_MOVES);
    }
    if (depth == 1 && evaluate_move != 0) {
        int parent_ready = 0;
        for (index = 0; index < move_count; ++index) {
            uint8_t captured = work.squares[moves[index].to];
            int32_t leaf_score;
            int32_t score;
            uint32_t mac_eval_cycles = 0u;
            uint32_t started;
            if (captured != 0u && PIECE_TYPE(captured) == PIECE_K) {
                leaf_score = -SEARCH_MATE + 1;
            } else {
                started = clock != 0 ? clock(context) : 0u;
                if (!evaluate_move(context, &work, moves[index],
                                   !parent_ready, &leaf_score,
                                   &mac_eval_cycles))
                    return 0;
                parent_ready = 1;
                if (clock != 0)
                    result->eval_cycles += clock(context) - started;
                ++result->nodes;
                result->mac_cycles += mac_eval_cycles;
            }
            score = -leaf_score;
            insert_candidate(result, top_n, moves[index], score);
            if (score > root_alpha)
                root_alpha = score;
        }
        if (clock != 0)
            result->cpu_cycles = clock(context) - search_started;
        return 1;
    }
    if (depth == 1 && evaluate_batch != 0) {
        for (index = 0; index < move_count; index += XQ_SEARCH_BATCH_MAX) {
            xq_search_move_t batch_moves[XQ_SEARCH_BATCH_MAX];
            int batch_map[XQ_SEARCH_BATCH_MAX];
            int32_t batch_scores[XQ_SEARCH_BATCH_MAX];
            int32_t leaf_scores[XQ_SEARCH_BATCH_MAX];
            int chunk = move_count - index;
            int batch_count = 0;
            int offset;
            uint32_t batch_mac_cycles = 0u;
            uint32_t started;
            if (chunk > XQ_SEARCH_BATCH_MAX)
                chunk = XQ_SEARCH_BATCH_MAX;
            for (offset = 0; offset < chunk; ++offset) {
                xq_search_move_t move = moves[index + offset];
                uint8_t captured = work.squares[move.to];
                if (captured != 0u && PIECE_TYPE(captured) == PIECE_K) {
                    leaf_scores[offset] = -SEARCH_MATE + 1;
                } else {
                    batch_moves[batch_count] = move;
                    batch_map[batch_count] = offset;
                    ++batch_count;
                }
            }
            if (batch_count != 0) {
                started = clock != 0 ? clock(context) : 0u;
                if (!evaluate_batch(context, &work, batch_moves, batch_count,
                                    batch_scores, &batch_mac_cycles))
                    return 0;
                if (clock != 0)
                    result->eval_cycles += clock(context) - started;
                result->nodes += (uint32_t)batch_count;
                result->mac_cycles += batch_mac_cycles;
                ++result->batches;
                for (offset = 0; offset < batch_count; ++offset)
                    leaf_scores[batch_map[offset]] = batch_scores[offset];
            }
            for (offset = 0; offset < chunk; ++offset) {
                int32_t score = -leaf_scores[offset];
                insert_candidate(result, top_n, moves[index + offset], score);
                if (score > root_alpha)
                    root_alpha = score;
            }
        }
        if (clock != 0)
            result->cpu_cycles = clock(context) - search_started;
        return 1;
    }
    for (index = 0; index < move_count; ++index) {
        uint8_t captured;
        int32_t score;
        apply_move(&work, moves[index], &captured);
        score = -negamax(&work, depth - 1, 1, -SEARCH_INF, -root_alpha,
                         evaluate, context, evaluate_move, evaluate_batch,
                         clock,
                         &result->nodes, &result->mac_cycles,
                         &result->movegen_cycles, &result->eval_cycles,
                         &result->batches, &ok);
        work.side ^= 1;
        work.squares[moves[index].from] = work.squares[moves[index].to];
        work.squares[moves[index].to] = captured;
        if (!ok)
            return 0;
        insert_candidate(result, top_n, moves[index], score);
        if (score > root_alpha)
            root_alpha = score;
    }
    if (clock != 0)
        result->cpu_cycles = clock(context) - search_started;
    return 1;
}
