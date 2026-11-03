/* Combine the proven UART search service and the DDR framebuffer renderer in
 * one bare-metal image.  Keeping the service implementation in this
 * translation unit lets the GUI command loop reuse its validated static NNUE
 * and sparse-accelerator helpers without duplicating inference code. */
#define main xq_uart_service_main
#include "xiangqi_service_core.c"
#undef main

#include "xiangqi_fb_gui.h"
#include "xiangqi_mouse_input.h"
#include "xiangqi_pikafish_link.h"

#define HID_BASE              0x1fe00400u
#define HID_ID_VALUE          0x43483935u
#define HID_VERSION_MIN       0x0002001fu
#define HID_ID                (*(volatile uint32_t *)(HID_BASE + 0x00u))
#define HID_VERSION           (*(volatile uint32_t *)(HID_BASE + 0x04u))
#define HID_STATUS            (*(volatile uint32_t *)(HID_BASE + 0x08u))
#define HID_MOUSE_XY          (*(volatile uint32_t *)(HID_BASE + 0x0cu))
#define HID_MOUSE_FRAMES      (*(volatile uint32_t *)(HID_BASE + 0x1cu))
#define HID_PARSE_ERRORS      (*(volatile uint32_t *)(HID_BASE + 0x20u))
#define HID_STATUS_MOUSE_SEEN (1u << 4)
#define BLACK_AUTO_DEPTH      2
#define PIKAFISH_MODEL_DDR    0x10000000u
#define PIKAFISH_MODEL_BYTES  51585654u
#define PIKAFISH_MODEL_END    (PIKAFISH_MODEL_DDR + PIKAFISH_MODEL_BYTES)
#define PIKAFISH_MODEL_CRC32  0x11983ca3u
#define ZSTD_FRAME_MAGIC      0xfd2fb528u

#if PIKAFISH_MODEL_END > 0x1b000000u
#error "Pikafish model overlaps the accelerator DDR reservation"
#endif

static uint32_t command_length;
static int pikafish_host_mode;
static int pikafish_pending;
static int pikafish_model_resident;
static uint32_t pikafish_request_ticks;
static uint32_t crc32_table[256];
static const char start_fen[] =
    "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w";

static int poll_uart_line(char *line, uint32_t capacity)
{
    while ((UART_STATUS & UART_RX_READY) != 0u) {
        char value = (char)(UART_DATA & 255u);
        if (value == 27) {
            /* Esc: exit the chess service and return to the bootloader. */
            uart_puts("\nXQ EXIT - returning to bootloader\n");
            __asm__ volatile ("fence iorw, iorw" ::: "memory");
            ((void (*)(uint32_t, uint32_t))0x1c000000u)(0, 0);
        }
        if (value == '\r' || value == '\n') {
            if (command_length == 0u)
                continue;
            line[command_length] = '\0';
            command_length = 0u;
            return 1;
        }
        if ((value == '\b' || value == 127) && command_length != 0u) {
            --command_length;
            continue;
        }
        if (value >= 32 && value < 127 && command_length + 1u < capacity)
            line[command_length++] = value;
    }
    return 0;
}

static int hid_mouse_abi_available(void)
{
    return HID_ID == HID_ID_VALUE && HID_VERSION >= HID_VERSION_MIN;
}

static uint8_t hid_mouse_buttons(void)
{
    return (uint8_t)(HID_STATUS & 7u);
}

static void print_square(int square)
{
    uart_putc((char)('a' + square % 9));
    uart_putc((char)('0' + square / 9));
}

static void print_mouse_info(const xq_mouse_input_t *mouse)
{
    uint32_t status = HID_STATUS;
    uint32_t xy = HID_MOUSE_XY;
    uart_puts("XQ OK MOUSE ID=");
    uart_put_hex(HID_ID);
    uart_puts(" VER=");
    uart_put_hex(HID_VERSION);
    uart_puts(" SEEN=");
    uart_put_uint((status & HID_STATUS_MOUSE_SEEN) != 0u);
    uart_puts(" X=");
    uart_put_uint(xy & 0x7ffu);
    uart_puts(" Y=");
    uart_put_uint((xy >> 11) & 0x3ffu);
    uart_puts(" BUTTONS=");
    uart_put_uint(status & 7u);
    uart_puts(" FRAMES=");
    uart_put_uint(HID_MOUSE_FRAMES);
    uart_puts(" ERRORS=");
    uart_put_uint(HID_PARSE_ERRORS);
    uart_puts(" MODE=");
    uart_puts(pikafish_host_mode ?
              "RED-HUMAN-BLACK-PIKAFISH" :
              "RED-HUMAN-BLACK-GO2");
    uart_puts(" SELECTED=");
    if (mouse->selected_square < 0)
        uart_puts("none");
    else
        print_square(mouse->selected_square);
    uart_putc('\n');
}

static const char *skip_spaces(const char *text)
{
    while (*text == ' ')
        ++text;
    return text;
}

static int parse_uint_argument(const char **cursor, uint32_t *value)
{
    const char *text = skip_spaces(*cursor);
    uint32_t parsed = 0u;
    int digits = 0;
    while (*text >= '0' && *text <= '9') {
        uint32_t digit = (uint32_t)(*text - '0');
        if (parsed > 429496729u ||
            (parsed == 429496729u && digit > 5u))
            return 0;
        parsed = parsed * 10u + digit;
        ++text;
        digits = 1;
    }
    if (!digits)
        return 0;
    *cursor = text;
    *value = parsed;
    return 1;
}

static int parse_int_argument(const char **cursor, int32_t *value)
{
    const char *text = skip_spaces(*cursor);
    uint32_t magnitude = 0u;
    uint32_t limit;
    int negative = 0;
    int digits = 0;
    if (*text == '-') {
        negative = 1;
        ++text;
    } else if (*text == '+') {
        ++text;
    }
    limit = negative ? 2147483648u : 2147483647u;
    while (*text >= '0' && *text <= '9') {
        uint32_t digit = (uint32_t)(*text - '0');
        if (magnitude > limit / 10u ||
            (magnitude == limit / 10u && digit > limit % 10u))
            return 0;
        magnitude = magnitude * 10u + digit;
        ++text;
        digits = 1;
    }
    if (!digits)
        return 0;
    *value = negative ? (int32_t)(0u - magnitude) : (int32_t)magnitude;
    *cursor = text;
    return 1;
}

static uint32_t model_read_le32(uint32_t address)
{
    volatile const uint8_t *bytes =
        (volatile const uint8_t *)(uintptr_t)address;
    return (uint32_t)bytes[0] |
           ((uint32_t)bytes[1] << 8) |
           ((uint32_t)bytes[2] << 16) |
           ((uint32_t)bytes[3] << 24);
}

static void initialize_crc32_table(void)
{
    uint32_t index;
    for (index = 0u; index < 256u; ++index) {
        uint32_t crc = index;
        int bit;
        for (bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^
                  ((crc & 1u) ? 0xedb88320u : 0u);
        crc32_table[index] = crc;
    }
}

static uint32_t model_crc32(uint32_t address, uint32_t length)
{
    volatile const uint8_t *bytes =
        (volatile const uint8_t *)(uintptr_t)address;
    uint32_t crc = 0xffffffffu;
    uint32_t offset;
    for (offset = 0u; offset < length; ++offset)
        crc = crc32_table[(crc ^ bytes[offset]) & 255u] ^ (crc >> 8);
    return crc ^ 0xffffffffu;
}

static int verify_pikafish_model(void)
{
    uint32_t start;
    uint32_t cycles;
    uint32_t actual_crc;
    uint32_t magic = model_read_le32(PIKAFISH_MODEL_DDR);
    if (magic != ZSTD_FRAME_MAGIC) {
        pikafish_model_resident = 0;
        uart_puts("XQ ERR PFMODEL HEADER=");
        uart_put_hex(magic);
        uart_puts(" EXPECTED=");
        uart_put_hex(ZSTD_FRAME_MAGIC);
        uart_putc('\n');
        return 0;
    }
    uart_puts("XQ PFMODEL SCAN ADDR=");
    uart_put_hex(PIKAFISH_MODEL_DDR);
    uart_puts(" BYTES=");
    uart_put_uint(PIKAFISH_MODEL_BYTES);
    uart_putc('\n');
    start = CLINT_MTIME_LOW;
    actual_crc = model_crc32(PIKAFISH_MODEL_DDR, PIKAFISH_MODEL_BYTES);
    cycles = CLINT_MTIME_LOW - start;
    if (actual_crc != PIKAFISH_MODEL_CRC32) {
        pikafish_model_resident = 0;
        uart_puts("XQ ERR PFMODEL CRC32=");
        uart_put_hex(actual_crc);
        uart_puts(" EXPECTED=");
        uart_put_hex(PIKAFISH_MODEL_CRC32);
        uart_puts(" CYCLES=");
        uart_put_uint(cycles);
        uart_putc('\n');
        return 0;
    }
    pikafish_model_resident = 1;
    uart_puts("XQ OK PFMODEL ADDR=");
    uart_put_hex(PIKAFISH_MODEL_DDR);
    uart_puts(" END=");
    uart_put_hex(PIKAFISH_MODEL_END);
    uart_puts(" BYTES=");
    uart_put_uint(PIKAFISH_MODEL_BYTES);
    uart_puts(" FORMAT=ZSTD CRC32=");
    uart_put_hex(actual_crc);
    uart_puts(" CYCLES=");
    uart_put_uint(cycles);
    uart_puts(" RESIDENT=1\n");
    return 1;
}

static void print_search_result(const board_t *root,
                                const xq_search_result_t *result)
{
    uint32_t other_cycles;
    int index;
    uart_puts("XQ OK BESTMOVE=");
    if (result->count == 0) {
        uart_puts("none SCORE=-30000 RED_SCORE=");
        uart_put_int(root->side == 0 ? -30000 : 30000);
    } else {
        char move[5];
        xq_search_move_to_iccs(result->moves[0], move);
        uart_puts(move);
        uart_puts(" SCORE=");
        uart_put_int(result->scores[0]);
        uart_puts(" RED_SCORE=");
        uart_put_int(root->side == 0 ? result->scores[0] :
                     -result->scores[0]);
    }
    uart_puts(" DEPTH=");
    uart_put_uint((uint32_t)result->depth);
    uart_puts(" NODES=");
    uart_put_uint(result->nodes);
    uart_puts(" MAC_CYCLES=");
    uart_put_uint(result->mac_cycles);
    uart_puts(" COUNT=");
    uart_put_uint((uint32_t)result->count);
    uart_puts(" TOP=");
    for (index = 0; index < result->count; ++index) {
        char move[5];
        if (index != 0)
            uart_putc(',');
        xq_search_move_to_iccs(result->moves[index], move);
        uart_puts(move);
        uart_putc(':');
        uart_put_int(result->scores[index]);
    }
    other_cycles = result->cpu_cycles;
    if (other_cycles >= result->movegen_cycles)
        other_cycles -= result->movegen_cycles;
    else
        other_cycles = 0u;
    if (other_cycles >= result->eval_cycles)
        other_cycles -= result->eval_cycles;
    else
        other_cycles = 0u;
    uart_puts(" CPU_CYCLES=");
    uart_put_uint(result->cpu_cycles);
    uart_puts(" MOVEGEN_CYCLES=");
    uart_put_uint(result->movegen_cycles);
    uart_puts(" EVAL_CYCLES=");
    uart_put_uint(result->eval_cycles);
    uart_puts(" OTHER_CYCLES=");
    uart_put_uint(other_cycles);
    uart_puts(" BATCHES=");
    uart_put_uint(result->batches);
    uart_putc('\n');
}

static int show_search_result(board_t *board,
                              const xq_search_result_t *result,
                              int32_t *red_score_out,
                              uint32_t *inference_ticks_out)
{
    int32_t red_score;
    int from;
    int to;
    *inference_ticks_out = result->cpu_cycles;
    if (result->count == 0) {
        *red_score_out = board->side == 0 ? -30000 : 30000;
        return xq_fb_gui_show(board, -1, -1, *red_score_out,
                              result->nodes, *inference_ticks_out,
                              XQ_FB_STATE_NO_MOVE);
    }
    from = result->moves[0].from;
    to = result->moves[0].to;
    red_score = board->side == 0 ? result->scores[0] : -result->scores[0];
    *red_score_out = red_score;
    board->squares[to] = board->squares[from];
    board->squares[from] = 0u;
    board->side ^= 1;
    return xq_fb_gui_show(board, -1, -1, red_score,
                          result->nodes, *inference_ticks_out,
                          XQ_FB_STATE_BEST_MOVE);
}

static int process_eval_hdmi(const char *fen, board_t *display_board,
                             int32_t *display_red_score,
                             uint32_t *inference_ticks)
{
    board_t board;
    int32_t score;
    uint32_t cycles;
    int red_features;
    int black_features;
    if (!parse_fen(&board, fen)) {
        uart_puts("XQ ERR FEN\n");
        return 0;
    }
    if (!evaluate(&board, &score, &cycles, &red_features, &black_features)) {
        uart_puts("XQ ERR MAC CODE=");
        uart_put_int(mac.last_result);
        uart_puts(" HW=");
        uart_put_uint(mac_kernel_error_code(MAC_REG_BASE));
        uart_putc('\n');
        return 0;
    }
    *inference_ticks = cycles;
    if (!xq_fb_gui_show(&board, -1, -1,
                         board.side == 0 ? score : -score,
                         0u, *inference_ticks, XQ_FB_STATE_EVALUATED)) {
        uart_puts("XQ ERR FB_DMA STATUS=");
        uart_put_hex(xq_fb_gui_status());
        uart_putc('\n');
        return 0;
    }
    *display_board = board;
    *display_red_score = board.side == 0 ? score : -score;
    uart_puts("XQ OK SCORE=");
    uart_put_int(score);
    uart_puts(" RED_SCORE=");
    uart_put_int(board.side == 0 ? score : -score);
    uart_puts(" MAC_CYCLES=");
    uart_put_uint(cycles);
    uart_puts(" FEATURES=");
    uart_put_uint((uint32_t)red_features);
    uart_putc(',');
    uart_put_uint((uint32_t)black_features);
    uart_putc('\n');
    return 1;
}

static int process_go_hdmi(const char *fen, int depth, int eval_mode,
                           board_t *display_board,
                           int32_t *display_red_score,
                           uint32_t *inference_ticks)
{
    board_t root;
    board_t shown;
    xq_search_result_t result;
    xq_search_eval_move_fn evaluate_move = 0;
    xq_search_eval_batch_fn evaluate_children = 0;
    if (!parse_fen(&root, fen)) {
        uart_puts("XQ ERR FEN\n");
        return 0;
    }
    if (eval_mode == EVAL_MODE_MAC_BATCH)
        evaluate_children = evaluate_batch;
    else if (eval_mode == EVAL_MODE_CPU_FUSED || !sparse_hw_available)
        evaluate_move = evaluate_sparse_move;
    else
        evaluate_children = evaluate_sparse_hardware_batch;

    if (!xq_search_go(&root, depth, XQ_SEARCH_MAX_TOP,
                      search_evaluate, evaluate_move, evaluate_children,
                      search_clock, 0, &result)) {
        uart_puts("XQ ERR SEARCH MAC_CODE=");
        uart_put_int(mac.last_result);
        uart_putc('\n');
        return 0;
    }
    /* Finish drawing before sending the response newline.  UART clients may
     * submit their next command as soon as that line arrives, and the simple
     * UART has no room for a command while a full framebuffer is rendered. */
    shown = root;
    if (!show_search_result(&shown, &result, display_red_score,
                            inference_ticks)) {
        uart_puts("XQ ERR FB_DMA STATUS=");
        uart_put_hex(xq_fb_gui_status());
        uart_putc('\n');
        return 0;
    }
    *display_board = shown;
    print_search_result(&root, &result);
    return 1;
}

static int request_pikafish_reply(const board_t *board, int32_t red_score)
{
    char fen[XQ_PIKAFISH_FEN_CAPACITY];
    if (!pikafish_host_mode) {
        uart_puts("XQ ERR PFMODE LOCAL\n");
        return 0;
    }
    if (pikafish_pending) {
        uart_puts("XQ ERR PF BUSY\n");
        return 0;
    }
    if (board->side != 1) {
        uart_puts("XQ ERR PF TURN\n");
        return 0;
    }
    if (!xq_pikafish_board_to_fen(board, fen, sizeof(fen))) {
        uart_puts("XQ ERR PF FEN\n");
        return 0;
    }
    if (!xq_fb_gui_show(board, -1, -1, red_score, 0u,
                         XQ_FB_TIME_UNAVAILABLE,
                         XQ_FB_STATE_BLACK_THINK)) {
        uart_puts("XQ ERR FB_DMA STATUS=");
        uart_put_hex(xq_fb_gui_status());
        uart_putc('\n');
        return 0;
    }
    pikafish_request_ticks = CLINT_MTIME_LOW;
    pikafish_pending = 1;
    uart_puts("XQ PF REQUEST FEN=");
    uart_puts(fen);
    uart_putc('\n');
    return 1;
}

static int process_pikafish_move(board_t *board, const char *arguments,
                                 int32_t *red_score,
                                 uint32_t *inference_ticks)
{
    const char *cursor = skip_spaces(arguments);
    const char *move_text = cursor;
    xq_search_move_t move;
    int32_t parsed_score;
    uint32_t nodes;
    uint32_t engine_ms;
    uint32_t roundtrip_ticks;
    uint32_t engine_ticks;

    if (!pikafish_host_mode || !pikafish_pending) {
        uart_puts("XQ ERR PF NOT_PENDING\n");
        return 0;
    }
    if (!xq_pikafish_parse_move(cursor, &move)) {
        uart_puts("XQ ERR PF MOVE_FORMAT\n");
        return 0;
    }
    cursor += 4;
    if (!parse_int_argument(&cursor, &parsed_score) ||
        !parse_uint_argument(&cursor, &nodes) ||
        !parse_uint_argument(&cursor, &engine_ms) ||
        *skip_spaces(cursor) != '\0') {
        uart_puts("XQ ERR PF RESULT_FORMAT\n");
        return 0;
    }
    if (!xq_pikafish_apply_move(board, move_text, &move)) {
        uart_puts("XQ ERR PF ILLEGAL\n");
        return 0;
    }
    roundtrip_ticks = CLINT_MTIME_LOW - pikafish_request_ticks;
    engine_ticks = engine_ms > 159072u ? 0xffffffffu :
                   engine_ms * 27000u;
    *red_score = parsed_score;
    *inference_ticks = engine_ticks;
    pikafish_pending = 0;
    if (!xq_fb_gui_show(board, move.from, move.to, *red_score, nodes,
                         *inference_ticks, XQ_FB_STATE_BLACK_MOVE)) {
        uart_puts("XQ ERR FB_DMA STATUS=");
        uart_put_hex(xq_fb_gui_status());
        uart_putc('\n');
        return 0;
    }
    uart_puts("XQ OK PFMOVE=");
    uart_putc(move_text[0]);
    uart_putc(move_text[1]);
    uart_putc(move_text[2]);
    uart_putc(move_text[3]);
    uart_puts(" RED_SCORE=");
    uart_put_int(*red_score);
    uart_puts(" NODES=");
    uart_put_uint(nodes);
    uart_puts(" ENGINE_MS=");
    uart_put_uint(engine_ms);
    uart_puts(" ROUNDTRIP_CYCLES=");
    uart_put_uint(roundtrip_ticks);
    uart_puts(" BACKEND=PIKAFISH-UCI-HOST\n");
    return 1;
}

static int process_pikafish_no_move(board_t *board, const char *arguments,
                                    int32_t *red_score,
                                    uint32_t *inference_ticks)
{
    const char *cursor = arguments;
    int32_t parsed_score;
    uint32_t nodes;
    uint32_t engine_ms;
    uint32_t roundtrip_ticks;
    uint32_t engine_ticks;
    if (!pikafish_host_mode || !pikafish_pending) {
        uart_puts("XQ ERR PF NOT_PENDING\n");
        return 0;
    }
    if (!parse_int_argument(&cursor, &parsed_score) ||
        !parse_uint_argument(&cursor, &nodes) ||
        !parse_uint_argument(&cursor, &engine_ms) ||
        *skip_spaces(cursor) != '\0') {
        uart_puts("XQ ERR PF RESULT_FORMAT\n");
        return 0;
    }
    roundtrip_ticks = CLINT_MTIME_LOW - pikafish_request_ticks;
    engine_ticks = engine_ms > 159072u ? 0xffffffffu :
                   engine_ms * 27000u;
    *red_score = parsed_score;
    *inference_ticks = engine_ticks;
    pikafish_pending = 0;
    if (!xq_fb_gui_show(board, -1, -1, *red_score, nodes,
                         *inference_ticks, XQ_FB_STATE_RED_WINS)) {
        uart_puts("XQ ERR FB_DMA STATUS=");
        uart_put_hex(xq_fb_gui_status());
        uart_putc('\n');
        return 0;
    }
    uart_puts("XQ OK PFNOMOVE RED_SCORE=");
    uart_put_int(*red_score);
    uart_puts(" NODES=");
    uart_put_uint(nodes);
    uart_puts(" ENGINE_MS=");
    uart_put_uint(engine_ms);
    uart_puts(" ROUNDTRIP_CYCLES=");
    uart_put_uint(roundtrip_ticks);
    uart_puts(" BACKEND=PIKAFISH-UCI-HOST\n");
    return 1;
}

static int process_black_reply(board_t *board, int32_t *red_score,
                               uint32_t *inference_ticks,
                               int print_response)
{
    board_t root;
    xq_search_result_t result;
    xq_search_eval_move_fn evaluate_move = 0;
    xq_search_eval_batch_fn evaluate_children = 0;
    int from;
    int to;

    if (board->side != 1) {
        if (print_response)
            uart_puts("XQ ERR BLACK TURN\n");
        return 0;
    }
    if (!xq_fb_gui_show(board, -1, -1,
                         *red_score, 0u, XQ_FB_TIME_UNAVAILABLE,
                         XQ_FB_STATE_BLACK_THINK)) {
        uart_puts("XQ ERR FB_DMA STATUS=");
        uart_put_hex(xq_fb_gui_status());
        uart_putc('\n');
        return 0;
    }

    if (sparse_hw_available)
        evaluate_children = evaluate_sparse_hardware_batch;
    else
        evaluate_move = evaluate_sparse_move;
    root = *board;
    if (!xq_search_go(&root, BLACK_AUTO_DEPTH, XQ_SEARCH_MAX_TOP,
                      search_evaluate, evaluate_move, evaluate_children,
                      search_clock, 0, &result)) {
        *inference_ticks = XQ_FB_TIME_UNAVAILABLE;
        (void)xq_fb_gui_show(board, -1, -1, *red_score, 0u,
                             *inference_ticks, XQ_FB_STATE_SEARCH_ERROR);
        if (print_response) {
            uart_puts("XQ ERR SEARCH MAC_CODE=");
            uart_put_int(mac.last_result);
            uart_putc('\n');
        }
        return 0;
    }

    *inference_ticks = result.cpu_cycles;
    if (result.count == 0) {
        *red_score = 30000;
        if (!xq_fb_gui_show(board, -1, -1, *red_score,
                             result.nodes, *inference_ticks,
                             XQ_FB_STATE_RED_WINS)) {
            uart_puts("XQ ERR FB_DMA STATUS=");
            uart_put_hex(xq_fb_gui_status());
            uart_putc('\n');
            return 0;
        }
    } else {
        from = result.moves[0].from;
        to = result.moves[0].to;
        *red_score = -result.scores[0];
        board->squares[to] = board->squares[from];
        board->squares[from] = 0u;
        board->side = 0;
        if (!xq_fb_gui_show(board, -1, -1, *red_score,
                             result.nodes, *inference_ticks,
                             XQ_FB_STATE_BLACK_MOVE)) {
            uart_puts("XQ ERR FB_DMA STATUS=");
            uart_put_hex(xq_fb_gui_status());
            uart_putc('\n');
            return 0;
        }
    }
    if (print_response)
        print_search_result(&root, &result);
    return 1;
}

static int restart_game(board_t *board, xq_mouse_input_t *mouse,
                        int32_t *red_score, uint32_t *inference_ticks,
                        int print_response)
{
    board_t fresh;
    int32_t score;
    uint32_t cycles;
    int red_features;
    int black_features;

    if (!parse_fen(&fresh, start_fen) ||
        !evaluate(&fresh, &score, &cycles, &red_features, &black_features)) {
        if (print_response)
            uart_puts("XQ ERR RESET\n");
        return 0;
    }
    if (!xq_fb_gui_show(&fresh, -1, -1, score, 0u, cycles,
                        XQ_FB_STATE_RESTARTED)) {
        uart_puts("XQ ERR FB_DMA STATUS=");
        uart_put_hex(xq_fb_gui_status());
        uart_putc('\n');
        return 0;
    }
    *board = fresh;
    *red_score = score;
    *inference_ticks = cycles;
    pikafish_pending = 0;
    xq_mouse_input_init(mouse, hid_mouse_buttons());
    if (print_response) {
        uart_puts("XQ OK RESET SCORE=");
        uart_put_int(score);
        uart_puts(" MAC_CYCLES=");
        uart_put_uint(cycles);
        uart_putc('\n');
    }
    return 1;
}

static void process_mouse_input(board_t *board, xq_mouse_input_t *mouse,
                                int32_t *red_score,
                                uint32_t *inference_ticks)
{
    uint32_t xy = HID_MOUSE_XY;
    xq_mouse_action_t action = xq_mouse_input_update(
        mouse, board, (int)(xy & 0x7ffu), (int)((xy >> 11) & 0x3ffu),
        hid_mouse_buttons());
    int selected_from = mouse->selected_square;
    int selected_to = -1;
    xq_fb_state_t state;

    if (action == XQ_MOUSE_ACTION_NONE)
        return;
    if (action == XQ_MOUSE_ACTION_RESTART) {
        (void)restart_game(board, mouse, red_score, inference_ticks, 0);
        return;
    }

    switch (action) {
    case XQ_MOUSE_ACTION_SELECTED:
        state = XQ_FB_STATE_SELECTED;
        break;
    case XQ_MOUSE_ACTION_RESELECTED:
        state = XQ_FB_STATE_RESELECTED;
        break;
    case XQ_MOUSE_ACTION_CANCELLED:
        state = XQ_FB_STATE_CANCELLED;
        selected_from = -1;
        break;
    case XQ_MOUSE_ACTION_ILLEGAL:
        state = XQ_FB_STATE_ILLEGAL;
        selected_to = mouse->event_to;
        break;
    case XQ_MOUSE_ACTION_SELECT_OWN:
        state = XQ_FB_STATE_SELECT_OWN;
        selected_from = -1;
        break;
    case XQ_MOUSE_ACTION_MOVED:
    {
        int32_t side_score;
        uint32_t cycles;
        int red_features;
        int black_features;
        selected_from = mouse->event_from;
        selected_to = mouse->event_to;
        state = XQ_FB_STATE_MOUSE_MOVE;
        if (pikafish_host_mode && board->side == 1) {
            (void)request_pikafish_reply(board, *red_score);
            return;
        }
        if (evaluate(board, &side_score, &cycles,
                     &red_features, &black_features)) {
            *red_score = board->side == 0 ? side_score : -side_score;
            *inference_ticks = cycles;
        } else {
            *inference_ticks = XQ_FB_TIME_UNAVAILABLE;
            state = XQ_FB_STATE_EVAL_ERROR;
        }
        if (board->side == 1) {
            (void)process_black_reply(board, red_score, inference_ticks, 0);
            return;
        }
        break;
    }
    default:
        return;
    }

    if (!xq_fb_gui_show(board, selected_from, selected_to,
                         *red_score, 0u, *inference_ticks, state)) {
        uart_puts("XQ ERR FB_DMA STATUS=");
        uart_put_hex(xq_fb_gui_status());
        uart_putc('\n');
    }
}

int main(void)
{
    board_t board;
    int32_t score;
    uint32_t cycles;
    uint32_t inference_ticks;
    int red_features;
    int black_features;
    int mouse_available;
    xq_mouse_input_t mouse;

    pikafish_host_mode = 0;
    pikafish_pending = 0;
    pikafish_model_resident = 0;
    initialize_crc32_table();
    configure_mac();
    uart_puts("\nXQ HDMI SERVICE BOOT\n");
    if (!model_valid()) {
        uart_puts("XQ FATAL MODEL\n");
        for (;;) { }
    }
    initialize_scoring();
    if (mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_ID) != MAC_KERNEL_ID ||
        mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_VERSION) !=
            MAC_KERNEL_VERSION) {
        uart_puts("XQ FATAL MAC_ABI\n");
        for (;;) { }
    }
    if (initialize_sparse_hardware())
        uart_puts("XQ SPARSE HW READY\n");
    else
        uart_puts("XQ SPARSE HW UNAVAILABLE; CPU FALLBACK\n");
    if (!xq_fb_gui_init()) {
        uart_puts("XQ FATAL FB_ABI\n");
        for (;;) { }
    }
    mouse_available = hid_mouse_abi_available();
    xq_mouse_input_init(&mouse, hid_mouse_buttons());
    if (mouse_available)
        uart_puts("XQ MOUSE ABI READY\n");
    else
        uart_puts("XQ MOUSE ABI UNAVAILABLE\n");
    if (!parse_fen(&board, start_fen) ||
        !evaluate(&board, &score, &cycles, &red_features, &black_features)) {
        uart_puts("XQ FATAL SELFTEST\n");
        for (;;) { }
    }
    inference_ticks = cycles;
    if (!xq_fb_gui_show(&board, -1, -1, score, 0u,
                        inference_ticks, XQ_FB_STATE_READY)) {
        uart_puts("XQ FATAL FB_DMA STATUS=");
        uart_put_hex(xq_fb_gui_status());
        uart_putc('\n');
        for (;;) { }
    }
    uart_puts("XQ SELFTEST PASS SCORE=");
    uart_put_int(score);
    uart_puts(" MAC_CYCLES=");
    uart_put_uint(cycles);
    uart_putc('\n');
    uart_puts("XQ HDMI GUI READY\n");
    uart_puts("XQ BLACK AUTO GO2 READY\n");
    uart_puts("XQ PIKAFISH UCI BRIDGE READY\n");
    uart_puts("XQ SERVICE READY\n");

    for (;;) {
        int board_changed = 0;
        if (mouse_available && board.side == 0)
            process_mouse_input(&board, &mouse, &score, &inference_ticks);
        if (!poll_uart_line(command_line, sizeof(command_line)))
            continue;
        if (text_equal(command_line, "PING")) {
            uart_puts("XQ OK PONG\n");
        } else if (text_equal(command_line, "INFO")) {
            print_info();
        } else if (text_equal(command_line, "MOUSE")) {
            print_mouse_info(&mouse);
        } else if (text_equal(command_line, "RESET")) {
            board_changed = restart_game(
                &board, &mouse, &score, &inference_ticks, 1);
        } else if (text_equal(command_line, "BLACK")) {
            if (pikafish_host_mode)
                (void)request_pikafish_reply(&board, score);
            else
                board_changed = process_black_reply(
                    &board, &score, &inference_ticks, 1);
        } else if (text_equal(command_line, "PFMODE HOST")) {
            pikafish_host_mode = 1;
            pikafish_pending = 0;
            uart_puts("XQ OK PFMODE=HOST BACKEND=PIKAFISH-UCI-HOST\n");
        } else if (text_equal(command_line, "PFMODE LOCAL")) {
            pikafish_host_mode = 0;
            pikafish_pending = 0;
            uart_puts("XQ OK PFMODE=LOCAL BACKEND=BOARD-GO2\n");
        } else if (text_equal(command_line, "PFSTATUS")) {
            uart_puts("XQ OK PFMODE=");
            uart_puts(pikafish_host_mode ? "HOST" : "LOCAL");
            uart_puts(" PENDING=");
            uart_put_uint((uint32_t)pikafish_pending);
            uart_puts(" MODEL_RESIDENT=");
            uart_put_uint((uint32_t)pikafish_model_resident);
            uart_puts(" MODEL_ADDR=");
            uart_put_hex(PIKAFISH_MODEL_DDR);
            uart_putc('\n');
        } else if (text_equal(command_line, "PFMODEL")) {
            (void)verify_pikafish_model();
        } else if (text_equal(command_line, "PFGO")) {
            (void)request_pikafish_reply(&board, score);
        } else if (text_starts_with(command_line, "PFMOVE ")) {
            board_changed = process_pikafish_move(
                &board, command_line + 7, &score, &inference_ticks);
        } else if (text_starts_with(command_line, "PFNOMOVE ")) {
            board_changed = process_pikafish_no_move(
                &board, command_line + 9, &score, &inference_ticks);
        } else if (text_equal(command_line, "HELP")) {
            uart_puts("XQ OK COMMANDS=PING,INFO,MOUSE,RESET,BLACK,PFMODE<space>HOST|LOCAL,PFSTATUS,PFMODEL,PFGO,PFMOVE<space>MOVE<space>RED_SCORE<space>NODES<space>MS,PFNOMOVE<space>RED_SCORE<space>NODES<space>MS,EVAL<space>FEN,GO<space>FEN,GO2<space>FEN\n");
        } else if (text_starts_with(command_line, "EVAL ")) {
            pikafish_pending = 0;
            board_changed = process_eval_hdmi(
                command_line + 5, &board, &score, &inference_ticks);
        } else if (text_starts_with(command_line, "GO ")) {
            board_changed = process_go_hdmi(
                command_line + 3, 1, EVAL_MODE_SPARSE_HW, &board, &score,
                &inference_ticks);
        } else if (text_starts_with(command_line, "GO2 ")) {
            board_changed = process_go_hdmi(
                command_line + 4, 2, EVAL_MODE_SPARSE_HW, &board, &score,
                &inference_ticks);
        } else if (text_starts_with(command_line, "GOB ")) {
            board_changed = process_go_hdmi(
                command_line + 4, 1, EVAL_MODE_MAC_BATCH, &board, &score,
                &inference_ticks);
        } else if (text_starts_with(command_line, "GO2B ")) {
            board_changed = process_go_hdmi(
                command_line + 5, 2, EVAL_MODE_MAC_BATCH, &board, &score,
                &inference_ticks);
        } else if (text_starts_with(command_line, "GOC ")) {
            board_changed = process_go_hdmi(
                command_line + 4, 1, EVAL_MODE_CPU_FUSED, &board, &score,
                &inference_ticks);
        } else if (text_starts_with(command_line, "GO2C ")) {
            board_changed = process_go_hdmi(
                command_line + 5, 2, EVAL_MODE_CPU_FUSED, &board, &score,
                &inference_ticks);
        } else {
            uart_puts("XQ ERR COMMAND\n");
        }
        if (board_changed)
            xq_mouse_input_init(&mouse, hid_mouse_buttons());
    }
}
