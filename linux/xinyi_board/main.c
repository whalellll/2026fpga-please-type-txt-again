#define _POSIX_C_SOURCE 200809L
#include "runtime.h"
#if XINYI_UI_FEEDBACK
#include "ui_feedback.h"
#endif
#include "xiangqi_fb_gui.h"
#include "../pikafish/gui1080_config.h"
#include "../pikafish/include/video_fb.h"
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];
static volatile sig_atomic_t exit_requested;
static void stop(int number){(void)number;exit_requested=1;}
static uint64_t milliseconds(void)
{struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;return (uint64_t)t.tv_sec*1000u+(unsigned)t.tv_nsec/1000000u;}
#if XINYI_UI_NAV_DIAG
extern unsigned xy_fb_nav_cost_ms(unsigned);
/* Temporary board diagnostic only: at most sixteen explicit controls.
 * Preview and CoreMark use the real runtime actions; no photo capture. */
static volatile sig_atomic_t nav_command,nav_signal_ms;
static void navigation_signal(int number)
{nav_signal_ms=(sig_atomic_t)(uint32_t)milliseconds();nav_command=number==SIGUSR1?1:number==SIGUSR2?2:number==SIGURG?4:number==SIGALRM?5:number==SIGPROF?6:number==SIGXCPU?7:3;}
#endif
static const char *path(const char *name)
{
    const char *p=getenv(name);
    return p && *p=='/' && strlen(p)<900?p:NULL;
}
static int configuration(xy_runtime_config *c)
{
    memset(c,0,sizeof(*c));
    c->coach_worker=path("XINYI_COACH_WORKER");c->models=path("XINYI_MODELS");
    c->engine=path("XINYI_ENGINE");c->speech_worker=path("XINYI_SPEECH_WORKER");
    c->pcm=path("XINYI_PCM");c->coremark=path("XINYI_COREMARK");
    /* Full hash is supplied only by the runtime kit's checked current CRAM
     * assignment receipt. CPU/device registers cannot read back a bitstream. */
    const char *bit=getenv("XINYI_CURRENT_CRAM_SHA256");
    if(bit && strlen(bit)==64 && strspn(bit,"0123456789abcdef")==64)c->bitstream=bit;
    c->search_nodes=512;
    return c->coach_worker && c->models && c->engine && c->speech_worker && c->pcm && c->coremark;
}
int main(int argc,char **argv)
{
    xy_runtime_config config;
    setvbuf(stdout,NULL,_IOLBF,0);
    if(!configuration(&config)){
        fputs("XINYI_CONFIG_REJECTED: use the hash-checked private kit launcher\n",stderr);return 2;
    }
    if(argc==2 && !strcmp(argv[1],"--check-config")){
        puts("XINYI_CONFIG_PATHS_PASS_NOT_HARDWARE_ACCEPTANCE");return 0;
    }
    if(argc!=1)return 2;
    struct sigaction action={0};action.sa_handler=stop;sigemptyset(&action.sa_mask);
    if(sigaction(SIGTERM,&action,NULL) || sigaction(SIGINT,&action,NULL))return 2;
#if XINYI_UI_NAV_DIAG
    struct sigaction nav_action={0};nav_action.sa_handler=navigation_signal;
    sigemptyset(&nav_action.sa_mask);sigaddset(&nav_action.sa_mask,SIGUSR1);sigaddset(&nav_action.sa_mask,SIGUSR2);sigaddset(&nav_action.sa_mask,SIGWINCH);sigaddset(&nav_action.sa_mask,SIGURG);sigaddset(&nav_action.sa_mask,SIGALRM);sigaddset(&nav_action.sa_mask,SIGPROF);sigaddset(&nav_action.sa_mask,SIGXCPU);
    if(sigaction(SIGUSR1,&nav_action,NULL) || sigaction(SIGUSR2,&nav_action,NULL) || sigaction(SIGWINCH,&nav_action,NULL) || sigaction(SIGURG,&nav_action,NULL) || sigaction(SIGALRM,&nav_action,NULL) || sigaction(SIGPROF,&nav_action,NULL) || sigaction(SIGXCPU,&nav_action,NULL))return 2;
#endif
    xy_platform *platform=xy_platform_open();
    if(!platform){fputs("XINYI_PLATFORM_IDENTITY_REJECTED\n",stderr);return 3;}
    xq_linux_video_regs=xy_platform_video_regs(platform);
    xq_linux_framebuffers[0]=xy_platform_pixels(platform,0);
    xq_linux_framebuffers[1]=xy_platform_pixels(platform,1);
    if(!xq_fb_gui_init()){
        (void)xy_platform_close(platform);fputs("XINYI_GUI_ABI_REJECTED\n",stderr);return 3;
    }
    xy_runtime runtime;
    if(!xy_runtime_init(&runtime,platform,&config)){
        (void)xy_runtime_shutdown(&runtime);(void)xy_platform_close(platform);
        fputs("XINYI_RUNTIME_START_FAILED\n",stderr);return 3;
    }
    (void)xy_platform_terminal_attach(platform,STDIN_FILENO);
    printf("XINYI_FUNCTIONAL_CANDIDATE cpu_hz=%u GUI1080p30 production_ready=false\n",xy_platform_cpu_hz(platform));
    puts("XINYI_CAMERA_EXCLUSIVE_SOURCE GUI_AND_PREVIEW_COMPOSITION_UNAVAILABLE");
    int first=1;uint64_t last_present=0;uint32_t photo_present_token=0;
#if XINYI_UI_NAV_DIAG
    unsigned nav_count=0,nav_active=0,nav_page=0,nav_cost[5]={0};xy_page nav_target=XY_HOME;
    uint32_t nav_start=0,nav_dispatch=0,nav_draw_ms=0,nav_frame=0,nav_submit=0,nav_publish_ms=0;
#endif
#if XINYI_UI_FEEDBACK
    xy_feedback feedback={0};
#endif
    while(!exit_requested && !runtime.fatal
#if XINYI_HOME_R13
          && !runtime.exit_requested
#endif
         ){
        xy_platform_input input;
        uint32_t previous_token=runtime.app.token;
        xy_job previous_job=runtime.app.job;
        int previous_cancelling=runtime.app.cancelling;
        (void)xy_runtime_poll(&runtime);
        /* At most one line per completed phase. No transcript, board, FEN,
         * frame number, CRC, corners or camera payload reaches the UART. */
        if(runtime.app.token==previous_token && !previous_cancelling && !runtime.app.cancelling &&
           previous_job!=runtime.app.job && (runtime.app.mode==XY_COACH || previous_job==XY_COREMARK)){
            if(previous_job==XY_CAPTURE){
                photo_present_token=runtime.app.token;
                printf("XINYI_PHOTO_PHASE phase=capture_and_geometry okay=%u elapsed_ms=%u\n",
                       runtime.app.current_photo_valid!=0,runtime.app.photo_latency_ms);
            }else if(previous_job==XY_RECOMMEND)
                printf("XINYI_PHOTO_PHASE phase=recommendation okay=%u elapsed_ms=%u\n",
                       runtime.app.has_recommendation!=0,runtime.app.photo_latency_ms);
            else if(previous_job==XY_ANNOUNCE)
                printf("XINYI_PHOTO_PHASE phase=audio okay=%u\n",runtime.speech.state==XY_SPEECH_DONE);
            else if(previous_job==XY_COREMARK){
                if(runtime.app.coremark_origin==XY_COREMARK_REFERENCE)
                    puts("XINYI_REFERENCE_PRESENTATION source=main_rom current_measured=0");
                else {
                int measured=runtime.app.coremark_origin==XY_COREMARK_BOARD &&
                             runtime.coremark.status==XY_CM_DONE && runtime.coremark.valid &&
                             runtime.coremark.is_board && runtime.app.coremark_measured;
                printf("XINYI_GUI_COREMARK origin=%u status=%u valid=%d board=%d measured=%d perf_iterations=%llu perf_ticks=%llu validation_ticks=%llu cpu_hz=%u score_per_mhz=%.9f\n",
                       (unsigned)runtime.app.coremark_origin,
                       (unsigned)runtime.coremark.status,runtime.coremark.valid,runtime.coremark.is_board,
                       measured,(unsigned long long)runtime.coremark.perf_iterations,
                       (unsigned long long)runtime.coremark.perf_ticks,
                       (unsigned long long)runtime.coremark.validation_ticks,runtime.coremark.cpu_hz,
                       measured?runtime.app.coremark_per_mhz:0.0);
                }
            }
            fflush(stdout);
        }
        if(xy_platform_read_input(platform,&input)){
            int terminal=xy_platform_terminal_key(platform);
            if(terminal==27 || input.key==27){
                xy_runtime_cancel(&runtime);
#if XINYI_UI_FEEDBACK
                xy_feedback_reset(&feedback);
#endif
            }
            else if(terminal==32 || input.key==32)
                (void)xy_runtime_space(&runtime,input.key==32?input.key_first_ms:0);
#if XINYI_BATTLE_R17
            else if(terminal || input.key)(void)xy_runtime_key(&runtime,input.key?input.key:terminal);
#endif
#if XINYI_UI_FEEDBACK
            if(input.mouse_sample){
                xy_feedback_view old=feedback.view;int board_press=0;
                xy_pointer_event action=xy_feedback_step(&feedback,&runtime.app,input.mouse_valid,
                    input.mouse_x,input.mouse_y,input.left_down,input.left_click,milliseconds(),&board_press);
                if(action)(void)xy_runtime_action(&runtime,action);
                else if(board_press)(void)xy_runtime_pointer(&runtime,input.mouse_x,input.mouse_y);
                if(memcmp(&old,&feedback.view,sizeof(old)))runtime.dirty=1;
                xy_fb_feedback(&feedback.view);
            }
#else
            if(input.left_click)
                (void)xy_runtime_pointer(&runtime,input.mouse_x,input.mouse_y);
#endif
        }
#if XINYI_UI_NAV_DIAG
        int command=nav_command;
        if(command && !nav_active){
            nav_command=0;
            if(nav_count<16 && runtime.app.job==XY_IDLE && (!runtime.camera_active || (command==2 && runtime.app.preview_state)) &&
               !runtime.coach_active && !runtime.engine_owner && !runtime.speech_owner &&
               ((command==1 && (runtime.app.page==XY_HOME || (runtime.app.page==XY_CAMERA_DEBUG && !runtime.app.preview_state))) ||
                (command==2 && (runtime.app.page==XY_BENCHMARK || runtime.app.page==XY_CAMERA_DEBUG || runtime.app.page==XY_GAME)) ||
                ((command==5 || command==7) && runtime.app.page==XY_HOME) ||
                (command==6 && runtime.app.page==XY_BENCHMARK) ||
                ((command==3 || command==4) && runtime.app.page==XY_HOME))){
                nav_start=(uint32_t)nav_signal_ms;nav_dispatch=(uint32_t)milliseconds()-nav_start;
                nav_target=command==7?XY_GAME:command==5 || (command==1 && runtime.app.page==XY_CAMERA_DEBUG)?XY_CAMERA_DEBUG:
                    command==6 || command==1?XY_BENCHMARK:XY_HOME;
                int accepted=1;
                if(command==3){xy_fb_ram_diag_mode_set(!xy_fb_ram_diag_mode());xy_fb_invalidate();runtime.dirty=1;}
                else if(command==4)runtime.dirty=1;
                else accepted=xy_runtime_action(&runtime,command==7?XY_ACTION_START:command==5?XY_ACTION_CAMERA:command==6?XY_ACTION_CM_RUN:
                    command==1?(runtime.app.page==XY_CAMERA_DEBUG?XY_ACTION_PREVIEW:XY_ACTION_COREMARK):XY_ACTION_HOME);
                if(accepted){
                    nav_active=1;nav_count++;
                    printf("XINYI_NAV_DIAG_BEGIN sequence=%u target=%u kind=%d cache=%d dispatch_ms=%u\n",nav_count,(unsigned)nav_target,command,xy_fb_ram_diag_mode(),nav_dispatch);
                }
            }
        }
        if(nav_active==1 && nav_target==XY_CAMERA_DEBUG && runtime.app.preview_state==2){
            printf("XINYI_PREVIEW_READY elapsed_ms=%u physical_hid=0\n",(uint32_t)milliseconds()-nav_start);nav_active=0;
        }
        if(nav_active==2){
            uint32_t status=xq_linux_video_regs[3],frame=xq_linux_video_regs[9];
            if(runtime.app.page!=nav_target || (status&((1u<<3)|(1u<<5))))nav_active=0;
            else if((status&6u)==(2u|(nav_page<<2)) && (uint32_t)(frame-nav_frame)>=2u){
                printf("XINYI_NAV_DIAG_COMPLETE sequence=%u target=%u cache=%d dispatch_ms=%u draw_ms=%u publish_ms=%u submit_ms=%u scanout_ms=%u\n",
                    nav_count,(unsigned)nav_target,xy_fb_ram_diag_mode(),nav_dispatch,nav_draw_ms,nav_publish_ms,nav_submit-nav_start,(uint32_t)milliseconds()-nav_start);
                printf("XINYI_NAV_COST sequence=%u restore_feedback_ms=%u restore_dynamic_ms=%u base_ms=%u overlay_ms=%u feedback_ms=%u\n",
                    nav_count,nav_cost[0],nav_cost[1],nav_cost[2],nav_cost[3],nav_cost[4]);
                nav_active=0;
            }else if((uint32_t)milliseconds()-nav_submit>1000u){
                puts("XINYI_NAV_DIAG_SCANOUT_TIMEOUT");nav_active=0;
            }
        }
#endif
#if XINYI_HOME_R13
        if(runtime.exit_requested)break;
#endif
        if(xy_platform_take_invalidation(platform)){xy_fb_invalidate();first=1;}
#if XINYI_BATTLE_R17
        uint32_t visible_before=xq_linux_video_regs[3],visible_frame=xq_linux_video_regs[9];
        if(visible_before==xq_linux_video_regs[3])
            (void)xy_runtime_display_ack(&runtime,visible_before,visible_frame,milliseconds());
#endif
        uint64_t now=milliseconds();
        int benchmark_throttle=runtime.app.job==XY_COREMARK && !runtime.app.cancelling &&
                               now-last_present<1000;
#if XINYI_UI_FEEDBACK
        if(feedback.view.hover || feedback.view.pressed || feedback.view.released)benchmark_throttle=0;
#endif
#if XINYI_GUI_FAST_NAV_R21
        /* Idle navigation is waiting only for preparation/microphone shutdown.
         * Preserve the visible page and dirty flag until its destination exists.
         * Active jobs and cancellation keep their normal status rendering. */
        int idle_navigation_wait=!first && runtime.navigation_requested &&
            (runtime.app.page!=runtime.destination_page || runtime.app.mode!=runtime.destination_mode) &&
            runtime.app.job==XY_IDLE && !runtime.app.cancelling && !runtime.app.navigation_pending &&
            !runtime.camera_active && !runtime.coach_active && !runtime.engine_owner && !runtime.speech_owner;
#endif
#if XINYI_BATTLE_R17
        /* HOME is only an internal microphone/drain barrier during restart.
         * Keep dirty/first until the next poll has restored the game page. */
        if(!(runtime.restart_requested && runtime.app.page==XY_HOME))
#endif
#if XINYI_GUI_FAST_NAV_R21
        if(!idle_navigation_wait)
#endif
        if(first || (!benchmark_throttle && runtime.dirty)){
            unsigned draw_page=0;int ready=1;
#if XINYI_GUI_DOUBLE_BUFFER
            ready=xy_platform_gui_back_page(platform,&draw_page);
            if(!ready){runtime.fatal=1;break;}
#endif
            if(ready==1){
#if XINYI_GUI_METRIC_DELTAS
                if(first && xy_platform_gui_initial_idle(platform))
                    xy_fb_render(&runtime.app,xq_linux_framebuffers[draw_page^1u]);
#endif
#if XINYI_UI_NAV_DIAG
                uint32_t draw_started=(uint32_t)milliseconds();
#endif
                xy_fb_render(&runtime.app,xq_linux_framebuffers[draw_page]);
#if XINYI_UI_NAV_DIAG
                if(nav_active==1 && runtime.app.page==nav_target){nav_draw_ms=(uint32_t)milliseconds()-draw_started;nav_publish_ms=xy_fb_ram_diag_publish_ms();for(unsigned phase=0;phase<5;phase++)nav_cost[phase]=xy_fb_nav_cost_ms(phase);}
#endif
                int presented=xy_platform_present(platform,draw_page);
                if(!presented){runtime.fatal=1;break;}
#if XINYI_GUI_DOUBLE_BUFFER
                if(presented==1){
#endif
                    if(first)puts("XINYI_GUI_FIRST_PRESENTED physical_visibility_pending=1");
                    runtime.dirty=0;first=0;last_present=milliseconds();
#if XINYI_BATTLE_R17
                    xy_runtime_frame_submitted(&runtime,draw_page,xq_linux_video_regs[9]);
#endif
#if XINYI_UI_NAV_DIAG
                    if(nav_active==1 && runtime.app.page==nav_target){nav_page=draw_page;nav_frame=xq_linux_video_regs[9];nav_submit=(uint32_t)last_present;nav_active=2;}
#endif
                    if(photo_present_token){
                        if(runtime.app.token==photo_present_token && !runtime.app.cancelling){
                            int valid=runtime.photo_started_ms && last_present>=runtime.photo_started_ms &&
                                      last_present-runtime.photo_started_ms<=7200000u;
                            printf("XINYI_PHOTO_PRESENT elapsed_ms=%llu time_valid=%u gui_buffer_presented=1 physical_visibility_pending=1\n",
                                (unsigned long long)(valid?last_present-runtime.photo_started_ms:0),valid!=0);
                        }
                        photo_present_token=0;
                    }
#if XINYI_GUI_DOUBLE_BUFFER
                }
#endif
            }
        }
        /* A running coach performs the expensive image work in its child.
         * Poll it at 20 Hz so the GUI leaves CPU time to inference. Keep the
         * existing fast loop for cancellation, navigation and voice service. */
        int compute_wait=runtime.app.job==XY_COREMARK ||
            (runtime.app.mode==XY_COACH && runtime.app.job==XY_CAPTURE && !runtime.app.cancelling);
        const struct timespec pause={0,compute_wait?50000000:5000000};
        nanosleep(&pause,NULL);
    }
    int okay=xy_runtime_shutdown(&runtime);
    xy_platform_terminal_restore(platform);
    if(!xy_platform_close(platform))okay=0;
    puts(okay?"XINYI_STOPPED_RESOURCES_RELEASED":"XINYI_STOP_UNCONFIRMED_RESET_REQUIRED");
    return okay?0:4;
}
