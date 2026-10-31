#define _POSIX_C_SOURCE 200809L

#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "video_fb.h"
#include "xiangqi_fb_gui.h"
#include "xiangqi_mouse_input.h"
#include "xiangqi_search.h"

#define HID_PAGE_PHYS          0x1fe00000u
#define HID_PAGE_BYTES         0x00001000u
#define HID_OFFSET             0x00000400u
#define HID_ID_VALUE           0x43483935u
#define HID_VERSION_MIN        0x0002001fu
#define HID_PRESS_COUNTS_MIN   0x00020020u
#define HID_ID                 0x00u
#define HID_VERSION            0x04u
#define HID_STATUS             0x08u
#define HID_MOUSE_XY           0x0cu
#define HID_MOUSE_FRAME_COUNT  0x1cu
#define HID_MOUSE_PRESS_COUNTS 0x28u
#define VIDEO_MMIO_PAGE_BYTES  0x00001000u

volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];

static volatile uint32_t *hid_regs;
static int hid_has_press_counts;
static volatile sig_atomic_t stop_requested;

static uint32_t read_mouse_press_counts(void)
{
    return hid_has_press_counts ? hid_regs[HID_MOUSE_PRESS_COUNTS >> 2] : 0u;
}

static const uint8_t red_back_rank[9] = {
    PIECE_R, PIECE_N, PIECE_B, PIECE_A, PIECE_K,
    PIECE_A, PIECE_B, PIECE_N, PIECE_R
};

static void on_signal(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

static void reset_board(xq_search_board_t *board)
{
    int file;
    memset(board, 0, sizeof(*board));
    for (file = 0; file < 9; ++file) {
        board->squares[file] = red_back_rank[file];
        board->squares[9 * 9 + file] =
            (uint8_t)(red_back_rank[file] | SIDE_BLACK);
    }
    board->squares[2 * 9 + 1] = PIECE_C;
    board->squares[2 * 9 + 7] = PIECE_C;
    board->squares[7 * 9 + 1] = PIECE_C | SIDE_BLACK;
    board->squares[7 * 9 + 7] = PIECE_C | SIDE_BLACK;
    for (file = 0; file < 9; file += 2) {
        board->squares[3 * 9 + file] = PIECE_P;
        board->squares[6 * 9 + file] = PIECE_P | SIDE_BLACK;
    }
    board->side = 0;
}

static void *map_physical(int fd, uint32_t address, uint32_t bytes)
{
    void *mapping = mmap(NULL, bytes, PROT_READ | PROT_WRITE, MAP_SHARED,
                         fd, (off_t)address);
    return mapping == MAP_FAILED ? NULL : mapping;
}

static int map_hardware(void)
{
    int fd = open("/dev/mem", O_RDWR | O_SYNC);
    uint8_t *hid_page;
    if (fd < 0) {
        perror("xiangqi-input-test: open /dev/mem");
        return 0;
    }
    xq_linux_video_regs = map_physical(fd, VIDEO_FB_REG_BASE,
                                       VIDEO_MMIO_PAGE_BYTES);
    xq_linux_framebuffers[0] = map_physical(fd, VIDEO_FB0_CPU_UNCACHED,
                                            VIDEO_FB_SLOT_BYTES);
    xq_linux_framebuffers[1] = map_physical(fd, VIDEO_FB1_CPU_UNCACHED,
                                            VIDEO_FB_SLOT_BYTES);
    hid_page = map_physical(fd, HID_PAGE_PHYS, HID_PAGE_BYTES);
    close(fd);
    if (!xq_linux_video_regs || !xq_linux_framebuffers[0] ||
        !xq_linux_framebuffers[1] || !hid_page) {
        fprintf(stderr, "xiangqi-input-test: physical mmap failed\n");
        return 0;
    }
    hid_regs = (volatile uint32_t *)(void *)(hid_page + HID_OFFSET);
    if (hid_regs[HID_ID >> 2] != HID_ID_VALUE ||
        hid_regs[HID_VERSION >> 2] < HID_VERSION_MIN) {
        fprintf(stderr,
                "xiangqi-input-test: CH9350 ABI mismatch id=%08x version=%08x\n",
                (unsigned int)hid_regs[HID_ID >> 2],
                (unsigned int)hid_regs[HID_VERSION >> 2]);
        return 0;
    }
    hid_has_press_counts = hid_regs[HID_VERSION >> 2] >= HID_PRESS_COUNTS_MIN;
    return xq_fb_gui_init();
}

static int software_input_selftest(void)
{
    xq_search_board_t board;
    xq_mouse_input_t mouse;
    xq_mouse_action_t action;
    reset_board(&board);
    xq_mouse_input_init(&mouse, 0);
    action = xq_mouse_input_update(&mouse, &board, 224, 456,
                                   XQ_MOUSE_BUTTON_LEFT);
    if (action != XQ_MOUSE_ACTION_SELECTED || mouse.selected_square != 29)
        return 0;
    (void)xq_mouse_input_update(&mouse, &board, 224, 456, 0);
    action = xq_mouse_input_update(&mouse, &board, 224, 392,
                                   XQ_MOUSE_BUTTON_LEFT);
    return action == XQ_MOUSE_ACTION_MOVED &&
           board.squares[29] == 0u && board.squares[38] == PIECE_P &&
           board.side == 1;
}

static xq_fb_state_t action_state(xq_mouse_action_t action)
{
    switch (action) {
    case XQ_MOUSE_ACTION_RESELECTED:
        return XQ_FB_STATE_RESELECTED;
    case XQ_MOUSE_ACTION_CANCELLED:
        return XQ_FB_STATE_CANCELLED;
    case XQ_MOUSE_ACTION_MOVED:
        return XQ_FB_STATE_MOUSE_MOVE;
    case XQ_MOUSE_ACTION_ILLEGAL:
        return XQ_FB_STATE_ILLEGAL;
    case XQ_MOUSE_ACTION_SELECT_OWN:
        return XQ_FB_STATE_SELECT_OWN;
    case XQ_MOUSE_ACTION_SELECTED:
    default:
        return XQ_FB_STATE_SELECTED;
    }
}

int main(void)
{
    xq_search_board_t board;
    xq_mouse_input_t mouse;
    uint32_t select_count = 0;
    uint32_t move_count = 0;
    uint32_t poll_count = 0;

    setvbuf(stdout, NULL, _IOLBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    if (!software_input_selftest()) {
        fprintf(stderr, "XQ INPUT TEST SOFTWARE_SELFTEST_FAIL\n");
        return 2;
    }
    puts("XQ INPUT TEST SOFTWARE_SELFTEST_PASS select=c3 move=c3c4");
    if (!map_hardware())
        return 3;

    reset_board(&board);
    xq_mouse_input_init(&mouse, (uint8_t)(hid_regs[HID_STATUS >> 2] & 7u));
    if (!xq_fb_gui_show(&board, -1, -1, 0, 0,
                        XQ_FB_TIME_UNAVAILABLE, XQ_FB_STATE_READY))
        return 4;
    printf("XQ INPUT TEST RAW_READY version=%08x status=%08x xy=%08x "
           "frames=%u press=%08x\n",
           (unsigned int)hid_regs[HID_VERSION >> 2],
           (unsigned int)hid_regs[HID_STATUS >> 2],
           (unsigned int)hid_regs[HID_MOUSE_XY >> 2],
           (unsigned int)hid_regs[HID_MOUSE_FRAME_COUNT >> 2],
           (unsigned int)read_mouse_press_counts());
    puts("XQ INPUT TEST READY raw-level polling; select a piece then click a legal destination");

    while (!stop_requested) {
        uint32_t xy = hid_regs[HID_MOUSE_XY >> 2];
        uint8_t buttons = (uint8_t)(hid_regs[HID_STATUS >> 2] & 7u);
        xq_mouse_action_t action;

        action = xq_mouse_input_update(&mouse, &board,
                                       (int)(xy & 0x7ffu),
                                       (int)((xy >> 11) & 0x3ffu), buttons);
        if (action != XQ_MOUSE_ACTION_NONE) {
            printf("XQ INPUT TEST LEVEL_PRESS press=%08x frames=%u "
                   "buttons=%u x=%u y=%u action=%d\n",
                   (unsigned)read_mouse_press_counts(),
                   (unsigned)hid_regs[HID_MOUSE_FRAME_COUNT >> 2],
                   (unsigned)buttons, (unsigned)(xy & 0x7ffu),
                   (unsigned)((xy >> 11) & 0x3ffu), (int)action);
        }
        if (action == XQ_MOUSE_ACTION_RESTART) {
            reset_board(&board);
            move_count = 0;
            select_count = 0;
            xq_mouse_input_init(
                &mouse, (uint8_t)(hid_regs[HID_STATUS >> 2] & 7u));
            (void)xq_fb_gui_show(&board, -1, -1, 0, 0,
                                 XQ_FB_TIME_UNAVAILABLE,
                                 XQ_FB_STATE_RESTARTED);
            puts("XQ INPUT TEST RESTART");
        } else if (action != XQ_MOUSE_ACTION_NONE) {
            int selected_from = mouse.selected_square;
            int selected_to = mouse.event_to;
            if (action == XQ_MOUSE_ACTION_SELECTED ||
                action == XQ_MOUSE_ACTION_RESELECTED) {
                ++select_count;
                printf("XQ INPUT TEST SELECT_PASS square=%d count=%u\n",
                       mouse.selected_square, (unsigned)select_count);
            }
            if (action == XQ_MOUSE_ACTION_MOVED) {
                ++move_count;
                selected_from = mouse.event_from;
                printf("XQ INPUT TEST MOVE_PASS from=%d to=%d count=%u "
                       "next_side=%s\n", mouse.event_from, mouse.event_to,
                       (unsigned)move_count, board.side ? "black" : "red");
            }
            (void)xq_fb_gui_show(&board, selected_from, selected_to,
                                 0, 0, XQ_FB_TIME_UNAVAILABLE,
                                 action_state(action));
        }
        ++poll_count;
        if ((poll_count & 0x00ffffffu) == 0u) {
            uint32_t heartbeat_xy = hid_regs[HID_MOUSE_XY >> 2];
            printf("XQ INPUT TEST POLL_HEARTBEAT polls=%u selects=%u "
                   "moves=%u frames=%u buttons=%u x=%u y=%u\n",
                   (unsigned)poll_count, (unsigned)select_count,
                   (unsigned)move_count,
                   (unsigned)hid_regs[HID_MOUSE_FRAME_COUNT >> 2],
                   (unsigned)(hid_regs[HID_STATUS >> 2] & 7u),
                   (unsigned)(heartbeat_xy & 0x7ffu),
                   (unsigned)((heartbeat_xy >> 11) & 0x3ffu));
        }
    }
    video_fb_control(0, 0, 0);
    puts("XQ INPUT TEST STOPPED");
    return 0;
}
