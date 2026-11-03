#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef XQ_RENDERER_SOURCE
#define XQ_RENDERER_SOURCE "../linux/pikafish/xiangqi_fb_gui_1080.c"
#endif
#include XQ_RENDERER_SOURCE
#include "xiangqi_mouse_input.h"

volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];

#define CHECK(condition) do { if (!(condition)) { \
    fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); exit(1); \
} } while (0)

static void initial_board(xq_search_board_t *b)
{
    const uint8_t back[] = {PIECE_R, PIECE_N, PIECE_B, PIECE_A, PIECE_K,
                            PIECE_A, PIECE_B, PIECE_N, PIECE_R};
    int i;
    memset(b, 0, sizeof(*b));
    for (i = 0; i < 9; ++i) {
        b->squares[i] = back[i];
        b->squares[81+i] = back[i] | SIDE_BLACK;
    }
    for (i = 0; i < 9; i += 2) {
        b->squares[27+i] = PIECE_P;
        b->squares[54+i] = PIECE_P | SIDE_BLACK;
    }
    b->squares[19] = b->squares[25] = PIECE_C;
    b->squares[64] = b->squares[70] = PIECE_C | SIDE_BLACK;
}

static void check_piece_font(void)
{
    unsigned int glyph, row, col;
    for (glyph = 0; glyph < XQ_PIECE_GLYPH_COUNT; ++glyph) {
        unsigned int intermediate = 0, opaque = 0;
        for (row = 0; row < XQ_PIECE_GLYPH_SIZE; ++row) {
            for (col = 0; col < XQ_PIECE_GLYPH_SIZE; ++col) {
                unsigned int packed = xq_piece_alpha4[glyph][row * 24 + col / 2];
                unsigned int alpha = col & 1u ? packed & 15u : packed >> 4;
                if (alpha) {
                    int dx = (int)col - 24, dy = (int)row - 24;
                    /* Blending must never reach the outlined or shaded rim. */
                    CHECK(dx*dx + dy*dy <= 27*27);
                }
                intermediate += alpha > 0 && alpha < 15;
                opaque += alpha == 15;
            }
        }
        CHECK(intermediate > 100 && opaque > 20);
    }
}

static unsigned int text_width(const char *text, int scale)
{
    unsigned int width = 0;
    while (*text) width += ascii_glyph(*text++, scale)->advance;
    return width;
}

static void check_ui_font(uint16_t *pixels)
{
    unsigned int i, x, y, blended = 0, untouched = 0;
    const xq_ui_glyph_t *river = &xq_ui_zh48[XQ_HZ_CHU];
    CHECK(river->width == 48 && river->height == 48);
    CHECK(text_width("PLAY WITH INTELLIGENCE",2) <= 352);
    CHECK(text_width("-2147483648",5) <= 352);
    CHECK(text_width("4294967295",3) <= 300);
    CHECK(text_width("159072",3) <= 146);
    CHECK(text_width("CONFIDENCE",1) <= 142);
    for (i=0; i<XQ_HZ_COUNT; ++i) {
        const xq_ui_glyph_t *g = &xq_ui_zh32[i];
        CHECK(g->width == 32 && g->height == 32);
        CHECK(g->offset + g->width * g->height / 2 <= sizeof(xq_ui_alpha4));
    }
    /* Blending must use the actual background and honor an odd clipping edge.
     * Every pixel outside the clip, including a neighbor sharing a word, stays. */
    fill_screen(pixels, 0x001fu);
    set_clip(5,7,31,29);
    draw_ui_glyph(pixels,-3,-4,river,0xf800u);
    reset_clip();
    for (y=0; y<VIDEO_FB_HEIGHT; ++y) {
        for (x=0; x<VIDEO_FB_WIDTH; ++x) {
            uint16_t value = ((volatile uint16_t *)pixels)[y*VIDEO_FB_WIDTH+x];
            if (x<5 || x>=36 || y<7 || y>=36) {
                if (value != 0x001fu) fprintf(stderr,"clip x=%u y=%u value=%04x\n",x,y,value);
                CHECK(value == 0x001fu);
            }
            else {
                CHECK(!(value & 0x07e0u));
                blended += (value & 0xf800u) && (value & 31u);
                untouched += value == 0x001fu;
            }
        }
    }
    CHECK(blended > 50 && untouched > 50);
}

int main(void)
{
    uint8_t *allocation = malloc(VIDEO_FB_FRAME_BYTES + 128);
    uint16_t *current = (uint16_t *)(allocation + 64);
    uint16_t *reference = malloc(VIDEO_FB_FRAME_BYTES);
    uint32_t regs[64] = {0};
    xq_search_board_t board;
    xq_mouse_input_t mouse;
    unsigned int i, step;
    int from = -1, to = -1;
    CHECK(allocation && reference);
    check_piece_font();
    memset(allocation, 0xa5, VIDEO_FB_FRAME_BYTES + 128);
    check_ui_font(current);
    xq_linux_video_regs = regs;
    regs[VIDEO_FB_ID/4] = FB_ID_VALUE;
    regs[VIDEO_FB_FB0_BASE/4] = VIDEO_FB0_PHYS;
    regs[VIDEO_FB_FB1_BASE/4] = VIDEO_FB1_PHYS;
    regs[VIDEO_FB_SIZE/4] = (1080u << 16) | 1920u;
    regs[VIDEO_FB_STRIDE/4] = 3840;
    regs[VIDEO_FB_BYTES/4] = 4147200;
    CHECK(xq_fb_gui_init());
    {
        const unsigned int offsets[] = {VIDEO_FB_ID, VIDEO_FB_FB0_BASE,
            VIDEO_FB_FB1_BASE, VIDEO_FB_SIZE, VIDEO_FB_STRIDE, VIDEO_FB_BYTES};
        for (i = 0; i < ARRAY_COUNT(offsets); ++i) {
            unsigned int word = offsets[i]/4;
            uint32_t original = regs[word];
            regs[word] ^= 1;
            CHECK(!xq_fb_gui_init());
            regs[word] = original;
        }
    }
    for (i = 0; i < 90; ++i) {
        int x = BOARD_X + (int)(i % 9) * CELL;
        int y = BOARD_Y + (9 - (int)i / 9) * CELL;
        CHECK(xq_mouse_screen_to_square(x, y) == (int)i);
        CHECK(xq_mouse_screen_to_square(x+37, y+37) == (int)i);
    }
    CHECK(xq_mouse_screen_to_square(-1, -1) == -1);
    CHECK(xq_mouse_screen_to_square(1919, 1079) == -1);
    CHECK(xq_mouse_screen_to_square(BOARD_X + 40, BOARD_Y) == -1);
    initial_board(&board);
    xq_mouse_input_init(&mouse, 0);
    CHECK(xq_mouse_input_update(&mouse, &board, XQ_FB_RESTART_X+10,
        XQ_FB_RESTART_Y+10, XQ_MOUSE_BUTTON_LEFT) == XQ_MOUSE_ACTION_RESTART);
    xq_mouse_input_init(&mouse, 0);
    CHECK(xq_mouse_input_update(&mouse, &board, BOARD_X + 2*CELL,
        BOARD_Y + 6*CELL, XQ_MOUSE_BUTTON_LEFT) == XQ_MOUSE_ACTION_SELECTED);
    (void)xq_mouse_input_update(&mouse, &board, BOARD_X + 2*CELL, BOARD_Y + 6*CELL, 0);
    CHECK(xq_mouse_input_update(&mouse, &board, BOARD_X + 2*CELL,
        BOARD_Y + 5*CELL, XQ_MOUSE_BUTTON_LEFT) == XQ_MOUSE_ACTION_MOVED);
    CHECK(board.squares[29] == 0 && board.squares[38] == PIECE_P);
    initial_board(&board);
    draw_scene(current, &board, -1, -1, 0, 0, XQ_FB_TIME_UNAVAILABLE, XQ_FB_STATE_READY);
    save_scene(&board, -1, -1, 0, 0, XQ_FB_TIME_UNAVAILABLE, XQ_FB_STATE_READY);
    for (step = 0; step < 96; ++step) {
        xq_search_move_t moves[XQ_SEARCH_MAX_MOVES];
        int count = xq_search_legal_moves(&board, moves, XQ_SEARCH_MAX_MOVES);
        uint32_t nodes = step % 2 ? 0xffffffffu : step * 15999u;
        uint32_t ticks = step % 3 ? step * 270000u : XQ_FB_TIME_UNAVAILABLE;
        xq_fb_state_t state = (xq_fb_state_t)(step % 16);
        uint32_t rate = step % 5 == 0 ? XQ_FB_WIN_RATE_UNAVAILABLE : (step * 113) % 1001;
        int32_t score = step < 48 ? (int32_t)step-24 :
            step % 3 == 0 ? INT32_MIN : step % 3 == 1 ? INT32_MAX : 0;
        if (count && step % 2 == 0) {
            xq_search_move_t move = moves[(step * 17u) % (unsigned int)count];
            from = move.from; to = move.to;
            board.squares[to] = board.squares[from];
            board.squares[from] = 0;
            board.side ^= 1;
        } else { from = -1; to = count ? moves[0].from : -1; }
        if (step >= 48 && step % 7 == 0) show_red_win_rate=0;
        else xq_fb_gui_set_red_win_rate(rate);
        if (step % 4 == 0) {
            xqvoice_command_t event = {0};
            event.type = XQVOICE_COMMAND_DISPLAY;
            event.display_state = XQVOICE_DISPLAY_COMPLETE;
            event.token_count = 4;
            event.confidence_permille = 901;
            for (i = 0; i < 4; ++i) event.tokens[i] = (uint8_t)(1 + (step+i) % 24);
            xq_fb_gui_set_voice_display(&event);
            CHECK(voice_display.token_count == 4);
            CHECK(voice_display.confidence_permille == 901);
        } else if (step % 4 == 1) {
            xqvoice_command_t event = {0};
            event.type = XQVOICE_COMMAND_DISPLAY;
            event.display_state = XQVOICE_DISPLAY_CAPTURING;
            xq_fb_gui_set_voice_display(&event);
            CHECK(voice_display.token_count == 4);
            CHECK(voice_display.confidence_permille == 901);
        }
#ifdef GUI_FB_COUNTED
        gui_fb_reads=gui_fb_writes=0;
#endif
        redraw_dirty_scene(current, &board, from, to, score, nodes, ticks, state);
#ifdef GUI_FB_COUNTED
        printf("GUI_IO step=%u reads=%llu writes=%llu\n",step,
            (unsigned long long)gui_fb_reads,(unsigned long long)gui_fb_writes);
#endif
        draw_scene(reference, &board, from, to, score, nodes, ticks, state);
        if (memcmp(current, reference, VIDEO_FB_FRAME_BYTES)) {
            for (i=0; i<VIDEO_FB_FRAME_BYTES/2; ++i)
                if (current[i] != reference[i]) break;
            fprintf(stderr, "dirty/full mismatch step=%u x=%u y=%u\n", step, i%1920, i/1920);
            return 1;
        }
        { uint32_t hash=2166136261u;for(i=0;i<VIDEO_FB_FRAME_BYTES/2;i++)hash=(hash^current[i])*16777619u;
          printf("GUI_FRAME step=%u fnv=%08x\n",step,hash); }
        save_scene(&board, from, to, score, nodes, ticks, state);
        for (i=0; i<64; ++i) {
            CHECK(allocation[i] == 0xa5);
            CHECK(allocation[64+VIDEO_FB_FRAME_BYTES+i] == 0xa5);
        }
    }
    puts("GUI1080_HOST_PASS abi-negative=6 hit-squares=90 legal-move=1 dirty-full=96 guarded-rgb565=PASS aa-glyphs=11 ui-aa-clip-blend=PASS text-layout=PASS");
    free(reference);
    free(allocation);
    return 0;
}
