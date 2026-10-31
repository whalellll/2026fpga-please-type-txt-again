/* Host rasterization of the actual Linux framebuffer renderer; no FPGA access. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef XQ_GUI_1080
#include "../linux/pikafish/xiangqi_fb_gui_1080.c"
#else
#include "../linux/pikafish/xiangqi_fb_gui_linux.c"
#endif

volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];

int main(int argc, char **argv)
{
    xq_search_board_t board;
    static const uint8_t back[9] = {
        PIECE_R, PIECE_N, PIECE_B, PIECE_A, PIECE_K,
        PIECE_A, PIECE_B, PIECE_N, PIECE_R
    };
    uint16_t *pixels = calloc(VIDEO_FB_WIDTH * VIDEO_FB_HEIGHT, 2);
    FILE *out;
    unsigned int i;
    if ((argc != 2 && argc != 3) || !pixels)
        return 1;
    memset(&board, 0, sizeof(board));
    for (i = 0; i < 9; ++i) {
        board.squares[i] = back[i];
        board.squares[81 + i] = back[i] | SIDE_BLACK;
    }
    for (i = 0; i < 9; i += 2) {
        board.squares[27 + i] = PIECE_P;
        board.squares[54 + i] = PIECE_P | SIDE_BLACK;
    }
    board.squares[19] = board.squares[25] = PIECE_C;
    board.squares[64] = board.squares[70] = PIECE_C | SIDE_BLACK;
    xq_fb_gui_set_red_win_rate(637);
    xq_fb_gui_set_voice_feedback("VOICE READY");
#ifdef XQ_GUI_1080
    if (argc == 3 && strcmp(argv[2], "voice") == 0) {
        xqvoice_command_t event = {0};
        event.type = XQVOICE_COMMAND_DISPLAY;
        event.display_state = XQVOICE_DISPLAY_COMPLETE;
        event.confidence_permille = 901;
        event.token_count = 4;
        event.tokens[0] = 1; event.tokens[1] = 16;
        event.tokens[2] = 19; event.tokens[3] = 13;
        xq_fb_gui_set_voice_display(&event);
    }
#endif
    draw_scene(pixels, &board, 29, -1, 18, 12480,
               CLINT_TICKS_PER_US * 142000, XQ_FB_STATE_SELECTED);
    out = fopen(argv[1], "wb");
    if (!out)
        return 2;
    fprintf(out, "P6\n%u %u\n255\n", VIDEO_FB_WIDTH, VIDEO_FB_HEIGHT);
    for (i = 0; i < VIDEO_FB_WIDTH * VIDEO_FB_HEIGHT; ++i) {
        unsigned int p = pixels[i];
        unsigned char rgb[3] = {
            (unsigned char)(((p >> 11) * 255 + 15) / 31),
            (unsigned char)((((p >> 5) & 63) * 255 + 31) / 63),
            (unsigned char)(((p & 31) * 255 + 15) / 31)
        };
        if (fwrite(rgb, 1, 3, out) != 3)
            return 3;
    }
    free(pixels);
    return fclose(out) != 0;
}
