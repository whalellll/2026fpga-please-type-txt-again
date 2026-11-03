#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "video_fb.h"
#include "xiangqi_fb_gui.h"
#include "xiangqi_mouse_input.h"
#include "xiangqi_pikafish_link.h"

#define TEST_MMIO_BYTES 0x1000u

volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];

static volatile int frame_thread_stop;

static void reset_board(xq_search_board_t *board)
{
    static const uint8_t back_rank[9] = {
        PIECE_R, PIECE_N, PIECE_B, PIECE_A, PIECE_K,
        PIECE_A, PIECE_B, PIECE_N, PIECE_R
    };
    int file;
    memset(board, 0, sizeof(*board));
    for (file = 0; file < 9; ++file) {
        board->squares[file] = back_rank[file];
        board->squares[81 + file] = (uint8_t)(back_rank[file] | SIDE_BLACK);
    }
    for (file = 0; file < 9; file += 2) {
        board->squares[27 + file] = PIECE_P;
        board->squares[54 + file] = PIECE_P | SIDE_BLACK;
    }
    board->side = 0;
}

static uint64_t monotonic_milliseconds(void)
{
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (uint64_t)now.tv_sec * 1000u + (uint64_t)now.tv_nsec / 1000000u;
}

static void *advance_frames(void *unused)
{
    struct timespec delay = {0, 1000000};
    (void)unused;
    while (!frame_thread_stop) {
        ++xq_linux_video_regs[VIDEO_FB_FRAME_COUNT >> 2];
        nanosleep(&delay, NULL);
    }
    return NULL;
}

static int test_mouse_selection(void)
{
    xq_search_board_t board;
    xq_mouse_input_t mouse;
    xq_mouse_action_t action;
    char fen[XQ_PIKAFISH_FEN_CAPACITY];
    reset_board(&board);
    if (!xq_pikafish_board_to_fen(&board, fen, sizeof(fen)) ||
        strcmp(fen,
               "rnbakabnr/9/9/p1p1p1p1p/9/9/P1P1P1P1P/9/9/RNBAKABNR "
               "w - - 0 1") != 0) {
        fprintf(stderr, "initial FEN failed: %s\n", fen);
        return 0;
    }
    xq_mouse_input_init(&mouse, 0);

    /* The coordinate captured on the board maps to red pawn square c3. */
    action = xq_mouse_input_update(&mouse, &board, 222, 449,
                                   XQ_MOUSE_BUTTON_LEFT);
    if (action != XQ_MOUSE_ACTION_SELECTED || mouse.selected_square != 29) {
        fprintf(stderr, "selection failed: action=%d square=%d\n",
                action, mouse.selected_square);
        return 0;
    }
    (void)xq_mouse_input_update(&mouse, &board, 222, 449, 0);
    action = xq_mouse_input_update(&mouse, &board, 222, 449,
                                   XQ_MOUSE_BUTTON_RIGHT);
    if (action != XQ_MOUSE_ACTION_CANCELLED || mouse.selected_square != -1) {
        fprintf(stderr, "cancel failed: action=%d square=%d\n",
                action, mouse.selected_square);
        return 0;
    }
    (void)xq_mouse_input_update(&mouse, &board, 222, 449, 0);
    action = xq_mouse_input_update(&mouse, &board, 224, 456,
                                   XQ_MOUSE_BUTTON_LEFT);
    if (action != XQ_MOUSE_ACTION_SELECTED || mouse.selected_square != 29) {
        fprintf(stderr, "move selection failed: action=%d square=%d\n",
                action, mouse.selected_square);
        return 0;
    }
    (void)xq_mouse_input_update(&mouse, &board, 224, 456, 0);
    action = xq_mouse_input_update(&mouse, &board, 224, 392,
                                   XQ_MOUSE_BUTTON_LEFT);
    if (action != XQ_MOUSE_ACTION_MOVED || board.squares[29] != 0u ||
        board.squares[38] != PIECE_P || board.side != 1) {
        fprintf(stderr, "legal move failed: action=%d from=%u to=%u side=%d\n",
                action, (unsigned)board.squares[29],
                (unsigned)board.squares[38], board.side);
        return 0;
    }
    if (!xq_pikafish_board_to_fen(&board, fen, sizeof(fen)) ||
        strcmp(fen,
               "rnbakabnr/9/9/p1p1p1p1p/9/2P6/P3P1P1P/9/9/RNBAKABNR "
               "b - - 0 1") != 0) {
        fprintf(stderr, "moved FEN failed: %s\n", fen);
        return 0;
    }
    return 1;
}

static int test_wdl_parser(void)
{
    uint32_t wins = 0;
    uint32_t draws = 0;
    uint32_t losses = 0;
    if (!xq_pikafish_parse_wdl(
            "info depth 6 score cp 18 wdl 347 411 242 nodes 100", 
            &wins, &draws, &losses) ||
        wins != 347u || draws != 411u || losses != 242u) {
        fprintf(stderr, "WDL parse failed: %u %u %u\n",
                wins, draws, losses);
        return 0;
    }
    if (xq_pikafish_parse_wdl("info wdl 500 500 1 nodes 4",
                              &wins, &draws, &losses) ||
        xq_pikafish_parse_wdl("info nodes 4", &wins, &draws, &losses)) {
        fprintf(stderr, "invalid WDL was accepted\n");
        return 0;
    }
    return 1;
}

static int test_framebuffer_selection(void)
{
    xq_search_board_t board;
    pthread_t thread;
    uint16_t *fb0;
    uint16_t *fb1;
    uint16_t *before;
    uint64_t start_ms;
    uint64_t elapsed_ms;
    int changed = 0;
    int rate_changed = 0;
    size_t index;

    xq_linux_video_regs = calloc(1, TEST_MMIO_BYTES);
    fb0 = calloc(1, VIDEO_FB_SLOT_BYTES);
    fb1 = malloc(VIDEO_FB_SLOT_BYTES);
    before = malloc(VIDEO_FB_FRAME_BYTES);
    if (!xq_linux_video_regs || !fb0 || !fb1 || !before)
        return 0;
    memset(fb1, 0x5a, VIDEO_FB_SLOT_BYTES);
    xq_linux_framebuffers[0] = fb0;
    xq_linux_framebuffers[1] = fb1;
    xq_linux_video_regs[VIDEO_FB_ID >> 2] = 0x58514642u;
    xq_linux_video_regs[VIDEO_FB_FB0_BASE >> 2] = VIDEO_FB0_PHYS;
    xq_linux_video_regs[VIDEO_FB_FB1_BASE >> 2] = VIDEO_FB1_PHYS;
    xq_linux_video_regs[VIDEO_FB_STATUS >> 2] = VIDEO_FB_STATUS_ACTIVE;

    frame_thread_stop = 0;
    if (pthread_create(&thread, NULL, advance_frames, NULL) != 0)
        return 0;
    reset_board(&board);
    if (!xq_fb_gui_init() ||
        !xq_fb_gui_show(&board, -1, -1, 0, 0,
                        XQ_FB_TIME_UNAVAILABLE, XQ_FB_STATE_READY)) {
        fprintf(stderr, "initial framebuffer show failed\n");
        frame_thread_stop = 1;
        pthread_join(thread, NULL);
        return 0;
    }
    memcpy(before, fb0, VIDEO_FB_FRAME_BYTES);
    xq_fb_gui_set_red_win_rate(637u);
    if (!xq_fb_gui_show(&board, -1, -1, 0, 0,
                        XQ_FB_TIME_UNAVAILABLE, XQ_FB_STATE_READY)) {
        fprintf(stderr, "win-rate framebuffer show failed\n");
        frame_thread_stop = 1;
        pthread_join(thread, NULL);
        return 0;
    }
    for (index = 210u * VIDEO_FB_WIDTH + 720u;
         index < 264u * VIDEO_FB_WIDTH + 1190u; ++index) {
        unsigned int x = (unsigned int)(index % VIDEO_FB_WIDTH);
        if (x >= 720u && x < 1190u && fb0[index] != before[index]) {
            rate_changed = 1;
            break;
        }
    }
    if (!rate_changed) {
        fprintf(stderr, "win-rate panel did not change\n");
        frame_thread_stop = 1;
        pthread_join(thread, NULL);
        return 0;
    }
    start_ms = monotonic_milliseconds();
    if (!xq_fb_gui_show(&board, 29, 29, 0, 0,
                        XQ_FB_TIME_UNAVAILABLE, XQ_FB_STATE_SELECTED)) {
        fprintf(stderr, "selection framebuffer show failed\n");
        frame_thread_stop = 1;
        pthread_join(thread, NULL);
        return 0;
    }
    elapsed_ms = monotonic_milliseconds() - start_ms;
    frame_thread_stop = 1;
    pthread_join(thread, NULL);

    {
        const uint8_t *pixels = (const uint8_t *)fb0;
        uint32_t hash = 2166136261u;
        for (index = 0; index < VIDEO_FB_FRAME_BYTES; ++index)
            hash = (hash ^ pixels[index]) * 16777619u;
        printf("RASTER_FNV1A=%08x\n", (unsigned)hash);
    }

#ifndef XQ_TEST_NO_STALL
    /* The first frame must fail promptly if video scanout never advances. */
    if (!xq_fb_gui_init()) {
        fprintf(stderr, "framebuffer reinitialization failed\n");
        return 0;
    }
    start_ms = monotonic_milliseconds();
    if (xq_fb_gui_show(&board, -1, -1, 0, 0,
                       XQ_FB_TIME_UNAVAILABLE, XQ_FB_STATE_READY)) {
        fprintf(stderr, "stalled video frame counter was accepted\n");
        return 0;
    }
    if (monotonic_milliseconds() - start_ms > 5000u) {
        fprintf(stderr, "stalled video frame counter timed out too slowly\n");
        return 0;
    }
#endif

    for (index = 0; index < VIDEO_FB_FRAME_BYTES / sizeof(*fb0); ++index) {
        if (fb0[index] != before[index]) {
            changed = 1;
            break;
        }
    }
    for (index = 0; index < VIDEO_FB_SLOT_BYTES / sizeof(*fb1); ++index) {
        if (fb1[index] != 0x5a5au) {
            fprintf(stderr, "inactive framebuffer was modified\n");
            return 0;
        }
    }
    if (!changed || elapsed_ms > 500u) {
        fprintf(stderr, "selection redraw changed=%d elapsed_ms=%llu\n",
                changed, (unsigned long long)elapsed_ms);
        return 0;
    }
    free(before);
    free(fb1);
    free(fb0);
    free((void *)xq_linux_video_regs);
    return 1;
}

int main(void)
{
    if (!test_mouse_selection() || !test_wdl_parser() ||
        !test_framebuffer_selection())
        return 1;
    puts("PASS test_xiangqi_gui_host");
    return 0;
}
