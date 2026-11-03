#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "xq_picture.h"
#include "xiangqi_pikafish_link.h"

static const char initial[] =
 "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";
int main(void)
{
    xqp_game game;
    xq_search_board_t board, red, black;
    xqv_result result;
    assert(xqv_parse_fen(initial, &board));
    {
        xqv_frame frame;
        uint32_t *pixels = malloc(XQV_FRAME_BYTES);
        assert(pixels);
        frame.rgb565 = pixels;
        frame.bytes = XQV_FRAME_BYTES;
        frame.frame_id = 77;
        frame.captured_ms = 1;
        assert(xqv_stub_recognize("linux/boot/v2_1_sd/rootfs_payloads/picture/opening.stub", &frame, &result));
        assert(result.is_stub && result.frame_id == 77 && result.piece_count == 32);
        assert(!strcmp(result.fen, initial));
        free(pixels);
    }
    assert(!xqv_parse_fen("9/9 w - - 0 1", &red));
    assert(!xqv_parse_fen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w", &red));
    xqp_init(&game, &board, 800);
    red = board;
    assert(xq_pikafish_apply_move(&red, "h2e2", NULL));
    xqv_board_result(&red, 10, 799, &result);
    assert(xqp_observe(&game, &result, 10) == XQP_RETAKE);
    assert(game.failures == 0 && game.phase == XQP_RED);
    xqv_board_result(&red, 10, 900, &result);
    result.frame_id = 9;
    assert(xqp_observe(&game, &result, 10) == XQP_BAD_RESULT);
    result.frame_id = 10;
    assert(xqp_observe(&game, &result, 10) == XQP_SEARCH);
    assert(!strcmp(game.red_move, "h2e2"));
    black = red;
    assert(xq_pikafish_apply_move(&black, "b9c7", NULL));
    assert(!xqp_engine_move(&game, &board, "b9c7"));
    assert(xqp_engine_move(&game, &black, "b9c7"));
    /* A high board score cannot hide an uncertain piece (L1). */
    xqv_board_result(&red, 11, 900, &result);
    result.pieces[0].confidence = 799;
    assert(xqp_observe(&game, &result, 11) == XQP_RETAKE);
    assert(game.failures == 0);
    result.pieces[0].confidence = 900;
    assert(xqp_observe(&game, &result, 11) == XQP_MISMATCH);
    assert(xqp_observe(&game, &result, 11) == XQP_EDIT);
    assert(game.phase == XQP_MANUAL && game.resume_phase == XQP_BLACK);
    game.observed = black;
    assert(xqp_confirm_manual(&game) == XQP_ACCEPTED);
    assert(game.phase == XQP_RED && game.failures == 0);
    /* L3: an unsuccessful manual correction cannot advance the game. */
    xqv_board_result(&board, 12, 900, &result);
    assert(xqp_observe(&game, &result, 12) == XQP_MISMATCH);
    assert(xqp_observe(&game, &result, 12) == XQP_EDIT);
    assert(xqp_edit(&game, 0, 1));
    assert(!xqp_edit(&game, 90, 1));
    assert(xqp_confirm_manual(&game) == XQP_NEWGAME_REQUIRED);
    assert(game.phase == XQP_RESTART);
    /* Reject FEN/piece-list disagreement, duplicates and malformed counts. */
    xqv_board_result(&board, 13, 900, &result);
    assert(xqv_result_board(&result, 13, &red));
    result.pieces[1] = result.pieces[0];
    assert(!xqv_result_board(&result, 13, &red));
    /* L2 can also repair a red observation, then enter the engine once. */
    xqp_init(&game, &board, 800);
    xqv_board_result(&board, 14, 900, &result);
    assert(xqp_observe(&game, &result, 14) == XQP_MISMATCH);
    assert(xqp_observe(&game, &result, 14) == XQP_EDIT);
    red = board;
    assert(xq_pikafish_apply_move(&red, "h2e2", NULL));
    game.observed = red;
    assert(xqp_confirm_manual(&game) == XQP_SEARCH);
    assert(game.phase == XQP_ENGINE);
    puts("XQ_PICTURE_STATE_TEST_PASS L1 L2 L3 legal-red exact-black stale-frame");
    return 0;
}
