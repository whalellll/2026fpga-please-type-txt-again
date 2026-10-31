#include "xq_picture.h"
#include "xiangqi_pikafish_link.h"
#include <string.h>

void xqp_init(xqp_game *g, const xq_search_board_t *board, uint16_t threshold)
{
    memset(g, 0, sizeof(*g));
    g->confirmed = g->expected = g->observed = *board;
    /* An unset/invalid threshold fails closed. Production value comes from
     * a verified training package; 800 in the development stub is not it. */
    g->threshold = threshold && threshold <= 1000 ? threshold : 1001;
    g->phase = XQP_RED;
}

static xqp_event compare(xqp_game *g, xqp_phase phase)
{
    if (phase == XQP_BLACK) {
        if (memcmp(g->observed.squares, g->expected.squares, 90))
            return XQP_MISMATCH;
        g->confirmed = g->expected;
        g->phase = XQP_RED;
        g->failures = 0;
        return XQP_ACCEPTED;
    }
    if (phase == XQP_RED) {
        xq_search_move_t moves[XQ_SEARCH_MAX_MOVES];
        int i, matches = 0, match = 0;
        int n = xq_search_legal_moves(&g->confirmed, moves, XQ_SEARCH_MAX_MOVES);
        for (i = 0; i < n; ++i) {
            xq_search_board_t next = g->confirmed;
            next.squares[moves[i].to] = next.squares[moves[i].from];
            next.squares[moves[i].from] = 0;
            if (!memcmp(next.squares, g->observed.squares, 90)) {
                ++matches;
                match = i;
            }
        }
        if (matches != 1) return XQP_MISMATCH;
        xq_search_move_to_iccs(moves[match], g->red_move);
        g->confirmed = g->observed;
        g->confirmed.side = 1;
        g->phase = XQP_ENGINE;
        g->failures = 0;
        return XQP_SEARCH;
    }
    return XQP_BAD_RESULT;
}

xqp_event xqp_observe(xqp_game *g, const xqv_result *r, uint32_t frame)
{
    xq_search_board_t board;
    xqp_event event;
    unsigned i;
    if ((g->phase != XQP_RED && g->phase != XQP_BLACK) ||
        !xqv_result_board(r, frame, &board)) return XQP_BAD_RESULT;
    if (r->confidence < g->threshold) return XQP_RETAKE;
    for (i = 0; i < r->piece_count; ++i)
        if (r->pieces[i].confidence < g->threshold) return XQP_RETAKE;
    g->observed = board;
    event = compare(g, g->phase);
    if (event != XQP_MISMATCH) return event;
    if (++g->failures >= 2) {
        g->resume_phase = g->phase;
        g->phase = XQP_MANUAL;
        return XQP_EDIT;
    }
    return XQP_MISMATCH;
}

xqp_event xqp_confirm_manual(xqp_game *g)
{
    xqp_event event;
    if (g->phase != XQP_MANUAL) return XQP_BAD_RESULT;
    event = compare(g, g->resume_phase);
    if (event == XQP_ACCEPTED || event == XQP_SEARCH) return event;
    g->phase = XQP_RESTART;
    return XQP_NEWGAME_REQUIRED;
}

int xqp_edit(xqp_game *g, unsigned square, int direction)
{
    unsigned index;
    uint8_t piece;
    if (g->phase != XQP_MANUAL || square >= 90 || !direction) return 0;
    piece = g->observed.squares[square];
    index = !piece ? 0u : (piece & 7u) + ((piece & SIDE_BLACK) ? 7u : 0u);
    index = (index + (direction > 0 ? 1u : 14u)) % 15u;
    g->observed.squares[square] = (uint8_t)(!index ? 0u :
        ((index - 1u) % 7u + 1u) | (index > 7u ? SIDE_BLACK : 0u));
    return 1;
}

int xqp_engine_move(xqp_game *g, const xq_search_board_t *expected, const char *move)
{
    xq_search_board_t checked;
    if (g->phase != XQP_ENGINE || !move || strlen(move) != 4) return 0;
    checked = g->confirmed;
    if (!xq_pikafish_apply_move(&checked, move, NULL) ||
        checked.side != expected->side || memcmp(checked.squares, expected->squares, 90))
        return 0;
    g->expected = checked;
    memcpy(g->black_move, move, 5);
    g->phase = XQP_BLACK;
    return 1;
}

void xqp_hid_init(xqp_hid *h, uint32_t frame, uint64_t now)
{
    h->last_frame = frame;
    h->pending_reports = 0;
    h->key = 0;
    h->first_ms = h->last_report_ms = now;
}

int xqp_hid_poll_key(xqp_hid *h, uint32_t frame, uint32_t packed, uint64_t now)
{
    if (h->pending_reports && now - h->first_ms >= 2000) {
        h->pending_reports = 0;
        h->last_frame = frame;
        return -1;
    }
    if (frame != h->last_frame) {
        uint32_t delta = frame - h->last_frame;
        unsigned key = (packed >> 16) & 255u, usage = packed & 255u;
        unsigned modifiers = (packed >> 8) & 255u;
        h->last_frame = frame;
        h->last_report_ms = now;
        if (key == 'R' || key == 'C') key += 'a' - 'A';
        if ((modifiers & ~0x22u) ||
            !((key == 32 && usage == 0x2c && !modifiers) ||
              (key == 27 && usage == 0x29 && !modifiers) ||
              (key == 'r' && usage == 0x15) || (key == 'c' && usage == 6))) {
            h->pending_reports = 0;
            return 0;
        }
        if (!h->pending_reports) { h->first_ms = now; h->key = key; }
        else if (h->key != key) { h->pending_reports = 0; return -1; }
        if (delta > 2 || h->pending_reports + delta > 2) {
            h->pending_reports = 0;
            return -1;
        }
        h->pending_reports += delta;
    }
    if (h->pending_reports == 2 && now - h->last_report_ms >= 250) {
        h->pending_reports = 0;
        return (int)h->key;
    }
    return 0;
}

int xqp_hid_poll(xqp_hid *h, uint32_t frame, uint32_t packed, uint64_t now)
{
    int key = xqp_hid_poll_key(h, frame, packed, now);
    return key < 0 ? -1 : key == 32;
}
