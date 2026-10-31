#include <stdint.h>
#include "video_fb.h"

#define UART_DATA (*(volatile uint32_t *)(uintptr_t)0x1fe001e0u)
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

#define BOARD_X 96
#define BOARD_Y 72
#define CELL    64

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

static void uart_putc(char c)
{
    if (c == '\n')
        UART_DATA = '\r';
    UART_DATA = (uint8_t)c;
}

static void uart_puts(const char *text)
{
    while (*text)
        uart_putc(*text++);
}

static void uart_hex(uint32_t value)
{
    static const char digits[] = "0123456789abcdef";
    int shift;
    uart_puts("0x");
    for (shift = 28; shift >= 0; shift -= 4)
        uart_putc(digits[(value >> shift) & 15u]);
}

static void put_pixel(volatile uint16_t *fb, int x, int y, uint16_t colour)
{
    if ((unsigned int)x < VIDEO_FB_WIDTH &&
        (unsigned int)y < VIDEO_FB_HEIGHT)
        fb[(unsigned int)y * VIDEO_FB_WIDTH + (unsigned int)x] = colour;
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
    int xx, yy;
    for (yy = y; yy < y + h; ++yy)
        for (xx = x; xx < x + w; ++xx)
            put_pixel(fb, xx, yy, colour);
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

static void draw_piece(volatile uint16_t *fb, int file, int rank, char label,
                       uint16_t ink, int selected)
{
    int x = BOARD_X + file * CELL;
    int y = BOARD_Y + rank * CELL;
    if (selected)
        draw_ring(fb, x, y, 31, 4, C_GOLD);
    draw_disc(fb, x, y, 25, C_PIECE);
    draw_ring(fb, x, y, 25, 3, ink);
    draw_char(fb, x - 10, y - 14, label, 4, ink);
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
    draw_text(fb, 154, 350, "CHU RIVER", 3, C_RED);
    draw_text(fb, 416, 350, "HAN", 3, C_BLACK);
}

static void draw_position(volatile uint16_t *fb, int selected_file)
{
    static const char back_rank[9] = {'R','N','B','A','K','A','B','N','R'};
    int file;
    for (file = 0; file < 9; ++file) {
        draw_piece(fb, file, 0, back_rank[file], C_BLACK, 0);
        draw_piece(fb, file, 9, back_rank[file], C_RED,
                   file == selected_file);
    }
    draw_piece(fb, 1, 2, 'C', C_BLACK, 0);
    draw_piece(fb, 7, 2, 'C', C_BLACK, 0);
    draw_piece(fb, 1, 7, 'C', C_RED, 0);
    draw_piece(fb, 7, 7, 'C', C_RED, 0);
    for (file = 0; file < 9; file += 2) {
        draw_piece(fb, file, 3, 'P', C_BLACK, 0);
        draw_piece(fb, file, 6, 'P', C_RED, 0);
    }
}

static void draw_panel(volatile uint16_t *fb)
{
    fill_rect(fb, 690, 35, 540, 650, C_PANEL);
    fill_rect(fb, 704, 49, 512, 622, C_BG);
    draw_text(fb, 744, 82, "FPGA XIANGQI", 4, C_GOLD);
    hline(fb, 744, 1170, 130, 3, C_GREEN);
    draw_text(fb, 744, 174, "DDR RGB565", 3, C_WHITE);
    draw_text(fb, 744, 222, "DMA SCANOUT", 3, C_WHITE);
    draw_text(fb, 744, 270, "720P60", 3, C_WHITE);
    draw_text(fb, 744, 350, "MAC MEMORY SAFE", 3, C_GREEN);
    draw_text(fb, 744, 446, "RED TO MOVE", 4, C_RED);
    draw_disc(fb, 774, 550, 20, C_RED);
    draw_ring(fb, 774, 550, 20, 3, C_GOLD);
    draw_text(fb, 820, 538, "READY", 3, C_GOLD);
}

static void draw_scene(volatile uint16_t *fb, int selected_file)
{
    fill_screen(fb, C_BG);
    draw_board(fb);
    draw_position(fb, selected_file);
    draw_panel(fb);
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

static void wait_frames(uint32_t count)
{
    uint32_t start = video_fb_read(VIDEO_FB_FRAME_COUNT);
    while ((uint32_t)(video_fb_read(VIDEO_FB_FRAME_COUNT) - start) < count)
        ;
}

int main(void)
{
    volatile uint16_t *fb0;
    volatile uint16_t *fb1;
    uint32_t status;
    unsigned int front = 0;

    uart_puts("Xiangqi DDR framebuffer demo starting\n");
    if (video_fb_read(VIDEO_FB_ID) != FB_ID_VALUE) {
        uart_puts("XIANGQI_FB_ID_FAIL\n");
        return 1;
    }

    fb0 = video_fb_pixels(0);
    fb1 = video_fb_pixels(1);
    draw_scene(fb0, 0);
    draw_scene(fb1, 1);
    video_fb_control(1, 0, 1);
    if (!wait_active(0, 10000000u)) {
        uart_puts("XIANGQI_FB_DMA_FAIL timeout\n");
        return 2;
    }
    wait_frames(2);
    status = video_fb_read(VIDEO_FB_STATUS);
    if (status & (VIDEO_FB_STATUS_UNDERFLOW | VIDEO_FB_STATUS_DMA_ERROR)) {
        uart_puts("XIANGQI_FB_DMA_FAIL status=");
        uart_hex(status);
        uart_putc('\n');
        return 3;
    }
    uart_puts("XIANGQI_FB_GUI_READY status=");
    uart_hex(status);
    uart_puts("\nHDMI should show the animated Xiangqi board.\n");

    for (;;) {
        wait_frames(60);
        front ^= 1u;
        video_fb_present(front);
        (void)wait_active(front, 10000000u);
    }
}
