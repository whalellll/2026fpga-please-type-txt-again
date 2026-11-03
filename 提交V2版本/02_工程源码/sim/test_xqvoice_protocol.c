#include <stdio.h>
#include <string.h>

#include "xqvoice_notation.h"

static int failures;

#define CHECK(condition, message) do { \
    if (!(condition)) { \
        fprintf(stderr, "XQVOICE_PROTOCOL_FAIL: %s\n", message); \
        ++failures; \
    } \
} while (0)

static void initial_board(xq_search_board_t *board)
{
    static const uint8_t back[9] = {
        PIECE_R, PIECE_N, PIECE_B, PIECE_A, PIECE_K,
        PIECE_A, PIECE_B, PIECE_N, PIECE_R
    };
    int file;

    memset(board, 0, sizeof(*board));
    for (file = 0; file < 9; ++file) {
        board->squares[file] = back[file];
        board->squares[81 + file] = (uint8_t)(back[file] | SIDE_BLACK);
    }
    board->squares[19] = PIECE_C;
    board->squares[25] = PIECE_C;
    board->squares[64] = PIECE_C | SIDE_BLACK;
    board->squares[70] = PIECE_C | SIDE_BLACK;
    for (file = 0; file < 9; file += 2) {
        board->squares[27 + file] = PIECE_P;
        board->squares[54 + file] = PIECE_P | SIDE_BLACK;
    }
}

int main(void)
{
    const char wire[] = "XQVOICE/1 42 MOVE ma 6 jin 7 913\n";
    xqvoice_command_t command;
    xq_search_board_t board;
    xq_search_move_t move;
    char formatted[128];

    CHECK(xqvoice_parse_command(wire, sizeof(wire) - 1, &command),
          "valid move did not parse");
    CHECK(command.sequence == 42 && command.type == XQVOICE_COMMAND_MOVE &&
          command.piece == XQVOICE_PIECE_MA && command.source_file == 6 &&
          command.action == XQVOICE_ACTION_JIN && command.target == 7 &&
          command.confidence_permille == 913,
          "parsed move fields differ");
    CHECK(xqvoice_format_command(formatted, sizeof(formatted), &command) > 0 &&
          strcmp(formatted, wire) == 0, "move round trip differs");
    CHECK(!xqvoice_parse_command("XQVOICE/1 1 MOVE ma 0 jin 7 900", 35,
                                 &command), "file zero was accepted");
    CHECK(!xqvoice_parse_command("XQVOICE/2 1 RESTART 900", 24, &command),
          "unknown protocol version was accepted");

    initial_board(&board);
    command.sequence = 1;
    command.type = XQVOICE_COMMAND_MOVE;
    command.piece = XQVOICE_PIECE_MA;
    command.source_file = 2;
    command.action = XQVOICE_ACTION_JIN;
    command.target = 3;
    CHECK(xqvoice_resolve_move(&board, &command, &move) == 1 &&
          move.from == 1 && move.to == 20,
          "red ma er jin san did not resolve");

    memset(&board, 0, sizeof(board));
    board.side = 0;
    board.squares[4] = PIECE_K;
    board.squares[85] = PIECE_K | SIDE_BLACK;
    board.squares[49] = PIECE_P;
    board.squares[23] = PIECE_N; /* red file six, rank two */
    command.source_file = 6;
    command.target = 7;
    CHECK(xqvoice_resolve_move(&board, &command, &move) == 1 &&
          move.from == 23 && move.to == 42,
          "ma liu jin qi did not resolve");

    command.target = 9;
    CHECK(xqvoice_resolve_move(&board, &command, &move) == 0,
          "illegal notation resolved");

    if (failures)
        return 1;
    puts("XQVOICE_PROTOCOL_PASS phrase=ma-liu-jin-qi ipc=XQVOICE/1");
    return 0;
}
