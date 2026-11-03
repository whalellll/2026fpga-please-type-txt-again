#include "xq_vision.h"
#include "xiangqi_pikafish_link.h"
#include <stdio.h>
#include <string.h>

static uint8_t fen_piece(char c)
{
    static const char pieces[] = "KABNRCPkabnrcp";
    const char *p = strchr(pieces, c);
    unsigned index;
    if (!p || !c) return 0;
    index = (unsigned)(p - pieces);
    return (uint8_t)(index % 7u + 1u + (index >= 7u ? SIDE_BLACK : 0u));
}

int xqv_parse_fen(const char *fen, xq_search_board_t *board)
{
    xq_search_board_t parsed;
    char canonical[XQV_FEN_BYTES];
    int rank = 9, file = 0;
    const char *p = fen;
    if (!p || !board) return 0;
    memset(&parsed, 0, sizeof(parsed));
    while (*p && *p != ' ') {
        char c = *p++;
        if (c == '/') {
            if (file != 9 || rank == 0) return 0;
            --rank;
            file = 0;
        } else if (c >= '1' && c <= '9') {
            file += c - '0';
            if (file > 9) return 0;
        } else {
            uint8_t piece = fen_piece(c);
            if (!piece || file >= 9) return 0;
            parsed.squares[rank * 9 + file++] = piece;
        }
    }
    if (rank != 0 || file != 9 || *p++ != ' ') return 0;
    if (*p != 'w' && *p != 'b') return 0;
    parsed.side = *p == 'b';
    if (!xq_pikafish_board_to_fen(&parsed, canonical, sizeof(canonical)) ||
        strcmp(fen, canonical)) return 0;
    *board = parsed;
    return 1;
}

void xqv_board_result(const xq_search_board_t *board, uint32_t frame,
                      uint16_t confidence, xqv_result *out)
{
    unsigned square;
    memset(out, 0, sizeof(*out));
    out->abi_version = XQV_ABI_VERSION;
    out->frame_id = frame;
    out->confidence = confidence;
    (void)xq_pikafish_board_to_fen(board, out->fen, sizeof(out->fen));
    for (square = 0; square < 90; ++square) {
        uint8_t p = board->squares[square];
        xqv_piece *piece;
        if (!p) continue;
        if (out->piece_count >= XQV_MAX_PIECES) {
            out->piece_count = XQV_MAX_PIECES + 1;
            return;
        }
        piece = &out->pieces[out->piece_count++];
        piece->class_id = (uint8_t)((p & 7u) - 1u + ((p & SIDE_BLACK) ? 7u : 0u));
        piece->file = (uint8_t)(square % 9);
        piece->rank = (uint8_t)(square / 9);
        piece->confidence = confidence;
    }
}

int xqv_result_board(const xqv_result *r, uint32_t frame, xq_search_board_t *board)
{
    xq_search_board_t parsed;
    uint8_t squares[90] = {0}, counts[14] = {0};
    static const uint8_t limits[7] = {1, 2, 2, 2, 2, 2, 5};
    unsigned i;
    if (!r || r->abi_version != XQV_ABI_VERSION || r->frame_id != frame ||
        r->confidence > 1000 || r->piece_count > XQV_MAX_PIECES ||
        !memchr(r->fen, 0, sizeof(r->fen)) || !xqv_parse_fen(r->fen, &parsed))
        return 0;
    for (i = 0; i < r->piece_count; ++i) {
        const xqv_piece *p = &r->pieces[i];
        unsigned square;
        if (p->class_id >= 14 || p->file >= 9 || p->rank >= 10 ||
            p->confidence > 1000) return 0;
        square = p->rank * 9u + p->file;
        if (squares[square] || ++counts[p->class_id] > limits[p->class_id % 7])
            return 0;
        squares[square] = (uint8_t)(p->class_id % 7u + 1u +
                                    (p->class_id >= 7u ? SIDE_BLACK : 0u));
    }
    if (counts[0] != 1 || counts[7] != 1 ||
        memcmp(squares, parsed.squares, sizeof(squares))) return 0;
    *board = parsed;
    return 1;
}

int xqv_stub_recognize(void *path, const xqv_frame *frame, xqv_result *out)
{
    FILE *file;
    char header[80], fen[XQV_FEN_BYTES], extra;
    unsigned confidence;
    xq_search_board_t board;
    int okay = 0;
    if (!path || !frame || !out || !frame->rgb565 ||
        frame->bytes != XQV_FRAME_BYTES) return 0;
    file = fopen((const char *)path, "r");
    if (!file) return 0;
    if (fgets(header, sizeof(header), file) &&
        sscanf(header, "XQV_STUB_V1 %u %c", &confidence, &extra) == 1 &&
        confidence <= 1000 && fgets(fen, sizeof(fen), file)) {
        fen[strcspn(fen, "\r\n")] = 0;
        if (xqv_parse_fen(fen, &board)) {
            xqv_board_result(&board, frame->frame_id, (uint16_t)confidence, out);
            out->is_stub = 1;
            okay = xqv_result_board(out, frame->frame_id, &board);
        }
    }
    fclose(file);
    return okay;
}
