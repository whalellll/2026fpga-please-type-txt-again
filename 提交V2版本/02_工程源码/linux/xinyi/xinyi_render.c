#include "xinyi_product.h"
#include <stdarg.h>
#include <stdio.h>

typedef struct { char *out; size_t cap, used; } writer;
static void writef(writer *w, const char *format, ...)
{
    va_list args;
    int n;
    if (w->used >= w->cap) return;
    va_start(args, format);
    n = vsnprintf(w->out + w->used, w->cap - w->used, format, args);
    va_end(args);
    if (n < 0) w->used = w->cap;
    else if ((size_t)n >= w->cap - w->used) w->used = w->cap;
    else w->used += (size_t)n;
}
static void quoted(writer *w, const char *s)
{
    const unsigned char *p = (const unsigned char *)s;
    writef(w, "\"");
    for (; *p; ++p) {
        if (*p == '\\' || *p == '"') writef(w, "\\%c", *p);
        else if (*p < 32) writef(w, "\\u%04x", *p);
        else writef(w, "%c", *p);
    }
    writef(w, "\"");
}
size_t xy_state_json(const xy_app *a, char *out, size_t cap)
{
    writer w = {out, cap, 0};
    unsigned i;
    xy_pointer_target targets[XY_POINTER_TARGETS];
    unsigned target_count;
    const xq_search_board_t *b;
    if (!a || !out || !cap) return 0;
    b = a->mode == XY_COACH ? &a->photo.board : &a->voice_board;
    writef(&w, "{\"page\":%u,\"mode\":%u,\"job\":%u,\"token\":%u,\"cancelling\":%d,\"microphone\":%d,\"has_board\":%d,\"geometry_failed\":%d,\"recommended\":%d,\"from\":%u,\"to\":%u,\"confidence\":%u,\"removed\":%u,\"corrected_count\":%u,\"position_reason\":%u,\"photo_ms\":%u,\"voice_total\":%u,\"voice_success\":%u,\"voice_tail_ms\":%u,\"coremark_progress\":%u,\"coremark_elapsed_ms\":%u,\"coremark_measured\":%d,\"coremark_origin\":%u,\"coremark\":%.9f,\"coremark_cpu_hz\":%u,",
        a->page, a->mode, a->job, a->token, a->cancelling, a->microphone_enabled,
        a->mode == XY_COACH ? a->has_board : a->voice_has_board,
        a->geometry_failed, a->has_recommendation,
        a->recommendation.from, a->recommendation.to, a->photo.confidence,
        a->photo.removed_count, a->photo.corrected_cells, a->photo.reason,
        a->photo_latency_ms, a->voice_commands, a->voice_successes, a->voice_tail_ms,
        a->coremark_progress, a->coremark_elapsed_ms, a->coremark_measured,
        a->coremark_origin, a->coremark_per_mhz, a->coremark_cpu_hz);
    writef(&w, "\"message\":"); quoted(&w, a->message);
    writef(&w, ",\"notation\":"); quoted(&w, a->notation);
    writef(&w, ",\"voice_heard\":"); quoted(&w, a->voice_heard);
    writef(&w, ",\"voice_result\":"); quoted(&w, a->voice_result);
    writef(&w, ",\"coremark_identity\":"); quoted(&w, a->coremark_identity);
    writef(&w, ",\"coremark_reference_shown\":%d,\"coremark_display\":%.9f,\"coremark_log_visible\":%d,\"coremark_log_page\":%u,\"coremark_log_bytes\":%u,\"coremark_log_truncated\":%d",
        a->coremark_reference_shown,xy_coremark_display_score(a),a->coremark_log_visible,
        a->coremark_log_page,(unsigned)a->coremark_log_used,a->coremark_log_truncated);
    writef(&w, ",\"board\":[");
    for (i = 0; i < 90; ++i) writef(&w, "%s%u", i ? "," : "", b->squares[i]);
    writef(&w, "],\"corrected\":[");
    for (i = 0; i < 90; ++i) writef(&w, "%s%u", i ? "," : "", a->photo.corrected[i]);
    writef(&w, "],\"actions\":[");
    target_count=xy_pointer_targets(a,targets,XY_POINTER_TARGETS);
    for(i=0;i<target_count;++i)writef(&w,"%s{\"action\":%u,\"x\":%u,\"y\":%u,\"w\":%u,\"h\":%u}",
        i?",":"",targets[i].action,targets[i].x,targets[i].y,targets[i].w,targets[i].h);
    writef(&w, "]}");
    if (w.used >= w.cap) { out[0] = 0; return 0; }
    return w.used;
}
