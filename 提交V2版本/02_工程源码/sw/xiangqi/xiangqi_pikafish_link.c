#include "xiangqi_pikafish_link.h"

static const char *find_token(const char *text, const char *token)
{
    while (*text != '\0') {
        const char *left = text;
        const char *right = token;
        while (*right != '\0' && *left == *right) {
            ++left;
            ++right;
        }
        if (*right == '\0')
            return text;
        ++text;
    }
    return 0;
}

static char piece_to_fen(uint8_t piece)
{
    static const char red_pieces[] = " KABNRCP";
    char value;
    if ((piece & 7u) == 0u || (piece & 7u) > PIECE_P)
        return '\0';
    value = red_pieces[piece & 7u];
    if ((piece & SIDE_BLACK) != 0u)
        value = (char)(value - 'A' + 'a');
    return value;
}

static int append_char(char *text, uint32_t capacity,
                       uint32_t *length, char value)
{
    if (*length + 1u >= capacity)
        return 0;
    text[(*length)++] = value;
    return 1;
}

int xq_pikafish_board_to_fen(const xq_search_board_t *board,
                             char *fen, uint32_t capacity)
{
    static const char suffix[] = " - - 0 1";
    uint32_t length = 0u;
    uint32_t index;
    int rank;
    if (board == 0 || fen == 0 || capacity == 0u)
        return 0;
    for (rank = 9; rank >= 0; --rank) {
        int file;
        int empty = 0;
        for (file = 0; file < 9; ++file) {
            char piece = piece_to_fen(board->squares[rank * 9 + file]);
            if (piece == '\0') {
                ++empty;
                continue;
            }
            if (empty != 0) {
                if (!append_char(fen, capacity, &length,
                                 (char)('0' + empty)))
                    return 0;
                empty = 0;
            }
            if (!append_char(fen, capacity, &length, piece))
                return 0;
        }
        if (empty != 0 &&
            !append_char(fen, capacity, &length, (char)('0' + empty)))
            return 0;
        if (rank != 0 && !append_char(fen, capacity, &length, '/'))
            return 0;
    }
    if (!append_char(fen, capacity, &length, ' ') ||
        !append_char(fen, capacity, &length, board->side ? 'b' : 'w'))
        return 0;
    /* Pikafish validates all six FEN fields. Xiangqi has no castling or
     * en-passant state, and this GUI submits each displayed position as a
     * fresh search root, so use canonical placeholders and counters. */
    for (index = 0u; suffix[index] != '\0'; ++index) {
        if (!append_char(fen, capacity, &length, suffix[index]))
            return 0;
    }
    fen[length] = '\0';
    return 1;
}

int xq_pikafish_parse_move(const char *text, xq_search_move_t *move)
{
    if (text == 0 || move == 0 ||
        text[0] < 'a' || text[0] > 'i' ||
        text[1] < '0' || text[1] > '9' ||
        text[2] < 'a' || text[2] > 'i' ||
        text[3] < '0' || text[3] > '9' ||
        (text[4] != '\0' && text[4] != ' '))
        return 0;
    move->from = (uint8_t)((text[1] - '0') * 9 + text[0] - 'a');
    move->to = (uint8_t)((text[3] - '0') * 9 + text[2] - 'a');
    return 1;
}

int xq_pikafish_apply_move(xq_search_board_t *board, const char *text,
                           xq_search_move_t *move_out)
{
    xq_search_move_t move;
    if (board == 0 || !xq_pikafish_parse_move(text, &move) ||
        !xq_search_is_legal(board, move))
        return 0;
    board->squares[move.to] = board->squares[move.from];
    board->squares[move.from] = 0u;
    board->side ^= 1;
    if (move_out != 0)
        *move_out = move;
    return 1;
}

int xq_pikafish_parse_wdl(const char *line, uint32_t *wins,
                          uint32_t *draws, uint32_t *losses)
{
    uint32_t values[3];
    const char *cursor;
    int field;
    if (line == 0 || wins == 0 || draws == 0 || losses == 0)
        return 0;
    cursor = find_token(line, " wdl ");
    if (cursor == 0)
        return 0;
    cursor += 5;
    for (field = 0; field < 3; ++field) {
        uint32_t value = 0;
        int digits = 0;
        while (*cursor >= '0' && *cursor <= '9') {
            value = value * 10u + (uint32_t)(*cursor - '0');
            if (value > 1000u)
                return 0;
            ++cursor;
            ++digits;
        }
        if (digits == 0)
            return 0;
        values[field] = value;
        if (field != 2) {
            if (*cursor != ' ')
                return 0;
            while (*cursor == ' ')
                ++cursor;
        }
    }
    if (*cursor != '\0' && *cursor != ' ' &&
        *cursor != '\r' && *cursor != '\n')
        return 0;
    if (values[0] + values[1] + values[2] != 1000u)
        return 0;
    *wins = values[0];
    *draws = values[1];
    *losses = values[2];
    return 1;
}
