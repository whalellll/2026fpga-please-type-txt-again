#define _POSIX_C_SOURCE 200809L
#include "runtime.h"
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
    while(!exit_requested && !runtime.fatal){
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
            if(terminal==27 || input.key==27)xy_runtime_cancel(&runtime);
            else if(terminal==32 || input.key==32)
                (void)xy_runtime_space(&runtime,input.key==32?input.key_first_ms:0);
            if(input.left_click)
                (void)xy_runtime_pointer(&runtime,input.mouse_x,input.mouse_y);
        }
        if(xy_platform_take_invalidation(platform)){xy_fb_invalidate();first=1;}
        uint64_t now=milliseconds();
        int benchmark_throttle=runtime.app.job==XY_COREMARK && !runtime.app.cancelling &&
                               now-last_present<1000;
        if(first || (!benchmark_throttle && runtime.dirty)){
            xy_fb_render(&runtime.app,xq_linux_framebuffers[0]);
            if(!xy_platform_present(platform,0)){runtime.fatal=1;break;}
            if(first)puts("XINYI_GUI_FIRST_PRESENTED physical_visibility_pending=1");
            runtime.dirty=0;first=0;last_present=milliseconds();
            if(photo_present_token){
                if(runtime.app.token==photo_present_token && !runtime.app.cancelling){
                    int valid=runtime.photo_started_ms && last_present>=runtime.photo_started_ms &&
                              last_present-runtime.photo_started_ms<=7200000u;
                    printf("XINYI_PHOTO_PRESENT elapsed_ms=%llu time_valid=%u gui_buffer_presented=1 physical_visibility_pending=1\n",
                        (unsigned long long)(valid?last_present-runtime.photo_started_ms:0),valid!=0);
                }
                photo_present_token=0;
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
