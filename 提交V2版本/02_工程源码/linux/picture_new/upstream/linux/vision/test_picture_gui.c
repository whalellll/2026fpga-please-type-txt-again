/* Execute the actual GUI adapter with camera/display/engine boundaries
 * mocked. This checks orchestration, not Linux mmap or Pikafish strength. */
#include <assert.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <errno.h>
#ifdef _WIN32
#include <direct.h>
#else
#include <unistd.h>
#endif
#ifdef _WIN32
#include <windows.h>
static void test_pause(void) { Sleep(1); }
#else
#include <time.h>
static void test_pause(void) { struct timespec t={0,1000000}; (void)nanosleep(&t,NULL); }
#endif
#include "xq_picture.h"
#include "xq_camera.h"
#include "xq_picture_display.h"
#include "xq_picture_font.h"
#include "xiangqi_fb_gui.h"
#include "xiangqi_mouse_input.h"
#include "xiangqi_pikafish_link.h"
#include "xq_speech.h"
#define HID_STATUS 8u
#define GUI_TICKS_PER_MS 27000u
static uint32_t hid[16];
static volatile uint32_t *hid_regs = hid;
static volatile sig_atomic_t stop_requested;
static unsigned searches, captures, redraws;
static uint32_t mock_camera[32];
static int mock_background;
static int mock_capture_failure;
static unsigned stops;
static unsigned speech_calls;
static uint32_t speech_underflows;
static int release_search;
static int diagnostic_visible;
static const uint32_t *topview;
void xq_fb_gui_picture_topview(const uint32_t *p) {topview=p;}
static char feedback[128];
static char displayed_feedback[128];
static unsigned capture_statuses, inference_statuses;
static unsigned redraws_at_capture;
static int capture_was_background;
static uint64_t clock_calls;
static uint64_t monotonic_milliseconds(void) { return ++clock_calls; }
int xq_fb_gui_init(void) { ++redraws; return 1; }
int xq_fb_gui_show(const xq_search_board_t *b, int f, int t, int32_t score,
                    uint32_t n, uint32_t ticks, xq_fb_state_t state)
{ (void)b; (void)f; (void)t; (void)score; (void)n; (void)ticks; (void)state;
  snprintf(displayed_feedback,sizeof(displayed_feedback),"%s",feedback); return 1; }
void xq_fb_gui_set_red_win_rate(uint32_t p) { (void)p; }
static void supported_text(const char *text)
{
    const unsigned char *p=(const unsigned char *)text;
    if (!p) return;
    while (*p) {
        unsigned code=*p++,i;
        if (code<128) continue;
        assert((code&0xf0u)==0xe0u && p[0] && p[1]);
        code=((code&15u)<<12)|((p[0]&63u)<<6)|(p[1]&63u);
        p+=2;
        for (i=0;i<sizeof(xqp_glyphs)/sizeof(xqp_glyphs[0]);++i)
            if (xqp_glyphs[i].code==code) break;
        assert(i<sizeof(xqp_glyphs)/sizeof(xqp_glyphs[0]));
    }
}
void xq_fb_gui_picture_feedback(const char *a, const char *b, const char *c)
{ supported_text(a); supported_text(b); supported_text(c);
  snprintf(feedback, sizeof(feedback), "%s", a); }
void xq_fb_gui_picture_diagnostic(const uint32_t *p,const xqg_detection *d,
                                  const xqv_result *r,const xqp_metrics *m)
{ (void)d; (void)r; (void)m; diagnostic_visible=p!=NULL; }
int xqc_linux_open(xqc_linux *c, int (*cancel)(void *), void *context)
{ (void)cancel; (void)context;c->io.camera=mock_camera;c->io.background=mock_background;return 1; }
int xqc_linux_close(xqc_linux *c) { (void)c; return 0; }
int xqc_stop(xqc_camera *c) { (void)c;++stops;return 0; }
int xqs_linux_play(const xqs_phrase *p,const char *dir,unsigned volume,
                   int (*cancel_fn)(void *),void *context,uint32_t *underflows)
{ (void)p; (void)dir; (void)volume; (void)cancel_fn; (void)context;
  ++speech_calls; *underflows=speech_underflows; return 1; }
int xqc_capture(xqc_camera *c, uint32_t *p, size_t bytes, xqv_frame *f)
{
  assert(strstr(displayed_feedback,"正在拍摄"));
  redraws_at_capture=redraws;
  capture_was_background=c->background;
  ++capture_statuses;
  if(mock_capture_failure){p[0]=0xdeadbeef;return XQC_CANCELLED;}
  memset(p,0,bytes);
  f->rgb565=p; f->bytes=bytes; f->frame_id=++captures; f->captured_ms=1; return 0; }
static int test_recognize(void *path,const xqv_frame *f,xqv_result *r)
{
    assert(strstr(displayed_feedback,"正在识别"));
    assert(redraws==redraws_at_capture+(capture_was_background?0u:1u));
    ++inference_statuses;
    return xqv_stub_recognize(path,f,r);
}
static int request_black_move(xq_search_board_t *b, int32_t *score, uint32_t *rate,
                               uint32_t *nodes, uint32_t *ticks, char *best)
{
    (void)score; (void)rate; (void)nodes; (void)ticks;
    while (!__atomic_load_n(&release_search,__ATOMIC_ACQUIRE)) test_pause();
    ++searches;
    strcpy(best, "b9c7");
    return xq_pikafish_apply_move(b, best, NULL);
}
#define xqv_stub_recognize test_recognize
#include "xq_picture_gui.inc"
#undef xqv_stub_recognize
static void stub(const char *path, const xq_search_board_t *board, unsigned confidence)
{
    char fen[128];
    FILE *f = fopen(path, "w");
    assert(f && xq_pikafish_board_to_fen(board, fen, sizeof(fen)));
    assert(fprintf(f, "XQV_STUB_V1 %u\n%s\n", confidence, fen) > 0);
    assert(!fclose(f));
}
static xq_search_board_t model_board;
static unsigned model_bad;
static void *model_reply(void *unused)
{
    char request[600],response[600],tmp[600],magic[32],backend[64];
    unsigned long long token;unsigned frame,crc,i;
    xqv_result result;xqg_detection boxes[32];FILE *f;
    (void)unused;
    snprintf(request,sizeof(request),"%s/request.txt",picture_model_dir);
    snprintf(response,sizeof(response),"%s/result.txt",picture_model_dir);
    snprintf(tmp,sizeof(tmp),"%s/reply.part",picture_model_dir);
    for(i=0;i<10000 && !(f=fopen(request,"r"));i++)test_pause();
    assert(i<10000);
    assert(fscanf(f,"%31s %llu %u %x %63s",magic,&token,&frame,&crc,backend)==5);fclose(f);
    xqv_board_result(&model_board,frame,900,&result);xqg_stub_geometry(&result,boxes);
    f=fopen(tmp,"w");assert(f);
    fprintf(f,"XQ_MODEL_RESULT_V1 %llu %u %08x %s %u %u\n%s\n",token+(model_bad==2),frame,
        crc^(model_bad==1),model_bad==3?"WRONG_BACKEND":backend,model_bad==4?1:0,result.piece_count,result.fen);
    for(i=0;i<result.piece_count;i++)fprintf(f,"%u %u %u %u %u %u %u %u\n",
        result.pieces[i].class_id,result.pieces[i].file,result.pieces[i].rank,result.pieces[i].confidence,
        boxes[i].x0,boxes[i].y0,boxes[i].x1,boxes[i].y1);
    fputs("320 640\n832 640\n832 64\n320 64\n",f);assert(!fclose(f));assert(!rename(tmp,response));
    return NULL;
}
int main(int argc, char **argv)
{
    xq_search_board_t board, red;
    uint32_t rate=0, nodes=0, ticks=0;
    int32_t score=0;
    unsigned square, before;
    char calibration_path[512];
    assert(argc == 2);
    hid_regs=NULL;
    assert(!picture_cancel(NULL)); /* live loader handoff precedes HID mmap */
    hid_regs=hid;
    before=(unsigned)clock_calls;
    assert(!picture_cancel(NULL) && clock_calls==before);
    assert(xqv_parse_fen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1", &board));
    picture_stub = argv[1];
    picture_pixels = malloc(XQV_FRAME_BYTES);
    assert(picture_pixels);
    /* Exercise the real open call site: only an acknowledged private-bank
     * session can survive the first GUI draw without a sensor reset. */
#ifdef _WIN32
    assert(!_putenv_s("XQ_PICTURE_MODE","roi-preview"));
#else
    assert(!setenv("XQ_PICTURE_MODE","roi-preview",1));
#endif
    free(picture_pixels);picture_pixels=NULL;
    mock_background=0;stops=0;
    assert(picture_open() && stops==1);free(picture_pixels);picture_pixels=NULL;
    mock_background=1;stops=0;mock_camera[CAMERA_REG_CONTROL/4]=1;
    assert(picture_open() && stops==1);free(picture_pixels);picture_pixels=NULL;
    stops=0;mock_camera[CAMERA_REG_CONTROL/4]=9;
    mock_camera[CAMERA_REG_STATUS/4]=CAMERA_STATUS_BACKGROUND_ACTIVE|15;
    assert(picture_open() && stops==0);free(picture_pixels);picture_pixels=NULL;
    picture_preview_only=0;picture_enabled=0;mock_background=0;
    picture_camera.io.background=0;
    picture_stub=argv[1];
    picture_pixels=malloc(XQV_FRAME_BYTES);assert(picture_pixels);
    (void)picture_poll_key; /* report-pair semantics have a separate test */
    snprintf(calibration_path,sizeof(calibration_path),"%s.calibration",argv[1]);
    picture_calibration_path=calibration_path;
    picture_reset(&board);
    assert(picture_needs_calibration && strstr(feedback,"摆好开局"));
    stub(argv[1],&board,900);
    picture_step(&board,1,&score,&rate,&nodes,&ticks);
    assert(!picture_needs_calibration && !searches && picture_grid.valid);
    assert(!picture_diagnostic && !diagnostic_visible);
    assert(capture_statuses==1 && inference_statuses==1);
    assert(redraws==redraws_at_capture+1 && strstr(displayed_feedback,"识别成功"));
    assert(picture_metrics.comparisons==1 && picture_metrics.matches==1);
    picture_camera.io.background=1;
    red = board;
    assert(xq_pikafish_apply_move(&red, "h2e2", NULL));
    stub(argv[1], &red, 799);
    picture_step(&board, 1, &score, &rate, &nodes, &ticks);
    assert(!searches && picture_game.phase == XQP_RED);
    assert(strstr(feedback, "不确定"));
    stub(argv[1], &red, 900);
    picture_step(&board, 1, &score, &rate, &nodes, &ticks);
    assert(picture_search.active && picture_game.phase==XQP_ENGINE && !searches);
    assert(!picture_diagnostic && !diagnostic_visible);
    assert(redraws==redraws_at_capture && strstr(displayed_feedback,"识别成功"));
    assert(picture_key('r',&board,1,&score,&rate,&nodes,&ticks));
    assert(diagnostic_visible && picture_game.phase==XQP_ENGINE);
    before=captures;
    assert(picture_key(32,&board,1,&score,&rate,&nodes,&ticks) && captures==before);
    __atomic_store_n(&release_search,1,__ATOMIC_RELEASE);
    for (square=0; square<1000 && !__atomic_load_n(&picture_search.done,__ATOMIC_ACQUIRE); ++square) test_pause();
    assert(__atomic_load_n(&picture_search.done,__ATOMIC_ACQUIRE));
    picture_finish_search(&board,&score,&rate,&nodes,&ticks);
    assert(searches == 1 && picture_game.phase == XQP_BLACK);
    assert(picture_key('r',&board,1,&score,&rate,&nodes,&ticks));
    assert(!diagnostic_visible);
    assert(strstr(feedback, "请把黑方马从b9走到c7"));
    assert(picture_key('r',&board,1,&score,&rate,&nodes,&ticks));
    assert(diagnostic_visible && picture_game.phase==XQP_BLACK);
    stub(argv[1],&picture_game.expected,900);
    assert(picture_key(32,&board,1,&score,&rate,&nodes,&ticks));
    assert(picture_game.phase==XQP_BLACK && searches==1);
    assert(picture_key('c',&board,1,&score,&rate,&nodes,&ticks));
    assert(picture_game.phase==XQP_BLACK && searches==1 && !picture_needs_calibration);
    assert(picture_key('r',&board,1,&score,&rate,&nodes,&ticks));
    assert(!diagnostic_visible && picture_game.phase==XQP_BLACK);
    stub(argv[1],&red,900);
    picture_step(&board, 1, &score, &rate, &nodes, &ticks);
    assert(picture_game.failures == 1 && picture_game.phase == XQP_BLACK);
    picture_step(&board, 1, &score, &rate, &nodes, &ticks);
    assert(picture_game.phase == XQP_MANUAL);
    /* Drive the existing screen-to-square hit test and real edit cycling. */
    for (square=0; square<90; ++square) {
        unsigned attempts=0;
        uint32_t x=XQ_FB_BOARD_X + (square % 9) * XQ_FB_CELL;
        uint32_t y=XQ_FB_BOARD_Y + (9 - square / 9) * XQ_FB_CELL;
        while (picture_game.observed.squares[square] != picture_game.expected.squares[square]) {
            assert(attempts++ < 15);
            assert(picture_mouse(&board, x | (y << 11), 1) == 1);
            assert(picture_mouse(&board, x | (y << 11), 0) == 0);
        }
    }
    before=captures;
    picture_step(&board, 1, &score, &rate, &nodes, &ticks);
    assert(captures == before && picture_game.phase == XQP_RED && searches == 1);
    assert(strstr(displayed_feedback,"手动确认成功"));
    assert(redraws==redraws_at_capture); /* background snapshots never invalidate GUI pages */
    assert(picture_mouse(&board, XQ_FB_RESTART_X | (XQ_FB_RESTART_Y << 11), 1) == 2);
    picture_reset(&red);
    assert(picture_game.phase == XQP_RED && picture_game.failures == 0);
    /* Three calibration failures preserve the game and offer four corners.
     * Simulate unavailable persistence, then recover it for manual approval. */
    assert(xqv_parse_fen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",&board));
    picture_reset(&board); stub(argv[1],&board,900);
    picture_calibration_path="build/picture-host-tests/missing/calibration";
    for (square=0; square<3; ++square) picture_step(&board,1,&score,&rate,&nodes,&ticks);
    assert(picture_diagnostic && picture_metrics.calibrating && picture_needs_calibration);
    picture_calibration_path=calibration_path;
    {
        const unsigned points[4][2]={{320,640},{832,640},{832,64},{320,64}};
        for (square=0; square<4; ++square) {
            uint32_t xy=(XQP_IMAGE_X+points[square][0]/2)|((XQP_IMAGE_Y+points[square][1]/2)<<11);
            picture_buttons=0;
            assert(picture_mouse(&board,xy,1)==1);
        }
    }
    assert(!picture_needs_calibration && !picture_metrics.calibrating && picture_game.phase==XQP_RED);
    before=redraws;
    picture_camera.io.poisoned=1;
    assert(!picture_exit_frame(&board) && redraws==before);
    picture_camera.io.poisoned=0;
    assert(picture_exit_frame(&board) && strstr(feedback,"已退出"));
    {
        xqs_phrase phrase={{XQS_WELCOME},1};
        picture_voice_mode=2; speech_underflows=2;
        picture_say(&phrase,0);
        assert(picture_voice_mode==2 && speech_calls==1);
        speech_underflows=3;
        picture_say(&phrase,0);
        assert(picture_voice_mode==1 && speech_calls==2);
        picture_say(&phrase,0); assert(speech_calls==2);
        picture_say(&phrase,1); assert(picture_voice_mode==0 && speech_calls==3);
    }
    assert(picture_key(27,&board,1,&score,&rate,&nodes,&ticks) && stop_requested);
    stop_requested=0;picture_preview_only=1;picture_voice_mode=0;
    picture_reset(&red);board=red;
    assert(!picture_needs_calibration);
    before=searches;
    picture_step(&board,1,&score,&rate,&nodes,&ticks);
    assert(searches==before && !memcmp(board.squares,red.squares,90));
    assert(picture_metrics.preview_only && !picture_result.abi_version && !picture_diagnostic);
    assert(picture_key('r',&board,1,&score,&rate,&nodes,&ticks));
    assert(picture_key('c',&board,1,&score,&rate,&nodes,&ticks));
    assert(picture_metrics.calibrating);
    {
        const unsigned corners[4][2]={{200,650},{1000,650},{1000,50},{200,50}};
        for(square=0;square<4;square++) {
            uint32_t xy=(XQP_IMAGE_X+corners[square][0]/2)|((XQP_IMAGE_Y+corners[square][1]/2)<<11);
            picture_buttons=0;assert(picture_mouse(&board,xy,1)==1);
        }
    }
    assert(!picture_metrics.calibrating && picture_metrics.manual_geometry && topview);
    assert(searches==before && !picture_result.abi_version);
    /* Mock transport only: strict identity rejection and first-frame/new-move
     * orchestration use the actual model IPC, never model accuracy evidence. */
    {
        char directory[512],path[600];pthread_t worker;
        snprintf(directory,sizeof(directory),"%s.model",argv[1]);
#ifdef _WIN32
        assert(!_mkdir(directory) || errno==EEXIST);
#else
        assert(!mkdir(directory,0700) || errno==EEXIST);
#endif
        picture_model_dir=directory;picture_model_backend="pc-quantized-mac";
        picture_preview_only=0;picture_model_mode=1;picture_voice_mode=0;
        assert(xqv_parse_fen("rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1",&board));
        memset(picture_pixels,0,XQV_FRAME_BYTES);picture_reset(&board);model_board=board;
        assert(!picture_needs_calibration && strstr(feedback,"按空格开始"));
        for(model_bad=1;model_bad<=4;model_bad++) {
            assert(!pthread_create(&worker,NULL,model_reply,NULL));
            picture_step(&board,1,&score,&rate,&nodes,&ticks);assert(!pthread_join(worker,NULL));
            assert(!picture_started && !picture_search.active);
        }
        model_bad=0;assert(!pthread_create(&worker,NULL,model_reply,NULL));
        picture_step(&board,1,&score,&rate,&nodes,&ticks);assert(!pthread_join(worker,NULL));
        assert(picture_started && !picture_result.is_stub && !picture_metrics.is_stub && !picture_search.active);
        assert(picture_key('r',&board,1,&score,&rate,&nodes,&ticks) && topview);
        {
            const xqg_detection *d=&picture_display_boxes[0];
            uint32_t xy=(XQP_IMAGE_X+(d->x0+d->x1)/4)|((XQP_IMAGE_Y+(d->y0+d->y1)/4)<<11);
            picture_buttons=0;assert(picture_mouse(&board,xy,2)==1);
            assert(picture_game.phase==XQP_RED && !memcmp(board.squares,model_board.squares,90));
        }
        for(unsigned i=0;i<picture_result.piece_count;i++) {
            assert(picture_display_boxes[i].x0>=320 && picture_display_boxes[i].x1<=958);
            assert(picture_display_boxes[i].y0<=718 && picture_display_boxes[i].y1<=718);
        }
        before=captures;
        assert(picture_key('c',&board,1,&score,&rate,&nodes,&ticks));
        assert(captures==before && !picture_calibration_request && !picture_metrics.calibrating);
        mock_capture_failure=1;
        picture_step(&board,1,&score,&rate,&nodes,&ticks);
        assert(picture_metrics.has_frame && topview && picture_manual.grid.valid);
        assert(picture_pixels[0]==0 && picture_result.piece_count==32);
        mock_capture_failure=0;
        model_bad=1;assert(!pthread_create(&worker,NULL,model_reply,NULL));
        picture_step(&board,1,&score,&rate,&nodes,&ticks);assert(!pthread_join(worker,NULL));
        assert(picture_started && picture_metrics.has_frame && !picture_result.piece_count);
        assert(!topview && !picture_manual.grid.valid && !memcmp(board.squares,model_board.squares,90));
        model_bad=0;
        assert(picture_key('r',&board,1,&score,&rate,&nodes,&ticks));
        assert(xq_pikafish_apply_move(&model_board,"h2e2",NULL));
        assert(!pthread_create(&worker,NULL,model_reply,NULL));
        picture_step(&board,1,&score,&rate,&nodes,&ticks);assert(!pthread_join(worker,NULL));
        assert(picture_search.active && picture_game.phase==XQP_ENGINE);picture_join_search();
        assert(picture_key('r',&board,1,&score,&rate,&nodes,&ticks) && topview);
        assert(picture_exit_frame(&board) && picture_diagnostic && topview);
        assert(strstr(feedback,"已退出"));
        snprintf(path,sizeof(path),"%s/frame.rgb565",directory);remove(path);
#ifdef _WIN32
        _rmdir(directory);
#else
        rmdir(directory);
#endif
    }
    remove(argv[1]);
    remove(calibration_path);
    free(picture_pixels);
    free(picture_capture_pixels);
    free(picture_topview);
    puts("XQ_PICTURE_GUI_TEST_PASS mock-camera L1 search-once black-prompt L2 mouse-edit restart");
    return 0;
}
