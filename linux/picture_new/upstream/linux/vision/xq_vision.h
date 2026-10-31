#ifndef XQ_VISION_H
#define XQ_VISION_H
#include <stddef.h>
#include <stdint.h>
#include "xiangqi_search.h"

/* ABI 1: immutable, ordinary RAM only; never pass an O_SYNC mapping to a
 * detector, PNG encoder or byte-oriented library. a0 is red's bottom left.
 * FEN uses KABNRCP/kabnrcp. Turn/history belong to the game, not the camera. */
#define XQV_ABI_VERSION 1u
#define XQV_WIDTH 1280u
#define XQV_HEIGHT 720u
#define XQV_FRAME_BYTES 1843200u
#define XQV_FEN_BYTES 128u
#define XQV_MAX_PIECES 32u
typedef struct {
    const uint32_t *rgb565;
    size_t bytes;
    uint32_t frame_id;
    uint64_t captured_ms;
} xqv_frame;
/* class_id 0..6 red K,A,B,N,R,C,P; 7..13 black in the same order.
 * Confidence is integer permille [0,1000], never a float or inferred score. */
typedef struct {
    uint8_t class_id, file, rank;
    uint16_t confidence;
} xqv_piece;
typedef struct {
    uint32_t abi_version, frame_id;
    char fen[XQV_FEN_BYTES];
    xqv_piece pieces[XQV_MAX_PIECES];
    uint32_t piece_count;
    uint16_t confidence;
    uint8_t is_stub;
} xqv_result;
typedef int (*xqv_recognize_fn)(void *context, const xqv_frame *, xqv_result *);

/* File stub format: XQV_STUB_V1 <confidence-permille>\n<canonical FEN>\n.
 * Reopened for each frame so a human can replace it between Space presses.
 * It never claims a measured detection confidence or production inference. */
int xqv_stub_recognize(void *path, const xqv_frame *, xqv_result *);
int xqv_parse_fen(const char *, xq_search_board_t *);
int xqv_result_board(const xqv_result *, uint32_t expected_frame,
                     xq_search_board_t *);
void xqv_board_result(const xq_search_board_t *, uint32_t frame,
                      uint16_t confidence, xqv_result *);
#endif
