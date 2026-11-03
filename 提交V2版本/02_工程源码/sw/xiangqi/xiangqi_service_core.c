#include <stddef.h>
#include <stdint.h>

#include "xiangqi_sparse_eval.h"
#include "xiangqi_nnue_mac.h"
#include "xiangqi_search.h"

#define UART_BASE       0x1fe001e0u
#define UART_DATA       (*(volatile uint32_t *)(UART_BASE + 0u))
#define UART_STATUS     (*(volatile uint32_t *)(UART_BASE + 4u))
#define UART_RX_READY   (1u << 8)

#define CLINT_MTIME_LOW (*(volatile uint32_t *)0x0200bff8u)

#define MAC_REG_BASE    0x1fe10000u
#define MAC_DDR_BASE    0x1b000000u
#define MAC_CPU_ALIAS   0x9b000000u

#define INPUT_OFFSET    0x0000u
#define WEIGHT_OFFSET   0x2000u
#define BIAS_OFFSET     0xa000u
#define OUTPUT_OFFSET   0xb000u

/* Dedicated sparse-evaluator staging area.  Keep it disjoint from the
 * generic MAC buffers above while staying inside the 1 MiB accelerator DDR
 * aperture. */
#define SPARSE_MODEL_OFFSET   0x20000u
#define SPARSE_PARENT_OFFSET  0x53000u
#define SPARSE_WEIGHT_OFFSET  0x53400u
#define SPARSE_DESC_OFFSET    0x53600u

#define SPARSE_MODEL_BUS  (MAC_DDR_BASE + SPARSE_MODEL_OFFSET)
#define SPARSE_PARENT_BUS (MAC_DDR_BASE + SPARSE_PARENT_OFFSET)
#define SPARSE_WEIGHT_BUS (MAC_DDR_BASE + SPARSE_WEIGHT_OFFSET)
#define SPARSE_DESC_BUS   (MAC_DDR_BASE + SPARSE_DESC_OFFSET)

#define SPARSE_MODEL_CPU ((uint8_t *)(uintptr_t)(MAC_CPU_ALIAS + \
                                                 SPARSE_MODEL_OFFSET))
#define SPARSE_PARENT_CPU ((int32_t *)(uintptr_t)(MAC_CPU_ALIAS + \
                                                  SPARSE_PARENT_OFFSET))
#define SPARSE_WEIGHT_CPU ((uint8_t *)(uintptr_t)(MAC_CPU_ALIAS + \
                                                  SPARSE_WEIGHT_OFFSET))
#define SPARSE_DESC_CPU ((xq_sparse_descriptor_t *)(uintptr_t)(MAC_CPU_ALIAS + \
                                                               SPARSE_DESC_OFFSET))

#define MODEL_HEADER_BYTES 48u
#define MODEL_HIDDEN       128u
#define MODEL_FEATURE_ROWS (2u * 9u * 90u)
#define MODEL_FW_BYTES     (MODEL_FEATURE_ROWS * MODEL_HIDDEN)
#define MODEL_FB_BYTES     MODEL_HIDDEN
#define MODEL_OW_BYTES     (2u * MODEL_HIDDEN)
#define MAX_ACTIVE_FEATURES 32u
#define MAX_BATCH_FEATURES  (3u * XQ_SEARCH_BATCH_MAX)
#define LINE_BYTES          160u

#if (SPARSE_MODEL_OFFSET + MODEL_FW_BYTES) > SPARSE_PARENT_OFFSET
#error "Sparse model overlaps parent buffer"
#endif
#if (SPARSE_PARENT_OFFSET + 2u * MODEL_HIDDEN * 4u) > SPARSE_WEIGHT_OFFSET
#error "Sparse parent overlaps output weights"
#endif
#if (SPARSE_WEIGHT_OFFSET + MODEL_OW_BYTES) > SPARSE_DESC_OFFSET
#error "Sparse output weights overlap descriptors"
#endif
#if (SPARSE_DESC_OFFSET + XQ_SEARCH_BATCH_MAX * 32u) > 0x00100000u
#error "Sparse staging exceeds accelerator DDR aperture"
#endif

#define EVAL_MODE_SPARSE_HW 0
#define EVAL_MODE_MAC_BATCH 1
#define EVAL_MODE_CPU_FUSED 2

typedef xq_search_board_t board_t;

extern const uint8_t xq_model_start[];
extern const uint8_t xq_model_end[];

static int32_t accum_red[MODEL_HIDDEN];
static int32_t accum_black[MODEL_HIDDEN];
static int32_t sparse_base_red[MODEL_HIDDEN];
static int32_t sparse_base_black[MODEL_HIDDEN];
static int32_t scaled_output_weights[2u * MODEL_HIDDEN];
static int64_t score_bias_numerator;
static int sparse_parent_bucket[2];
static int32_t batch_accum_red[XQ_SEARCH_BATCH_MAX][MODEL_HIDDEN];
static int32_t batch_accum_black[XQ_SEARCH_BATCH_MAX][MODEL_HIDDEN];
static size_t batch_feature_offsets[MAX_BATCH_FEATURES];
static int8_t batch_delta_matrix[XQ_SEARCH_BATCH_MAX][MAX_BATCH_FEATURES];
static int8_t batch_delta_packed[XQ_SEARCH_BATCH_MAX * MAX_BATCH_FEATURES];
static char command_line[LINE_BYTES];
static xiangqi_nnue_mac_t mac;
static int sparse_hw_available;
static uint32_t sparse_hw_jobs;
static uint32_t sparse_hw_positions;
static uint32_t sparse_hw_cycles;
static uint32_t sparse_hw_fallbacks;
static uint32_t sparse_hw_errors;
static uint32_t sparse_hw_last_error;

typedef struct {
    uint8_t squares[90];
    int bucket[2];
    int feature_count[2];
    uint32_t full_refreshes;
    uint32_t incremental_positions;
    uint32_t feature_deltas;
    uint32_t batch_positions;
    uint32_t batch_jobs;
    int valid;
} accumulator_cache_t;

static accumulator_cache_t accumulator_cache;

typedef struct {
    const int8_t *remove_from;
    const int8_t *add_to;
    const int8_t *remove_capture;
} sparse_delta_t;

static const int8_t zero_feature_row[MODEL_HIDDEN];

static const int8_t king_bucket[90] = {
    -1, -1, -1, 1, 0, 1, -1, -1, -1,
    -1, -1, -1, 1, 1, 1, -1, -1, -1,
    -1, -1, -1, 1, 1, 1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, -1, -1, -1, -1, -1, -1,
    -1, -1, -1, 1, 1, 1, -1, -1, -1,
    -1, -1, -1, 1, 1, 1, -1, -1, -1,
    -1, -1, -1, 1, 0, 1, -1, -1, -1
};

void *memset(void *destination, int value, size_t bytes)
{
    /* Word-first fill: byte-granular stores through the uncached MAC DDR
     * alias (0x9b00xxxx) stall this platform; 32-bit stores are safe.
     * Head/tail bytes keep exact byte semantics for any alignment. */
    uint8_t *out = (uint8_t *)destination;
    uint32_t word = (uint32_t)(uint8_t)value * 0x01010101u;
    while (bytes != 0u && (((uintptr_t)out & 3u) != 0u)) {
        *out++ = (uint8_t)value;
        --bytes;
    }
    {
        uint32_t *words = (uint32_t *)(void *)out;
        while (bytes >= 4u) {
            *words++ = word;
            bytes -= 4u;
        }
        out = (uint8_t *)words;
    }
    while (bytes-- != 0u)
        *out++ = (uint8_t)value;
    return destination;
}

void *memcpy(void *destination, const void *source, size_t bytes)
{
    /* Word-first copy with the same uncached-alias rationale as memset. */
    uint8_t *out = (uint8_t *)destination;
    const uint8_t *in = (const uint8_t *)source;
    while (bytes != 0u && (((uintptr_t)out & 3u) != 0u)) {
        *out++ = *in++;
        --bytes;
    }
    {
        uint32_t *words_out = (uint32_t *)(void *)out;
        const uint32_t *words_in = (const uint32_t *)(const void *)in;
        while (bytes >= 4u) {
            *words_out++ = *words_in++;
            bytes -= 4u;
        }
        out = (uint8_t *)words_out;
        in = (const uint8_t *)words_in;
    }
    while (bytes-- != 0u)
        *out++ = *in++;
    return destination;
}

static void memory_fence(void *context, void *buffer, size_t bytes)
{
    (void)context;
    (void)buffer;
    (void)bytes;
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
}

static void uart_putc(char value)
{
    if (value == '\n')
        UART_DATA = (uint8_t)'\r';
    UART_DATA = (uint8_t)value;
}

static void uart_puts(const char *text)
{
    while (*text != '\0')
        uart_putc(*text++);
}

static void uart_put_uint(uint32_t value)
{
    char digits[10];
    uint32_t count = 0u;
    if (value == 0u) {
        uart_putc('0');
        return;
    }
    while (value != 0u) {
        digits[count++] = (char)('0' + value % 10u);
        value /= 10u;
    }
    while (count != 0u)
        uart_putc(digits[--count]);
}

static void uart_put_int(int32_t value)
{
    if (value < 0) {
        uart_putc('-');
        uart_put_uint((uint32_t)(-(int64_t)value));
    } else {
        uart_put_uint((uint32_t)value);
    }
}

static void uart_put_hex(uint32_t value)
{
    static const char digits[] = "0123456789abcdef";
    int shift;
    uart_puts("0x");
    for (shift = 28; shift >= 0; shift -= 4)
        uart_putc(digits[(value >> shift) & 15u]);
}

static char uart_getc(void)
{
    while ((UART_STATUS & UART_RX_READY) == 0u) {
    }
    return (char)(UART_DATA & 255u);
}

static void uart_getline(char *line, uint32_t capacity)
{
    uint32_t length = 0u;
    for (;;) {
        char value = uart_getc();
        if (value == '\r' || value == '\n') {
            if (length == 0u)
                continue;
            line[length] = '\0';
            return;
        }
        if ((value == '\b' || value == 127) && length != 0u) {
            --length;
            continue;
        }
        if (value >= 32 && value < 127 && length + 1u < capacity)
            line[length++] = value;
    }
}

static int text_equal(const char *left, const char *right)
{
    while (*left != '\0' && *left == *right) {
        ++left;
        ++right;
    }
    return *left == *right;
}

static int text_starts_with(const char *text, const char *prefix)
{
    while (*prefix != '\0') {
        if (*text++ != *prefix++)
            return 0;
    }
    return 1;
}

static uint32_t read_le32(const uint8_t *bytes)
{
    return (uint32_t)bytes[0] |
           ((uint32_t)bytes[1] << 8) |
           ((uint32_t)bytes[2] << 16) |
           ((uint32_t)bytes[3] << 24);
}

static uint8_t piece_from_fen(char value)
{
    int black = value >= 'a' && value <= 'z';
    char upper = black ? (char)(value - 'a' + 'A') : value;
    uint8_t piece;
    switch (upper) {
    case 'K': piece = PIECE_K; break;
    case 'A': piece = PIECE_A; break;
    case 'B':
    case 'E': piece = PIECE_B; break;
    case 'N':
    case 'H': piece = PIECE_N; break;
    case 'R': piece = PIECE_R; break;
    case 'C': piece = PIECE_C; break;
    case 'P': piece = PIECE_P; break;
    default: return 0u;
    }
    return (uint8_t)(piece | (black ? SIDE_BLACK : 0));
}

static int parse_fen(board_t *board, const char *fen)
{
    int file = 0;
    int rank = 9;
    int separators = 0;
    memset(board, 0, sizeof(*board));

    while (*fen != '\0' && *fen != ' ') {
        char value = *fen++;
        if (value == '/') {
            if (file != 9 || rank == 0)
                return 0;
            file = 0;
            --rank;
            ++separators;
        } else if (value >= '1' && value <= '9') {
            file += value - '0';
            if (file > 9)
                return 0;
        } else {
            uint8_t piece = piece_from_fen(value);
            if (piece == 0u || file >= 9)
                return 0;
            board->squares[rank * 9 + file] = piece;
            ++file;
        }
    }
    if (rank != 0 || file != 9 || separators != 9)
        return 0;
    while (*fen == ' ')
        ++fen;
    if (*fen != 'w' && *fen != 'W' && *fen != 'b' && *fen != 'B')
        return 0;
    board->side = (*fen == 'b' || *fen == 'B') ? 1 : 0;
    return 1;
}

static int map_square(int perspective, int square)
{
    if (perspective == 0)
        return square;
    return (9 - square / 9) * 9 + square % 9;
}

static int feature_type(int perspective, int piece_side, int piece_type)
{
    int ally = perspective == piece_side;
    if (piece_type == PIECE_A || piece_type == PIECE_B)
        return 0;
    if (piece_type == PIECE_N)
        return ally ? 1 : 5;
    if (piece_type == PIECE_R)
        return ally ? 2 : 6;
    if (piece_type == PIECE_C)
        return ally ? 3 : 7;
    if (piece_type == PIECE_P)
        return ally ? 4 : 8;
    return -1;
}

static int perspective_bucket(const board_t *board, int perspective)
{
    uint8_t king = (uint8_t)(PIECE_K |
        (perspective != 0 ? SIDE_BLACK : 0));
    int square;
    for (square = 0; square < 90; ++square) {
        if (board->squares[square] == king) {
            int bucket = king_bucket[square];
            return bucket < 0 ? 0 : bucket;
        }
    }
    return 0;
}

static int feature_offset(int perspective, int bucket, int square,
                          uint8_t piece, size_t *offset)
{
    int type;
    uint32_t row;
    if (piece == 0u || (piece & 7u) == PIECE_K)
        return 0;
    type = feature_type(perspective, (piece & SIDE_BLACK) != 0u,
                        piece & 7u);
    if (type < 0)
        return 0;
    row = ((uint32_t)bucket * 9u + (uint32_t)type) * 90u +
          (uint32_t)map_square(perspective, square);
    *offset = (size_t)row * MODEL_HIDDEN;
    return 1;
}

static uint32_t feature_row(int perspective, int bucket, int square,
                            uint8_t piece)
{
    size_t offset;
    if (!feature_offset(perspective, bucket, square, piece, &offset))
        return XQ_SPARSE_INVALID_ROW;
    return (uint32_t)(offset / MODEL_HIDDEN);
}

static int collect_features(const board_t *board, int perspective,
                            size_t *offsets)
{
    int bucket = perspective_bucket(board, perspective);
    int count = 0;
    int square;

    for (square = 0; square < 90; ++square) {
        uint8_t piece = board->squares[square];
        size_t offset;
        if (count >= (int)MAX_ACTIVE_FEATURES ||
            !feature_offset(perspective, bucket, square, piece, &offset))
            continue;
        offsets[count++] = offset;
    }
    return count;
}

static int model_valid(void)
{
    size_t bytes = (size_t)(xq_model_end - xq_model_start);
    return bytes == MODEL_HEADER_BYTES + MODEL_FW_BYTES +
                    MODEL_FB_BYTES + MODEL_OW_BYTES &&
           xq_model_start[0] == 'X' && xq_model_start[1] == 'Q' &&
           xq_model_start[2] == '8' &&
           read_le32(xq_model_start + 4u) == MODEL_HIDDEN &&
           read_le32(xq_model_start + 8u) == 2u &&
           read_le32(xq_model_start + 12u) == 9u &&
           read_le32(xq_model_start + 16u) == 90u;
}

static int run_accumulation(const int8_t *feature_weights,
                            const size_t *offsets, int count,
                            int32_t *output, uint32_t *cycles)
{
    int result;
    if (count == 0) {
        memset(output, 0, MODEL_HIDDEN * sizeof(output[0]));
        *cycles = 0u;
        return 1;
    }
    result = xiangqi_nnue_mac_accum(&mac, feature_weights, offsets, count,
                                    MODEL_HIDDEN, output);
    *cycles = mac.last_cycles;
    return result;
}

static void apply_feature_delta(const int8_t *feature_weights,
                                size_t offset, int sign, int32_t *output)
{
    int index;
    for (index = 0; index < (int)MODEL_HIDDEN; ++index)
        output[index] += sign * (int32_t)feature_weights[offset + index];
}

static int refresh_perspective(const board_t *board, int perspective,
                               const int8_t *feature_weights,
                               int32_t *output, int *feature_count,
                               uint32_t *cycles)
{
    size_t offsets[MAX_ACTIVE_FEATURES];
    *feature_count = collect_features(board, perspective, offsets);
    if (!run_accumulation(feature_weights, offsets, *feature_count,
                          output, cycles))
        return 0;
    ++accumulator_cache.full_refreshes;
    return 1;
}

static int update_perspective(const board_t *board, int perspective,
                              int bucket, const int8_t *feature_weights,
                              int32_t *output, int *feature_count,
                              uint32_t *cycles)
{
    int square;
    if (!accumulator_cache.valid ||
        accumulator_cache.bucket[perspective] != bucket) {
        return refresh_perspective(board, perspective, feature_weights,
                                   output, feature_count, cycles);
    }

    *cycles = 0u;
    *feature_count = accumulator_cache.feature_count[perspective];
    for (square = 0; square < 90; ++square) {
        uint8_t old_piece = accumulator_cache.squares[square];
        uint8_t new_piece = board->squares[square];
        size_t offset;
        if (old_piece == new_piece)
            continue;
        if (feature_offset(perspective, bucket, square, old_piece, &offset)) {
            apply_feature_delta(feature_weights, offset, -1, output);
            --*feature_count;
            ++accumulator_cache.feature_deltas;
        }
        if (feature_offset(perspective, bucket, square, new_piece, &offset)) {
            apply_feature_delta(feature_weights, offset, 1, output);
            ++*feature_count;
            ++accumulator_cache.feature_deltas;
        }
    }
    return 1;
}

static int prepare_accumulators(const board_t *board, uint32_t *total_cycles,
                                int *red_features, int *black_features)
{
    const int8_t *feature_weights =
        (const int8_t *)(xq_model_start + MODEL_HEADER_BYTES);
    uint32_t red_cycles;
    uint32_t black_cycles;
    int red_bucket = perspective_bucket(board, 0);
    int black_bucket = perspective_bucket(board, 1);

    if (!update_perspective(board, 0, red_bucket, feature_weights,
                            accum_red, red_features, &red_cycles) ||
        !update_perspective(board, 1, black_bucket, feature_weights,
                            accum_black, black_features, &black_cycles)) {
        accumulator_cache.valid = 0;
        return 0;
    }

    if (accumulator_cache.valid)
        ++accumulator_cache.incremental_positions;
    memcpy(accumulator_cache.squares, board->squares,
           sizeof(accumulator_cache.squares));
    accumulator_cache.bucket[0] = red_bucket;
    accumulator_cache.bucket[1] = black_bucket;
    accumulator_cache.feature_count[0] = *red_features;
    accumulator_cache.feature_count[1] = *black_features;
    accumulator_cache.valid = 1;
    *total_cycles = red_cycles + black_cycles;
    return 1;
}

static void initialize_scoring(void)
{
    const int8_t *feature_weights =
        (const int8_t *)(xq_model_start + MODEL_HEADER_BYTES);
    const int8_t *feature_biases = feature_weights + MODEL_FW_BYTES;
    const int8_t *output_weights = feature_biases + MODEL_FB_BYTES;
    int index;
    score_bias_numerator =
        (int64_t)(int32_t)read_le32(xq_model_start + 44u) * 127 * 127;
    for (index = 0; index < (int)(2u * MODEL_HIDDEN); ++index)
        scaled_output_weights[index] =
            (int32_t)output_weights[index] * 1092;
}

static int initialize_sparse_hardware(void)
{
    const uint8_t *feature_weights =
        xq_model_start + MODEL_HEADER_BYTES;
    const uint8_t *feature_biases = feature_weights + MODEL_FW_BYTES;
    const uint8_t *output_weights = feature_biases + MODEL_FB_BYTES;

    sparse_hw_available = 0;
    if (xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_ID) != XQ_SPARSE_ID ||
        xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_VERSION) !=
            XQ_SPARSE_VERSION ||
        xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_MODEL_ROWS) !=
            MODEL_FEATURE_ROWS ||
        xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_DIVISOR) !=
            XQ_SPARSE_SCORE_DIVISOR)
        return 0;

    /* The model and output layer are immutable for the lifetime of the
     * service.  Stage them once; each search batch then copies only 1 KiB of
     * parent state plus at most 512 bytes of descriptors. */
    memcpy(SPARSE_MODEL_CPU, feature_weights, MODEL_FW_BYTES);
    memcpy(SPARSE_WEIGHT_CPU, output_weights, MODEL_OW_BYTES);
    memory_fence(0, SPARSE_MODEL_CPU, MODEL_FW_BYTES);
    memory_fence(0, SPARSE_WEIGHT_CPU, MODEL_OW_BYTES);
    sparse_hw_available = 1;
    return 1;
}

static uint32_t wait_sparse_hardware(uint32_t timeout)
{
    uint32_t status;
    do {
        status = xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_STATUS);
        if ((status & XQ_SPARSE_STATUS_DONE) != 0u)
            return status;
    } while (--timeout != 0u);
    return 0u;
}

static int run_sparse_hardware(int count, int32_t *scores,
                               uint32_t *cycles)
{
    uint64_t bias_bits = (uint64_t)score_bias_numerator;
    uint32_t status;
    int index;

    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_CONTROL,
                    XQ_SPARSE_CONTROL_CLEAR);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_CHILD_COUNT,
                    (uint32_t)count);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_MODEL_BASE,
                    SPARSE_MODEL_BUS);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_PARENT_BASE,
                    SPARSE_PARENT_BUS);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_OUTPUT_WEIGHT,
                    SPARSE_WEIGHT_BUS);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_DESCRIPTOR,
                    SPARSE_DESC_BUS);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_BIAS_LO,
                    (uint32_t)bias_bits);
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_BIAS_HI,
                    (uint32_t)(bias_bits >> 32));
    memory_fence(0, SPARSE_PARENT_CPU,
                 2u * MODEL_HIDDEN * sizeof(SPARSE_PARENT_CPU[0]));
    xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_CONTROL,
                    XQ_SPARSE_CONTROL_START);
    status = wait_sparse_hardware(mac.timeout_polls);
    *cycles = xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_CYCLES);
    if ((status & XQ_SPARSE_STATUS_DONE) == 0u ||
        (status & XQ_SPARSE_STATUS_ERROR) != 0u) {
        sparse_hw_last_error =
            (status & XQ_SPARSE_STATUS_DONE) == 0u ? 0xffffffffu :
            xq_sparse_error_code(status);
        ++sparse_hw_errors;
        sparse_hw_available = 0;
        xq_sparse_write(MAC_REG_BASE, XQ_SPARSE_REG_CONTROL,
                        XQ_SPARSE_CONTROL_CLEAR);
        return 0;
    }
    for (index = 0; index < count; ++index)
        scores[index] = (int32_t)xq_sparse_read(
            MAC_REG_BASE, XQ_SPARSE_REG_RESULT((uint32_t)index));
    return 1;
}

static int32_t score_accumulators(int side, const int32_t *red,
                                  const int32_t *black)
{
    const int8_t *feature_weights =
        (const int8_t *)(xq_model_start + MODEL_HEADER_BYTES);
    const int8_t *feature_biases = feature_weights + MODEL_FW_BYTES;
    const int32_t *weights_stm;
    const int32_t *weights_opp;
    const int32_t *accum_stm;
    const int32_t *accum_opp;
    int64_t numerator;
    int index;

    accum_stm = side == 0 ? red : black;
    accum_opp = side == 0 ? black : red;
    weights_stm = scaled_output_weights;
    weights_opp = scaled_output_weights + MODEL_HIDDEN;

    /* The embedded model scales are exactly 627/127, 250/127 and
     * 1092/127. Keeping one rational numerator matches the desktop model
     * without pulling floating-point runtime code into the board service. */
    numerator = score_bias_numerator;
    for (index = 0; index < (int)MODEL_HIDDEN; ++index) {
        int64_t hidden_stm = (int64_t)627 * accum_stm[index] +
                             (int64_t)250 * feature_biases[index];
        int64_t hidden_opp = (int64_t)627 * accum_opp[index] +
                             (int64_t)250 * feature_biases[index];
        if (hidden_stm > 0)
            numerator += hidden_stm * weights_stm[index];
        if (hidden_opp > 0)
            numerator += hidden_opp * weights_opp[index];
    }
    return (int32_t)(numerator / ((int64_t)127 * 127 * 32 * 128));
}

static int evaluate(const board_t *board, int32_t *score,
                    uint32_t *total_cycles, int *red_features,
                    int *black_features)
{
    if (!prepare_accumulators(board, total_cycles, red_features,
                              black_features))
        return 0;
    *score = score_accumulators(board->side, accum_red, accum_black);
    return 1;
}

static void build_sparse_delta(const board_t *parent,
                               xq_search_move_t move, int perspective,
                               int bucket, sparse_delta_t *delta)
{
    const int8_t *feature_weights =
        (const int8_t *)(xq_model_start + MODEL_HEADER_BYTES);
    uint8_t moved = parent->squares[move.from];
    uint8_t captured = parent->squares[move.to];
    size_t offset;
    delta->remove_from = zero_feature_row;
    delta->add_to = zero_feature_row;
    delta->remove_capture = zero_feature_row;
    if (feature_offset(perspective, bucket, move.from, moved, &offset))
        delta->remove_from = feature_weights + offset;
    if (feature_offset(perspective, bucket, move.to, moved, &offset))
        delta->add_to = feature_weights + offset;
    if (feature_offset(perspective, bucket, move.to, captured, &offset))
        delta->remove_capture = feature_weights + offset;
}

static void build_sparse_descriptor(const board_t *parent,
                                    xq_search_move_t move,
                                    int red_bucket, int black_bucket,
                                    xq_sparse_descriptor_t *descriptor)
{
    uint8_t moved = parent->squares[move.from];
    uint8_t captured = parent->squares[move.to];
    descriptor->child_side = (uint32_t)(parent->side ^ 1);
    descriptor->red_remove_from =
        feature_row(0, red_bucket, move.from, moved);
    descriptor->red_add_to =
        feature_row(0, red_bucket, move.to, moved);
    descriptor->red_remove_capture =
        feature_row(0, red_bucket, move.to, captured);
    descriptor->black_remove_from =
        feature_row(1, black_bucket, move.from, moved);
    descriptor->black_add_to =
        feature_row(1, black_bucket, move.to, moved);
    descriptor->black_remove_capture =
        feature_row(1, black_bucket, move.to, captured);
    descriptor->reserved = 0u;
}

static int prepare_sparse_parent(const board_t *parent,
                                 uint32_t *mac_cycles)
{
    const int8_t *feature_weights =
        (const int8_t *)(xq_model_start + MODEL_HEADER_BYTES);
    const int8_t *feature_biases = feature_weights + MODEL_FW_BYTES;
    int red_features;
    int black_features;
    int lane;
    if (!prepare_accumulators(parent, mac_cycles, &red_features,
                              &black_features))
        return 0;
    sparse_parent_bucket[0] = accumulator_cache.bucket[0];
    sparse_parent_bucket[1] = accumulator_cache.bucket[1];
    for (lane = 0; lane < (int)MODEL_HIDDEN; ++lane) {
        sparse_base_red[lane] = 627 * accum_red[lane] +
                                250 * feature_biases[lane];
        sparse_base_black[lane] = 627 * accum_black[lane] +
                                  250 * feature_biases[lane];
    }
    return 1;
}

static int32_t sparse_delta_lane(const sparse_delta_t *delta, int lane)
{
    return -(int32_t)delta->remove_from[lane] +
           (int32_t)delta->add_to[lane] -
           (int32_t)delta->remove_capture[lane];
}

static int32_t score_sparse_child(const board_t *parent,
                                  xq_search_move_t move)
{
    sparse_delta_t red_delta;
    sparse_delta_t black_delta;
    const int32_t *red_weights;
    const int32_t *black_weights;
    int child_side = parent->side ^ 1;
    int64_t numerator = score_bias_numerator;
    int lane;
    build_sparse_delta(parent, move, 0, sparse_parent_bucket[0],
                       &red_delta);
    build_sparse_delta(parent, move, 1, sparse_parent_bucket[1],
                       &black_delta);
    red_weights = scaled_output_weights +
                  (child_side == 0 ? 0 : MODEL_HIDDEN);
    black_weights = scaled_output_weights +
                    (child_side == 0 ? MODEL_HIDDEN : 0);
    for (lane = 0; lane < (int)MODEL_HIDDEN; ++lane) {
        int32_t hidden_red = sparse_base_red[lane] +
            627 * sparse_delta_lane(&red_delta, lane);
        int32_t hidden_black = sparse_base_black[lane] +
            627 * sparse_delta_lane(&black_delta, lane);
        if (hidden_red > 0)
            numerator += (int64_t)hidden_red * red_weights[lane];
        if (hidden_black > 0)
            numerator += (int64_t)hidden_black * black_weights[lane];
    }
    return (int32_t)(numerator / ((int64_t)127 * 127 * 32 * 128));
}

static int evaluate_sparse_move(void *context, const board_t *parent,
                                xq_search_move_t move, int new_parent,
                                int32_t *score, uint32_t *cycles)
{
    uint8_t moved = parent->squares[move.from];
    int moved_side = (moved & SIDE_BLACK) != 0u;
    int destination_bucket;
    uint32_t setup_cycles = 0u;
    int red_features;
    int black_features;
    (void)context;
    if (new_parent && !prepare_sparse_parent(parent, &setup_cycles))
        return 0;
    if ((moved & 7u) == PIECE_K) {
        destination_bucket = king_bucket[move.to];
        if (destination_bucket < 0)
            destination_bucket = 0;
        if (destination_bucket != sparse_parent_bucket[moved_side]) {
            board_t child = *parent;
            child.squares[move.to] = child.squares[move.from];
            child.squares[move.from] = 0u;
            child.side ^= 1;
            if (!evaluate(&child, score, cycles,
                          &red_features, &black_features))
                return 0;
            *cycles += setup_cycles;
            return 1;
        }
    }
    *score = score_sparse_child(parent, move);
    *cycles = setup_cycles;
    return 1;
}

static int append_batch_delta(size_t offset, int position, int sign,
                              int *feature_count)
{
    int feature;
    for (feature = 0; feature < *feature_count; ++feature) {
        if (batch_feature_offsets[feature] == offset) {
            batch_delta_matrix[position][feature] = (int8_t)
                (batch_delta_matrix[position][feature] + sign);
            return 1;
        }
    }
    if (*feature_count >= (int)MAX_BATCH_FEATURES)
        return 0;
    batch_feature_offsets[*feature_count] = offset;
    batch_delta_matrix[position][*feature_count] = (int8_t)sign;
    ++*feature_count;
    return 1;
}

static int append_move_deltas(const board_t *parent,
                              xq_search_move_t move, int perspective,
                              int bucket, int position, int *feature_count)
{
    uint8_t moved = parent->squares[move.from];
    uint8_t captured = parent->squares[move.to];
    size_t offset;
    if (feature_offset(perspective, bucket, move.from, moved, &offset) &&
        !append_batch_delta(offset, position, -1, feature_count))
        return 0;
    if (feature_offset(perspective, bucket, move.to, moved, &offset) &&
        !append_batch_delta(offset, position, 1, feature_count))
        return 0;
    if (feature_offset(perspective, bucket, move.to, captured, &offset) &&
        !append_batch_delta(offset, position, -1, feature_count))
        return 0;
    return 1;
}

static void apply_move_delta_cpu(const board_t *parent,
                                 xq_search_move_t move, int perspective,
                                 int bucket, const int32_t *parent_accum,
                                 int32_t *output)
{
    const int8_t *feature_weights =
        (const int8_t *)(xq_model_start + MODEL_HEADER_BYTES);
    uint8_t moved = parent->squares[move.from];
    uint8_t captured = parent->squares[move.to];
    size_t offset;
    memcpy(output, parent_accum, MODEL_HIDDEN * sizeof(output[0]));
    if (feature_offset(perspective, bucket, move.from, moved, &offset))
        apply_feature_delta(feature_weights, offset, -1, output);
    if (feature_offset(perspective, bucket, move.to, moved, &offset))
        apply_feature_delta(feature_weights, offset, 1, output);
    if (feature_offset(perspective, bucket, move.to, captured, &offset))
        apply_feature_delta(feature_weights, offset, -1, output);
}

static int run_delta_batch(const board_t *parent,
                           const xq_search_move_t *moves, int count,
                           int perspective, int bucket,
                           const int32_t *parent_accum, int32_t *output,
                           uint32_t *cycles)
{
    const int8_t *feature_weights =
        (const int8_t *)(xq_model_start + MODEL_HEADER_BYTES);
    int feature_count = 0;
    int position;
    int feature;
    memset(batch_delta_matrix, 0, sizeof(batch_delta_matrix));
    for (position = 0; position < count; ++position) {
        if (!append_move_deltas(parent, moves[position], perspective,
                                bucket, position, &feature_count))
            return 0;
    }
    if (feature_count == 0) {
        for (position = 0; position < count; ++position) {
            memcpy(output + position * MODEL_HIDDEN, parent_accum,
                   MODEL_HIDDEN * sizeof(output[0]));
        }
        *cycles = 0u;
        return 1;
    }
    for (position = 0; position < count; ++position) {
        for (feature = 0; feature < feature_count; ++feature) {
            batch_delta_packed[position * feature_count + feature] =
                batch_delta_matrix[position][feature];
        }
    }
    if (!xiangqi_nnue_mac_batch_delta(
            &mac, feature_weights, batch_feature_offsets,
            batch_delta_packed, count, feature_count, MODEL_HIDDEN,
            parent_accum, output))
        return 0;
    *cycles = mac.last_cycles;
    ++accumulator_cache.batch_jobs;
    return 1;
}

static int evaluate_batch(void *context, const xq_search_board_t *parent,
                          const xq_search_move_t *moves, int count,
                          int32_t *scores, uint32_t *total_cycles)
{
    xq_search_move_t normal_moves[XQ_SEARCH_BATCH_MAX];
    int normal_map[XQ_SEARCH_BATCH_MAX];
    int fallback_map[XQ_SEARCH_BATCH_MAX];
    int normal_count = 0;
    int fallback_count = 0;
    int parent_bucket[2];
    uint32_t setup_cycles;
    uint32_t red_cycles;
    uint32_t black_cycles;
    int red_features;
    int black_features;
    int index;
    (void)context;
    if (count <= 0 || count > XQ_SEARCH_BATCH_MAX)
        return 0;
    if (!prepare_accumulators(parent, &setup_cycles, &red_features,
                              &black_features))
        return 0;
    parent_bucket[0] = accumulator_cache.bucket[0];
    parent_bucket[1] = accumulator_cache.bucket[1];
    for (index = 0; index < count; ++index) {
        board_t child = *parent;
        child.squares[moves[index].to] = child.squares[moves[index].from];
        child.squares[moves[index].from] = 0u;
        child.side ^= 1;
        if (perspective_bucket(&child, 0) != parent_bucket[0] ||
            perspective_bucket(&child, 1) != parent_bucket[1]) {
            fallback_map[fallback_count++] = index;
        } else {
            normal_moves[normal_count] = moves[index];
            normal_map[normal_count++] = index;
        }
    }
    *total_cycles = setup_cycles;
    if (normal_count != 0) {
        if (!run_delta_batch(parent, normal_moves, normal_count, 0,
                             parent_bucket[0], accum_red,
                             &batch_accum_red[0][0], &red_cycles) ||
            !run_delta_batch(parent, normal_moves, normal_count, 1,
                             parent_bucket[1], accum_black,
                             &batch_accum_black[0][0], &black_cycles))
            return 0;
        *total_cycles += red_cycles + black_cycles;
        accumulator_cache.batch_positions += (uint32_t)normal_count;
        for (index = 0; index < normal_count; ++index) {
            scores[normal_map[index]] = score_accumulators(
                parent->side ^ 1, batch_accum_red[index],
                batch_accum_black[index]);
        }
    }
    for (index = 0; index < fallback_count; ++index) {
        int original = fallback_map[index];
        board_t child = *parent;
        int child_bucket[2];
        int features;
        child.squares[moves[original].to] = child.squares[moves[original].from];
        child.squares[moves[original].from] = 0u;
        child.side ^= 1;
        child_bucket[0] = perspective_bucket(&child, 0);
        child_bucket[1] = perspective_bucket(&child, 1);
        if (child_bucket[0] != parent_bucket[0]) {
            if (!refresh_perspective(&child, 0,
                    (const int8_t *)(xq_model_start + MODEL_HEADER_BYTES),
                    batch_accum_red[original], &features, &red_cycles))
                return 0;
        } else {
            apply_move_delta_cpu(parent, moves[original], 0,
                                 parent_bucket[0], accum_red,
                                 batch_accum_red[original]);
            red_cycles = 0u;
        }
        if (child_bucket[1] != parent_bucket[1]) {
            if (!refresh_perspective(&child, 1,
                    (const int8_t *)(xq_model_start + MODEL_HEADER_BYTES),
                    batch_accum_black[original], &features, &black_cycles))
                return 0;
        } else {
            apply_move_delta_cpu(parent, moves[original], 1,
                                 parent_bucket[1], accum_black,
                                 batch_accum_black[original]);
            black_cycles = 0u;
        }
        *total_cycles += red_cycles + black_cycles;
        scores[original] = score_accumulators(
            child.side, batch_accum_red[original],
            batch_accum_black[original]);
    }
    return 1;
}

static int score_bucket_change_child(const board_t *parent,
                                     xq_search_move_t move,
                                     const int parent_bucket[2],
                                     int scratch_index, int32_t *score,
                                     uint32_t *cycles)
{
    const int8_t *feature_weights =
        (const int8_t *)(xq_model_start + MODEL_HEADER_BYTES);
    board_t child = *parent;
    int child_bucket[2];
    uint32_t red_cycles = 0u;
    uint32_t black_cycles = 0u;
    int features;

    child.squares[move.to] = child.squares[move.from];
    child.squares[move.from] = 0u;
    child.side ^= 1;
    child_bucket[0] = perspective_bucket(&child, 0);
    child_bucket[1] = perspective_bucket(&child, 1);

    if (child_bucket[0] != parent_bucket[0]) {
        if (!refresh_perspective(&child, 0, feature_weights,
                batch_accum_red[scratch_index], &features, &red_cycles))
            return 0;
    } else {
        apply_move_delta_cpu(parent, move, 0, parent_bucket[0], accum_red,
                             batch_accum_red[scratch_index]);
    }
    if (child_bucket[1] != parent_bucket[1]) {
        if (!refresh_perspective(&child, 1, feature_weights,
                batch_accum_black[scratch_index], &features,
                &black_cycles))
            return 0;
    } else {
        apply_move_delta_cpu(parent, move, 1, parent_bucket[1], accum_black,
                             batch_accum_black[scratch_index]);
    }
    *cycles = red_cycles + black_cycles;
    *score = score_accumulators(child.side,
                                batch_accum_red[scratch_index],
                                batch_accum_black[scratch_index]);
    return 1;
}

static int evaluate_sparse_hardware_batch(
    void *context, const xq_search_board_t *parent,
    const xq_search_move_t *moves, int count,
    int32_t *scores, uint32_t *total_cycles)
{
    int hardware_map[XQ_SEARCH_BATCH_MAX];
    int32_t hardware_scores[XQ_SEARCH_BATCH_MAX];
    int parent_bucket[2];
    int hardware_count = 0;
    uint32_t setup_cycles = 0u;
    uint32_t hardware_cycles = 0u;
    int index;
    (void)context;

    if (count < 1 || count > XQ_SEARCH_BATCH_MAX)
        return 0;
    if (!prepare_sparse_parent(parent, &setup_cycles))
        return 0;
    *total_cycles = setup_cycles;
    parent_bucket[0] = sparse_parent_bucket[0];
    parent_bucket[1] = sparse_parent_bucket[1];

    for (index = 0; index < count; ++index) {
        board_t child = *parent;
        int child_red_bucket;
        int child_black_bucket;
        uint32_t fallback_cycles = 0u;
        child.squares[moves[index].to] = child.squares[moves[index].from];
        child.squares[moves[index].from] = 0u;
        child.side ^= 1;
        child_red_bucket = perspective_bucket(&child, 0);
        child_black_bucket = perspective_bucket(&child, 1);

        if (sparse_hw_available &&
            child_red_bucket == parent_bucket[0] &&
            child_black_bucket == parent_bucket[1]) {
            hardware_map[hardware_count] = index;
            build_sparse_descriptor(parent, moves[index],
                                    parent_bucket[0], parent_bucket[1],
                                    &SPARSE_DESC_CPU[hardware_count]);
            ++hardware_count;
        } else if (child_red_bucket == parent_bucket[0] &&
                   child_black_bucket == parent_bucket[1]) {
            scores[index] = score_sparse_child(parent, moves[index]);
            ++sparse_hw_fallbacks;
        } else {
            if (!score_bucket_change_child(parent, moves[index],
                                           parent_bucket, index,
                                           &scores[index],
                                           &fallback_cycles))
                return 0;
            *total_cycles += fallback_cycles;
            ++sparse_hw_fallbacks;
        }
    }

    if (hardware_count == 0)
        return 1;

    memcpy(SPARSE_PARENT_CPU, sparse_base_red,
           MODEL_HIDDEN * sizeof(sparse_base_red[0]));
    memcpy(SPARSE_PARENT_CPU + MODEL_HIDDEN, sparse_base_black,
           MODEL_HIDDEN * sizeof(sparse_base_black[0]));
    if (!run_sparse_hardware(hardware_count, hardware_scores,
                             &hardware_cycles)) {
        *total_cycles += hardware_cycles;
        for (index = 0; index < hardware_count; ++index) {
            int original = hardware_map[index];
            scores[original] = score_sparse_child(parent, moves[original]);
        }
        sparse_hw_fallbacks += (uint32_t)hardware_count;
        return 1;
    }

    *total_cycles += hardware_cycles;
    ++sparse_hw_jobs;
    sparse_hw_positions += (uint32_t)hardware_count;
    sparse_hw_cycles += hardware_cycles;
    for (index = 0; index < hardware_count; ++index)
        scores[hardware_map[index]] = hardware_scores[index];
    return 1;
}

static void configure_mac(void)
{
    memset(&mac, 0, sizeof(mac));
    memset(&accumulator_cache, 0, sizeof(accumulator_cache));
    sparse_hw_available = 0;
    sparse_hw_jobs = 0u;
    sparse_hw_positions = 0u;
    sparse_hw_cycles = 0u;
    sparse_hw_fallbacks = 0u;
    sparse_hw_errors = 0u;
    sparse_hw_last_error = 0u;
    mac.reg_base = MAC_REG_BASE;
    mac.input_addr = MAC_DDR_BASE + INPUT_OFFSET;
    mac.weight_addr = MAC_DDR_BASE + WEIGHT_OFFSET;
    mac.bias_addr = MAC_DDR_BASE + BIAS_OFFSET;
    mac.output_addr = MAC_DDR_BASE + OUTPUT_OFFSET;
    mac.input_buffer = (uint8_t *)(MAC_CPU_ALIAS + INPUT_OFFSET);
    mac.weight_buffer = (uint8_t *)(MAC_CPU_ALIAS + WEIGHT_OFFSET);
    mac.bias_buffer = (uint8_t *)(MAC_CPU_ALIAS + BIAS_OFFSET);
    mac.output_buffer = (uint8_t *)(MAC_CPU_ALIAS + OUTPUT_OFFSET);
    mac.input_capacity = 0x2000u;
    mac.weight_capacity = 0x8000u;
    mac.bias_capacity = 0x1000u;
    mac.output_capacity = 0x8000u;
    mac.timeout_polls = 1000000u;
    mac.cache_clean = memory_fence;
    mac.cache_invalidate = memory_fence;
}

static void print_info(void)
{
    uart_puts("XQ OK INFO ABI=2 MODEL=orange_h128_i8 H=128 MODEL_BYTES=");
    uart_put_uint((uint32_t)(xq_model_end - xq_model_start));
    uart_puts(" MAC_ID=");
    uart_put_hex(mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_ID));
    uart_puts(" MAC_VER=");
    uart_put_hex(mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_VERSION));
    uart_puts(" SPARSE_ID=");
    uart_put_hex(xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_ID));
    uart_puts(" SPARSE_VER=");
    uart_put_hex(xq_sparse_read(MAC_REG_BASE, XQ_SPARSE_REG_VERSION));
    uart_puts(" SEARCH=BOARD-GO1,GO2 EVAL=");
    uart_puts(sparse_hw_available ? "SPARSE-HW16" : "CPU-FUSED");
    uart_puts(" BATCH=HW16+MAC16+CPU TOP=5 HDMI=RGB565 UART=115200 FULL_REFRESHES=");
    uart_put_uint(accumulator_cache.full_refreshes);
    uart_puts(" INCREMENTAL_POSITIONS=");
    uart_put_uint(accumulator_cache.incremental_positions);
    uart_puts(" FEATURE_DELTAS=");
    uart_put_uint(accumulator_cache.feature_deltas);
    uart_puts(" BATCH_POSITIONS=");
    uart_put_uint(accumulator_cache.batch_positions);
    uart_puts(" BATCH_JOBS=");
    uart_put_uint(accumulator_cache.batch_jobs);
    uart_puts(" SPARSE_JOBS=");
    uart_put_uint(sparse_hw_jobs);
    uart_puts(" SPARSE_POSITIONS=");
    uart_put_uint(sparse_hw_positions);
    uart_puts(" SPARSE_CYCLES=");
    uart_put_uint(sparse_hw_cycles);
    uart_puts(" SPARSE_FALLBACKS=");
    uart_put_uint(sparse_hw_fallbacks);
    uart_puts(" SPARSE_ERRORS=");
    uart_put_uint(sparse_hw_errors);
    uart_puts(" SPARSE_LAST_ERROR=");
    uart_put_hex(sparse_hw_last_error);
    uart_putc('\n');
}

static void process_eval(const char *fen)
{
    board_t board;
    int32_t score;
    uint32_t cycles;
    int red_features;
    int black_features;
    if (!parse_fen(&board, fen)) {
        uart_puts("XQ ERR FEN\n");
        return;
    }
    if (!evaluate(&board, &score, &cycles, &red_features, &black_features)) {
        uart_puts("XQ ERR MAC CODE=");
        uart_put_int(mac.last_result);
        uart_puts(" HW=");
        uart_put_uint(mac_kernel_error_code(MAC_REG_BASE));
        uart_putc('\n');
        return;
    }
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
}

static int search_evaluate(
    void *context, const xq_search_board_t *board,
    int32_t *score, uint32_t *cycles)
{
    int red_features;
    int black_features;
    (void)context;
    return evaluate(board, score, cycles, &red_features, &black_features);
}

static uint32_t search_clock(void *context)
{
    (void)context;
    return CLINT_MTIME_LOW;
}

static void process_go(const char *fen, int depth, int eval_mode)
{
    board_t board;
    xq_search_result_t result;
    xq_search_eval_move_fn evaluate_move = 0;
    xq_search_eval_batch_fn evaluate_children = 0;
    uint32_t other_cycles;
    int index;
    if (!parse_fen(&board, fen)) {
        uart_puts("XQ ERR FEN\n");
        return;
    }
    if (eval_mode == EVAL_MODE_MAC_BATCH) {
        evaluate_children = evaluate_batch;
    } else if (eval_mode == EVAL_MODE_CPU_FUSED || !sparse_hw_available) {
        evaluate_move = evaluate_sparse_move;
    } else {
        evaluate_children = evaluate_sparse_hardware_batch;
    }
    if (!xq_search_go(&board, depth, XQ_SEARCH_MAX_TOP,
                      search_evaluate,
                      evaluate_move,
                      evaluate_children,
                      search_clock,
                      0, &result)) {
        uart_puts("XQ ERR SEARCH MAC_CODE=");
        uart_put_int(mac.last_result);
        uart_putc('\n');
        return;
    }
    uart_puts("XQ OK BESTMOVE=");
    if (result.count == 0) {
        uart_puts("none SCORE=-30000 RED_SCORE=");
        uart_put_int(board.side == 0 ? -30000 : 30000);
    } else {
        char move[5];
        xq_search_move_to_iccs(result.moves[0], move);
        uart_puts(move);
        uart_puts(" SCORE=");
        uart_put_int(result.scores[0]);
        uart_puts(" RED_SCORE=");
        uart_put_int(board.side == 0 ? result.scores[0] : -result.scores[0]);
    }
    uart_puts(" DEPTH=");
    uart_put_uint((uint32_t)result.depth);
    uart_puts(" NODES=");
    uart_put_uint(result.nodes);
    uart_puts(" MAC_CYCLES=");
    uart_put_uint(result.mac_cycles);
    uart_puts(" COUNT=");
    uart_put_uint((uint32_t)result.count);
    uart_puts(" TOP=");
    for (index = 0; index < result.count; ++index) {
        char move[5];
        if (index != 0)
            uart_putc(',');
        xq_search_move_to_iccs(result.moves[index], move);
        uart_puts(move);
        uart_putc(':');
        uart_put_int(result.scores[index]);
    }
    other_cycles = result.cpu_cycles;
    if (other_cycles >= result.movegen_cycles)
        other_cycles -= result.movegen_cycles;
    else
        other_cycles = 0u;
    if (other_cycles >= result.eval_cycles)
        other_cycles -= result.eval_cycles;
    else
        other_cycles = 0u;
    uart_puts(" CPU_CYCLES=");
    uart_put_uint(result.cpu_cycles);
    uart_puts(" MOVEGEN_CYCLES=");
    uart_put_uint(result.movegen_cycles);
    uart_puts(" EVAL_CYCLES=");
    uart_put_uint(result.eval_cycles);
    uart_puts(" OTHER_CYCLES=");
    uart_put_uint(other_cycles);
    uart_puts(" BATCHES=");
    uart_put_uint(result.batches);
    uart_putc('\n');
}

int main(void)
{
    static const char start_fen[] =
        "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w";
    board_t board;
    int32_t score;
    uint32_t cycles;
    int red_features;
    int black_features;

    configure_mac();
    uart_puts("\nXQ SERVICE BOOT\n");
    if (!model_valid()) {
        uart_puts("XQ FATAL MODEL\n");
        for (;;) {
        }
    }
    initialize_scoring();
    if (mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_ID) != MAC_KERNEL_ID ||
        mac_kernel_read(MAC_REG_BASE, MAC_KERNEL_REG_VERSION) !=
            MAC_KERNEL_VERSION) {
        uart_puts("XQ FATAL MAC_ABI\n");
        for (;;) {
        }
    }
    if (initialize_sparse_hardware())
        uart_puts("XQ SPARSE HW READY\n");
    else
        uart_puts("XQ SPARSE HW UNAVAILABLE; CPU FALLBACK\n");
    if (!parse_fen(&board, start_fen) ||
        !evaluate(&board, &score, &cycles, &red_features, &black_features)) {
        uart_puts("XQ FATAL SELFTEST\n");
        for (;;) {
        }
    }
    uart_puts("XQ SELFTEST PASS SCORE=");
    uart_put_int(score);
    uart_puts(" MAC_CYCLES=");
    uart_put_uint(cycles);
    uart_putc('\n');
    uart_puts("XQ SERVICE READY\n");

    for (;;) {
        uart_getline(command_line, sizeof(command_line));
        if (text_equal(command_line, "PING")) {
            uart_puts("XQ OK PONG\n");
        } else if (text_equal(command_line, "INFO")) {
            print_info();
        } else if (text_equal(command_line, "HELP")) {
            uart_puts("XQ OK COMMANDS=PING,INFO,EVAL<space>FEN,GO<space>FEN,GO2<space>FEN,GOB<space>FEN,GO2B<space>FEN,GOC<space>FEN,GO2C<space>FEN\n");
        } else if (text_starts_with(command_line, "EVAL ")) {
            process_eval(command_line + 5);
        } else if (text_starts_with(command_line, "GO ")) {
            process_go(command_line + 3, 1, EVAL_MODE_SPARSE_HW);
        } else if (text_starts_with(command_line, "GO2 ")) {
            process_go(command_line + 4, 2, EVAL_MODE_SPARSE_HW);
        } else if (text_starts_with(command_line, "GOB ")) {
            process_go(command_line + 4, 1, EVAL_MODE_MAC_BATCH);
        } else if (text_starts_with(command_line, "GO2B ")) {
            process_go(command_line + 5, 2, EVAL_MODE_MAC_BATCH);
        } else if (text_starts_with(command_line, "GOC ")) {
            process_go(command_line + 4, 1, EVAL_MODE_CPU_FUSED);
        } else if (text_starts_with(command_line, "GO2C ")) {
            process_go(command_line + 5, 2, EVAL_MODE_CPU_FUSED);
        } else {
            uart_puts("XQ ERR COMMAND\n");
        }
    }
}
