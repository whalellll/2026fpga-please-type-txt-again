#define _POSIX_C_SOURCE 200809L
#include "xinyi_product.h"
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef XINYI_HOST_PREVIEW
volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];
#endif

/* Synthetic-only adapter. No camera, speech recognizer, engine or benchmark is
 * invoked. It exercises the production controller and actual RGB565 renderer.
 * A permanent host-preview banner is added by the server and framebuffer. */
typedef struct {
    xy_app app;
    unsigned scenario;
    uint64_t started;
    uint64_t capture_started;
    uint16_t *pixels;
} host_app;
static uint64_t now_ms(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) return 0;
    return (uint64_t)t.tv_sec * 1000u + (unsigned)t.tv_nsec / 1000000u;
}
static int mic(void *context, int enabled) { (void)context; (void)enabled; return 1; }
static int accept(void *context, uint32_t token)
{
    host_app *h = context;
    (void)token;
    h->started = now_ms();
    return 1;
}
static int recommend(void *context, uint32_t token, const xq_search_board_t *b)
{ (void)b; return accept(context, token); }
static int capture_start(void *context, uint32_t token)
{
    host_app *h=context;
    int accepted=accept(context,token);
    h->capture_started=h->started;
    return accepted;
}
static int voice(void *context, uint32_t token, const char *text)
{ (void)text; return accept(context, token); }
static int benchmark(void *context, uint32_t token, unsigned target)
{ (void)target; return accept(context, token); }
static void cancel(void *context, xy_job job, uint32_t token)
{ (void)job; (void)token; ((host_app *)context)->started = now_ms(); }
static void speak(void *context,const char *text)
{ (void)text;((host_app *)context)->started=now_ms(); }
static void initial(xq_search_board_t *b)
{
    static const uint8_t back[9] = {PIECE_R, PIECE_N, PIECE_B, PIECE_A, PIECE_K,
                                   PIECE_A, PIECE_B, PIECE_N, PIECE_R};
    unsigned i;
    memset(b, 0, sizeof(*b));
    for (i = 0; i < 9; ++i) {
        b->squares[i] = back[i]; b->squares[81+i] = back[i] | SIDE_BLACK;
    }
    for (i = 0; i < 9; i += 2) {
        b->squares[27+i] = PIECE_P;
        b->squares[54+i] = PIECE_P | SIDE_BLACK;
    }
    b->squares[19] = b->squares[25] = PIECE_C;
    b->squares[64] = b->squares[70] = PIECE_C | SIDE_BLACK;
}
static unsigned synthetic(host_app *h, xy_detection *d)
{
    unsigned n = 0, i;
    xq_search_board_t b;
    initial(&b);
    if (h->scenario == 3) b.squares[85] = 0;
    for (i = 0; i < 90; ++i) if (b.squares[i]) {
        uint8_t p = b.squares[i];
        d[n].class_id = (uint8_t)((p & 7u)-1u + ((p & SIDE_BLACK) ? 7u : 0u));
        d[n].file = i % 9; d[n].rank = i / 9; d[n].confidence = 964;
        ++n;
    }
    if (h->scenario == 1) d[n++] = (xy_detection){4, 4, 4, 203};
    if (h->scenario == 2) d[n++] = (xy_detection){11, 0, 3, 110};
    return n;
}
xy_app *xy_host_create(void)
{
    host_app *h = calloc(1, sizeof(*h));
    xy_backend b;
    if (!h) return NULL;
    memset(&b, 0, sizeof(b));
    b.context = h; b.microphone = mic; b.capture = capture_start; b.recommend = recommend;
    b.voice_command = voice; b.coremark = benchmark; b.cancel = cancel; b.speak=speak;
    xy_app_init(&h->app, &b);
    return &h->app;
}
void xy_host_destroy(xy_app *a)
{
    if(a) { free(((host_app *)a)->pixels); free(a); }
}
size_t xy_host_rgb888(xy_app *a,unsigned char *out,size_t capacity)
{
    host_app *h=(host_app *)a;
    unsigned i;
    if(!a || !out || capacity<1920u*1080u*3u) return 0;
    if(!h->pixels)h->pixels=calloc(1920u*1080u,2);
    if(!h->pixels)return 0;
    xy_fb_render(a,h->pixels);
    for(i=0;i<1920u*1080u;++i) {
        unsigned p=h->pixels[i];
        out[i*3]=(unsigned char)(((p>>11)*255+15)/31);
        out[i*3+1]=(unsigned char)((((p>>5)&63)*255+31)/63);
        out[i*3+2]=(unsigned char)(((p&31)*255+15)/31);
    }
    return 1920u*1080u*3u;
}
int xy_host_event(xy_app *a, const char *event)
{
    host_app *h = (host_app *)a;
    uint64_t elapsed;
    if (!a || !event) return 0;
    if (!strcmp(event, "start")) return xy_navigate(a, XY_GAME, XY_COACH);
    if (!strcmp(event, "home")) return xy_navigate(a, XY_HOME, a->mode);
    if (!strcmp(event, "coach")) return xy_navigate(a, XY_GAME, XY_COACH);
    if (!strcmp(event, "voice")) return xy_navigate(a, XY_GAME, XY_VOICE);
    if (!strcmp(event, "capture")) return xy_capture_begin(a);
    if (!strcmp(event, "cancel")) return xy_cancel(a);
    if (!strcmp(event, "coremark")) return xy_coremark_begin(a, XY_COREMARK_MOCK);
    if (!strcmp(event, "coremark-reference")) return xy_coremark_begin(a, XY_COREMARK_REFERENCE);
    if (!strcmp(event, "coremark-log")) return xy_coremark_log_action(a,XY_ACTION_CM_LOG);
    if (!strcmp(event, "coremark-log-close")) return xy_coremark_log_action(a,XY_ACTION_CM_LOG_CLOSE);
    if (!strcmp(event, "coremark-log-prev")) return xy_coremark_log_action(a,XY_ACTION_CM_LOG_PREV);
    if (!strcmp(event, "coremark-log-next")) return xy_coremark_log_action(a,XY_ACTION_CM_LOG_NEXT);
    if (!strcmp(event, "say")) return xy_voice_begin(a, "炮二平五");
    if (!strcmp(event, "say-invalid")) return xy_voice_begin(a, "无法解析的合成命令");
    if (!strncmp(event, "scenario-", 9)) {
        const char *s = event + 9;
        if (!strcmp(s, "valid")) h->scenario = 0;
        else if (!strcmp(s, "third-rook")) h->scenario = 1;
        else if (!strcmp(s, "duplicate")) h->scenario = 2;
        else if (!strcmp(s, "missing-king")) h->scenario = 3;
        else if (!strcmp(s, "geometry-failure")) h->scenario = 4;
        else return 0;
        return 1;
    }
    if (strcmp(event, "tick")) return 0;
    elapsed = now_ms() - h->started;
    if (a->cancelling) {
        if (elapsed >= 100) return xy_cancel_complete(a, a->token);
        return 1;
    }
    if (a->job == XY_CAPTURE && elapsed >= 450) {
        xy_detection d[34];
        unsigned n = synthetic(h, d);
        return xy_capture_complete(a, a->token, h->scenario != 4, d, n,
                                   (unsigned)elapsed);
    }
    if (a->job == XY_RECOMMEND && elapsed >= 220) {
        int result=xy_recommend_complete(a, a->token, 1,
                    (xq_search_move_t){25, 22}, "炮二平五");
        (void)xy_photo_elapsed(a,a->token,(unsigned)(now_ms()-h->capture_started));
        return result;
    }
    if (a->job == XY_VOICE_COMMAND && elapsed >= 500) {
        int okay = !strcmp(a->voice_heard, "炮二平五");
        xq_search_board_t b;
        initial(&b);
        if (okay) {
            b.squares[25] = 0; b.squares[22] = PIECE_C;
            b.squares[88] = 0; b.squares[69] = PIECE_N | SIDE_BLACK;
        }
        return xy_voice_complete(a, a->token, okay, &b, okay ?
            "合成走法已执行；电脑马八进七（模拟）" : "合成命令未能解析", (unsigned)elapsed);
    }
    if (a->job == XY_ANNOUNCE && elapsed >= 180) {
        (void)xy_photo_elapsed(a,a->token,(unsigned)(now_ms()-h->capture_started));
        return xy_announce_complete(a,a->token,1);
    }
    if (a->job == XY_COREMARK) {
        if(a->coremark_origin==XY_COREMARK_REFERENCE){
            unsigned ms=elapsed>=10000?10000:(unsigned)elapsed;
            (void)xy_coremark_progress(a,a->token,ms,ms/10);
            if(ms>=10000)return xy_coremark_reference_complete(a,a->token);
            return 1;
        }
        unsigned p = elapsed >= 4500 ? 1000 : (unsigned)(elapsed * 1000 / 4500);
        (void)xy_coremark_progress(a, a->token, (unsigned)elapsed, p);
        if (elapsed >= 4500)
            return xy_coremark_complete(a, a->token, 0, 0, 0, 0, 0, NULL);
    }
    return 1;
}
