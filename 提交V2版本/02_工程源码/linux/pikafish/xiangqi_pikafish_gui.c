#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "video_fb.h"
#include "../vision/picture_video_compat.h"
#ifdef PIKAFISH_DIRECT_CORE
#include "pikafish_embedded.h"
#endif
#include "xiangqi_fb_gui.h"
#include "xiangqi_gui_command.h"
#include "xiangqi_mouse_input.h"
#include "xiangqi_pikafish_link.h"
#include "xiangqi_search.h"
#include "xqvoice_gui_ipc.h"
#include "xqvoice_display.h"

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
#define HID_STATUS_MOUSE_SEEN  (1u << 4)

#define VIDEO_MMIO_PAGE_BYTES  0x00001000u
#define ENGINE_PATH            "/usr/bin/pikafish"
#define ENGINE_DIRECTORY       "/opt/pikafish"
#define ENGINE_MODEL           "pff1-view:0x10000000:68122688"
#define ENGINE_HASH_MIB        8
#define ENGINE_MOVE_TIME_MS    1000
#define ENGINE_UCI_TIMEOUT_MS  1200000u
#define ENGINE_NNUE_TIMEOUT_MS 1200000u
#define GUI_TICKS_PER_MS       27000u
#define GUI_FRAMES_PER_SECOND  60u
#define GUI_IDLE_SLEEP_NS      1000000L
#define GUI_CONTROL_FIFO       "/run/xiangqi-pikafish.in"
#define GUI_CONTROL_LINE_BYTES 96u

volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];
#ifdef XQ_PICTURE_INPUT
uint8_t xq_linux_video_dirty_rows[VIDEO_FB_HEIGHT];
static volatile uint32_t *picture_live_framebuffer;
void xq_linux_video_copy(unsigned int buffer)
{
    const uint32_t *src=(const uint32_t *)(uintptr_t)xq_linux_framebuffers[0];
    (void)buffer;
    video_fb_copy_dirty_rows(picture_live_framebuffer,src,xq_linux_video_dirty_rows);
}
#endif

static volatile uint32_t *hid_regs;
static int hid_has_press_counts;

static uint32_t read_mouse_press_counts(void)
{
    return hid_has_press_counts ? hid_regs[HID_MOUSE_PRESS_COUNTS >> 2] : 0u;
}
#ifndef PIKAFISH_DIRECT_CORE
static FILE *engine_input;
static FILE *engine_output;
static int engine_output_fd = -1;
static pid_t engine_pid = -1;
#endif
static volatile sig_atomic_t stop_requested;
#define XQVOICE_MIN_CONFIDENCE 650u
static xqvoice_gui_ipc_t voice_ipc={.fd=-1};

static int open_control_channel(int *is_stdin)
{
    const char *configured = getenv("XQ_GUI_INPUT");
    const char *path = configured != NULL && configured[0] != '\0' ?
                       configured : GUI_CONTROL_FIFO;
    struct stat info;
    int fd;

    *is_stdin = 0;
    if (strcmp(path, "-") == 0) {
        *is_stdin = 1;
        return STDIN_FILENO;
    }
    if (stat(path, &info) != 0) {
        if (errno != ENOENT || mkfifo(path, 0660) != 0) {
            fprintf(stderr, "XQ LINUX INPUT FIFO FAILED path=%s error=%s\n",
                    path, strerror(errno));
            return -1;
        }
    } else if (!S_ISFIFO(info.st_mode)) {
        fprintf(stderr, "XQ LINUX INPUT FIFO FAILED path=%s reason=not-fifo\n",
                path);
        return -1;
    }
    fd = open(path, O_RDONLY | O_NONBLOCK);
    if (fd < 0) {
        fprintf(stderr, "XQ LINUX INPUT FIFO FAILED path=%s error=%s\n",
                path, strerror(errno));
        return -1;
    }
    printf("XQ LINUX INPUT FIFO READY path=%s commands=XQ_MOVE,XQ_NEWGAME,XQ_STATUS\n",
           path);
    return fd;
}

static int read_control_line(int fd, char *line, size_t capacity,
                             size_t *length)
{
    char value;
    ssize_t count;

    if (fd < 0 || line == NULL || capacity < 2u || length == NULL)
        return 0;
    for (;;) {
        count = read(fd, &value, 1u);
        if (count == 1) {
            if ((unsigned char)value == 27u) {
                *length = 0u;
                return 2;
            }
            if (value == '\r' || value == '\n') {
                if (*length == 0u)
                    continue;
                line[*length] = '\0';
                *length = 0u;
                return 1;
            }
            if (*length + 1u < capacity)
                line[(*length)++] = value;
            else
                *length = 0u;
            continue;
        }
        if (count == 0)
            return 0;
        if (errno == EINTR)
            continue;
        if (errno == EAGAIN || errno == EWOULDBLOCK)
            return 0;
        *length = 0u;
        return 0;
    }
}

typedef enum {
    ENGINE_START_IDLE = 0,
    ENGINE_START_WAIT_UCI,
    ENGINE_START_WAIT_NNUE,
    ENGINE_START_READY,
    ENGINE_START_FAILED
} engine_start_state_t;

static engine_start_state_t engine_start_state;
static uint32_t engine_start_deadline_frame;
#ifndef PIKAFISH_DIRECT_CORE
static unsigned int engine_marker_index;
static unsigned int pff1_load_marker_index;
static unsigned int pff1_ready_marker_index;
static unsigned int pff1_failed_marker_index;
static int pff1_load_seen;
static int pff1_ready_seen;
static int pff1_failed_seen;
#endif

static const uint8_t red_back_rank[9] = {
    PIECE_R, PIECE_N, PIECE_B, PIECE_A, PIECE_K,
    PIECE_A, PIECE_B, PIECE_N, PIECE_R
};

static void on_signal(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

static uint32_t video_frame_count(void)
{
    return video_fb_read(VIDEO_FB_FRAME_COUNT);
}

static uint32_t milliseconds_to_frames(uint32_t milliseconds)
{
    return (milliseconds * GUI_FRAMES_PER_SECOND + 999u) / 1000u;
}

static uint64_t frames_to_milliseconds(uint32_t frames)
{
    return ((uint64_t)frames * 1000u + GUI_FRAMES_PER_SECOND / 2u) /
           GUI_FRAMES_PER_SECOND;
}

static uint64_t monotonic_milliseconds(void)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0)
        return 0u;
    return (uint64_t)now.tv_sec * 1000u +
           (uint64_t)now.tv_nsec / 1000000u;
}

static int frame_deadline_reached(uint32_t now, uint32_t deadline)
{
    return (int32_t)(now - deadline) >= 0;
}

/* Voice events are preview only; this handler has no board/mouse/engine access. */
static void process_voice_command(const xqvoice_command_t *command)
{
    xqvoice_command_t preview = *command;
    unsigned int index;
    if (command->type != XQVOICE_COMMAND_DISPLAY) {
        preview.type = XQVOICE_COMMAND_DISPLAY;
        preview.display_state = XQVOICE_DISPLAY_COMPLETE;
        if (command->type == XQVOICE_COMMAND_MOVE) {
            preview.token_count = 4;
            preview.tokens[0] = (uint8_t)command->piece;
            preview.tokens[1] = command->source_file + 9;
            preview.tokens[2] = (uint8_t)command->action + 18;
            preview.tokens[3] = command->target + 9;
        } else {
            preview.token_count = 1;
            preview.tokens[0] = command->type == XQVOICE_COMMAND_RESTART ? 22 :
                                command->type == XQVOICE_COMMAND_CANCEL ? 23 : 24;
        }
    }
    xq_fb_gui_set_voice_display(&preview);
    xq_fb_gui_refresh_voice_display();
    (void)xqvoice_gui_ipc_reply(&voice_ipc, XQVOICE_REPLY_DISPLAYED, "preview-only");
    printf("XQ LINUX VOICE DISPLAY sequence=%u state=%s score=%u text=",
           preview.sequence, xqvoice_display_state_name(preview.display_state),
           preview.confidence_permille);
    for (index = 0; index < preview.token_count; ++index)
        fputs(xqvoice_token_text(preview.tokens[index]), stdout);
    puts(" executed=0");
}

static void wait_for_next_video_frame(uint32_t *last_frame)
{
    const struct timespec idle = {0, GUI_IDLE_SLEEP_NS};
    unsigned int sleep_count = 0;

    while (!stop_requested && sleep_count++ < 50u) {
        uint32_t current = video_frame_count();
        if (current != *last_frame) {
            *last_frame = current;
            return;
        }
        /*
         * This is a single-core 49.5 MHz system. Staying runnable here,
         * especially while the engine child had a lower nice priority,
         * starved Pikafish during its long startup. The hardware press
         * counters preserve short clicks while the GUI sleeps.
         */
        (void)nanosleep(&idle, NULL);
    }
    /* A stalled video counter must not stop engine readiness or HID polling. */
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
        perror("xiangqi-pikafish: open /dev/mem");
        return 0;
    }
    xq_linux_video_regs = map_physical(fd, VIDEO_FB_REG_BASE,
                                       VIDEO_MMIO_PAGE_BYTES);
    xq_linux_framebuffers[0] = map_physical(fd, VIDEO_FB0_CPU_UNCACHED,
                                            VIDEO_FB_SLOT_BYTES);
#ifdef XQ_PICTURE_INPUT
    picture_live_framebuffer=(volatile uint32_t *)(uintptr_t)xq_linux_framebuffers[0];
    xq_linux_framebuffers[0]=calloc(1,VIDEO_FB_FRAME_BYTES);
    if(!picture_live_framebuffer){free((void *)xq_linux_framebuffers[0]);xq_linux_framebuffers[0]=NULL;}
#endif
    /* This GUI patches framebuffer 0 in place and never page-flips. */
    xq_linux_framebuffers[1] = NULL;
    hid_page = map_physical(fd, HID_PAGE_PHYS, HID_PAGE_BYTES);
    close(fd);
    if (!xq_linux_video_regs || !xq_linux_framebuffers[0] || !hid_page) {
        fprintf(stderr, "xiangqi-pikafish: physical mmap failed\n");
        return 0;
    }
    hid_regs = (volatile uint32_t *)(void *)(hid_page + HID_OFFSET);
    if (hid_regs[HID_ID >> 2] != HID_ID_VALUE ||
        hid_regs[HID_VERSION >> 2] < HID_VERSION_MIN) {
        fprintf(stderr,
                "xiangqi-pikafish: CH9350 ABI mismatch id=%08x version=%08x\n",
                (unsigned int)hid_regs[HID_ID >> 2],
                (unsigned int)hid_regs[HID_VERSION >> 2]);
        return 0;
    }
    hid_has_press_counts = hid_regs[HID_VERSION >> 2] >= HID_PRESS_COUNTS_MIN;
    return xq_fb_gui_init();
}

#ifndef PIKAFISH_DIRECT_CORE
static int send_engine_command(const char *command)
{
    if (!engine_input || fputs(command, engine_input) == EOF ||
        fputc('\n', engine_input) == EOF || fflush(engine_input) != 0)
        return 0;
    return 1;
}

static int marker_byte(char byte, const char *marker, unsigned int *marker_index)
{
    if (byte == marker[*marker_index])
        ++*marker_index;
    else
        *marker_index = byte == marker[0] ? 1u : 0u;
    return marker[*marker_index] == '\0';
}

static int engine_marker_byte(char byte, const char *marker)
{
    return marker_byte(byte, marker, &engine_marker_index);
}
#endif

static int start_engine_async(void)
{
#ifdef PIKAFISH_DIRECT_CORE
    engine_start_state = ENGINE_START_WAIT_NNUE;
    engine_start_deadline_frame = 0;
    puts("XQ LINUX ENGINE DIRECT START");
    return pikafish_embedded_start(ENGINE_MODEL, ENGINE_HASH_MIB);
#else
    int to_child[2];
    int from_child[2];
    int flags;
    if (pipe(to_child) != 0) {
        perror("xiangqi-pikafish: pipe");
        return 0;
    }
    if (pipe(from_child) != 0) {
        perror("xiangqi-pikafish: pipe");
        close(to_child[0]);
        close(to_child[1]);
        return 0;
    }
    engine_pid = fork();
    if (engine_pid < 0) {
        perror("xiangqi-pikafish: fork");
        close(to_child[0]);
        close(to_child[1]);
        close(from_child[0]);
        close(from_child[1]);
        return 0;
    }
    if (engine_pid == 0) {
        (void)prctl(PR_SET_PDEATHSIG, SIGKILL);
        if (getppid() == 1)
            _exit(125);
        /*
         * This is a single-core system.  Keep the framebuffer/input parent
         * responsive while the engine performs CPU-heavy initialization.
         * The parent sleeps between frames, so the engine still receives all
         * otherwise-idle CPU time at this lower priority.
         */
        (void)setpriority(PRIO_PROCESS, 0, 5);
        (void)dup2(to_child[0], STDIN_FILENO);
        (void)dup2(from_child[1], STDOUT_FILENO);
        close(to_child[0]);
        close(to_child[1]);
        close(from_child[0]);
        close(from_child[1]);
        if (chdir(ENGINE_DIRECTORY) != 0)
            _exit(126);
        execl(ENGINE_PATH, ENGINE_PATH, (char *)NULL);
        _exit(127);
    }
    close(to_child[0]);
    close(from_child[1]);
    engine_input = fdopen(to_child[1], "w");
    engine_output_fd = from_child[0];
    if (!engine_input) {
        close(engine_output_fd);
        engine_output_fd = -1;
        return 0;
    }
    setvbuf(engine_input, NULL, _IOLBF, 0);
    flags = fcntl(engine_output_fd, F_GETFL, 0);
    if (flags < 0 ||
        fcntl(engine_output_fd, F_SETFL, flags | O_NONBLOCK) != 0)
        return 0;
    engine_start_state = ENGINE_START_WAIT_UCI;
    engine_start_deadline_frame = 0;
    engine_marker_index = 0;
    pff1_load_marker_index = 0;
    pff1_ready_marker_index = 0;
    pff1_failed_marker_index = 0;
    pff1_load_seen = 0;
    pff1_ready_seen = 0;
    pff1_failed_seen = 0;
    puts("XQ LINUX ENGINE UCI START");
    return send_engine_command("uci");
#endif
}

/* Pump engine startup without ever blocking the mouse/UI loop. */
static int pump_engine_startup(void)
{
#ifdef PIKAFISH_DIRECT_CORE
    int status = pikafish_embedded_status();
    if (status == PIKAFISH_EMBEDDED_READY) {
        if (engine_start_state != ENGINE_START_READY) {
            engine_start_state = ENGINE_START_READY;
            puts("XQ LINUX PIKAFISH PFF1 READY");
            puts("XQ LINUX ENGINE DIRECT OK");
        }
        return 1;
    }
    if (status == PIKAFISH_EMBEDDED_FAILED) {
        engine_start_state = ENGINE_START_FAILED;
        puts("XQ LINUX PIKAFISH PFF1 FAILED");
        return -1;
    }
    if (engine_start_state == ENGINE_START_FAILED)
        return -1;
    if (frame_deadline_reached(video_frame_count(),
                               engine_start_deadline_frame)) {
        fprintf(stderr, "xiangqi-pikafish: direct core startup timeout\n");
        engine_start_state = ENGINE_START_FAILED;
        return -1;
    }
    return 0;
#else
    char bytes[256];
    const char *marker;
    ssize_t count;
    ssize_t index;
    int flags;
    unsigned int bytes_budget = 4096u;
    if (engine_start_state == ENGINE_START_READY)
        return 1;
    if (engine_start_state == ENGINE_START_FAILED)
        return -1;
    if (engine_start_state != ENGINE_START_WAIT_UCI &&
        engine_start_state != ENGINE_START_WAIT_NNUE)
        return 0;
    marker = engine_start_state == ENGINE_START_WAIT_UCI ? "uciok" : "readyok";
    /* Keep startup output from monopolizing the single RV32 CPU.  Pikafish
     * can emit a long stream while probing the board and loading defaults;
     * return to the HID loop after a bounded amount of pipe data. */
    while (bytes_budget != 0u) {
        count = read(engine_output_fd, bytes, sizeof(bytes));
        if (count == 0) {
            fprintf(stderr, "xiangqi-pikafish: engine exited during startup\n");
            engine_start_state = ENGINE_START_FAILED;
            return -1;
        }
        if (count < 0) {
            if (errno == EINTR)
                continue;
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                /* Drain already queued output before enforcing the deadline. */
                if (frame_deadline_reached(video_frame_count(),
                                           engine_start_deadline_frame)) {
                    fprintf(stderr,
                            "xiangqi-pikafish: engine startup timeout phase=%s\n",
                            engine_start_state == ENGINE_START_WAIT_UCI ?
                            "uci" : "nnue");
                    engine_start_state = ENGINE_START_FAILED;
                    return -1;
                }
                return 0;
            }
            perror("xiangqi-pikafish: read engine");
            engine_start_state = ENGINE_START_FAILED;
            return -1;
        }
        if ((unsigned int)count >= bytes_budget)
            bytes_budget = 0u;
        else
            bytes_budget -= (unsigned int)count;
        for (index = 0; index < count; ++index) {
            if (!pff1_load_seen &&
                marker_byte(bytes[index], "PIKAFISH_PFF1_LOAD",
                            &pff1_load_marker_index)) {
                pff1_load_seen = 1;
                pff1_load_marker_index = 0;
                puts("XQ LINUX PIKAFISH PFF1 LOAD");
            }
            if (!pff1_ready_seen &&
                marker_byte(bytes[index], "PIKAFISH_PFF1_READY",
                            &pff1_ready_marker_index)) {
                pff1_ready_seen = 1;
                pff1_ready_marker_index = 0;
                puts("XQ LINUX PIKAFISH PFF1 READY");
            }
            if (!pff1_failed_seen &&
                marker_byte(bytes[index], "PIKAFISH_PFF1_FAILED",
                            &pff1_failed_marker_index)) {
                pff1_failed_seen = 1;
                pff1_failed_marker_index = 0;
                puts("XQ LINUX PIKAFISH PFF1 FAILED");
            }
            if (!engine_marker_byte(bytes[index], marker))
                continue;
            engine_marker_index = 0;
            if (engine_start_state == ENGINE_START_WAIT_UCI) {
                puts("XQ LINUX ENGINE UCI OK");
                puts("XQ LINUX ENGINE NNUE START");
                if (!send_engine_command("setoption name Threads value 1") ||
                    !send_engine_command("setoption name Hash value 8") ||
                    !send_engine_command(
                        "setoption name UCI_ShowWDL value true") ||
                    !send_engine_command("setoption name EvalFile value "
                                         ENGINE_MODEL) ||
                    !send_engine_command("isready")) {
                    engine_start_state = ENGINE_START_FAILED;
                    return -1;
                }
                engine_start_state = ENGINE_START_WAIT_NNUE;
                engine_start_deadline_frame = video_frame_count() +
                    milliseconds_to_frames(ENGINE_NNUE_TIMEOUT_MS);
                return 0;
            }
            flags = fcntl(engine_output_fd, F_GETFL, 0);
            if (flags < 0 ||
                fcntl(engine_output_fd, F_SETFL, flags & ~O_NONBLOCK) != 0) {
                engine_start_state = ENGINE_START_FAILED;
                return -1;
            }
            engine_output = fdopen(engine_output_fd, "r");
            if (!engine_output) {
                engine_start_state = ENGINE_START_FAILED;
                return -1;
            }
            engine_output_fd = -1;
            engine_start_state = ENGINE_START_READY;
            puts("XQ LINUX ENGINE NNUE OK");
            return 1;
        }
    }
    return 0;
#endif
}

static void abort_engine(void)
{
#ifdef PIKAFISH_DIRECT_CORE
    pikafish_embedded_stop();
    engine_start_state = ENGINE_START_FAILED;
#else
    int status;
    if (engine_input) {
        fclose(engine_input);
        engine_input = NULL;
    }
    if (engine_output) {
        fclose(engine_output);
        engine_output = NULL;
    }
    if (engine_output_fd >= 0) {
        close(engine_output_fd);
        engine_output_fd = -1;
    }
    if (engine_pid > 0) {
        (void)kill(engine_pid, SIGKILL);
        (void)waitpid(engine_pid, &status, 0);
        engine_pid = -1;
    }
    engine_start_state = ENGINE_START_FAILED;
#endif
}

static void stop_engine(void)
{
#ifdef PIKAFISH_DIRECT_CORE
    pikafish_embedded_stop();
    engine_start_state = ENGINE_START_IDLE;
#else
    int status;
    if (engine_start_state != ENGINE_START_READY) {
        abort_engine();
        return;
    }
    if (engine_input) {
        (void)send_engine_command("quit");
        fclose(engine_input);
        engine_input = NULL;
    }
    if (engine_output) {
        fclose(engine_output);
        engine_output = NULL;
    }
    if (engine_pid > 0) {
        (void)waitpid(engine_pid, &status, 0);
        engine_pid = -1;
    }
    engine_start_state = ENGINE_START_IDLE;
#endif
}

#ifndef PIKAFISH_DIRECT_CORE
static uint32_t parse_unsigned_after(const char *line, const char *key)
{
    const char *value = strstr(line, key);
    unsigned long long parsed;
    if (!value)
        return 0;
    value += strlen(key);
    parsed = strtoull(value, NULL, 10);
    return parsed > 0xffffffffULL ? 0xffffffffu : (uint32_t)parsed;
}

static int parse_signed_after(const char *line, const char *key,
                              int *value_out)
{
    const char *value = strstr(line, key);
    if (!value)
        return 0;
    *value_out = (int)strtol(value + strlen(key), NULL, 10);
    return 1;
}
#endif

static int request_black_move(xq_search_board_t *board,
                              int32_t *red_score,
                              uint32_t *red_win_rate_out,
                              uint32_t *nodes_out, uint32_t *ticks_out,
                              char *bestmove_out)
{
#ifdef PIKAFISH_DIRECT_CORE
    char fen[XQ_PIKAFISH_FEN_CAPACITY];
    pikafish_embedded_result_t result;
    uint32_t red_win_rate = XQ_FB_WIN_RATE_UNAVAILABLE;
    int search_side = board->side;
    if (bestmove_out != NULL)
        bestmove_out[0] = '\0';
    if (!xq_pikafish_board_to_fen(board, fen, sizeof(fen))) {
        fputs("XQ LINUX SEARCH FAILED stage=fen\n", stderr);
        return 0;
    }
    if (!pikafish_embedded_search(fen, ENGINE_MOVE_TIME_MS, &result))
        return 0;
    if (result.have_wdl)
        red_win_rate = search_side ? result.losses : result.wins;
    *nodes_out = result.nodes;
    *red_win_rate_out = red_win_rate;
    *ticks_out = result.elapsed_ms > 0xffffffffu / GUI_TICKS_PER_MS
                   ? 0xffffffffu
                   : result.elapsed_ms * GUI_TICKS_PER_MS;
    if (result.have_score)
        *red_score = -result.score_cp;
    if (result.bestmove[0] == '\0' ||
        strcmp(result.bestmove, "(none)") == 0 ||
        strcmp(result.bestmove, "0000") == 0)
        return -1;
    if (bestmove_out != NULL)
        (void)snprintf(bestmove_out, 8u, "%.4s", result.bestmove);
    if (!xq_pikafish_apply_move(board, result.bestmove, NULL)) {
        fprintf(stderr, "xiangqi-pikafish: rejected direct move %.4s\n",
                result.bestmove);
        return 0;
    }
    printf("XQ LINUX PIKAFISH DIRECT BESTMOVE=%.4s NODES=%u "
           "RED_WIN_PERMILLE=%u ELAPSED_MS=%u\n",
           result.bestmove, (unsigned int)result.nodes,
           (unsigned int)red_win_rate, (unsigned int)result.elapsed_ms);
    return 1;
#else
    char fen[XQ_PIKAFISH_FEN_CAPACITY];
    char command[192];
    char line[512];
    char bestmove[8] = {0};
    uint32_t start_frame;
    uint64_t elapsed_ms;
    uint32_t nodes = 0;
    uint32_t red_win_rate = XQ_FB_WIN_RATE_UNAVAILABLE;
    int side_score = 0;
    int have_score = 0;
    int search_side = board->side;
    if (bestmove_out != NULL)
        bestmove_out[0] = '\0';
    if (!xq_pikafish_board_to_fen(board, fen, sizeof(fen)))
        return 0;
    if (snprintf(command, sizeof(command), "position fen %s", fen) <= 0 ||
        !send_engine_command(command))
        return 0;
    if (snprintf(command, sizeof(command), "go movetime %u",
                 ENGINE_MOVE_TIME_MS) <= 0 || !send_engine_command(command))
        return 0;
    start_frame = video_frame_count();
    while (fgets(line, sizeof(line), engine_output)) {
        if (strncmp(line, "info ", 5) == 0) {
            uint32_t latest_nodes = parse_unsigned_after(line, " nodes ");
            uint32_t wins;
            uint32_t draws;
            uint32_t losses;
            int latest_score;
            if (latest_nodes)
                nodes = latest_nodes;
            if (parse_signed_after(line, " score cp ", &latest_score)) {
                side_score = latest_score;
                have_score = 1;
            }
            if (xq_pikafish_parse_wdl(line, &wins, &draws, &losses)) {
                (void)draws;
                red_win_rate = search_side ? losses : wins;
            }
        } else if (sscanf(line, "bestmove %7s", bestmove) == 1) {
            break;
        }
    }
    elapsed_ms = frames_to_milliseconds(video_frame_count() - start_frame);
    *nodes_out = nodes;
    *red_win_rate_out = red_win_rate;
    *ticks_out = elapsed_ms > 0xffffffffu / GUI_TICKS_PER_MS
                   ? 0xffffffffu
                   : (uint32_t)elapsed_ms * GUI_TICKS_PER_MS;
    if (have_score)
        *red_score = -side_score;
    if (bestmove[0] == '\0' || strcmp(bestmove, "(none)") == 0 ||
        strcmp(bestmove, "0000") == 0)
        return -1;
    if (bestmove_out != NULL)
        (void)snprintf(bestmove_out, 8u, "%.4s", bestmove);
    if (!xq_pikafish_apply_move(board, bestmove, NULL)) {
        fprintf(stderr, "xiangqi-pikafish: rejected engine move %.4s\n",
                bestmove);
        return 0;
    }
    printf("XQ LINUX PIKAFISH BESTMOVE=%.4s NODES=%u "
           "RED_WIN_PERMILLE=%u ELAPSED_MS=%llu\n",
           bestmove, (unsigned int)nodes, (unsigned int)red_win_rate,
           (unsigned long long)elapsed_ms);
    return 1;
#endif
}

static void restart_game(xq_search_board_t *board, xq_mouse_input_t *mouse,
                         int32_t *score, uint32_t *red_win_rate,
                         uint32_t *nodes, uint32_t *ticks)
{
    reset_board(board);
    *score = 0;
    *red_win_rate = XQ_FB_WIN_RATE_UNAVAILABLE;
    *nodes = 0;
    *ticks = XQ_FB_TIME_UNAVAILABLE;
    xq_fb_gui_set_red_win_rate(*red_win_rate);
    xq_mouse_input_init(mouse, (uint8_t)(hid_regs[HID_STATUS >> 2] & 7u));
    if (engine_start_state == ENGINE_START_READY)
#ifdef PIKAFISH_DIRECT_CORE
        pikafish_embedded_new_game();
#else
        (void)send_engine_command("ucinewgame");
#endif
    (void)xq_fb_gui_show(board, -1, -1, *score, *nodes, *ticks,
                         XQ_FB_STATE_RESTARTED);
}

static const char *engine_status_name(int engine_ready, int engine_failed)
{
    if (engine_ready)
        return "ready";
    if (engine_failed)
        return "failed";
    return "loading";
}

static void process_software_command(
    const xq_gui_command_t *command, xq_search_board_t *board,
    xq_mouse_input_t *mouse, int32_t *red_score, uint32_t *red_win_rate,
    uint32_t *nodes, uint32_t *ticks, int engine_ready, int engine_failed)
{
    if (command->type == XQ_GUI_COMMAND_STATUS) {
        char fen[XQ_PIKAFISH_FEN_CAPACITY];
        if (xq_pikafish_board_to_fen(board, fen, sizeof(fen)))
            printf("XQ LINUX INJECT STATUS side=%s engine=%s nodes=%u "
                   "score=%d red_win_permille=%u fen=%s\n",
                   board->side ? "black" : "red",
                   engine_status_name(engine_ready, engine_failed),
                   (unsigned)*nodes, (int)*red_score,
                   (unsigned)*red_win_rate, fen);
        else
            puts("XQ LINUX INJECT STATUS_FAIL reason=fen");
        return;
    }
    if (command->type == XQ_GUI_COMMAND_NEW_GAME) {
        restart_game(board, mouse, red_score, red_win_rate, nodes, ticks);
        puts("XQ LINUX INJECT NEW_GAME_PASS");
        return;
    }
    if (command->type == XQ_GUI_COMMAND_MOVE) {
        char bestmove[8] = {0};
        uint64_t start_ms;
        uint64_t end_ms;
        uint64_t total_ms;
        int engine_result;

        if (!engine_ready) {
            printf("XQ LINUX INJECT MOVE_FAIL red=%.4s reason=%s\n",
                   command->move, engine_failed ? "engine-failed" :
                   "engine-not-ready");
            return;
        }
        if (board->side != 0u) {
            printf("XQ LINUX INJECT MOVE_FAIL red=%.4s reason=side-black\n",
                   command->move);
            return;
        }
        if (!xq_pikafish_apply_move(board, command->move, NULL)) {
            printf("XQ LINUX INJECT MOVE_FAIL red=%.4s reason=illegal-or-invalid\n",
                   command->move);
            return;
        }
        printf("XQ LINUX INJECT MOVE_START red=%.4s\n", command->move);
        start_ms = monotonic_milliseconds();
        *red_win_rate = XQ_FB_WIN_RATE_UNAVAILABLE;
        xq_fb_gui_set_red_win_rate(*red_win_rate);
        (void)xq_fb_gui_show(board, -1, -1, *red_score, *nodes,
                             XQ_FB_TIME_UNAVAILABLE,
                             XQ_FB_STATE_BLACK_THINK);
        engine_result = request_black_move(board, red_score, red_win_rate,
                                           nodes, ticks, bestmove);
        end_ms = monotonic_milliseconds();
        total_ms = end_ms >= start_ms ? end_ms - start_ms : 0u;
        xq_fb_gui_set_red_win_rate(*red_win_rate);
        if (engine_result > 0) {
            (void)xq_fb_gui_show(board, -1, -1, *red_score, *nodes, *ticks,
                                 XQ_FB_STATE_BLACK_MOVE);
            printf("XQ LINUX INJECT MOVE_PASS red=%.4s black=%.4s nodes=%u "
                   "search_ms=%u total_ms=%llu\n",
                   command->move, bestmove, (unsigned)*nodes,
                   (unsigned)(*ticks / GUI_TICKS_PER_MS),
                   (unsigned long long)total_ms);
        } else if (engine_result < 0) {
            (void)xq_fb_gui_show(board, -1, -1, *red_score, *nodes, *ticks,
                                 XQ_FB_STATE_RED_WINS);
            printf("XQ LINUX INJECT MOVE_PASS red=%.4s black=(none) "
                   "result=red-wins total_ms=%llu\n", command->move,
                   (unsigned long long)total_ms);
        } else {
            (void)xq_fb_gui_show(board, -1, -1, *red_score, *nodes, *ticks,
                                 XQ_FB_STATE_SEARCH_ERROR);
            printf("XQ LINUX INJECT MOVE_FAIL red=%.4s reason=search-error "
                   "total_ms=%llu\n", command->move,
                   (unsigned long long)total_ms);
        }
        xq_mouse_input_init(mouse,
                            (uint8_t)(hid_regs[HID_STATUS >> 2] & 7u));
    }
}

#ifdef XQ_PICTURE_INPUT
#include "../vision/xq_picture_gui.inc"
#endif

#ifdef PIKAFISH_DIRECT_CORE
int xiangqi_pikafish_gui_main(void)
#else
int main(void)
#endif
{
    xq_search_board_t board;
    xq_mouse_input_t mouse;
    int32_t red_score = 0;
    uint32_t red_win_rate = XQ_FB_WIN_RATE_UNAVAILABLE;
    uint32_t nodes = 0;
    uint32_t inference_ticks = XQ_FB_TIME_UNAVAILABLE;
    uint32_t press_counts;
    uint16_t left_press_count;
    uint16_t right_press_count;
    int engine_ready = 0;
    int engine_failed = 0;
#ifdef XQ_PICTURE_INPUT
    int picture_keep_display=0;
#endif
    uint32_t next_engine_wait_log_frame = 0;
    uint32_t last_poll_frame;
    int control_fd;
    int control_is_stdin;
    char control_line[GUI_CONTROL_LINE_BYTES];
    size_t control_line_length = 0u;
    setvbuf(stdout, NULL, _IOLBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    signal(SIGINT, on_signal);
    signal(SIGTERM, on_signal);
    if (
#ifndef PIKAFISH_DIRECT_CORE
        access(ENGINE_PATH, X_OK) != 0
#else
        0
#endif
        ) {
        fprintf(stderr, "xiangqi-pikafish: engine missing\n");
        return 2;
    }
    xq_fb_gui_set_red_win_rate(red_win_rate);

#ifdef XQ_PICTURE_INPUT
    if (!picture_open()) return 5;
#endif
    if (!map_hardware()) {
        fprintf(stderr, "xiangqi-pikafish: framebuffer/HID initialization failed\n");
        return 3;
    }
    puts("XQ LINUX HARDWARE READY; drawing initial framebuffer");
    reset_board(&board);
#ifdef XQ_PICTURE_INPUT
    if (picture_enabled) picture_reset(&board);
#endif
    press_counts = read_mouse_press_counts();
    left_press_count = (uint16_t)press_counts;
    right_press_count = (uint16_t)(press_counts >> 16);
    xq_mouse_input_init(&mouse, (uint8_t)(hid_regs[HID_STATUS >> 2] & 7u));

    if (!xq_fb_gui_show(&board, -1, -1, red_score, nodes,
                        inference_ticks, XQ_FB_STATE_READY)) {
        fprintf(stderr, "xiangqi-pikafish: initial framebuffer draw failed\n");
        return 4;
    }

    /* Model loading stays asynchronous so input and scanout remain live. */
    if (!start_engine_async()) {
        fprintf(stderr, "xiangqi-pikafish: engine startup failed\n");
        abort_engine();
        engine_failed = 1;
    } else {
        last_poll_frame = video_frame_count();
        engine_start_deadline_frame = last_poll_frame +
            milliseconds_to_frames(ENGINE_NNUE_TIMEOUT_MS);
        next_engine_wait_log_frame = last_poll_frame;
    }
    puts("XQ LINUX GUI READY; full Pikafish and official NNUE loading");
    puts("XQ LINUX INPUT READY; engine loading asynchronously; "
         "software=XQ_MOVE/XQ_NEWGAME/XQ_STATUS");
    last_poll_frame = video_frame_count();
    control_fd = open_control_channel(&control_is_stdin);
    if (control_is_stdin) {
        int stdin_flags = fcntl(STDIN_FILENO, F_GETFL, 0);
        if (stdin_flags >= 0)
            (void)fcntl(STDIN_FILENO, F_SETFL, stdin_flags | O_NONBLOCK);
    }

    if(xqvoice_gui_ipc_open(&voice_ipc,XQVOICE_GUI_SOCKET))
        xq_fb_gui_set_voice_feedback("VOICE DISPLAY");
    else xq_fb_gui_set_voice_feedback("VOICE OFFLINE");
    xq_fb_gui_refresh_voice_display();
    puts("XQ LINUX VOICE MODE display-only; chess actions disabled");
    while (!stop_requested) {
#ifdef XQ_PICTURE_INPUT
        if (picture_enabled) picture_finish_search(&board,&red_score,&red_win_rate,&nodes,&inference_ticks);
#endif
        xq_search_board_t board_before;
        uint32_t xy = hid_regs[HID_MOUSE_XY >> 2];
        uint32_t current_press_counts = read_mouse_press_counts();
        uint8_t buttons = (uint8_t)(hid_regs[HID_STATUS >> 2] & 7u);
        uint16_t current_left_count = (uint16_t)current_press_counts;
        uint16_t current_right_count =
            (uint16_t)(current_press_counts >> 16);
        uint8_t latched_buttons = 0;
        xq_mouse_action_t action;
        int control_result;
        if (!engine_ready && !engine_failed) {
            uint32_t now_frame = video_frame_count();
            int startup_result = pump_engine_startup();
            if (startup_result == 0 &&
                frame_deadline_reached(now_frame,
                                       next_engine_wait_log_frame)) {
                printf("XQ LINUX ENGINE WAIT phase=%s mouse_frames=%u "
                       "video_frames=%u\n",
                       engine_start_state == ENGINE_START_WAIT_UCI ?
                       "uci" : "nnue",
                       (unsigned)hid_regs[HID_MOUSE_FRAME_COUNT >> 2],
                       (unsigned)video_fb_read(VIDEO_FB_FRAME_COUNT));
                next_engine_wait_log_frame = now_frame +
                    milliseconds_to_frames(30000u);
            }
            if (startup_result > 0) {
                engine_ready = 1;
                puts("XQ LINUX PIKAFISH READY; mouse=move, "
                     "restart button=reset, Esc=exit");
            } else if (startup_result < 0) {
                engine_failed = 1;
                abort_engine();
                (void)xq_fb_gui_show(&board, mouse.selected_square, -1,
                                     red_score, nodes, inference_ticks,
                                     XQ_FB_STATE_SEARCH_ERROR);
            }
        }
        if (current_left_count != left_press_count)
            latched_buttons |= XQ_MOUSE_BUTTON_LEFT;
        if (current_right_count != right_press_count)
            latched_buttons |= XQ_MOUSE_BUTTON_RIGHT;
        left_press_count = current_left_count;
        right_press_count = current_right_count;
        if (latched_buttons != 0u) {
            mouse.previous_buttons &= (uint8_t)~latched_buttons;
            buttons |= latched_buttons;
        }
        control_result = read_control_line(control_fd, control_line,
                                           sizeof(control_line),
                                           &control_line_length);
        if (control_result == 2)
            break;
        if (control_result == 1) {
            xq_gui_command_t command;
#ifdef XQ_PICTURE_INPUT
            if (picture_enabled && !strcmp(control_line, "XQ_PICTURE_CAPTURE")) {
                picture_step(&board, engine_ready, &red_score, &red_win_rate, &nodes, &inference_ticks);
                picture_discard_input();
                press_counts = read_mouse_press_counts();
                left_press_count = (uint16_t)press_counts;
                right_press_count = (uint16_t)(press_counts >> 16);
                continue;
            }
#endif
            if (!xq_gui_command_parse(control_line, &command)) {
                printf("XQ LINUX INJECT MOVE_FAIL reason=command line=%s\n",
                       control_line);
            } else {
#ifdef XQ_PICTURE_INPUT
                if (picture_enabled && command.type == XQ_GUI_COMMAND_MOVE) {
                    puts("XQ_PICTURE_REJECT software move bypasses image confirmation");
                    continue;
                }
#endif
                process_software_command(
                    &command, &board, &mouse, &red_score, &red_win_rate,
                    &nodes, &inference_ticks, engine_ready, engine_failed);
#ifdef XQ_PICTURE_INPUT
                if (picture_enabled && command.type == XQ_GUI_COMMAND_NEW_GAME) {
                    picture_reset(&board);
                    (void)xq_fb_gui_show(&board, -1, -1, red_score, nodes, inference_ticks, XQ_FB_STATE_RESTARTED);
                }
#endif
                press_counts = read_mouse_press_counts();
                left_press_count = (uint16_t)press_counts;
                right_press_count = (uint16_t)(press_counts >> 16);
            }
        }
#ifdef XQ_PICTURE_INPUT
        if (picture_enabled) {
            int changed;
            int key=picture_poll_key();
            if (key && picture_key(key,&board,engine_ready,&red_score,&red_win_rate,&nodes,&inference_ticks)) {
                press_counts = read_mouse_press_counts();
                left_press_count = (uint16_t)press_counts;
                right_press_count = (uint16_t)(press_counts >> 16);
                wait_for_next_video_frame(&last_poll_frame);
                continue;
            }
            if (latched_buttons) picture_buttons &= (uint8_t)~latched_buttons;
            changed = picture_mouse(&board, xy, buttons);
            if (changed==4)
                picture_step(&board,engine_ready,&red_score,&red_win_rate,&nodes,&inference_ticks);
            if (changed==3) {
                (void)picture_key('c',&board,engine_ready,&red_score,&red_win_rate,&nodes,&inference_ticks);
                press_counts=read_mouse_press_counts();
                left_press_count=(uint16_t)press_counts;
                right_press_count=(uint16_t)(press_counts>>16);
            }
            if (changed == 2) {
                restart_game(&board, &mouse, &red_score, &red_win_rate, &nodes, &inference_ticks);
                picture_reset(&board);
            }
            if (changed)
                (void)xq_fb_gui_show(&board, -1, -1, red_score, nodes, inference_ticks, XQ_FB_STATE_READY);
            wait_for_next_video_frame(&last_poll_frame);
            continue;
        }
#endif
        board_before = board;
        action = xq_mouse_input_update(&mouse, &board,
                                       (int)(xy & 0x7ffu),
                                       (int)((xy >> 11) & 0x7ffu), buttons);
        if(action==XQ_MOUSE_ACTION_NONE) {
            xqvoice_command_t voice_command;
            if(xqvoice_gui_ipc_receive(&voice_ipc,&voice_command)>0)
                process_voice_command(&voice_command);
        }
        if (latched_buttons != 0u) {
            printf("XQ LINUX MOUSE PRESS left=%u right=%u frames=%u "
                   "buttons=%u x=%u y=%u action=%d\n",
                   (unsigned)current_left_count,
                   (unsigned)current_right_count,
                   (unsigned)hid_regs[HID_MOUSE_FRAME_COUNT >> 2],
                   (unsigned)buttons,
                   (unsigned)(xy & 0x7ffu),
                   (unsigned)((xy >> 11) & 0x7ffu), (int)action);
        }
        if (action == XQ_MOUSE_ACTION_RESTART) {
            restart_game(&board, &mouse, &red_score, &red_win_rate, &nodes,
                         &inference_ticks);
        } else if (action == XQ_MOUSE_ACTION_MOVED) {
            int engine_result;
            if (!engine_ready) {
                board = board_before;
                mouse.selected_square = mouse.event_from;
                (void)xq_fb_gui_show(
                    &board, mouse.selected_square, -1, red_score, nodes,
                    inference_ticks, engine_failed ?
                    XQ_FB_STATE_SEARCH_ERROR : XQ_FB_STATE_BLACK_THINK);
                puts("XQ LINUX MOVE DEFERRED; engine not ready");
                wait_for_next_video_frame(&last_poll_frame);
                continue;
            }
            red_win_rate = XQ_FB_WIN_RATE_UNAVAILABLE;
            xq_fb_gui_set_red_win_rate(red_win_rate);
            (void)xq_fb_gui_show(&board, -1, -1, red_score, nodes,
                                 XQ_FB_TIME_UNAVAILABLE,
                                 XQ_FB_STATE_BLACK_THINK);
            engine_result = request_black_move(
                &board, &red_score, &red_win_rate, &nodes,
                &inference_ticks, NULL);
            xq_fb_gui_set_red_win_rate(red_win_rate);
            if (engine_result > 0)
                (void)xq_fb_gui_show(&board, -1, -1, red_score, nodes,
                                     inference_ticks, XQ_FB_STATE_BLACK_MOVE);
            else if (engine_result < 0)
                (void)xq_fb_gui_show(&board, -1, -1, red_score, nodes,
                                     inference_ticks, XQ_FB_STATE_RED_WINS);
            else
                (void)xq_fb_gui_show(&board, -1, -1, red_score, nodes,
                                     inference_ticks, XQ_FB_STATE_SEARCH_ERROR);
            xq_mouse_input_init(&mouse,
                (uint8_t)(hid_regs[HID_STATUS >> 2] & 7u));
            press_counts = read_mouse_press_counts();
            left_press_count = (uint16_t)press_counts;
            right_press_count = (uint16_t)(press_counts >> 16);
        } else if (action != XQ_MOUSE_ACTION_NONE) {
            xq_fb_state_t state = XQ_FB_STATE_SELECTED;
            int selected_from = mouse.selected_square;
            int selected_to = mouse.event_to;
            uint32_t redraw_start_frame;
            int redraw_ok;
            if (action == XQ_MOUSE_ACTION_RESELECTED)
                state = XQ_FB_STATE_RESELECTED;
            else if (action == XQ_MOUSE_ACTION_CANCELLED)
                state = XQ_FB_STATE_CANCELLED;
            else if (action == XQ_MOUSE_ACTION_ILLEGAL)
                state = XQ_FB_STATE_ILLEGAL;
            else if (action == XQ_MOUSE_ACTION_SELECT_OWN)
                state = XQ_FB_STATE_SELECT_OWN;
            redraw_start_frame = video_frame_count();
            redraw_ok = xq_fb_gui_show(&board, selected_from, selected_to,
                                       red_score, nodes, inference_ticks,
                                       state);
            printf("XQ LINUX REDRAW action=%d ok=%d elapsed_ms=%llu\n",
                   (int)action, redraw_ok,
                   (unsigned long long)frames_to_milliseconds(
                       video_frame_count() - redraw_start_frame));
        }
        wait_for_next_video_frame(&last_poll_frame);
    }
    xqvoice_gui_ipc_close(&voice_ipc,XQVOICE_GUI_SOCKET);
#ifdef XQ_PICTURE_INPUT
    if (picture_enabled) {
        picture_join_search();
        picture_keep_display=picture_exit_frame(&board);
        (void)xqc_linux_close(&picture_camera);
        free(picture_pixels);
        free(picture_capture_pixels);
        free(picture_topview);
        xq_fb_gui_picture_topview(NULL);
    }
#endif
    stop_engine();
    if (control_fd >= 0 && !control_is_stdin)
        close(control_fd);
#ifdef XQ_PICTURE_INPUT
    /* Camera must have drained before the final frame is painted. Its owner
     * mappings have been closed, so preserve the independently mapped GUI. */
    if (!picture_keep_display) video_fb_control(0,0,0);
#else
    video_fb_control(0, 0, 0);
#endif
    puts("XQ LINUX PIKAFISH STOPPED");
    return 0;
}
