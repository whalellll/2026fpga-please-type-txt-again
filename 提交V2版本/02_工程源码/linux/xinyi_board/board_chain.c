/* Engineering entry point linked with the unchanged product runtime objects.
 * No GUI rendering or synthetic inference. It never claims physical HID,
 * HDMI visibility, listening acceptance or a GUI CoreMark measurement. */
#define _POSIX_C_SOURCE 200809L
#include "runtime.h"
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static volatile sig_atomic_t interrupted;
static void stop(int sig){(void)sig;interrupted=1;}
static uint64_t ms(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
    return (uint64_t)t.tv_sec*1000u+(unsigned)t.tv_nsec/1000000u;
}
static const char *path(const char *key)
{
    const char *p=getenv(key);
    return p && *p=='/' && strlen(p)<900?p:NULL;
}
static int configuration(xy_runtime_config *c)
{
    memset(c,0,sizeof(*c));
    c->coach_worker=path("XINYI_COACH_WORKER");c->models=path("XINYI_MODELS");
    c->engine=path("XINYI_ENGINE");c->speech_worker=path("XINYI_SPEECH_WORKER");
    c->pcm=path("XINYI_PCM");c->coremark=path("XINYI_COREMARK");
    c->bitstream=getenv("XINYI_CURRENT_CRAM_SHA256");c->search_nodes=512;
    return c->coach_worker && c->models && c->engine && c->speech_worker && c->pcm && c->coremark &&
        c->bitstream && (!strcmp(c->bitstream,"9ba02f105d6168e9445e9a15e2f7a1093d885229deae9e268994acdbe29f5ea1") ||
                        !strcmp(c->bitstream,"6565ad378524f3e2a34f6cdba6fcc46b2f928eb3677c0fe80971e05e8ec2ebdd"));
}
int main(int argc,char **argv)
{
    xy_runtime_config config;int benchmark=0,image=0,started=0,rc=1;
    setvbuf(stdout,NULL,_IONBF,0);
    if(argc!=2 || !configuration(&config)){puts("XINYI_CHAIN_CONFIG_REJECTED");return 2;}
    if(!strcmp(argv[1],"--check-config")){puts("XINYI_CHAIN_CONFIG_PASS_NOT_BOARD");return 0;}
    if(!strcmp(argv[1],"--coremark"))benchmark=1;
    else if(!strcmp(argv[1],"--image"))image=1;
    else if(!strcmp(argv[1],"--coremark-image"))benchmark=image=1;
    else return 2;
    struct sigaction action={0};action.sa_handler=stop;sigemptyset(&action.sa_mask);
    if(sigaction(SIGTERM,&action,NULL)||sigaction(SIGINT,&action,NULL))return 2;
    xy_platform *platform=xy_platform_open();
    if(!platform){puts("XINYI_CHAIN_PLATFORM_REJECTED");return 3;}
    xy_runtime r;
    if(!xy_runtime_init(&r,platform,&config)){
        (void)xy_runtime_shutdown(&r);(void)xy_platform_close(platform);
        puts("XINYI_CHAIN_RUNTIME_REJECTED");return 3;
    }
    uint64_t start=ms(),deadline=start+(image?7500000u:180000u);
    puts("XINYI_CHAIN_ENGINEERING_ONLY physical_hid=0 gui_coremark=0 no_synthetic_inference=1");
    if(benchmark && !xy_runtime_action(&r,XY_ACTION_COREMARK))goto done;
    if(!benchmark && !xy_runtime_action(&r,XY_ACTION_START))goto done;
    while(!interrupted && !r.fatal && ms()<deadline){
        xy_job previous=r.app.job;
        (void)xy_runtime_poll(&r);
        if(r.app.job!=previous)
            printf("XINYI_CHAIN_PHASE from=%u to=%u elapsed_ms=%llu photo_ms=%u\n",
                   (unsigned)previous,(unsigned)r.app.job,(unsigned long long)(ms()-start),r.app.photo_latency_ms);
        if(benchmark && r.app.job==XY_IDLE){
            printf("XINYI_CHAIN_COREMARK scope=headless board=%d valid=%d measured=%d perf_iterations=%llu perf_ticks=%llu validation_ticks=%llu cpu_hz=%u score_per_mhz=%.9f identity=%s\n",
                   r.coremark.is_board,r.coremark.valid,r.app.coremark_measured,
                   (unsigned long long)r.coremark.perf_iterations,(unsigned long long)r.coremark.perf_ticks,
                   (unsigned long long)r.coremark.validation_ticks,r.coremark.cpu_hz,
                   r.app.coremark_per_mhz,r.coremark.identity);
            if(!r.app.coremark_measured || r.coremark.status!=XY_CM_DONE)goto done;
            benchmark=0;
            if(!image){rc=0;break;}
            if(!xy_runtime_action(&r,XY_ACTION_START))goto done;
        }
        if(image && !benchmark && !started && r.app.page==XY_GAME &&
           !r.navigation_requested && !r.app.navigation_pending && xy_coach_ready(r.coach)){
            if(!xy_runtime_space(&r,0))goto done;
            started=1;puts("XINYI_CHAIN_AUTOMATED_CAPTURE_BEGIN physical_hid=0");
        }
        if(started && !r.app.cancelling && r.app.job==XY_IDLE){
            printf("XINYI_CHAIN_PHOTO geometry_ok=%d board_present=%d recommendation=%d corrected_cells=%u removed=%u position_reason=%u elapsed_ms=%u audio_ok=%d audio_cleanup=%d\n",
                   r.app.current_photo_valid,r.app.has_board,r.app.has_recommendation,
                   r.app.photo.corrected_cells,r.app.photo.removed_count,(unsigned)r.app.photo.reason,
                   r.app.photo_latency_ms,r.speech.state==XY_SPEECH_DONE,r.speech.cleanup_confirmed);
            rc=r.app.current_photo_valid && r.app.has_recommendation &&
               r.speech.state==XY_SPEECH_DONE && r.speech.cleanup_confirmed?0:1;break;
        }
        xy_platform_input input;
        if(xy_platform_read_input(platform,&input) && input.key==27){interrupted=1;break;}
        const struct timespec pause={0,5000000};nanosleep(&pause,NULL);
    }
done:
    if(interrupted || r.fatal || ms()>=deadline)rc=1;
    int released=xy_runtime_shutdown(&r);
    if(!xy_platform_close(platform))released=0;
    if(!released)rc=4;
    printf("XINYI_CHAIN_STOP released=%d result=%d physical_hid_acceptance=0\n",released,rc);
    return rc;
}
