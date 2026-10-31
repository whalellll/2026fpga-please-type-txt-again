/* Native 1080p Linux renderer. RGB565, word-safe uncached stores, dirty updates. */
#include "gui1080_config.h"
#include <stdint.h>
#include "video_fb.h"
#include "xiangqi_fb_gui.h"
#include "xiangqi_font_zh.h"
#include "xiangqi_piece_font_aa.h"
#include "xqvoice_display.h"
#include "xiangqi_ui_font_aa.h"

#define FB_ID_VALUE 0x58514642u

#include "xiangqi_gui_theme.h"

#define BOARD_X XQ_FB_BOARD_X
#define BOARD_Y XQ_FB_BOARD_Y
#define CELL    XQ_FB_CELL

#define ARRAY_COUNT(a) ((uint32_t)(sizeof(a) / sizeof((a)[0])))
#define CLINT_TICKS_PER_US 27u

/* The accelerator owns 0x1b000000..0x1b0fffff and the following MiB is a
 * hard guard band.  Fail the build if a future framebuffer change crosses
 * either that boundary or its fixed 4 MiB slots. */
#define ACCEL_DDR_END 0x1b100000u
#define FB_GUARD_END  0x1b200000u
#define FB_DDR_END    0x1c000000u

#if VIDEO_FB0_PHYS < FB_GUARD_END || VIDEO_FB0_PHYS < ACCEL_DDR_END
#error "Framebuffer 0 overlaps accelerator DDR or its guard band"
#endif
#if (VIDEO_FB0_PHYS + VIDEO_FB_FRAME_BYTES) > VIDEO_FB1_PHYS
#error "Framebuffer 0 image overlaps framebuffer 1"
#endif
#if (VIDEO_FB1_PHYS + VIDEO_FB_FRAME_BYTES) > FB_DDR_END
#error "Framebuffer 1 image exceeds the reserved framebuffer aperture"
#endif

/* Drawing is clipped while a dirty region is rebuilt.  Coordinates use an
 * exclusive right/bottom edge, matching fill_rect width/height semantics. */
static int clip_x0 = 0;
static int clip_y0 = 0;
static int clip_x1 = VIDEO_FB_WIDTH;
static int clip_y1 = VIDEO_FB_HEIGHT;
static int show_red_win_rate;
static uint32_t red_win_rate_permille = XQ_FB_WIN_RATE_UNAVAILABLE;

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

/* Native coverage masks are blended into the existing pixel, including the
 * textured river and gold button. Never issue subword uncached accesses. */
static uint16_t blend_ui_colour(uint16_t colour,uint16_t background,unsigned alpha)
{
    return (uint16_t)(((((colour >> 11) * alpha +
        (background >> 11) * (15u-alpha) + 7u) / 15u) << 11) |
        (((((colour >> 5) & 63u) * alpha +
        ((background >> 5) & 63u) * (15u-alpha) + 7u) / 15u) << 5) |
        (((colour & 31u) * alpha + (background & 31u) * (15u-alpha) + 7u) / 15u));
}

static void draw_ui_glyph(volatile uint16_t *fb, int x, int y,
                          const xq_ui_glyph_t *glyph, uint16_t colour)
{
    unsigned int row, col;
    if (!rect_visible(x, y, glyph->width, glyph->height))
        return;
#ifdef VIDEO_FB_LINUX_MMAP
    /* Compose both RGB565 pixels of a word before touching uncached DDR.
     * Opaque pairs need no read; clipped/transparent neighbors stay intact. */
    for(row=0;row<glyph->height;row++){
        int yy=y+(int)row;
        unsigned begin=x<clip_x0?(unsigned)(clip_x0-x):0;
        unsigned end=glyph->width;
        volatile uint32_t *words=(volatile uint32_t *)(uintptr_t)fb;
        if(yy<clip_y0 || yy>=clip_y1)continue;
        if(x+(int)end>clip_x1)end=(unsigned)(clip_x1-x);
        for(col=begin;col<end;){
            unsigned pixel=(unsigned)yy*VIDEO_FB_WIDTH+(unsigned)(x+(int)col);
            unsigned n=!(pixel&1u) && col+1<end?2:1;
            unsigned packed=xq_ui_alpha4[glyph->offset+(row*glyph->width+col)/2];
            unsigned a0=col&1u?packed&15u:packed>>4,a1=0;
            uint32_t pair;
            if(n==2){
                packed=xq_ui_alpha4[glyph->offset+(row*glyph->width+col+1)/2];
                a1=(col+1)&1u?packed&15u:packed>>4;
            }
            if(!(a0|a1)){col+=n;continue;}
            if(n==2 && a0==15 && a1==15)pair=(uint32_t)colour|((uint32_t)colour<<16);
            else {
                unsigned shift=(pixel&1u)*16;
                pair=words[pixel>>1];
                if(a0){
                    uint16_t value=a0==15?colour:blend_ui_colour(colour,(uint16_t)(pair>>shift),a0);
                    pair=(pair&~(0xffffu<<shift))|((uint32_t)value<<shift);
                }
                if(a1){
                    uint16_t value=a1==15?colour:blend_ui_colour(colour,(uint16_t)(pair>>16),a1);
                    pair=(pair&0xffffu)|((uint32_t)value<<16);
                }
            }
            words[pixel>>1]=pair;
            col+=n;
        }
    }
#else
    for (row = 0; row < glyph->height; ++row) {
        for (col = 0; col < glyph->width; ++col) {
            unsigned int pixel, alpha, packed;
            int xx = x + (int)col, yy = y + (int)row;
            uint16_t background, result;
            if (xx < clip_x0 || xx >= clip_x1 || yy < clip_y0 || yy >= clip_y1)
                continue;
            packed = xq_ui_alpha4[glyph->offset + (row * glyph->width + col) / 2];
            alpha = col & 1u ? packed & 15u : packed >> 4;
            if (!alpha)
                continue;
            if (alpha == 15u) {
                put_pixel(fb, xx, yy, colour);
                continue;
            }
            pixel = (unsigned int)yy * VIDEO_FB_WIDTH + (unsigned int)xx;
#ifdef VIDEO_FB_LINUX_MMAP
            {
                volatile uint32_t *words = (volatile uint32_t *)(uintptr_t)fb;
                uint32_t pair = words[pixel >> 1];
                background = (uint16_t)(pair >> ((pixel & 1u) * 16));
            }
#else
            background = fb[pixel];
#endif
            result = blend_ui_colour(colour,background,alpha);
            put_pixel(fb, xx, yy, result);
        }
    }
#endif
}

static const xq_ui_glyph_t *ascii_glyph(char c, int scale)
{
    const xq_ui_glyph_t *table = scale == 5 ? xq_ui_ascii5 :
        scale == 3 ? xq_ui_ascii3 : scale == 2 ? xq_ui_ascii2 : xq_ui_ascii1;
    return &table[(c >= 32 && c <= 126 ? (unsigned int)c : (unsigned int)'?') - 32u];
}

static void draw_text(volatile uint16_t *fb, int x, int y, const char *text,
                      int scale, uint16_t colour)
{
    while (*text) {
        const xq_ui_glyph_t *glyph = ascii_glyph(*text++, scale);
        draw_ui_glyph(fb, x, y, glyph, colour);
        x += glyph->advance;
    }
}

static void draw_hanzi(volatile uint16_t *fb, int x, int y,
                       xq_hanzi_t glyph_index, int scale, uint16_t colour)
{
    _Static_assert(XQ_HZ_COUNT == XQ_UI_HANZI_COUNT, "UI font enum differs");
    if ((unsigned int)glyph_index < XQ_HZ_COUNT)
        draw_ui_glyph(fb, x, y, scale == 3 ? &xq_ui_zh48[glyph_index] :
                      &xq_ui_zh32[glyph_index], colour);
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
    int y;
    for (y = -radius; y <= radius; ++y) {
        int extent = radius;
        if (cy+y < clip_y0 || cy+y >= clip_y1) continue;
        while (extent*extent + y*y > radius*radius) --extent;
        fill_rect(fb, cx-extent, cy+y, extent*2+1, 1, colour);
    }
}

static void draw_ring(volatile uint16_t *fb, int cx, int cy, int radius,
                      int thickness, uint16_t colour)
{
    int y;
    int outer = radius * radius;
    int inner = (radius - thickness) * (radius - thickness);
    for (y = -radius; y <= radius; ++y) {
        int extent=radius, gap=0;
        if (cy+y < clip_y0 || cy+y >= clip_y1) continue;
        while (extent*extent+y*y > outer) --extent;
        if (y*y >= inner) fill_rect(fb,cx-extent,cy+y,extent*2+1,1,colour);
        else {
            while (gap*gap+y*y < inner) ++gap;
            if (gap<=extent) {
                fill_rect(fb,cx-extent,cy+y,extent-gap+1,1,colour);
                fill_rect(fb,cx+gap,cy+y,extent-gap+1,1,colour);
            }
        }
    }
}


/* Rounded cards use horizontal word stores and respect dirty-region clipping. */
static void rounded_rect(volatile uint16_t *fb, int x, int y, int w, int h,
                         int radius, uint16_t colour)
{
    int row;
    fill_rect(fb, x, y + radius, w, h - 2 * radius, colour);
    for (row = 0; row < radius; ++row) {
        int inset = radius;
        int dy = radius - row - 1;
        while (inset > 0 && (radius - inset) * (radius - inset) + dy * dy <= radius * radius)
            --inset;
        fill_rect(fb, x + inset, y + row, w - 2 * inset, 1, colour);
        fill_rect(fb, x + inset, y + h - row - 1, w - 2 * inset, 1, colour);
    }
}

static void card(volatile uint16_t *fb, int x, int y, int w, int h)
{
    rounded_rect(fb, x, y, w, h, 14, C_BORDER);
    rounded_rect(fb, x + 1, y + 1, w - 2, h - 2, 13, C_CARD);
}

static void draw_piece_label(volatile uint16_t *fb, int x, int y,
                             xq_hanzi_t label, uint16_t ink)
{
    uint16_t shades[16];
    unsigned int alpha, row, col;
    _Static_assert(XQ_HZ_ZU + 1 == XQ_PIECE_GLYPH_COUNT,
                   "Piece font and piece label order must agree");
    if ((unsigned int)label >= XQ_PIECE_GLYPH_COUNT)
        return;
    /* Glyphs are entirely inside the flat ivory face, so fractional edges
     * need no framebuffer reads for blending. put_pixel still uses safe
     * full-word stores on the uncached Linux DDR mapping. */
    for (alpha = 0; alpha < 16; ++alpha) {
        unsigned int r = (((ink >> 11) & 31u) * alpha +
                          ((C_PIECE >> 11) & 31u) * (15u - alpha) + 7u) / 15u;
        unsigned int g = (((ink >> 5) & 63u) * alpha +
                          ((C_PIECE >> 5) & 63u) * (15u - alpha) + 7u) / 15u;
        unsigned int b = ((ink & 31u) * alpha +
                          (C_PIECE & 31u) * (15u - alpha) + 7u) / 15u;
        shades[alpha] = (uint16_t)((r << 11) | (g << 5) | b);
    }
    for (row = 0; row < XQ_PIECE_GLYPH_SIZE; ++row) {
        for (col = 0; col < XQ_PIECE_GLYPH_SIZE; ++col) {
            uint8_t packed = xq_piece_alpha4[label][row * (XQ_PIECE_GLYPH_SIZE / 2) + col / 2];
            alpha = (col & 1u) ? packed & 15u : packed >> 4;
            if (alpha)
                put_pixel(fb, x + (int)col, y + (int)row, shades[alpha]);
        }
    }
}

static void draw_piece(volatile uint16_t *fb, int file, int rank,
                       xq_hanzi_t label, uint16_t ink, int selected)
{
    int x = BOARD_X + file * CELL;
    int y = BOARD_Y + rank * CELL;
    if (!rect_visible(x - 43, y - 43, 87, 87))
        return;
    draw_disc(fb, x + 3, y + 5, 35, 0x8ac9u);
    if (selected) {
        draw_disc(fb, x, y, 42, C_GOLD);
        draw_ring(fb, x, y, 42, 3, C_GREEN);
    }
    draw_disc(fb, x, y, 35, 0xb40du);
    draw_disc(fb, x, y - 2, 33, C_PIECE);
    draw_ring(fb, x, y - 2, 29, 1, ink);
    draw_piece_label(fb, x - 24, y - 26, label, ink);
}

static void draw_board(volatile uint16_t *fb)
{
    int file, rank, row;
    rounded_rect(fb, 106, 100, 852, 930, 22, C_SHADOW);
    rounded_rect(fb, 96, 88, 852, 930, 22, 0x7247u);
    rounded_rect(fb, 108, 100, 828, 906, 14, 0xe6b2u);
    fill_rect(fb, 120, 112, 804, 882, C_BOARD);
    /* Low-contrast grain is deterministic, so full and dirty redraws agree. */
    for (row = 114; row < 994; row += 7) {
        uint16_t shade = row % 21 ? 0xd5cdu : 0xde2fu;
        fill_rect(fb, 120, row, 804, 1, shade);
    }
    for (rank = 0; rank < 10; ++rank)
        hline(fb, BOARD_X, BOARD_X + 8 * CELL, BOARD_Y + rank * CELL, 2, C_LINE);
    for (file = 0; file < 9; ++file) {
        int x = BOARD_X + file * CELL;
        if (file == 0 || file == 8)
            vline(fb, x, BOARD_Y, BOARD_Y + 9 * CELL, 2, C_LINE);
        else {
            vline(fb, x, BOARD_Y, BOARD_Y + 4 * CELL, 2, C_LINE);
            vline(fb, x, BOARD_Y + 5 * CELL, BOARD_Y + 9 * CELL, 2, C_LINE);
        }
    }
    diagonal(fb, BOARD_X + 3 * CELL, BOARD_Y, BOARD_X + 5 * CELL, BOARD_Y + 2 * CELL, C_LINE);
    diagonal(fb, BOARD_X + 5 * CELL, BOARD_Y, BOARD_X + 3 * CELL, BOARD_Y + 2 * CELL, C_LINE);
    diagonal(fb, BOARD_X + 3 * CELL, BOARD_Y + 7 * CELL, BOARD_X + 5 * CELL, BOARD_Y + 9 * CELL, C_LINE);
    diagonal(fb, BOARD_X + 5 * CELL, BOARD_Y + 7 * CELL, BOARD_X + 3 * CELL, BOARD_Y + 9 * CELL, C_LINE);
    {
        static const uint8_t chu_he[] = {XQ_HZ_CHU, XQ_HZ_HE};
        static const uint8_t han_jie[] = {XQ_HZ_HAN, XQ_HZ_JIE_BORDER};
        draw_hanzi_text(fb, 294, 532, chu_he, 2, 3, C_LINE);
        draw_hanzi_text(fb, 690, 532, han_jie, 2, 3, C_LINE);
    }
    for (file = 0; file < 9; ++file) {
        char label[2] = {(char)('A' + file), 0};
        /* Keep coordinates clear of the bottom rank's piece shadows. */
        draw_text(fb, BOARD_X + file * CELL - ascii_glyph(label[0],1)->advance/2,
                  1018, label, 1, C_GOLD);
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
        if (rect_visible(x - 43, y - 43, 87, 87))
            draw_ring(fb, x, y, 42, 3, C_GOLD);
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
    draw_hanzi_text(fb, x + 150, y, unit, unit_count, 2, C_TEXT);
}

static void draw_panel_turn(volatile uint16_t *fb, const xq_search_board_t *board)
{
    card(fb, 1052, 252, 740, 90);
    draw_disc(fb, 1098, 297, 18, board->side ? C_PIECE : C_RED);
    draw_hanzi_text(fb, 1142, 280, board->side ? text_black_turn : text_red_turn, 4, 2, C_TEXT);
    draw_text(fb, 1584, 290, board->side ? "ENGINE" : "YOUR TURN", 2, C_GOLD);
}

static void draw_panel_score(volatile uint16_t *fb, int32_t score,
                             int use_win_rate, uint32_t win_rate_permille)
{
    card(fb, 1052, 366, 740, 120);
    draw_hanzi_text(fb, 1080, 384, use_win_rate ? text_red_win_rate : text_score,
                    use_win_rate ? 4 : 2, 2, C_TEXT);
    if (use_win_rate) {
        uint32_t rate = win_rate_permille > 1000u ? 1000u : win_rate_permille;
        draw_permille_percent(fb, 1440, 389, win_rate_permille, 5, C_GOLD);
        rounded_rect(fb, 1080, 450, 684, 10, 5, C_DIVIDER);
        if (win_rate_permille != XQ_FB_WIN_RATE_UNAVAILABLE && rate > 0)
            fill_rect(fb, 1080, 450, (int)(684u * rate / 1000u), 10, C_RED);
    } else {
        draw_int(fb, 1440, 389, score, 5, C_GOLD);
    }
}

static void draw_panel_nodes(volatile uint16_t *fb, uint32_t nodes)
{
    card(fb, 1052, 510, 356, 112);
    draw_hanzi_text(fb, 1080, 528, text_nodes, 2, 2, C_TEXT);
    draw_uint(fb, 1080, 580, nodes, 3, C_GOLD);
}

static void draw_panel_time_value(volatile uint16_t *fb, uint32_t inference_ticks)
{
    card(fb, 1432, 510, 360, 112);
    draw_hanzi_text(fb, 1460, 528, text_inference_time, 4, 2, C_TEXT);
    draw_inference_time(fb, 1460, 574, inference_ticks);
}

static void draw_panel_status(volatile uint16_t *fb, const xq_search_board_t *board,
                              xq_fb_state_t state)
{
    card(fb, 1052, 646, 740, 100);
    draw_text(fb, 1080, 662, "GAME STATUS", 1, C_GREEN);
    draw_disc(fb, 1094, 709, 7, board->side ? C_GOLD : C_GREEN);
    draw_state(fb, 1124, 691, state, C_TEXT);
    draw_hanzi_text(fb, 1648, 692, text_status, 2, 2, C_GOLD);
}

static char voice_feedback[18] = "VOICE OFFLINE";
static uint32_t voice_feedback_generation;
static int voice_display_active;
static xqvoice_command_t voice_display;
static xqvoice_display_state_t voice_text_state;

static void draw_voice_extra(volatile uint16_t *fb, int x, int y,
                              unsigned int glyph_index, uint16_t colour)
{
    if (glyph_index < 14)
        draw_ui_glyph(fb, x, y, &xq_ui_voice32[glyph_index], colour);
}

static int draw_voice_token(volatile uint16_t *fb, int x, int y, uint8_t token,
                              uint16_t colour)
{
    static const uint8_t pieces[9] = {
        XQ_HZ_JU, XQ_HZ_MA, XQ_HZ_PAO, XQ_HZ_BING, XQ_HZ_ZU,
        XQ_HZ_SHUAI, XQ_HZ_JIANG, XQ_HZ_SHI_BLACK, XQ_HZ_XIANG
    };
    if (token >= 1 && token <= 9)
        draw_hanzi(fb, x, y, (xq_hanzi_t)pieces[token - 1], 2, colour);
    else if (token >= 10 && token <= 21)
        draw_voice_extra(fb, x, y, token - 10, colour);
    else if (token == 22) {
        draw_hanzi(fb, x, y, XQ_HZ_CHONG, 2, colour);
        draw_voice_extra(fb, x + 34, y, 12, colour);
    } else if (token == 23) {
        draw_hanzi(fb, x, y, XQ_HZ_QU, 2, colour);
        draw_hanzi(fb, x + 34, y, XQ_HZ_XIAO, 2, colour);
    } else if (token == 24) {
        draw_voice_extra(fb, x, y, 10, colour);
        draw_voice_extra(fb, x + 34, y, 13, colour);
    }
    return token >= 22 ? 68 : 34;
}

static void draw_voice_feedback(volatile uint16_t *fb)
{
    card(fb, 1052, 770, 740, 112);
    draw_text(fb, 1080, 788, "VOICE CONTROL", 2, C_GREEN);
    if (voice_display_active) {
        unsigned int index;
        int x = 1080;
        uint16_t colour = voice_text_state == XQVOICE_DISPLAY_LOW_CONFIDENCE ||
            voice_text_state == XQVOICE_DISPLAY_REJECTED ||
            voice_display.display_state == XQVOICE_DISPLAY_OVERFLOW ||
            voice_display.display_state == XQVOICE_DISPLAY_ERROR ? C_GOLD : C_TEXT;
        draw_text(fb, 1452, 792, xqvoice_display_state_name(voice_display.display_state), 1, colour);
        draw_text(fb, 1650, 792, "CONFIDENCE", 1, C_GREEN);
        draw_permille_percent(fb, 1650, 820, voice_display.confidence_permille, 2, colour);
        for (index = 0; index < voice_display.token_count && x <= 1530; ++index)
            x += draw_voice_token(fb, x, 830, voice_display.tokens[index], colour);
        draw_text(fb, 1614, 844, "DISPLAY ONLY", 1, C_GREEN);
    } else {
        draw_text(fb, 1080, 837, voice_feedback, 2, C_TEXT);
    }
}

static void draw_restart_button(volatile uint16_t *fb)
{
    rounded_rect(fb, XQ_FB_RESTART_X, XQ_FB_RESTART_Y,
                 XQ_FB_RESTART_W, XQ_FB_RESTART_H, 14, C_GOLD);
    draw_hanzi_text(fb, 1352, XQ_FB_RESTART_Y + 16, text_restart, 4, 2, C_BG);
}

static void draw_panel(volatile uint16_t *fb, const xq_search_board_t *board,
                       int32_t score, uint32_t nodes,
                       uint32_t inference_ticks, xq_fb_state_t state)
{
    rounded_rect(fb, 1016, 88, 812, 930, 22, C_SHADOW);
    rounded_rect(fb, 1012, 84, 812, 930, 22, C_PANEL);
    draw_text(fb, 1052, 114, "PIKAFISH", 2, C_GOLD);
    draw_hanzi_text(fb, 1052, 154, text_chinese_chess, 4, 3, C_TEXT);
    draw_text(fb, 1440, 174, "PLAY WITH INTELLIGENCE", 2, C_GREEN);
    hline(fb, 1052, 1792, 224, 1, C_DIVIDER);
    draw_panel_turn(fb, board);
    draw_panel_score(fb, score, show_red_win_rate, red_win_rate_permille);
    draw_panel_nodes(fb, nodes);
    draw_panel_time_value(fb, inference_ticks);
    draw_panel_status(fb, board, state);
    draw_voice_feedback(fb);
    draw_restart_button(fb);
    draw_text(fb, 1080, 989, "LEFT SELECT   RIGHT CANCEL", 1, C_GREEN);
}

static void draw_scene(volatile uint16_t *fb,
                       const xq_search_board_t *board,
                       int selected_from, int selected_to,
                       int32_t score, uint32_t nodes,
                       uint32_t inference_ticks, xq_fb_state_t state)
{
    reset_clip();
    fill_screen(fb, C_BG);
    draw_text(fb, 96, 38, "XIANGQI", 3, C_TEXT);
    draw_text(fb, 1490, 42, "1920 X 1080   60 HZ", 2, C_GREEN);
    draw_text(fb, 96, 1046, "A QUIET SPACE FOR YOUR NEXT MOVE", 1, C_GOLD);
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
    set_clip(x - 43, y - 43, 87, 87);
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

    if (displayed_scene.board.side != board->side) {
        set_clip(1078,277,698,46);
        draw_panel_turn(fb, board);
        reset_clip();
    }
    if (displayed_scene.score != score ||
        displayed_scene.show_red_win_rate != show_red_win_rate ||
        displayed_scene.red_win_rate_permille != red_win_rate_permille) {
        if (displayed_scene.show_red_win_rate != show_red_win_rate) {
            draw_panel_score(fb, score, show_red_win_rate,red_win_rate_permille);
        } else {
            set_clip(1432,376,360,100);
            draw_panel_score(fb, score, show_red_win_rate,red_win_rate_permille);
            reset_clip();
            if (show_red_win_rate) {
                set_clip(1080,450,684,10);
                draw_panel_score(fb,score,show_red_win_rate,red_win_rate_permille);
                reset_clip();
            }
        }
    }
    if (displayed_scene.nodes != nodes) {
        set_clip(1078,566,316,56);
        draw_panel_nodes(fb, nodes);
        reset_clip();
    }
    if (displayed_scene.inference_ticks != inference_ticks) {
        set_clip(1458,568,322,54);
        draw_panel_time_value(fb, inference_ticks);
        reset_clip();
    }
    if (displayed_scene.state != state ||
        displayed_scene.board.side != board->side) {
        set_clip(1080,685,550,50);
        draw_panel_status(fb, board, state);
        reset_clip();
    }
    if (displayed_scene.voice_feedback_generation !=
        voice_feedback_generation)
        draw_voice_feedback(fb);
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

static unsigned int current_front;
static int display_started;

int xq_fb_gui_init(void)
{
    current_front = 0u;
    display_started = 0;
    if (video_fb_read(VIDEO_FB_ID) != FB_ID_VALUE ||
        video_fb_read(VIDEO_FB_FB0_BASE) != VIDEO_FB0_PHYS ||
        video_fb_read(VIDEO_FB_FB1_BASE) != VIDEO_FB1_PHYS ||
        video_fb_read(VIDEO_FB_SIZE) != ((VIDEO_FB_HEIGHT << 16) | VIDEO_FB_WIDTH) ||
        video_fb_read(VIDEO_FB_STRIDE) != VIDEO_FB_STRIDE_BYTES ||
        video_fb_read(VIDEO_FB_BYTES) != VIDEO_FB_FRAME_BYTES)
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
