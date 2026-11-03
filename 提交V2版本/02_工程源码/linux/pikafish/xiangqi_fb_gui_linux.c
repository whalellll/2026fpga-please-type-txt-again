/* Linux copy of sw/xiangqi/xiangqi_fb_gui.c. The shared renderer is a
 * frozen FPGA build input (SHA-256 8384611e667d230133146ee4afb40b6ab67bd2239ef9634313147e8e98cd5b3a).
 * This copy uses full-word writes for the board's uncached DDR mapping. */
#include <stdint.h>
#include "video_fb.h"
#include "../vision/picture_video_compat.h"
#include "xiangqi_fb_gui.h"
#include "xiangqi_font_zh.h"
#ifdef XQ_PICTURE_INPUT
#include "../vision/xq_picture_display.h"
#include "../vision/xq_picture_font.h"
#include <string.h>
#include <stdio.h>
#endif
#include "xqvoice_display.h"
#include "xqvoice_display_font.h"

#define FB_ID_VALUE 0x58514642u

#define C_BG       0x10a4u
#define C_PANEL    0x2148u
#define C_BOARD    0xd5adu
#define C_LINE     0x5144u
#define C_PIECE    0xff19u
#define C_RED      0xd104u
#define C_BLACK    0x18c3u
#define C_WHITE    0xffffu
#define C_GOLD     0xff20u
#define C_GREEN    0x4e6au

#define BOARD_X XQ_FB_BOARD_X
#define BOARD_Y XQ_FB_BOARD_Y
#define CELL    XQ_FB_CELL

#define ARRAY_COUNT(a) ((uint32_t)(sizeof(a) / sizeof((a)[0])))
#define CLINT_TICKS_PER_US 27u

/* The accelerator owns 0x1b000000..0x1b0fffff and the following MiB is a
 * hard guard band.  Fail the build if a future framebuffer change crosses
 * either that boundary or its fixed 2 MiB slots. */
#define ACCEL_DDR_END 0x1b100000u
#define FB_GUARD_END  0x1b200000u
#define FB_DDR_END    0x1b600000u

#if VIDEO_FB0_PHYS < FB_GUARD_END || VIDEO_FB0_PHYS < ACCEL_DDR_END
#error "Framebuffer 0 overlaps accelerator DDR or its guard band"
#endif
#if (VIDEO_FB0_PHYS + VIDEO_FB_FRAME_BYTES) > VIDEO_FB1_PHYS
#error "Framebuffer 0 image overlaps framebuffer 1"
#endif
#if (VIDEO_FB1_PHYS + VIDEO_FB_FRAME_BYTES) > FB_DDR_END
#error "Framebuffer 1 image exceeds the reserved framebuffer aperture"
#endif

static const uint8_t font5x7[36][7] = {
    {14,17,17,31,17,17,17}, {30,17,17,30,17,17,30},
    {14,17,16,16,16,17,14}, {30,17,17,17,17,17,30},
    {31,16,16,30,16,16,31}, {31,16,16,30,16,16,16},
    {14,17,16,23,17,17,15}, {17,17,17,31,17,17,17},
    {14,4,4,4,4,4,14},      {7,2,2,2,18,18,12},
    {17,18,20,24,20,18,17}, {16,16,16,16,16,16,31},
    {17,27,21,21,17,17,17}, {17,25,21,19,17,17,17},
    {14,17,17,17,17,17,14}, {30,17,17,30,16,16,16},
    {14,17,17,17,21,18,13}, {30,17,17,30,20,18,17},
    {15,16,16,14,1,1,30},   {31,4,4,4,4,4,4},
    {17,17,17,17,17,17,14}, {17,17,17,17,17,10,4},
    {17,17,17,21,21,21,10}, {17,17,10,4,10,17,17},
    {17,17,10,4,4,4,4},     {31,1,2,4,8,16,31},
    {14,17,19,21,25,17,14}, {4,12,4,4,4,4,14},
    {14,17,1,2,4,8,31},     {30,1,1,14,1,1,30},
    {2,6,10,18,31,2,2},     {31,16,16,30,1,1,30},
    {14,16,16,30,17,17,14}, {31,1,2,4,8,8,8},
    {14,17,17,14,17,17,14}, {14,17,17,15,1,1,14}
};

/* Drawing is clipped while a dirty region is rebuilt.  Coordinates use an
 * exclusive right/bottom edge, matching fill_rect width/height semantics. */
static int clip_x0 = 0;
static int clip_y0 = 0;
static int clip_x1 = VIDEO_FB_WIDTH;
static int clip_y1 = VIDEO_FB_HEIGHT;
static int show_red_win_rate;
static uint32_t red_win_rate_permille = XQ_FB_WIN_RATE_UNAVAILABLE;
#ifdef XQ_PICTURE_INPUT
static char picture_lines[3][128];
static const uint32_t *picture_rectified;
void xq_fb_gui_picture_topview(const uint32_t *pixels) { picture_rectified=pixels; }
static uint32_t picture_generation;
static uint32_t displayed_picture_generation;
static unsigned int current_front;
static int display_started;
static int picture_needs_scan_ack;
static const uint32_t *diagnostic_pixels;
static const xqg_detection *diagnostic_boxes;
static const xqv_result *diagnostic_result;
static xqp_metrics diagnostic_metrics;
void xq_fb_gui_picture_diagnostic(const uint32_t *pixels, const xqg_detection *boxes,
                                  const xqv_result *result, const xqp_metrics *metrics)
{
    if(pixels || diagnostic_pixels)display_started=0;
    diagnostic_pixels = pixels;
    diagnostic_boxes = boxes;
    diagnostic_result = result;
    if (metrics) diagnostic_metrics = *metrics;
}
void xq_fb_gui_picture_feedback(const char *a, const char *b, const char *c)
{
    const char *lines[3] = {a, b, c};
    unsigned i;
    for (i = 0; i < 3; ++i) {
        const char *text = lines[i] ? lines[i] : "";
        size_t length = strlen(text);
        if (length >= sizeof(picture_lines[i])) length = sizeof(picture_lines[i]) - 1;
        memcpy(picture_lines[i], text, length);
        picture_lines[i][length] = 0;
    }
    ++picture_generation;
}
#endif

static void set_clip(int x, int y, int w, int h)
{
    clip_x0 = x < 0 ? 0 : x;
    clip_y0 = y < 0 ? 0 : y;
    clip_x1 = x + w > (int)VIDEO_FB_WIDTH ? (int)VIDEO_FB_WIDTH : x + w;
    clip_y1 = y + h > (int)VIDEO_FB_HEIGHT ? (int)VIDEO_FB_HEIGHT : y + h;
}

static void reset_clip(void)
{
    clip_x0 = 0;
    clip_y0 = 0;
    clip_x1 = VIDEO_FB_WIDTH;
    clip_y1 = VIDEO_FB_HEIGHT;
}

static int rect_visible(int x, int y, int w, int h)
{
    return x < clip_x1 && y < clip_y1 &&
           x + w > clip_x0 && y + h > clip_y0;
}

static void put_pixel(volatile uint16_t *fb, int x, int y, uint16_t colour)
{
    if (x >= clip_x0 && x < clip_x1 && y >= clip_y0 && y < clip_y1) {
#if defined(VIDEO_FB_LINUX_MMAP) && defined(XQ_PICTURE_INPUT)
        xq_linux_video_dirty_rows[y]=1;
#endif
        unsigned int pixel = (unsigned int)y * VIDEO_FB_WIDTH + (unsigned int)x;
#ifdef VIDEO_FB_LINUX_MMAP
        volatile uint32_t *words = (volatile uint32_t *)(uintptr_t)fb;
        uint32_t old = words[pixel >> 1];
        words[pixel >> 1] = (pixel & 1u) ?
            ((old & 0x0000ffffu) | ((uint32_t)colour << 16)) :
            ((old & 0xffff0000u) | colour);
#else
        fb[pixel] = colour;
#endif
    }
}

static void fill_screen(volatile uint16_t *fb, uint16_t colour)
{
    volatile uint32_t *words = (volatile uint32_t *)(uintptr_t)fb;
    uint32_t packed = (uint32_t)colour | ((uint32_t)colour << 16);
    unsigned int i;
    for (i = 0; i < VIDEO_FB_FRAME_BYTES / 4u; ++i)
        words[i] = packed;
#if defined(VIDEO_FB_LINUX_MMAP) && defined(XQ_PICTURE_INPUT)
    memset(xq_linux_video_dirty_rows,1,VIDEO_FB_HEIGHT);
#endif
}

static void fill_rect(volatile uint16_t *fb, int x, int y, int w, int h,
                      uint16_t colour)
{
    int x0 = x;
    int y0 = y;
    int x1 = x + w;
    int y1 = y + h;
    int yy;
    if (x0 < clip_x0)
        x0 = clip_x0;
    if (y0 < clip_y0)
        y0 = clip_y0;
    if (x1 > clip_x1)
        x1 = clip_x1;
    if (y1 > clip_y1)
        y1 = clip_y1;
    if (x0 >= x1 || y0 >= y1)
        return;
#ifdef VIDEO_FB_LINUX_MMAP
    {
        volatile uint32_t *words = (volatile uint32_t *)(uintptr_t)fb;
        uint32_t packed = (uint32_t)colour | ((uint32_t)colour << 16);
        for (yy = y0; yy < y1; ++yy) {
#ifdef XQ_PICTURE_INPUT
            xq_linux_video_dirty_rows[yy]=1;
#endif
            unsigned int pixel = (unsigned int)yy * VIDEO_FB_WIDTH +
                                 (unsigned int)x0;
            unsigned int end = (unsigned int)yy * VIDEO_FB_WIDTH +
                               (unsigned int)x1;
            if (pixel & 1u) {
                uint32_t old = words[pixel >> 1];
                words[pixel >> 1] = (old & 0x0000ffffu) |
                                    ((uint32_t)colour << 16);
                ++pixel;
            }
            while (pixel + 1u < end) {
                words[pixel >> 1] = packed;
                pixel += 2u;
            }
            if (pixel < end) {
                uint32_t old = words[pixel >> 1];
                words[pixel >> 1] = (old & 0xffff0000u) | colour;
            }
        }
    }
#else
    {
        int xx;
        for (yy = y0; yy < y1; ++yy)
            for (xx = x0; xx < x1; ++xx)
                fb[(unsigned int)yy * VIDEO_FB_WIDTH + (unsigned int)xx] = colour;
    }
#endif
}

static void hline(volatile uint16_t *fb, int x0, int x1, int y, int thickness,
                  uint16_t colour)
{
    fill_rect(fb, x0, y - thickness / 2, x1 - x0 + 1, thickness, colour);
}

static void vline(volatile uint16_t *fb, int x, int y0, int y1, int thickness,
                  uint16_t colour)
{
    fill_rect(fb, x - thickness / 2, y0, thickness, y1 - y0 + 1, colour);
}

static void diagonal(volatile uint16_t *fb, int x0, int y0, int x1, int y1,
                     uint16_t colour)
{
    int dx = x1 > x0 ? x1 - x0 : x0 - x1;
    int sx = x0 < x1 ? 1 : -1;
    int dy = -(y1 > y0 ? y1 - y0 : y0 - y1);
    int sy = y0 < y1 ? 1 : -1;
    int err = dx + dy;
    for (;;) {
        fill_rect(fb, x0 - 1, y0 - 1, 3, 3, colour);
        if (x0 == x1 && y0 == y1)
            break;
        if (2 * err >= dy) { err += dy; x0 += sx; }
        if (2 * err <= dx) { err += dx; y0 += sy; }
    }
}

static const uint8_t *glyph(char c)
{
    if (c >= 'A' && c <= 'Z')
        return font5x7[(unsigned int)(c - 'A')];
    if (c >= '0' && c <= '9')
        return font5x7[26u + (unsigned int)(c - '0')];
    return (const uint8_t *)0;
}

static void draw_char(volatile uint16_t *fb, int x, int y, char c, int scale,
                      uint16_t colour)
{
    const uint8_t *rows = glyph(c);
    int row, col;
    if (c == '-') {
        fill_rect(fb, x, y + 3 * scale, 5 * scale, scale, colour);
        return;
    }
    if (c == '.') {
        fill_rect(fb, x + 2 * scale, y + 6 * scale, scale, scale, colour);
        return;
    }
    if (c == '%') {
        fill_rect(fb, x, y, 2 * scale, 2 * scale, colour);
        fill_rect(fb, x + 3 * scale, y + 5 * scale,
                  2 * scale, 2 * scale, colour);
        for (row = 0; row < 7; ++row)
            fill_rect(fb, x + (4 - (row * 4) / 6) * scale,
                      y + row * scale, scale, scale, colour);
        return;
    }
    if (!rows)
        return;
    for (row = 0; row < 7; ++row)
        for (col = 0; col < 5; ++col)
            if (rows[row] & (1u << (4 - col)))
                fill_rect(fb, x + col * scale, y + row * scale,
                          scale, scale, colour);
}

static void draw_text(volatile uint16_t *fb, int x, int y, const char *text,
                      int scale, uint16_t colour)
{
    while (*text) {
        draw_char(fb, x, y, *text++, scale, colour);
        x += 6 * scale;
    }
}

static void draw_hanzi(volatile uint16_t *fb, int x, int y,
                       xq_hanzi_t glyph_index, int scale, uint16_t colour)
{
    int row, col;
    if ((unsigned int)glyph_index >= XQ_HZ_COUNT)
        return;
    for (row = 0; row < 16; ++row) {
        uint16_t bits = xq_font16x16[glyph_index][row];
        for (col = 0; col < 16; ++col) {
            if (bits & (1u << (15 - col)))
                fill_rect(fb, x + col * scale, y + row * scale,
                          scale, scale, colour);
        }
    }
}

static void draw_hanzi_text(volatile uint16_t *fb, int x, int y,
                            const uint8_t *glyphs, uint32_t count,
                            int scale, uint16_t colour)
{
    uint32_t index;
    for (index = 0; index < count; ++index) {
        draw_hanzi(fb, x, y, (xq_hanzi_t)glyphs[index], scale, colour);
        x += 17 * scale;
    }
}

static void draw_int(volatile uint16_t *fb, int x, int y, int32_t value,
                     int scale, uint16_t colour)
{
    char text[12];
    char reverse[11];
    uint32_t magnitude;
    int count = 0;
    int out = 0;
    if (value < 0) {
        text[out++] = '-';
        magnitude = (uint32_t)(-(int64_t)value);
    } else {
        magnitude = (uint32_t)value;
    }
    if (magnitude == 0u)
        reverse[count++] = '0';
    while (magnitude != 0u) {
        reverse[count++] = (char)('0' + magnitude % 10u);
        magnitude /= 10u;
    }
    while (count != 0)
        text[out++] = reverse[--count];
    text[out] = '\0';
    draw_text(fb, x, y, text, scale, colour);
}

static void draw_uint(volatile uint16_t *fb, int x, int y, uint32_t value,
                      int scale, uint16_t colour)
{
    char text[11];
    char reverse[10];
    int count = 0;
    int out = 0;
    if (value == 0u)
        reverse[count++] = '0';
    while (value != 0u) {
        reverse[count++] = (char)('0' + value % 10u);
        value /= 10u;
    }
    while (count != 0)
        text[out++] = reverse[--count];
    text[out] = '\0';
    draw_text(fb, x, y, text, scale, colour);
}

static void draw_permille_percent(volatile uint16_t *fb, int x, int y,
                                  uint32_t permille, int scale,
                                  uint16_t colour)
{
    char text[8];
    int out = 0;
    uint32_t whole;
    if (permille == XQ_FB_WIN_RATE_UNAVAILABLE) {
        draw_text(fb, x, y, "--", scale, colour);
        return;
    }
    if (permille > 1000u)
        permille = 1000u;
    whole = permille / 10u;
    if (whole >= 100u)
        text[out++] = (char)('0' + whole / 100u);
    if (whole >= 10u)
        text[out++] = (char)('0' + (whole / 10u) % 10u);
    text[out++] = (char)('0' + whole % 10u);
    text[out++] = '.';
    text[out++] = (char)('0' + permille % 10u);
    text[out++] = '%';
    text[out] = '\0';
    draw_text(fb, x, y, text, scale, colour);
}

static void draw_disc(volatile uint16_t *fb, int cx, int cy, int radius,
                      uint16_t colour)
{
    int x, y;
    for (y = -radius; y <= radius; ++y)
        for (x = -radius; x <= radius; ++x)
            if (x * x + y * y <= radius * radius)
                put_pixel(fb, cx + x, cy + y, colour);
}

static void draw_ring(volatile uint16_t *fb, int cx, int cy, int radius,
                      int thickness, uint16_t colour)
{
    int x, y;
    int outer = radius * radius;
    int inner = (radius - thickness) * (radius - thickness);
    for (y = -radius; y <= radius; ++y) {
        for (x = -radius; x <= radius; ++x) {
            int d = x * x + y * y;
            if (d <= outer && d >= inner)
                put_pixel(fb, cx + x, cy + y, colour);
        }
    }
}

static void draw_piece(volatile uint16_t *fb, int file, int rank,
                       xq_hanzi_t label, uint16_t ink, int selected)
{
    int x = BOARD_X + file * CELL;
    int y = BOARD_Y + rank * CELL;
    if (!rect_visible(x - 32, y - 32, 65, 65))
        return;
    if (selected)
        draw_ring(fb, x, y, 31, 4, C_GOLD);
    draw_disc(fb, x, y, 25, C_PIECE);
    draw_ring(fb, x, y, 25, 3, ink);
    draw_hanzi(fb, x - 16, y - 16, label, 2, ink);
}

static void draw_board(volatile uint16_t *fb)
{
    int file, rank;
    fill_rect(fb, 62, 35, 584, 650, C_BOARD);
    fill_rect(fb, 72, 45, 564, 630, C_PIECE);
    fill_rect(fb, 82, 55, 544, 610, C_BOARD);
    for (rank = 0; rank < 10; ++rank)
        hline(fb, BOARD_X, BOARD_X + 8 * CELL,
              BOARD_Y + rank * CELL, 3, C_LINE);
    for (file = 0; file < 9; ++file) {
        int x = BOARD_X + file * CELL;
        if (file == 0 || file == 8) {
            vline(fb, x, BOARD_Y, BOARD_Y + 9 * CELL, 3, C_LINE);
        } else {
            vline(fb, x, BOARD_Y, BOARD_Y + 4 * CELL, 3, C_LINE);
            vline(fb, x, BOARD_Y + 5 * CELL, BOARD_Y + 9 * CELL, 3, C_LINE);
        }
    }
    diagonal(fb, BOARD_X + 3 * CELL, BOARD_Y,
             BOARD_X + 5 * CELL, BOARD_Y + 2 * CELL, C_LINE);
    diagonal(fb, BOARD_X + 5 * CELL, BOARD_Y,
             BOARD_X + 3 * CELL, BOARD_Y + 2 * CELL, C_LINE);
    diagonal(fb, BOARD_X + 3 * CELL, BOARD_Y + 7 * CELL,
             BOARD_X + 5 * CELL, BOARD_Y + 9 * CELL, C_LINE);
    diagonal(fb, BOARD_X + 5 * CELL, BOARD_Y + 7 * CELL,
             BOARD_X + 3 * CELL, BOARD_Y + 9 * CELL, C_LINE);
    {
        static const uint8_t chu_he[] = {XQ_HZ_CHU, XQ_HZ_HE};
        static const uint8_t han_jie[] = {XQ_HZ_HAN, XQ_HZ_JIE_BORDER};
        draw_hanzi_text(fb, 170, 344, chu_he, ARRAY_COUNT(chu_he), 2, C_RED);
        draw_hanzi_text(fb, 470, 344, han_jie, ARRAY_COUNT(han_jie), 2,
                        C_BLACK);
    }
}

static xq_hanzi_t piece_label(uint8_t piece)
{
    static const uint8_t red_labels[8] = {
        XQ_HZ_SHUAI, XQ_HZ_SHUAI, XQ_HZ_SHI_RED, XQ_HZ_XIANG_RED,
        XQ_HZ_MA, XQ_HZ_JU, XQ_HZ_PAO, XQ_HZ_BING
    };
    static const uint8_t black_labels[8] = {
        XQ_HZ_JIANG, XQ_HZ_JIANG, XQ_HZ_SHI_BLACK, XQ_HZ_XIANG,
        XQ_HZ_MA, XQ_HZ_JU, XQ_HZ_PAO, XQ_HZ_ZU
    };
    unsigned int type = piece & 7u;
    return (xq_hanzi_t)((piece & SIDE_BLACK) ?
                        black_labels[type] : red_labels[type]);
}

static void draw_position(volatile uint16_t *fb,
                          const xq_search_board_t *board,
                          int selected_from, int selected_to)
{
    int square;
    if ((unsigned int)selected_from < 90u &&
        board->squares[selected_from] == 0u) {
        int file = selected_from % 9;
        int screen_rank = 9 - selected_from / 9;
        int x = BOARD_X + file * CELL;
        int y = BOARD_Y + screen_rank * CELL;
        if (rect_visible(x - 32, y - 32, 65, 65))
            draw_ring(fb, x, y, 31, 4, C_GOLD);
    }
    for (square = 0; square < 90; ++square) {
        uint8_t piece = board->squares[square];
        int file;
        int screen_rank;
        if (piece == 0u)
            continue;
        file = square % 9;
        screen_rank = 9 - square / 9;
        draw_piece(fb, file, screen_rank, piece_label(piece),
                   (piece & SIDE_BLACK) ? C_BLACK : C_RED,
                   square == selected_from || square == selected_to);
    }
}

static const uint8_t text_chinese_chess[] = {
    XQ_HZ_ZHONG, XQ_HZ_GUO, XQ_HZ_XIANG, XQ_HZ_QI
};
static const uint8_t text_red_turn[] = {
    XQ_HZ_HONG, XQ_HZ_FANG, XQ_HZ_XING, XQ_HZ_QI
};
static const uint8_t text_black_turn[] = {
    XQ_HZ_HEI, XQ_HZ_FANG, XQ_HZ_XING, XQ_HZ_QI
};
static const uint8_t text_score[] = {XQ_HZ_PING, XQ_HZ_FEN};
static const uint8_t text_red_win_rate[] = {
    XQ_HZ_HONG, XQ_HZ_FANG, XQ_HZ_SHENG, XQ_HZ_LV
};
static const uint8_t text_nodes[] = {XQ_HZ_JIE_NODE, XQ_HZ_DIAN};
static const uint8_t text_inference_time[] = {
    XQ_HZ_TUI, XQ_HZ_LI, XQ_HZ_YONG, XQ_HZ_SHI_TIME
};
static const uint8_t text_microseconds[] = {XQ_HZ_WEI, XQ_HZ_MIAO};
static const uint8_t text_milliseconds[] = {XQ_HZ_HAO, XQ_HZ_MIAO};
static const uint8_t text_status[] = {XQ_HZ_ZHUANG, XQ_HZ_TAI};
static const uint8_t text_restart[] = {
    XQ_HZ_CHONG, XQ_HZ_XIN, XQ_HZ_KAI, XQ_HZ_SHI_BEGIN
};

static const uint8_t state_ready[] = {
    XQ_HZ_ZHUN, XQ_HZ_BEI, XQ_HZ_JIU, XQ_HZ_XU
};
static const uint8_t state_selected[] = {
    XQ_HZ_YI, XQ_HZ_XUAN, XQ_HZ_QI, XQ_HZ_ZI
};
static const uint8_t state_reselected[] = {
    XQ_HZ_CHONG, XQ_HZ_XIN, XQ_HZ_XUAN, XQ_HZ_ZE
};
static const uint8_t state_cancelled[] = {
    XQ_HZ_YI, XQ_HZ_QU, XQ_HZ_XIAO
};
static const uint8_t state_illegal[] = {
    XQ_HZ_FEI, XQ_HZ_FA, XQ_HZ_ZOU, XQ_HZ_FA
};
static const uint8_t state_select_own[] = {
    XQ_HZ_QING, XQ_HZ_XUAN, XQ_HZ_HONG,
    XQ_HZ_FANG, XQ_HZ_QI, XQ_HZ_ZI
};
static const uint8_t state_mouse_move[] = {
    XQ_HZ_HONG, XQ_HZ_FANG, XQ_HZ_LUO, XQ_HZ_ZI
};
static const uint8_t state_eval_error[] = {
    XQ_HZ_PING, XQ_HZ_GU, XQ_HZ_CUO, XQ_HZ_WU_ERROR
};
static const uint8_t state_black_think[] = {
    XQ_HZ_HEI, XQ_HZ_FANG, XQ_HZ_SI, XQ_HZ_KAO
};
static const uint8_t state_search_error[] = {
    XQ_HZ_SOU, XQ_HZ_SUO, XQ_HZ_CUO, XQ_HZ_WU_ERROR
};
static const uint8_t state_red_wins[] = {
    XQ_HZ_HONG, XQ_HZ_FANG, XQ_HZ_SHENG, XQ_HZ_LI_WIN
};
static const uint8_t state_black_move[] = {
    XQ_HZ_HEI, XQ_HZ_FANG, XQ_HZ_LUO, XQ_HZ_ZI
};
static const uint8_t state_evaluated[] = {
    XQ_HZ_PING, XQ_HZ_GU, XQ_HZ_WAN, XQ_HZ_CHENG
};
static const uint8_t state_no_move[] = {
    XQ_HZ_WU_NONE, XQ_HZ_FA, XQ_HZ_ZHAO
};
static const uint8_t state_best_move[] = {
    XQ_HZ_ZUI, XQ_HZ_JIA, XQ_HZ_ZHAO, XQ_HZ_FA
};
static const uint8_t state_restarted[] = {
    XQ_HZ_YI, XQ_HZ_CHONG, XQ_HZ_XIN, XQ_HZ_KAI, XQ_HZ_SHI_BEGIN
};

static void draw_state(volatile uint16_t *fb, int x, int y,
                       xq_fb_state_t state, uint16_t colour)
{
    const uint8_t *text = state_ready;
    uint32_t count = ARRAY_COUNT(state_ready);
    switch (state) {
    case XQ_FB_STATE_SELECTED:
        text = state_selected;
        count = ARRAY_COUNT(state_selected);
        break;
    case XQ_FB_STATE_RESELECTED:
        text = state_reselected;
        count = ARRAY_COUNT(state_reselected);
        break;
    case XQ_FB_STATE_CANCELLED:
        text = state_cancelled;
        count = ARRAY_COUNT(state_cancelled);
        break;
    case XQ_FB_STATE_ILLEGAL:
        text = state_illegal;
        count = ARRAY_COUNT(state_illegal);
        break;
    case XQ_FB_STATE_SELECT_OWN:
        text = state_select_own;
        count = ARRAY_COUNT(state_select_own);
        break;
    case XQ_FB_STATE_MOUSE_MOVE:
        text = state_mouse_move;
        count = ARRAY_COUNT(state_mouse_move);
        break;
    case XQ_FB_STATE_EVAL_ERROR:
        text = state_eval_error;
        count = ARRAY_COUNT(state_eval_error);
        break;
    case XQ_FB_STATE_BLACK_THINK:
        text = state_black_think;
        count = ARRAY_COUNT(state_black_think);
        break;
    case XQ_FB_STATE_SEARCH_ERROR:
        text = state_search_error;
        count = ARRAY_COUNT(state_search_error);
        break;
    case XQ_FB_STATE_RED_WINS:
        text = state_red_wins;
        count = ARRAY_COUNT(state_red_wins);
        break;
    case XQ_FB_STATE_BLACK_MOVE:
        text = state_black_move;
        count = ARRAY_COUNT(state_black_move);
        break;
    case XQ_FB_STATE_EVALUATED:
        text = state_evaluated;
        count = ARRAY_COUNT(state_evaluated);
        break;
    case XQ_FB_STATE_NO_MOVE:
        text = state_no_move;
        count = ARRAY_COUNT(state_no_move);
        break;
    case XQ_FB_STATE_BEST_MOVE:
        text = state_best_move;
        count = ARRAY_COUNT(state_best_move);
        break;
    case XQ_FB_STATE_RESTARTED:
        text = state_restarted;
        count = ARRAY_COUNT(state_restarted);
        break;
    case XQ_FB_STATE_READY:
    default:
        break;
    }
    draw_hanzi_text(fb, x, y, text, count, 2, colour);
}

static void draw_inference_time(volatile uint16_t *fb, int x, int y,
                                uint32_t inference_ticks)
{
    const uint8_t *unit;
    uint32_t unit_count;
    uint32_t value;
    if (inference_ticks == XQ_FB_TIME_UNAVAILABLE) {
        draw_text(fb, x, y + 5, "--", 3, C_GOLD);
        return;
    }
    if (inference_ticks < CLINT_TICKS_PER_US * 1000u) {
        value = (inference_ticks + CLINT_TICKS_PER_US / 2u) /
                CLINT_TICKS_PER_US;
        unit = text_microseconds;
        unit_count = ARRAY_COUNT(text_microseconds);
    } else {
        value = (inference_ticks +
                 (CLINT_TICKS_PER_US * 1000u) / 2u) /
                (CLINT_TICKS_PER_US * 1000u);
        unit = text_milliseconds;
        unit_count = ARRAY_COUNT(text_milliseconds);
    }
    draw_uint(fb, x, y + 5, value, 3, C_GOLD);
    draw_hanzi_text(fb, x + 150, y, unit, unit_count, 2, C_WHITE);
}

static void draw_panel_turn(volatile uint16_t *fb,
                            const xq_search_board_t *board)
{
    fill_rect(fb, 720, 148, 470, 50, C_BG);
    draw_hanzi_text(fb, 744, 158,
                    board->side ? text_black_turn : text_red_turn,
                    board->side ? ARRAY_COUNT(text_black_turn) :
                                  ARRAY_COUNT(text_red_turn),
                    2, board->side ? C_WHITE : C_RED);
}

static void draw_panel_score(volatile uint16_t *fb, int32_t score,
                             int use_win_rate, uint32_t win_rate_permille)
{
    fill_rect(fb, 720, 210, 470, 54, C_BG);
    if (use_win_rate) {
        draw_hanzi_text(fb, 744, 220, text_red_win_rate,
                        ARRAY_COUNT(text_red_win_rate), 2, C_WHITE);
        draw_permille_percent(fb, 910, 225, win_rate_permille, 3, C_GOLD);
    } else {
        draw_hanzi_text(fb, 744, 220, text_score, ARRAY_COUNT(text_score),
                        2, C_WHITE);
        draw_int(fb, 870, 225, score, 3, C_GOLD);
    }
}

static void draw_panel_nodes(volatile uint16_t *fb, uint32_t nodes)
{
    fill_rect(fb, 720, 270, 470, 54, C_BG);
    draw_hanzi_text(fb, 744, 278, text_nodes, ARRAY_COUNT(text_nodes),
                    2, C_WHITE);
    draw_uint(fb, 870, 283, nodes, 3, C_GOLD);
}

static void draw_panel_time_value(volatile uint16_t *fb,
                                  uint32_t inference_ticks)
{
    fill_rect(fb, 720, 374, 470, 54, C_BG);
    draw_inference_time(fb, 744, 382, inference_ticks);
}

static void draw_panel_status(volatile uint16_t *fb,
                              const xq_search_board_t *board,
                              xq_fb_state_t state)
{
    fill_rect(fb, 720, 452, 470, 135, C_BG);
    draw_hanzi_text(fb, 744, 466, text_status, ARRAY_COUNT(text_status),
                    2, C_WHITE);
    draw_disc(fb, 774, 544, 20, board->side ? C_BLACK : C_RED);
    draw_ring(fb, 774, 544, 20, 3, C_GOLD);
    draw_state(fb, 820, 528, state, C_GOLD);
}

#ifdef XQ_PICTURE_INPUT
static void draw_picture_line(volatile uint16_t *fb,const char *text,int y,unsigned rows)
{
    const unsigned char *p=(const unsigned char *)text;
    unsigned row_index=0;
    int x=736;
    while (*p) {
        unsigned code=*p++,i;
        int advance=12,width=10;
        if (code>=128) {
            if ((code&0xf0u)!=0xe0u || !p[0] || !p[1]) break;
            code=((code&15u)<<12)|((p[0]&63u)<<6)|(p[1]&63u);
            p+=2; advance=34; width=32;
        }
        if (x+width>1170) {
            if (++row_index>=rows) break;
            x=736; y+=34;
        }
        if (code<128) {
            if (code>='a' && code<='z') code-='a'-'A';
            draw_char(fb,x,y,(char)code,2,C_GOLD);
        } else {
            for (i=0;i<ARRAY_COUNT(xqp_glyphs);++i) if (xqp_glyphs[i].code==code) {
                int row,col;
                for (row=0;row<16;++row) for (col=0;col<16;++col)
                    if (xqp_glyphs[i].rows[row]&(1u<<(15-col)))
                        fill_rect(fb,x+2*col,y+2*row,2,2,C_GOLD);
                break;
            }
        }
        x+=advance;
    }
}

static void draw_picture_feedback(volatile uint16_t *fb)
{
    if (!picture_generation) return;
    fill_rect(fb,720,452,470,142,C_BG);
    /* Main action may wrap to two rows; preserve separate guidance and the
     * backend disclosure below it. No glyph can overrun the right panel. */
    draw_picture_line(fb,picture_lines[0],458,2);
    draw_picture_line(fb,picture_lines[1],526,1);
    draw_picture_line(fb,picture_lines[2],560,1);
}

static void draw_diagnostic_scene(volatile uint16_t *fb)
{
    unsigned x,y,i;
    char line[96];
    const xqp_metrics *m=&diagnostic_metrics;
    reset_clip();
    fill_rect(fb,0,0,VIDEO_FB_WIDTH,VIDEO_FB_HEIGHT,C_BG);
    draw_text(fb,32,32,m->model_backend?"CAMERA DIAGNOSTICS  R BACK  SPACE PHOTO":"CAMERA DIAGNOSTICS  R BACK  SPACE PHOTO  C CALIBRATE",2,C_GOLD);
    if (m->has_frame) {
        /* Nearest-neighbor preview: two pixels per aligned uncached store. */
        volatile uint32_t *words=(volatile uint32_t *)fb;
        if(picture_rectified && !m->calibrating) {
            for(y=0;y<360;y++)for(x=0;x<320;x+=2)
                words[((XQP_IMAGE_Y+y)*VIDEO_FB_WIDTH+XQP_IMAGE_X+160+x)/2]=picture_rectified[(y*320+x)/2];
            for(i=0;i<9;i++)fill_rect(fb,XQP_IMAGE_X+160+i*319/8,XQP_IMAGE_Y,1,360,C_GREEN);
            for(i=0;i<10;i++)fill_rect(fb,XQP_IMAGE_X+160,XQP_IMAGE_Y+i*359/9,320,1,C_GREEN);
        } else for (y=0; y<XQP_IMAGE_H; ++y) for (x=0; x<XQP_IMAGE_W; x+=2) {
            uint32_t lo=diagnostic_pixels[(2*y*XQV_WIDTH+2*x)/2]&65535u;
            uint32_t hi=diagnostic_pixels[(2*y*XQV_WIDTH+2*x+2)/2]&65535u;
            words[((XQP_IMAGE_Y+y)*VIDEO_FB_WIDTH+XQP_IMAGE_X+x)/2]=lo|(hi<<16);
        }
        for (i=0; i<diagnostic_result->piece_count && i<32; ++i) {
            const xqg_detection *d=&diagnostic_boxes[i];
            int bx=XQP_IMAGE_X+d->x0/2, by=XQP_IMAGE_Y+d->y0/2;
            int bw=(d->x1-d->x0)/2, bh=(d->y1-d->y0)/2;
            uint16_t color=i==m->selected?C_RED:C_GREEN;
            fill_rect(fb,bx,by,bw,2,color); fill_rect(fb,bx,by+bh,bw,2,color);
            fill_rect(fb,bx,by,2,bh,color); fill_rect(fb,bx+bw,by,2,bh+2,color);
            draw_uint(fb,bx,by-14,d->confidence,1,C_GOLD);
        }
    } else draw_text(fb,48,180,"SPACE TO CAPTURE A FROZEN FRAME",2,C_WHITE);
    if(m->preview_only)draw_text(fb,32,472,m->manual_geometry?"NO MODEL / MANUAL GEOMETRY":"NO MODEL / GEOMETRY NOT SET",2,C_GOLD);
    else if (m->is_stub) draw_text(fb,32,472,"STUB: SYNTHETIC BOXES / SCORES / GEOMETRY",2,C_RED);
    else if(m->model_backend)draw_text(fb,32,472,m->model_backend==1?"PC ASSISTED / EXPERIMENTAL / M0 FAILED":"RV32 DRIVER / EXPERIMENTAL / M0 FAILED",2,C_GOLD);
    snprintf(line,sizeof(line),"END TO END %llu MS",(unsigned long long)m->total_ms);
    draw_text(fb,736,96,line,2,C_GOLD);
    snprintf(line,sizeof(line),"CAPTURE %llu MS",(unsigned long long)m->capture_ms);
    draw_text(fb,736,128,line,2,C_WHITE);
    snprintf(line,sizeof(line),"INFER %llu MS  MAP %llu MS",
             (unsigned long long)m->inference_ms,(unsigned long long)m->mapping_ms);
    draw_text(fb,736,150,line,2,C_WHITE);
    if(m->model_backend)snprintf(line,sizeof(line),"PIECE MIN SCORE: UNCALIBRATED");
    else if(m->preview_only)snprintf(line,sizeof(line),"BOARD CONFIDENCE N/A: NO MODEL");
    else snprintf(line,sizeof(line),"BOARD CONFIDENCE %u / 1000",m->has_frame?diagnostic_result->confidence:0);
    draw_text(fb,736,180,line,2,C_GOLD);
    if (m->has_frame && m->selected<diagnostic_result->piece_count) {
        const xqv_piece *p=&diagnostic_result->pieces[m->selected];
        snprintf(line,sizeof(line),"PIECE %u CLASS %u CONF %u",m->selected,p->class_id,p->confidence);
        draw_text(fb,736,212,line,2,C_WHITE);
    }
    draw_text(fb,736,258,m->model_backend?"DETECT640 BOARD192 CLASS32":m->preview_only?"ROI640 + RGB32: NO MODEL":m->is_stub?"YOLOV5N W8A8: PENDING":"YOLOV5N W8A8: BOARD MAC",2,C_GOLD);
    if (m->parameters) snprintf(line,sizeof(line),"PARAMETERS %u",m->parameters);
    else snprintf(line,sizeof(line),m->model_backend?"FROZEN R2 / S8 + LUT / HOST FP32":"PARAMETERS: TRAINING PACKAGE PENDING");
    draw_text(fb,736,294,line,2,C_WHITE);
    draw_text(fb,736,318,"V2.1 BASELINE: 5.280149 COREMARK/MHZ",2,C_WHITE);
    draw_text(fb,736,340,"0.007297 COREMARK/LUT  42979 LUT",2,C_WHITE);
    snprintf(line,sizeof(line),"EXACT MATCH %u / %u",m->matches,m->comparisons);
    draw_text(fb,736,380,line,2,C_GOLD);
    if (m->comparisons) snprintf(line,sizeof(line),"ACCURACY %u.%u PERCENT",
        (unsigned)((uint64_t)m->matches*1000/m->comparisons/10),
        (unsigned)((uint64_t)m->matches*1000/m->comparisons%10));
    else snprintf(line,sizeof(line),"ACCURACY N/A: NO KNOWN REFERENCE");
    draw_text(fb,736,410,line,2,C_WHITE);
    snprintf(line,sizeof(line),"UNC %u UNSCORED %u BAD %u",m->uncertain,m->unscored,m->invalid);
    draw_text(fb,736,432,line,2,C_WHITE);
    draw_picture_feedback(fb);
    if(!m->model_backend) {
        fill_rect(fb,XQP_CAL_X,XQP_CAL_Y,XQP_CAL_W,XQP_CAL_H,C_PANEL);
        draw_text(fb,XQP_CAL_X+12,XQP_CAL_Y+16,"C CALIBRATE",2,C_GREEN);
    }
    if (m->calibrating) {
        snprintf(line,sizeof(line),"CORNERS A0 I0 I9 A9: %u / 4",m->corner_count);
        draw_text(fb,32,516,line,2,C_GOLD);
    }
}
#endif

static char voice_feedback[18] = "VOICE OFFLINE";
static uint32_t voice_feedback_generation;
static int voice_display_active;
static xqvoice_command_t voice_display;
static xqvoice_display_state_t voice_text_state;

static void draw_voice_extra(volatile uint16_t *fb, int x, int y,
                              unsigned int glyph_index, uint16_t colour)
{
    int row, col;
    if (glyph_index >= 14)
        return;
    for (row = 0; row < 16; ++row)
        for (col = 0; col < 16; ++col)
            if (xqvoice_font16[glyph_index][row] & (1u << (15 - col)))
                fill_rect(fb, x + col * 2, y + row * 2, 2, 2, colour);
}

static int draw_voice_token(volatile uint16_t *fb, int x, uint8_t token,
                              uint16_t colour)
{
    static const uint8_t pieces[9] = {
        XQ_HZ_JU, XQ_HZ_MA, XQ_HZ_PAO, XQ_HZ_BING, XQ_HZ_ZU,
        XQ_HZ_SHUAI, XQ_HZ_JIANG, XQ_HZ_SHI_BLACK, XQ_HZ_XIANG
    };
    if (token >= 1 && token <= 9)
        draw_hanzi(fb, x, 608, (xq_hanzi_t)pieces[token - 1], 2, colour);
    else if (token >= 10 && token <= 21)
        draw_voice_extra(fb, x, 608, token - 10, colour);
    else if (token == 22) {
        draw_hanzi(fb, x, 608, XQ_HZ_CHONG, 2, colour);
        draw_voice_extra(fb, x + 34, 608, 12, colour);
    } else if (token == 23) {
        draw_hanzi(fb, x, 608, XQ_HZ_QU, 2, colour);
        draw_hanzi(fb, x + 34, 608, XQ_HZ_XIAO, 2, colour);
    } else if (token == 24) {
        draw_voice_extra(fb, x, 608, 10, colour);
        draw_voice_extra(fb, x + 34, 608, 13, colour);
    }
    return token >= 22 ? 68 : 34;
}

static void draw_voice_feedback(volatile uint16_t *fb)
{
    fill_rect(fb, 720, 594, 245, 48, C_BG);
    if (voice_display_active) {
        unsigned int index;
        int x = 732;
        uint16_t colour = voice_text_state ==
                            XQVOICE_DISPLAY_LOW_CONFIDENCE ||
                          voice_text_state == XQVOICE_DISPLAY_REJECTED ||
                          voice_display.display_state == XQVOICE_DISPLAY_OVERFLOW ||
                          voice_display.display_state == XQVOICE_DISPLAY_ERROR ?
                          C_GOLD : C_GREEN;
        const char *state = xqvoice_display_state_name(voice_display.display_state);
        char score[5];
        unsigned int value = voice_display.confidence_permille;
        draw_text(fb, 732, 597, state, 1, colour);
        draw_text(fb, 858, 597, "DISPLAY ONLY", 1, C_WHITE);
        for (index = 0; index < voice_display.token_count && x <= 850; ++index)
            x += draw_voice_token(fb, x, voice_display.tokens[index], colour);
        score[0] = (char)('0' + value / 1000);
        score[1] = (char)('0' + (value / 100) % 10);
        score[2] = (char)('0' + (value / 10) % 10);
        score[3] = (char)('0' + value % 10);
        score[4] = '\0';
        draw_text(fb, 900, 617, score, 2, colour);
    } else {
        draw_text(fb, 744, 610, voice_feedback, 2, C_GREEN);
    }
}

static void draw_restart_button(volatile uint16_t *fb)
{
    fill_rect(fb, XQ_FB_RESTART_X, XQ_FB_RESTART_Y,
              XQ_FB_RESTART_W, XQ_FB_RESTART_H, C_GREEN);
    fill_rect(fb, XQ_FB_RESTART_X + 3, XQ_FB_RESTART_Y + 3,
              XQ_FB_RESTART_W - 6, XQ_FB_RESTART_H - 6, C_PANEL);
    draw_hanzi_text(fb, XQ_FB_RESTART_X + 34, XQ_FB_RESTART_Y + 8,
                    text_restart, ARRAY_COUNT(text_restart), 2, C_GOLD);
}

static void draw_panel(volatile uint16_t *fb,
                       const xq_search_board_t *board,
                       int32_t score, uint32_t nodes,
                       uint32_t inference_ticks, xq_fb_state_t state)
{
    fill_rect(fb, 690, 35, 540, 650, C_PANEL);
    fill_rect(fb, 704, 49, 512, 622, C_BG);
    draw_text(fb, 744, 82, "FPGA", 3, C_GOLD);
    draw_hanzi_text(fb, 840, 76, text_chinese_chess,
                    ARRAY_COUNT(text_chinese_chess), 2, C_GOLD);
    hline(fb, 744, 1170, 130, 3, C_GREEN);
    draw_panel_turn(fb, board);
    draw_panel_score(fb, score, show_red_win_rate, red_win_rate_permille);
    draw_panel_nodes(fb, nodes);
    draw_hanzi_text(fb, 744, 340, text_inference_time,
                    ARRAY_COUNT(text_inference_time), 2, C_WHITE);
    draw_panel_time_value(fb, inference_ticks);
    hline(fb, 744, 1170, 440, 2, C_GREEN);
    draw_panel_status(fb, board, state);
#ifdef XQ_PICTURE_INPUT
    draw_picture_feedback(fb);
#endif
    draw_voice_feedback(fb);
    draw_restart_button(fb);
    draw_text(fb, 744, 649, "DDR RGB565  DMA  720P60", 2, C_GREEN);
}

static void draw_scene(volatile uint16_t *fb,
                       const xq_search_board_t *board,
                       int selected_from, int selected_to,
                       int32_t score, uint32_t nodes,
                       uint32_t inference_ticks, xq_fb_state_t state)
{
    reset_clip();
    fill_screen(fb, C_BG);
    draw_board(fb);
    draw_position(fb, board, selected_from, selected_to);
    draw_panel(fb, board, score, nodes, inference_ticks, state);
}

typedef struct {
    xq_search_board_t board;
    int selected_from;
    int selected_to;
    int32_t score;
    int show_red_win_rate;
    uint32_t red_win_rate_permille;
    uint32_t nodes;
    uint32_t inference_ticks;
    xq_fb_state_t state;
    uint32_t voice_feedback_generation;
} xq_fb_scene_t;

static xq_fb_scene_t displayed_scene;

static void save_scene(const xq_search_board_t *board,
                       int selected_from, int selected_to,
                       int32_t score, uint32_t nodes,
                       uint32_t inference_ticks, xq_fb_state_t state)
{
    int square;
    for (square = 0; square < 90; ++square)
        displayed_scene.board.squares[square] = board->squares[square];
    displayed_scene.board.side = board->side;
    displayed_scene.selected_from = selected_from;
    displayed_scene.selected_to = selected_to;
    displayed_scene.score = score;
    displayed_scene.show_red_win_rate = show_red_win_rate;
    displayed_scene.red_win_rate_permille = red_win_rate_permille;
    displayed_scene.nodes = nodes;
    displayed_scene.inference_ticks = inference_ticks;
    displayed_scene.state = state;
    displayed_scene.voice_feedback_generation = voice_feedback_generation;
#ifdef XQ_PICTURE_INPUT
    displayed_picture_generation = picture_generation;
#endif
}

static void mark_dirty_square(uint8_t dirty[90], int square)
{
    if ((unsigned int)square < 90u)
        dirty[square] = 1u;
}

static void redraw_square(volatile uint16_t *fb,
                          const xq_search_board_t *board,
                          int selected_from, int selected_to, int square)
{
    int x = BOARD_X + (square % 9) * CELL;
    int y = BOARD_Y + (9 - square / 9) * CELL;
    set_clip(x - 33, y - 33, 67, 67);
    draw_board(fb);
    draw_position(fb, board, selected_from, selected_to);
    reset_clip();
}

static void redraw_dirty_scene(volatile uint16_t *fb,
                               const xq_search_board_t *board,
                               int selected_from, int selected_to,
                               int32_t score, uint32_t nodes,
                               uint32_t inference_ticks,
                               xq_fb_state_t state)
{
    uint8_t dirty[90];
    int square;
    for (square = 0; square < 90; ++square) {
        dirty[square] =
            displayed_scene.board.squares[square] != board->squares[square];
    }
    mark_dirty_square(dirty, displayed_scene.selected_from);
    mark_dirty_square(dirty, displayed_scene.selected_to);
    mark_dirty_square(dirty, selected_from);
    mark_dirty_square(dirty, selected_to);

    for (square = 0; square < 90; ++square) {
        if (dirty[square])
            redraw_square(fb, board, selected_from, selected_to, square);
    }

    if (displayed_scene.board.side != board->side)
        draw_panel_turn(fb, board);
    if (displayed_scene.score != score ||
        displayed_scene.show_red_win_rate != show_red_win_rate ||
        displayed_scene.red_win_rate_permille != red_win_rate_permille)
        draw_panel_score(fb, score, show_red_win_rate,
                         red_win_rate_permille);
    if (displayed_scene.nodes != nodes)
        draw_panel_nodes(fb, nodes);
    if (displayed_scene.inference_ticks != inference_ticks)
        draw_panel_time_value(fb, inference_ticks);
    if (displayed_scene.state != state ||
        displayed_scene.board.side != board->side)
        draw_panel_status(fb, board, state);
    if (displayed_scene.voice_feedback_generation !=
        voice_feedback_generation)
        draw_voice_feedback(fb);
#ifdef XQ_PICTURE_INPUT
    if (picture_generation && (picture_generation != displayed_picture_generation ||
        displayed_scene.state != state || displayed_scene.board.side != board->side))
        draw_picture_feedback(fb);
#endif
}

static int wait_active(unsigned int front, uint32_t timeout)
{
    uint32_t expected = front ? VIDEO_FB_STATUS_FRONT1 : 0u;
    while (timeout--) {
        uint32_t status = video_fb_read(VIDEO_FB_STATUS);
        if ((status & VIDEO_FB_STATUS_ACTIVE) &&
            (status & VIDEO_FB_STATUS_FRONT1) == expected)
            return 1;
    }
    return 0;
}

static int wait_frames(uint32_t count, uint32_t timeout)
{
    uint32_t start = video_fb_read(VIDEO_FB_FRAME_COUNT);
    while (timeout--) {
        if ((uint32_t)(video_fb_read(VIDEO_FB_FRAME_COUNT) - start) >= count)
            return 1;
    }
    return 0;
}

#ifndef XQ_PICTURE_INPUT
static unsigned int current_front;
static int display_started;
#endif

int xq_fb_gui_init(void)
{
    current_front = 0u;
#ifdef XQ_PICTURE_INPUT
    /* Camera overwrote physical pages, not our ordinary-RAM canvas. Retain
     * its scene and repaint only changed squares before restoring all rows. */
    memset(xq_linux_video_dirty_rows,1,VIDEO_FB_HEIGHT);
    picture_needs_scan_ack=1;
#else
    display_started = 0;
#endif
    if (video_fb_read(VIDEO_FB_ID) != FB_ID_VALUE ||
        video_fb_read(VIDEO_FB_FB0_BASE) != VIDEO_FB0_PHYS ||
        video_fb_read(VIDEO_FB_FB1_BASE) != VIDEO_FB1_PHYS)
        return 0;
    video_fb_control(0, 0, 1);
    return 1;
}

void xq_fb_gui_set_red_win_rate(uint32_t permille)
{
    show_red_win_rate = 1;
    red_win_rate_permille = permille;
}

void xq_fb_gui_set_voice_feedback(const char *text)
{
    unsigned int output = 0;

    if (!text)
        text = "VOICE OFFLINE";
    while (*text && output + 1u < sizeof(voice_feedback)) {
        char c = *text++;
        if ((c >= 'a' && c <= 'z'))
            c = (char)(c - 'a' + 'A');
        if ((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') ||
            c == ' ' || c == '-' || c == '.')
            voice_feedback[output++] = c;
    }
    voice_feedback[output] = '\0';
    ++voice_feedback_generation;
}

void xq_fb_gui_set_voice_display(const xqvoice_command_t *event)
{
    uint8_t index;
    if (!event || event->type != XQVOICE_COMMAND_DISPLAY ||
        event->token_count > XQVOICE_DISPLAY_MAX_TOKENS)
        return;
    voice_display.display_state = event->display_state;
    if ((event->token_count &&
         event->display_state != XQVOICE_DISPLAY_CAPTURING) ||
        event->display_state == XQVOICE_DISPLAY_LISTENING) {
        voice_display.token_count = event->token_count;
        voice_display.confidence_permille = event->confidence_permille;
        voice_text_state = event->display_state;
        for (index = 0; index < event->token_count; ++index)
            voice_display.tokens[index] = event->tokens[index];
    }
    voice_display_active = 1;
    ++voice_feedback_generation;
}

void xq_fb_gui_refresh_voice_display(void)
{
    if (!display_started)
        return;
    draw_voice_feedback(video_fb_pixels(current_front));
    video_fb_present(current_front);
    displayed_scene.voice_feedback_generation = voice_feedback_generation;
}

int xq_fb_gui_show(const xq_search_board_t *board,
                   int selected_from, int selected_to,
                   int32_t score, uint32_t nodes,
                   uint32_t inference_ticks, xq_fb_state_t state)
{
    uint32_t status;
    if (board == 0)
        return 0;
#ifdef XQ_PICTURE_INPUT
    if (diagnostic_pixels) {
        draw_diagnostic_scene(video_fb_pixels(current_front));
        video_fb_present(current_front);
        if (!wait_active(current_front,10000000u)) return 0;
    } else
#endif
    if (display_started) {
        /* Linux updates are deliberately small.  Patch the active page in
         * place so a missed page-flip acknowledgement cannot stall input. */
        redraw_dirty_scene(video_fb_pixels(current_front), board,
                           selected_from, selected_to,
                           score, nodes, inference_ticks, state);
        video_fb_present(current_front);
    } else {
        draw_scene(video_fb_pixels(current_front), board,
                   selected_from, selected_to,
                   score, nodes, inference_ticks, state);
        video_fb_present(current_front);
        if (!wait_active(current_front, 10000000u))
            return 0;
        if (!wait_frames(2, 10000000u))
            return 0;
    }
#ifdef XQ_PICTURE_INPUT
    if(picture_needs_scan_ack){
        if(!wait_active(current_front,10000000u))return 0;
        picture_needs_scan_ack=0;
    }
#endif
    status = video_fb_read(VIDEO_FB_STATUS);
    if (status & (VIDEO_FB_STATUS_UNDERFLOW | VIDEO_FB_STATUS_DMA_ERROR))
        return 0;
    display_started = 1;
    save_scene(board, selected_from, selected_to,
               score, nodes, inference_ticks, state);
    return 1;
}

uint32_t xq_fb_gui_status(void)
{
    return video_fb_read(VIDEO_FB_STATUS);
}
