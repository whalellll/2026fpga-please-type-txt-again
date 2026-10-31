/* Included after the Linux GUI engine adapter. This keeps the existing
 * embedded/child-engine lifecycle and FIFO owner in a single process. */
#include "xq_picture.h"
#include "xq_camera.h"
#include "xq_camera_retry.h"
#include "xq_picture_display.h"
#include "xq_speech.h"
#include "xq_roi.h"
#include <pthread.h>
#include <math.h>
#ifdef _WIN32
/* Host adapter tests need the same replace-existing semantics as POSIX
 * rename(). The board build never includes Windows headers. */
#include <windows.h>
#endif

static int picture_enabled;
static int picture_preview_only;
static int picture_model_mode;
static unsigned picture_model_geometry_manual;
static const char *picture_model_backend;
static xqr_manual picture_manual;
static uint32_t *picture_topview;
static uint64_t picture_preview_capture,picture_preview_view,picture_topview_capture,picture_topview_view;
static xqp_game picture_game;
static xqc_linux picture_camera;
static uint32_t *picture_pixels;
static uint32_t *picture_capture_pixels;
static const char *picture_stub;
static uint8_t picture_buttons;
static xqp_hid picture_keyboard;
static xqp_hid picture_cancel_keyboard;
static uint64_t picture_trigger_ms;
static int picture_busy_notice;
static int picture_diagnostic, picture_needs_calibration, picture_calibration_request;
static unsigned picture_calibration_failures, picture_corner_count;
static double picture_corners[4][2];
static xqg_grid picture_grid;
static xqg_detection picture_boxes[32];
static xqg_detection picture_display_boxes[32];
static xqv_result picture_result;
static xqp_metrics picture_metrics;
static const char *picture_calibration_path = "/run/xq-picture.calibration";
static const char *picture_pcm = "/opt/xq-picture/pcm";
static unsigned picture_voice_mode, picture_voice_volume=10, picture_started;
/* Per spoken phrase: two missing 16 kHz samples = 0.125 ms. Keep the raw
 * counter visible; larger gaps still invoke full -> moves -> off. */
enum { PICTURE_SPEECH_MAX_UNDERFLOWS = 2 };
static struct {
    pthread_t thread;
    xq_search_board_t board;
    int32_t score;
    uint32_t rate,nodes,ticks;
    char bestmove[8];
    int active,done,result;
} picture_search;
static void picture_discard_input(void);
static int picture_cancel(void *);

static void *picture_search_worker(void *ignored)
{
    (void)ignored;
    picture_search.result=request_black_move(&picture_search.board,&picture_search.score,
        &picture_search.rate,&picture_search.nodes,&picture_search.ticks,picture_search.bestmove);
    __atomic_store_n(&picture_search.done,1,__ATOMIC_RELEASE);
    return NULL;
}

static void picture_join_search(void)
{
    if (picture_search.active) {
        (void)pthread_join(picture_search.thread,NULL);
        picture_search.active=0;
    }
}

static void picture_say(const xqs_phrase *phrase,int move)
{
    uint32_t underflows=0;
    int okay;
    if (!picture_voice_mode || (!move && picture_voice_mode<2)) return;
    okay=xqs_linux_play(phrase,picture_pcm,picture_voice_volume,picture_cancel,NULL,&underflows);
    printf("XQ_PICTURE_SPEECH mode=%u okay=%d underflows=%u limit=%u volume=%u\n",
        picture_voice_mode,okay,underflows,PICTURE_SPEECH_MAX_UNDERFLOWS,picture_voice_volume);
    if (!okay || underflows>PICTURE_SPEECH_MAX_UNDERFLOWS) {
        picture_voice_mode=picture_voice_mode==2?1:0;
        printf("XQ_PICTURE_SPEECH_DEGRADED next=%s reason=%s\n",
            picture_voice_mode?"AI_MOVES_ONLY":"OFF",okay?"underflow":"playback-failed");
    }
    picture_discard_input();
}

static void picture_diagnostic_update(void)
{
    const uint32_t *view=NULL;
    picture_metrics.is_stub = !picture_preview_only && !picture_model_mode;
    picture_metrics.preview_only=picture_preview_only;
    picture_metrics.model_backend=picture_model_mode?(!strcmp(picture_model_backend,"pc-quantized-mac")?1:2):0;
    picture_metrics.manual_geometry=(picture_preview_only || (picture_model_mode && picture_model_geometry_manual)) && picture_manual.grid.valid;
    if((picture_preview_only || picture_model_mode) && picture_diagnostic && picture_metrics.has_frame &&
       !picture_metrics.calibrating && picture_manual.grid.valid) {
        if(!picture_topview)picture_topview=malloc(320u*360u*2u);
        if(picture_topview && (picture_topview_capture!=picture_preview_capture || picture_topview_view!=picture_preview_view)) {
            xqv_frame f={picture_pixels,XQV_FRAME_BYTES,picture_result.frame_id,0};
            if(xqr_rectify(&picture_manual,&f,picture_topview,320,360,320u*360u*2u)) {
                picture_topview_capture=picture_preview_capture;picture_topview_view=picture_preview_view;
            }
        }
        if(picture_topview && picture_topview_capture==picture_preview_capture && picture_topview_view==picture_preview_view)view=picture_topview;
    }
    memcpy(picture_display_boxes,picture_boxes,sizeof(picture_boxes));
    if(view)for(unsigned i=0;i<picture_result.piece_count && i<32;i++) {
        const double *h=picture_manual.grid.h;
        double lo_x=320,lo_y=360,hi_x=0,hi_y=0;
        for(unsigned corner=0;corner<4;corner++) {
            double x=corner&1?picture_boxes[i].x1:picture_boxes[i].x0;
            double y=corner&2?picture_boxes[i].y1:picture_boxes[i].y0;
            double a=h[0]-x*h[6],b=h[1]-x*h[7],c=x-h[2];
            double d=h[3]-y*h[6],e=h[4]-y*h[7],f=y-h[5],det=a*e-b*d;
            if(det==0)continue;
            double file=(c*e-b*f)/det,rank=(a*f-c*d)/det;
            double px=fmin(319,fmax(0,file*319/8)),py=fmin(359,fmax(0,(9-rank)*359/9));
            lo_x=fmin(lo_x,px);hi_x=fmax(hi_x,px);lo_y=fmin(lo_y,py);hi_y=fmax(hi_y,py);
        }
        if(hi_x>=lo_x && hi_y>=lo_y) {
            /* Renderer uses half-size raw coordinates. These coordinates are
             * display-only; recognition boxes and their original centres stay intact. */
            picture_display_boxes[i].x0=(uint16_t)(2*(160+lo_x));
            picture_display_boxes[i].x1=(uint16_t)(2*(160+hi_x));
            picture_display_boxes[i].y0=(uint16_t)(2*lo_y);
            picture_display_boxes[i].y1=(uint16_t)(2*hi_y);
        }
    }
    xq_fb_gui_picture_topview(view);
    picture_metrics.corner_count = picture_corner_count;
    xq_fb_gui_picture_diagnostic(picture_diagnostic ? picture_pixels : NULL,
        picture_display_boxes, &picture_result, &picture_metrics);
}

static int picture_save_calibration(void)
{
    char temporary[512];
    FILE *file;
    unsigned i;
    int okay=1;
    if (snprintf(temporary,sizeof(temporary),"%s.tmp",picture_calibration_path)>=(int)sizeof(temporary)) return 0;
    file=fopen(temporary,"w");
    if (!file) return 0;
    if (fprintf(file,"XQG1 STUB SYNTHETIC_GEOMETRY\n")<0) okay=0;
    for (i=0; i<8; ++i) if (fprintf(file,"%.17g\n",picture_grid.h[i])<0) okay=0;
    if (fclose(file)) okay=0;
    if (!okay) { remove(temporary); return 0; }
#ifdef _WIN32
    if (!MoveFileExA(temporary,picture_calibration_path,MOVEFILE_REPLACE_EXISTING)) {
#else
    if (rename(temporary,picture_calibration_path)) {
#endif
        remove(temporary); return 0;
    }
    return 1;
}

static const xq_search_board_t *picture_reference(void)
{
    return picture_game.phase==XQP_BLACK ||
        (picture_game.phase==XQP_MANUAL && picture_game.resume_phase==XQP_BLACK)
        ? &picture_game.expected : &picture_game.confirmed;
}

static int picture_confident(void)
{
    unsigned i;
    if (picture_result.confidence<picture_game.threshold) return 0;
    for (i=0; i<picture_result.piece_count; ++i)
        if (picture_result.pieces[i].confidence<picture_game.threshold) return 0;
    return 1;
}

static void picture_count_reference(const xq_search_board_t *reference)
{
    xq_search_board_t observed;
    if (!picture_confident()) { ++picture_metrics.uncertain; return; }
    if (!xqv_result_board(&picture_result,picture_result.frame_id,&observed)) {
        ++picture_metrics.invalid; return;
    }
    ++picture_metrics.comparisons;
    if (!memcmp(observed.squares,reference->squares,90)) ++picture_metrics.matches;
}

static void picture_discard_input(void)
{
    if (!hid_regs) return;
    uint32_t count = hid_regs[0x18u / 4u];
    if (count != picture_keyboard.last_frame && !picture_busy_notice) {
        puts("XQ_PICTURE_BUSY keyboard reports ignored; one photo at a time");
        picture_busy_notice = 1;
    }
    xqp_hid_init(&picture_keyboard, count, monotonic_milliseconds());
    picture_buttons = (uint8_t)(hid_regs[HID_STATUS >> 2] & 7u);
}

static int picture_cancel(void *ignored)
{
    uint32_t before,after,packed;
    (void)ignored;
    if (!hid_regs) return stop_requested!=0;
    before=hid_regs[0x18u/4u]; packed=hid_regs[0x14u/4u]; after=hid_regs[0x18u/4u];
    /* No pending report pair and no new reports: no clock syscall or input
     * reset is needed in the 1 ms audio FIFO loop. Pending pairs still need
     * the existing 250 ms quiet/2 s timeout checks. */
    if (before==after && after==picture_cancel_keyboard.last_frame &&
        !picture_cancel_keyboard.pending_reports) return stop_requested!=0;
    if (before==after && xqp_hid_poll_key(&picture_cancel_keyboard,after,packed,
            monotonic_milliseconds())==27) stop_requested=1;
    picture_discard_input();
    return stop_requested != 0;
}

static const char *picture_backend_label(void);
typedef struct {const xq_search_board_t *board;int32_t score;uint32_t nodes,ticks;} picture_capture_progress;
static void picture_capture_retry(void *context,unsigned attempt,int result,uint32_t status)
{
    const picture_capture_progress *p=context;char note[64];
    if(!result || picture_camera.io.poisoned || stop_requested)return;
    if(attempt<=3 || attempt%10==0) {
        printf("XQ_PICTURE_CAPTURE_RETRY attempt=%u code=%d status=%08x\n",attempt,result,status);fflush(stdout);
    }
    if(result!=XQC_START && result!=XQC_HOLD && result!=XQC_CHANGED)return;
    snprintf(note,sizeof(note),"AUTO RETRY %u  ESC CANCEL",attempt);
    xq_fb_gui_picture_feedback("正在拍摄 请稍候",note,picture_backend_label());
    if(!picture_camera.io.background)(void)xq_fb_gui_init();
    if(!xq_fb_gui_show(p->board,-1,-1,p->score,p->nodes,p->ticks,XQ_FB_STATE_READY))stop_requested=1;
}

#include "xq_picture_model.inc"

static int picture_open(void)
{
    const char *mode = getenv("XQ_PICTURE_MODE");
    if (!mode || !mode[0] || !strcmp(mode, "off")) return 1;
    picture_preview_only=!strcmp(mode,"roi-preview");
    picture_model_mode=!strcmp(mode,"model-experimental");
    if (strcmp(mode, "stub") && !picture_preview_only && !picture_model_mode) {
        fputs("XQ_PICTURE_FAIL model runtime requires an accepted training package; no fallback\n", stderr);
        return 0;
    }
    picture_stub = getenv("XQ_PICTURE_STUB");
    {
        const char *voice=getenv("XQ_PICTURE_VOICE"), *pcm=getenv("XQ_PICTURE_PCM");
        const char *volume=getenv("XQ_PICTURE_VOLUME");
        picture_voice_mode=voice && !strcmp(voice,"full")?2:voice && !strcmp(voice,"moves")?1:0;
        if (pcm && pcm[0]) picture_pcm=pcm;
        if (volume && atoi(volume)>=1 && atoi(volume)<=100) picture_voice_volume=(unsigned)atoi(volume);
    }
    if(picture_model_mode) {
        const char *timeout=getenv("XQ_MODEL_TIMEOUT_SECONDS");
        picture_model_timeout_ms=900000;
        if(timeout && timeout[0]) {
            char *end;unsigned long seconds=strtoul(timeout,&end,10);
            if(*end || seconds<5 || seconds>7200) {
                fputs("XQ_PICTURE_FAIL model timeout must be 5..7200 seconds\n",stderr);return 0;
            }
            picture_model_timeout_ms=(uint64_t)seconds*1000;
        }
        picture_model_backend=getenv("XQ_MODEL_BACKEND");picture_model_dir=getenv("XQ_MODEL_DIRECTORY");
        if(!picture_model_dir || !picture_model_dir[0] || !picture_model_backend ||
           (strcmp(picture_model_backend,"pc-fp32") && strcmp(picture_model_backend,"pc-quantized-mac") &&
            strcmp(picture_model_backend,"rv32-driver-quantized-mac"))) {
            fputs("XQ_PICTURE_FAIL explicit model worker backend/directory required\n",stderr);return 0;
        }
        picture_model_token=monotonic_milliseconds()*1000u;
    }
    if (!picture_preview_only && !picture_model_mode && (!picture_stub || !picture_stub[0])) {
        fputs("XQ_PICTURE_FAIL explicit XQ_PICTURE_STUB path required\n", stderr);
        return 0;
    }
    picture_pixels = malloc(XQV_FRAME_BYTES);
    if (!picture_pixels || !xqc_linux_open(&picture_camera, picture_cancel, NULL)) {
        fputs("XQ_PICTURE_FAIL camera owner or snapshot reservation unavailable\n", stderr);
        free(picture_pixels);
        picture_pixels = NULL;
        return 0;
    }
    /* Legacy capture shares GUI banks and must drain before drawing. A
     * committed private-bank session can stay warm across the Linux handoff. */
    if (!(picture_camera.io.background &&
          (picture_camera.io.camera[CAMERA_REG_CONTROL/4u]&CAMERA_CONTROL_BACKGROUND) &&
          (picture_camera.io.camera[CAMERA_REG_STATUS/4u]&CAMERA_STATUS_BACKGROUND_ACTIVE)) &&
        xqc_stop(&picture_camera.io)) {
        (void)xqc_linux_close(&picture_camera);
        free(picture_pixels);
        picture_pixels = NULL;
        return 0;
    }
    picture_enabled = 1;
    printf("XQ_PICTURE_MODE %s abi=1 threshold=%u DEVELOPMENT_ONLY camera=%s\n",
        picture_model_mode?picture_model_backend:picture_preview_only?"roi-preview NO_MODEL":"stub",
        picture_model_mode?50u:800u,
        picture_camera.io.background?"background":"legacy-preview");
    return 1;
}

static void picture_prompt(void)
{
    char move[128];
    if(picture_preview_only) {
        xq_fb_gui_picture_feedback(picture_diagnostic?"图像诊断":"按空格拍摄",
            picture_metrics.calibrating?"红方左下 右下 右上 左上":"R返回对弈 C棋盘校准",
            "ROI PREVIEW ONLY - MODEL NOT LOADED");
        return;
    }
    if(picture_model_mode) {
        const char *label=picture_game.phase==XQP_ENGINE?"黑方引擎思考中":
            picture_game.phase==XQP_BLACK?"摆好黑方棋子后按空格":
            picture_game.phase==XQP_MANUAL?"手动纠正 鼠标点格子改棋子":
            picture_game.phase==XQP_RESTART?"纠正失败 请整局重新开始":
            picture_game.phase==XQP_FINISHED?"对局结束 请重新开始":
            !picture_started?"按空格开始":"走棋后按空格拍摄";
        xq_fb_gui_picture_feedback(picture_diagnostic?"图像诊断":label,
            picture_diagnostic?"R返回对弈":"实验模型 识别结果待验收",picture_model_backend);
        return;
    }
    const char *prompt = "红方走棋后按一次空格拍照";
    const char *details = "图像模式 桩识别";
    if (picture_needs_calibration) {
        prompt = "请摆好开局局面后按空格";
        details = "首拍自动标定";
    } else if (picture_game.phase == XQP_BLACK) {
        static const char *pieces[8] = {"", "将", "士", "象", "马", "车", "炮", "卒"};
        xq_search_move_t m;
        if (xq_pikafish_parse_move(picture_game.black_move, &m)) {
            snprintf(move, sizeof(move), "请把黑方%s从%c%c走到%c%c",
                     pieces[picture_game.confirmed.squares[m.from] & 7u],
                     picture_game.black_move[0], picture_game.black_move[1],
                     picture_game.black_move[2], picture_game.black_move[3]);
            prompt = move;
        }
        details = "摆放后按一次空格确认";
    } else if (picture_game.phase == XQP_MANUAL) {
        prompt = "手动纠正 鼠标点格子改棋子";
        details = "左键下个棋子 右键上个棋子";
    } else if (picture_game.phase == XQP_RESTART) {
        prompt = "纠正失败 请整局重新开始";
        details = "鼠标点重新开始";
    } else if (picture_game.phase == XQP_ENGINE) {
        prompt = "黑方引擎思考中";
    } else if (picture_game.phase == XQP_FINISHED) {
        prompt = "对局结束 请重新开始";
    }
    if (picture_diagnostic) {
        prompt = picture_metrics.calibrating ? "请依次点选四角" : "摄像头诊断 空格重拍";
        details = picture_metrics.calibrating ? "红方左下 右下 右上 左上" : "R返回对弈 C棋盘校准";
    }
    xq_fb_gui_picture_feedback(prompt, details, picture_diagnostic ?
        "左键看置信度 右键改类别" : "桩识别 无真实模型");
}

static void picture_reset(const xq_search_board_t *board)
{
    picture_join_search();
    if (picture_started) {
        xqs_phrase phrase={{XQS_NEWGAME},1};
        picture_say(&phrase,0);
    }
    xqp_init(&picture_game, board, picture_model_mode?50:800); /* model frozen .05 candidate cutoff; uncalibrated */
    picture_needs_calibration=!picture_preview_only && !picture_model_mode;
    if(picture_model_mode){picture_started=0;picture_model_manual_pending=picture_model_manual_submit=picture_model_geometry_manual=0;}
    memset(&picture_manual,0,sizeof(picture_manual));
    picture_calibration_request=picture_calibration_failures=picture_corner_count=0;
    picture_diagnostic=0;
    memset(&picture_grid,0,sizeof(picture_grid));
    memset(&picture_metrics,0,sizeof(picture_metrics));
    picture_metrics.selected=32;
    picture_diagnostic_update();
    picture_buttons = (uint8_t)(hid_regs[HID_STATUS >> 2] & 7u);
    xqp_hid_init(&picture_keyboard, hid_regs[0x18u / 4u], monotonic_milliseconds());
    xqp_hid_init(&picture_cancel_keyboard,hid_regs[0x18u/4u],monotonic_milliseconds());
    picture_prompt();
}

#ifdef XQ_PICTURE_LATENCY_TIMING
static struct {
    uint64_t start_ms,end_ms,capture_ms,inference_ms,total_ms;
    const char *terminal;
    unsigned valid;
} picture_last_latency;
#endif
/* Counter-only timing ends at the displayed recognition outcome, before speech
 * or engine search. Protocol CRC and all capture/result guards stay in place. */
static void picture_latency_emit(uint64_t start,const char *terminal)
{
#ifdef XQ_PICTURE_LATENCY_TIMING
    uint64_t end;
    if(!picture_model_mode)return;
    end=monotonic_milliseconds();
    picture_last_latency.start_ms=start;picture_last_latency.end_ms=end;
    picture_last_latency.capture_ms=picture_metrics.capture_ms;
    picture_last_latency.inference_ms=picture_metrics.inference_ms;
    picture_last_latency.total_ms=end>=start?end-start:0;
    picture_last_latency.terminal=terminal;
    picture_last_latency.valid=end>=start && picture_metrics.capture_ms+picture_metrics.inference_ms<=end-start;
    printf("XQ_PICTURE_LATENCY token=%llu valid=%u terminal=%s capture_ms=%llu ipc_inclusive_ms=%llu mapping_ms=%llu total_ms=%llu\n",
        (unsigned long long)picture_model_token,picture_last_latency.valid,terminal,
        (unsigned long long)picture_metrics.capture_ms,(unsigned long long)picture_metrics.inference_ms,
        (unsigned long long)picture_metrics.mapping_ms,(unsigned long long)picture_last_latency.total_ms);fflush(stdout);
#else
    (void)start;(void)terminal;
#endif
}

static void picture_step(xq_search_board_t *board, int engine_ready,
                         int32_t *score, uint32_t *win_rate,
                         uint32_t *nodes, uint32_t *ticks)
{
    xqp_event event;
    uint64_t start = picture_trigger_ms ? picture_trigger_ms : monotonic_milliseconds();
    uint32_t frame_id = 0;
    int full_redraw = 0;
    int had_photo = 0;
    int model_initial = 0;
    uint64_t mapping_start=0;
    picture_trigger_ms = 0;
    picture_busy_notice = 0;
    xqp_hid_init(&picture_cancel_keyboard,hid_regs[0x18u/4u],monotonic_milliseconds());
    if (picture_search.active) {
        puts("XQ_PICTURE_BUSY engine owns MAC; capture deferred");
        return;
    }
    if (!picture_preview_only && !engine_ready && !picture_diagnostic && !picture_needs_calibration) {
        xq_fb_gui_picture_feedback("等待引擎就绪", "请再按一次空格", picture_backend_label());
        (void)xq_fb_gui_show(board, -1, -1, *score, *nodes, *ticks, XQ_FB_STATE_READY);
        return;
    }
    if (picture_game.phase == XQP_MANUAL && !picture_diagnostic && !picture_needs_calibration) {
        event = xqp_confirm_manual(&picture_game);
    } else if (picture_diagnostic || picture_needs_calibration ||
               picture_game.phase == XQP_RED || picture_game.phase == XQP_BLACK) {
        xqv_frame frame;
        xqv_result result;
        uint64_t capture_start,inference_start;
        int capture;
        picture_metrics.inference_ms=picture_metrics.mapping_ms=0;
        if(picture_model_mode && picture_model_manual_submit && picture_metrics.has_frame) {
            frame=(xqv_frame){picture_pixels,XQV_FRAME_BYTES,picture_result.frame_id,0};
            frame_id=frame.frame_id;had_photo=1;picture_metrics.capture_ms=0;
            goto model_frozen_ready;
        }
        if(picture_model_mode && !picture_capture_pixels) {
            picture_capture_pixels=malloc(XQV_FRAME_BYTES);
            if(!picture_capture_pixels) {
                xq_fb_gui_picture_feedback("采集错误 请再拍照","按空格重拍",picture_backend_label());return;
            }
        }
        if(!picture_model_mode)picture_metrics.has_frame=0;
        picture_corner_count=0;
        picture_diagnostic_update();
        xq_fb_gui_picture_feedback("正在拍摄 请稍候", "请勿重复按空格", picture_backend_label());
        if (!xq_fb_gui_show(board,-1,-1,*score,*nodes,*ticks,XQ_FB_STATE_READY)) {
            stop_requested=1;
            return;
        }
        capture_start=monotonic_milliseconds();
        {
            picture_capture_progress progress={board,*score,*nodes,*ticks};
            capture=xqc_capture_until_ready(&picture_camera.io,picture_model_mode?picture_capture_pixels:picture_pixels,
                                            XQV_FRAME_BYTES,&frame,picture_capture_retry,&progress);
        }
        if (picture_camera.io.poisoned) {
            fputs("XQ_PICTURE_FATAL writer did not drain; reset required, GUI drawing inhibited\n", stderr);
            stop_requested = 1;
            return;
        }
        /* Camera wrote both GUI pages; invalidate the entire renderer scene. */
        full_redraw = !picture_camera.io.background;
        had_photo = 1;
        picture_metrics.capture_ms=monotonic_milliseconds()-capture_start;
        if (capture) {
            picture_diagnostic_update();
            xq_fb_gui_picture_feedback("采集错误 请再拍照", "按空格重拍", picture_backend_label());
            if(full_redraw)(void)xq_fb_gui_init();
            (void)xq_fb_gui_show(board, -1, -1, *score, *nodes, *ticks, XQ_FB_STATE_READY);
            printf("XQ_PICTURE_CAPTURE_FAIL code=%d\n", capture);
            picture_latency_emit(start,"capture_error");
            return;
        }
        frame_id = frame.frame_id;
        if(picture_model_mode) {
            uint32_t *previous=picture_pixels;
            picture_pixels=picture_capture_pixels;picture_capture_pixels=previous;
            /* A rejected recognition still has a real fresh photograph.
             * Its overlays must never come from the preceding capture. */
            memset(&picture_result,0,sizeof(picture_result));
            picture_result.frame_id=frame_id;
            memset(picture_boxes,0,sizeof(picture_boxes));
            memset(&picture_manual,0,sizeof(picture_manual));
            picture_metrics.calibrating=0;picture_model_manual_pending=0;picture_model_geometry_manual=0;
            picture_metrics.has_frame=1;picture_metrics.mapping_ms=0;
            ++picture_preview_capture;
        }
        if(picture_preview_only) {
            memset(&picture_result,0,sizeof(picture_result));
            memset(picture_boxes,0,sizeof(picture_boxes));
            picture_result.frame_id=frame_id;picture_metrics.has_frame=1;
            picture_metrics.inference_ms=picture_metrics.mapping_ms=0;
            ++picture_preview_capture;
            if(picture_calibration_request) {
                picture_calibration_request=0;picture_corner_count=0;
                picture_metrics.calibrating=1;picture_diagnostic=1;
                memset(&picture_manual,0,sizeof(picture_manual));
            }
            picture_diagnostic_update();
            xq_fb_gui_picture_feedback("拍摄完毕", "ROI PREVIEW: MODEL NOT LOADED", "R VIEW  C MANUAL CORNERS");
            if((full_redraw && !xq_fb_gui_init()) || !xq_fb_gui_show(board,-1,-1,*score,*nodes,*ticks,XQ_FB_STATE_READY)) {
                stop_requested=1;return;
            }
            picture_metrics.total_ms=monotonic_milliseconds()-start;
            printf("XQ_ROI_PREVIEW frame=%u capture_ms=%llu no_model=1 no_fen=1\n",frame_id,
                (unsigned long long)picture_metrics.capture_ms);
            return;
        }
model_frozen_ready:
        /* Legacy preview needs one full restore after DMA drains. Background
         * capture leaves the GUI pages intact and updates only dirty rows. */
        xq_fb_gui_picture_feedback("拍摄完毕 正在识别", "请稍候 请勿重复按键", picture_backend_label());
        if ((full_redraw && !xq_fb_gui_init()) ||
            !xq_fb_gui_show(board,-1,-1,*score,*nodes,*ticks,XQ_FB_STATE_READY)) {
            stop_requested=1;
            return;
        }
        full_redraw=0;
        inference_start=monotonic_milliseconds();
        if (!(picture_model_mode?picture_model_wait(&frame,&result):
              xqv_stub_recognize((void *)picture_stub, &frame, &result))) {
            ++picture_metrics.invalid;
            picture_metrics.inference_ms=monotonic_milliseconds()-inference_start;
            picture_metrics.total_ms=monotonic_milliseconds()-start;
            picture_diagnostic_update();
            xq_fb_gui_picture_feedback(picture_model_mode?"识别不确定 请重拍":"桩识别配置错误",
                "请再拍照",picture_model_mode?picture_model_backend:"桩识别 无真实模型");
            if(picture_model_mode && picture_model_manual_pending) {
                picture_diagnostic=1;picture_metrics.calibrating=1;picture_corner_count=0;
                xq_fb_gui_picture_feedback("请依次点选四角","红方左下 右下 右上 左上",picture_model_backend);
                picture_diagnostic_update();
            }
            (void)xq_fb_gui_show(board, -1, -1, *score, *nodes, *ticks, XQ_FB_STATE_READY);
            printf("XQ_PICTURE_RECOGNIZE_FAIL backend=%s no_fallback=1\n",picture_model_mode?picture_model_backend:"stub");
            picture_latency_emit(start,"model_rejected");
            return;
        }
        mapping_start=monotonic_milliseconds();
        picture_metrics.inference_ms=mapping_start-inference_start;
        picture_result=result;
        picture_metrics.has_frame=1;
        if(!picture_model_mode)xqg_stub_geometry(&result,picture_boxes);
        if(picture_model_mode && !picture_started) {
            xq_search_board_t initial;
            if(!xqv_result_board(&result,frame_id,&initial))return;
            xqp_init(&picture_game,&initial,50);*board=initial;picture_started=1;model_initial=1;
            picture_prompt();
            xq_fb_gui_picture_feedback("识别成功 可以开始","走棋后按空格拍摄",picture_model_backend);
            puts("XQ_MODEL_INITIALIZED experimental=1 opening_required=0");
            goto photo_display;
        }
        if (picture_needs_calibration || picture_calibration_request) {
            const xq_search_board_t *reference=picture_reference();
            picture_calibration_request=0;
            picture_count_reference(reference);
            if (picture_confident() && xqg_fit(&picture_grid,picture_boxes,result.piece_count,reference,frame_id) &&
                picture_save_calibration()) {
                picture_needs_calibration=0;
                picture_calibration_failures=0;
                picture_metrics.calibrating=0;
                *board=picture_game.confirmed;
                picture_prompt();
                if (!picture_diagnostic)
                    xq_fb_gui_picture_feedback("识别成功 可以开始", "走棋后按空格拍摄", "桩识别 合成网格");
                puts("XQ_PICTURE_CALIBRATED backend=stub geometry=synthetic reference=exact");
            } else {
                if (++picture_calibration_failures>=3) {
                    picture_diagnostic=1;
                    picture_metrics.calibrating=1;
                    picture_corner_count=0;
                }
                picture_prompt();
                xq_fb_gui_picture_feedback("标定失败 请重摆重拍", "连续三次后点选四角", "桩识别 合成网格");
            }
            goto photo_display;
        }
        if (picture_diagnostic) {
            if (picture_game.phase==XQP_BLACK) picture_count_reference(&picture_game.expected);
            else if (picture_confident()) ++picture_metrics.unscored;
            else ++picture_metrics.uncertain;
            picture_prompt();
            xq_fb_gui_picture_feedback(picture_confident()?"拍摄识别已完成":"不确定 请再按空格",
                picture_model_mode?"R返回对弈":"R返回对弈 C棋盘校准",
                picture_model_mode?picture_model_backend:"桩识别 合成网格");
            goto photo_display;
        }
        if (picture_game.phase==XQP_BLACK) picture_count_reference(&picture_game.expected);
        else if (picture_confident()) ++picture_metrics.unscored;
        else ++picture_metrics.uncertain;
        if(picture_model_mode && picture_game.phase==XQP_RED) {
            xq_search_board_t seen;
            if(xqv_result_board(&result,frame_id,&seen) && !memcmp(seen.squares,picture_game.confirmed.squares,90)) {
                picture_prompt();xq_fb_gui_picture_feedback("识别成功 盘面未变化","走棋后按空格拍摄",picture_model_backend);
                goto photo_display;
            }
        }
        event = xqp_observe(&picture_game, &result, frame_id);
        picture_metrics.mapping_ms=monotonic_milliseconds()-mapping_start;
    } else return;

    picture_prompt();
    if (event==XQP_SEARCH)
        xq_fb_gui_picture_feedback(had_photo?"识别成功 黑方思考中":"手动确认 引擎思考中",
            "请稍候", picture_backend_label());
    if (event == XQP_RETAKE || event == XQP_BAD_RESULT) {
        xq_fb_gui_picture_feedback("不确定 请再按一次空格", "请重拍", picture_backend_label());
    } else if (event == XQP_MISMATCH) {
        *board = picture_game.observed;
        xq_fb_gui_picture_feedback("摆放不一致 请重新摆放", "按空格重拍", picture_backend_label());
    } else if (event == XQP_EDIT || event == XQP_NEWGAME_REQUIRED) {
        *board = picture_game.observed;
    } else {
        *board = picture_game.confirmed;
        if (event==XQP_ACCEPTED)
            xq_fb_gui_picture_feedback(had_photo?"识别成功 红方走棋":"手动确认成功 红方走棋",
                "走棋后按空格拍摄", picture_backend_label());
    }
    if (full_redraw && !xq_fb_gui_init()) {
        stop_requested = 1;
        return;
    }
    if (!xq_fb_gui_show(board,-1,-1,*score,*nodes,*ticks,
            event==XQP_SEARCH?XQ_FB_STATE_BLACK_THINK:XQ_FB_STATE_READY)) {
        puts("XQ_PICTURE_SYNC_FAIL reason=display");
        picture_game.phase = XQP_RESTART;
        return;
    }
    if (had_photo) picture_metrics.total_ms=monotonic_milliseconds()-start;
    printf("XQ_PICTURE_SYNC backend=%s frame=%u event=%d phase=%d failures=%u elapsed_ms=%llu\n",
            picture_model_mode?picture_model_backend:"stub",frame_id, (int)event, (int)picture_game.phase, picture_game.failures,
            (unsigned long long)picture_metrics.total_ms);
    if(had_photo)picture_latency_emit(start,"model_validated");
    if (event == XQP_SEARCH) {
        picture_search.board=picture_game.confirmed;
        picture_search.score=*score; picture_search.rate=*win_rate;
        picture_search.nodes=*nodes; picture_search.ticks=*ticks;
        picture_search.bestmove[0]=0;
        __atomic_store_n(&picture_search.done,0,__ATOMIC_RELEASE);
        {
            pthread_attr_t attributes;
            int error=pthread_attr_init(&attributes);
            if (!error) {
                /* musl defaults new threads to a much smaller stack than
                 * the original main-thread engine call. Preserve 8 MiB for
                 * recursive search rather than depending on libc defaults. */
                error=pthread_attr_setstacksize(&attributes,8u*1024u*1024u);
                if (!error) error=pthread_create(&picture_search.thread,&attributes,picture_search_worker,NULL);
                (void)pthread_attr_destroy(&attributes);
            }
            if (!error) picture_search.active=1;
            else picture_game.phase=XQP_RESTART;
        }
        if (!picture_search.active) {
            picture_prompt();
            (void)xq_fb_gui_show(board,-1,-1,*score,*nodes,*ticks,XQ_FB_STATE_READY);
        }
    }
    return;
photo_display:
    picture_metrics.mapping_ms=monotonic_milliseconds()-mapping_start;
    picture_metrics.total_ms=monotonic_milliseconds()-start;
    picture_diagnostic_update();
    if ((full_redraw && !xq_fb_gui_init()) ||
        !xq_fb_gui_show(board,-1,-1,*score,*nodes,*ticks,XQ_FB_STATE_READY)) stop_requested=1;
    picture_metrics.total_ms=monotonic_milliseconds()-start;
    if (!stop_requested && picture_diagnostic) {
        /* Publish latency to the first synchronized photo; the metrics panel
         * repaint itself is outside that photo-to-display interval. */
        picture_diagnostic_update();
        if (!xq_fb_gui_show(board,-1,-1,*score,*nodes,*ticks,XQ_FB_STATE_READY)) stop_requested=1;
    }
    picture_latency_emit(start,"model_validated");
    if (!stop_requested && !picture_needs_calibration && !picture_started) {
        xqs_phrase phrase={{XQS_WELCOME},1};
        picture_started=1;
        picture_say(&phrase,0);
    }
    if(!stop_requested && model_initial) {
        xqs_phrase phrase={{XQS_WELCOME},1};picture_say(&phrase,0);
    }
}

static void picture_finish_search(xq_search_board_t *board,int32_t *score,
                                   uint32_t *rate,uint32_t *nodes,uint32_t *ticks)
{
    if (!picture_search.active || !__atomic_load_n(&picture_search.done,__ATOMIC_ACQUIRE)) return;
    picture_join_search();
    if (stop_requested) return;
    *score=picture_search.score; *rate=picture_search.rate;
    *nodes=picture_search.nodes; *ticks=picture_search.ticks;
    if (picture_search.result>0 && xqp_engine_move(&picture_game,&picture_search.board,picture_search.bestmove)) {
        *board=picture_search.board;
        printf("XQ_PICTURE_PLACE_BLACK move=%s\n",picture_search.bestmove);
    } else picture_game.phase=picture_search.result<0?XQP_FINISHED:XQP_RESTART;
    picture_prompt();
    xq_fb_gui_set_red_win_rate(*rate);
    (void)xq_fb_gui_show(board,-1,-1,*score,*nodes,*ticks,XQ_FB_STATE_BLACK_MOVE);
    if (picture_game.phase==XQP_BLACK) {
        xqs_phrase phrase;
        if (xqs_move_phrase(&picture_game.confirmed,picture_game.black_move,&phrase)) picture_say(&phrase,1);
        else puts("XQ_PICTURE_SPEECH_SKIP ambiguous-notation");
        if (*ticks!=XQ_FB_TIME_UNAVAILABLE && xqs_numbers_phrase(*rate,*ticks/GUI_TICKS_PER_MS,&phrase)) picture_say(&phrase,0);
    }
}

static int picture_mouse(xq_search_board_t *board, uint32_t xy, uint8_t buttons)
{
    uint8_t pressed = buttons & (uint8_t)~picture_buttons;
    int x = (int)(xy & 0x7ffu), y = (int)((xy >> 11) & 0x3ffu);
    int square;
    picture_buttons = buttons;
    if (picture_diagnostic) {
        unsigned i;
        if ((pressed&1u) && x>=XQP_CAL_X && x<XQP_CAL_X+XQP_CAL_W &&
            y>=XQP_CAL_Y && y<XQP_CAL_Y+XQP_CAL_H) return 3;
        if ((pressed&1u) && picture_metrics.calibrating && picture_metrics.has_frame &&
            x>=XQP_IMAGE_X && x<XQP_IMAGE_X+XQP_IMAGE_W &&
            y>=XQP_IMAGE_Y && y<XQP_IMAGE_Y+XQP_IMAGE_H) {
            picture_corners[picture_corner_count][0]=2*(x-XQP_IMAGE_X);
            picture_corners[picture_corner_count++][1]=2*(y-XQP_IMAGE_Y);
            if (picture_corner_count==4) {
                if(picture_model_mode) {
                    xqr_manual candidate;
                    picture_corner_count=0;
                    if(!picture_model_manual_pending || !xqr_manual_init(&candidate,(xqr_roi){0,0,1280,720},
                       picture_corners,picture_preview_view+1))return 1;
                    picture_model_manual_submit=1;picture_metrics.calibrating=0;
                    return 4; /* Caller reruns the worker on this frozen frame. */
                }
                if(picture_preview_only) {
                    picture_corner_count=0;
                    picture_metrics.calibrating=!xqr_manual_init(&picture_manual,(xqr_roi){0,0,1280,720},
                        picture_corners,++picture_preview_view);
                    picture_prompt();picture_diagnostic_update();
                    return 1;
                }
                xqv_result mapped;
                xq_search_board_t b;
                xqg_grid candidate;
                const xq_search_board_t *reference=picture_reference();
                picture_corner_count=0;
                if (xqg_corners(&candidate,picture_corners) &&
                    xqg_map(&candidate,picture_boxes,picture_result.piece_count,picture_result.frame_id,&mapped) &&
                    xqv_result_board(&mapped,picture_result.frame_id,&b) &&
                    !memcmp(b.squares,reference->squares,90) && picture_confident()) {
                    picture_grid=candidate;
                    if (picture_save_calibration()) {
                        picture_needs_calibration=0;
                        picture_metrics.calibrating=0;
                    }
                }
            }
            picture_prompt(); picture_diagnostic_update(); return 1;
        }
        if (!picture_preview_only && picture_metrics.has_frame && !picture_metrics.calibrating && (pressed&3u)) {
            for (i=0; i<picture_result.piece_count; ++i) {
                const xqg_detection *d=&picture_display_boxes[i];
                int px=2*(x-XQP_IMAGE_X),py=2*(y-XQP_IMAGE_Y);
                if (px<d->x0 || px>d->x1 || py<d->y0 || py>d->y1) continue;
                picture_metrics.selected=i;
                /* Model R-page is read-only. Legacy STUB retains L2 editing. */
                if ((pressed&2u) && !picture_model_mode) {
                    if (picture_game.phase!=XQP_MANUAL &&
                        (picture_game.phase==XQP_RED || picture_game.phase==XQP_BLACK)) {
                        picture_game.resume_phase=picture_game.phase;
                        picture_game.phase=XQP_MANUAL;
                        (void)xqv_result_board(&picture_result,picture_result.frame_id,&picture_game.observed);
                    }
                    if (xqp_edit(&picture_game,picture_result.pieces[i].rank*9+picture_result.pieces[i].file,1)) {
                        *board=picture_game.observed;
                        xq_fb_gui_picture_feedback("手动纠正 R返回后空格提交", "本次编辑不计识别正确率",
                            picture_model_mode?picture_model_backend:"桩识别 合成网格");
                    }
                }
                picture_diagnostic_update(); return 1;
            }
        }
        return 0;
    }
    if ((pressed & 1u) && x >= XQ_FB_RESTART_X && x < XQ_FB_RESTART_X + XQ_FB_RESTART_W &&
        y >= XQ_FB_RESTART_Y && y < XQ_FB_RESTART_Y + XQ_FB_RESTART_H) return 2;
    square = xq_mouse_screen_to_square(x, y);
    if (square >= 0 && (pressed & 3u) &&
        xqp_edit(&picture_game, (unsigned)square, (pressed & 1u) ? 1 : -1)) {
        *board = picture_game.observed;
        return 1;
    }
    return 0;
}

static int picture_poll_key(void)
{
    uint32_t before, after = 0, packed = 0;
    unsigned retry;
    int event;
    for (retry = 0; retry < 4; ++retry) {
        before = hid_regs[0x18u / 4u];
        packed = hid_regs[0x14u / 4u];
        after = hid_regs[0x18u / 4u];
        if (before == after) break;
    }
    if (retry == 4) return 0;
    event = xqp_hid_poll_key(&picture_keyboard, after, packed, monotonic_milliseconds());
    if (event < 0) puts("XQ_PICTURE_HID_RETRY incomplete/ambiguous reports; release keys and press Space again");
    if (event > 0) picture_trigger_ms = event==32 || event=='c' ? picture_keyboard.first_ms : 0;
    return event > 0 ? event : 0;
}

static int picture_key(int key, xq_search_board_t *board, int engine_ready,
                        int32_t *score, uint32_t *rate, uint32_t *nodes, uint32_t *ticks)
{
    if (key==27) { stop_requested=1; return 1; }
    if (key=='r') {
        picture_diagnostic=!picture_diagnostic;
        picture_prompt(); picture_diagnostic_update();
        (void)xq_fb_gui_show(board,-1,-1,*score,*nodes,*ticks,XQ_FB_STATE_READY);
        return 1;
    }
    if (picture_search.active && (key==32 || key=='c')) {
        puts("XQ_PICTURE_BUSY engine owns MAC; capture deferred");
        picture_discard_input();
        return 1;
    }
    if (key=='c' && picture_diagnostic) {
        if(picture_model_mode) {
            if(picture_model_manual_pending && picture_metrics.has_frame) {
                picture_metrics.calibrating=1;picture_corner_count=0;
                xq_fb_gui_picture_feedback("请依次点选四角","红方左下 右下 右上 左上",picture_model_backend);
                picture_diagnostic_update();
            } else xq_fb_gui_picture_feedback("按空格重拍","自动识别",picture_model_backend);
            (void)xq_fb_gui_show(board,-1,-1,*score,*nodes,*ticks,XQ_FB_STATE_READY);
            return 1;
        }
        picture_calibration_request=1;
        picture_metrics.calibrating=0;
    } else if (key!=32) return 0;
    picture_step(board,engine_ready,score,rate,nodes,ticks);
    picture_discard_input();
    return 1;
}

static int picture_exit_frame(const xq_search_board_t *board)
{
    if (picture_camera.io.poisoned || xqc_stop(&picture_camera.io)) return 0;
    if(picture_diagnostic && picture_metrics.has_frame) {
        xq_fb_gui_picture_feedback("已退出对弈 串口终端可用", "串口命令 xiangqi-pikafish", "保留拍摄诊断画面");
        picture_diagnostic_update();
        return xq_fb_gui_show(board,-1,-1,0,0,0,XQ_FB_STATE_READY);
    }
    picture_diagnostic=0;
    picture_diagnostic_update();
    xq_fb_gui_picture_feedback("已退出对弈 串口终端可用", "串口命令 xiangqi-pikafish", "显示保留最后提示画面");
    return xq_fb_gui_init() && xq_fb_gui_show(board,-1,-1,0,0,0,XQ_FB_STATE_READY);
}
