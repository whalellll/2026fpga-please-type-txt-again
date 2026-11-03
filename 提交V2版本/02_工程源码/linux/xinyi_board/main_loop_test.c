/* Real main loop with explicit off-board platform/runtime events. */
#define _POSIX_C_SOURCE 200809L
#include "runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static xy_runtime *active;
static unsigned step,whole_compares,capture_renders,log_renders,reference_renders;
static unsigned photo_presents,last_present_step,invalid_clock,next_clock_invalid;
static uint64_t ticks;
static long sleeps[64];
static uint16_t pixels[16];
static uint32_t regs[16];
int xinyi_product_entry(int,char **);
int __real_memcmp(const void *,const void *,size_t);
int __wrap_memcmp(const void *a,const void *b,size_t n)
{if(n==sizeof(xy_app))++whole_compares;return __real_memcmp(a,b,n);}
static int output(const char *format,va_list arguments)
{
    char text[1024];int n=vsnprintf(text,sizeof(text),format,arguments);
    if(!strncmp(text,"XINYI_PHOTO_PRESENT ",20)){
        unsigned long long elapsed=0;unsigned valid=2;
        assert(sscanf(text,"XINYI_PHOTO_PRESENT elapsed_ms=%llu time_valid=%u",&elapsed,&valid)==2);
        assert(last_present_step==5 && step==5 && valid==!invalid_clock);
        if(valid)assert(elapsed>100);else assert(!elapsed);
        ++photo_presents;
    }
    fputs(text,stdout);return n;
}
int __wrap_printf(const char *format,...)
{va_list arguments;va_start(arguments,format);int n=output(format,arguments);va_end(arguments);return n;}
int __wrap___printf_chk(int flag,const char *format,...)
{(void)flag;va_list arguments;va_start(arguments,format);int n=output(format,arguments);va_end(arguments);return n;}
int clock_gettime(clockid_t id,struct timespec *t)
{(void)id;if(next_clock_invalid){next_clock_invalid=0;t->tv_sec=t->tv_nsec=0;return 0;}
 t->tv_sec=(time_t)(ticks/1000000000u);t->tv_nsec=(long)(ticks%1000000000u);return 0;}
int nanosleep(const struct timespec *t,struct timespec *remaining)
{(void)remaining;assert(step<64);sleeps[step]=t->tv_nsec;ticks+=(uint64_t)t->tv_sec*1000000000u+(unsigned long)t->tv_nsec;return 0;}
xy_platform *xy_platform_open(void){return (xy_platform *)regs;}
int xy_platform_close(xy_platform *p){(void)p;return 1;}
uint32_t xy_platform_cpu_hz(const xy_platform *p){return p?XINYI_CPU_HZ:0;}
volatile uint16_t *xy_platform_pixels(xy_platform *p,unsigned page){(void)p;(void)page;return pixels;}
volatile uint32_t *xy_platform_video_regs(xy_platform *p){(void)p;return regs;}
int xy_platform_present(xy_platform *p,unsigned page)
{(void)p;(void)page;last_present_step=step;ticks+=17000000;
 if(step==5 && invalid_clock)next_clock_invalid=1;
 return 1;}
int xy_platform_take_invalidation(xy_platform *p){(void)p;return 0;}
int xy_platform_terminal_attach(xy_platform *p,int fd){(void)p;(void)fd;return 1;}
int xy_platform_terminal_key(xy_platform *p){(void)p;return 0;}
void xy_platform_terminal_restore(xy_platform *p){(void)p;}
int xy_platform_read_input(xy_platform *p,xy_platform_input *out)
{
    (void)p;memset(out,0,sizeof(*out));out->left_click=step==9 || step==10;return 1;
}
int xq_fb_gui_init(void){return 1;}
void xy_fb_invalidate(void){}
void xy_fb_render(const xy_app *a,volatile uint16_t *fb)
{
    (void)fb;
    if(a->job==XY_CAPTURE && !a->cancelling)++capture_renders;
    if(a->coremark_log_visible)++log_renders;
    if(a->job==XY_COREMARK)++reference_renders;
}
xy_pointer_event xy_pointer_action(const xy_app *a,unsigned x,unsigned y)
{(void)a;(void)x;(void)y;return step==9?XY_ACTION_CM_LOG:XY_ACTION_CM_LOG_CLOSE;}
int xy_runtime_init(xy_runtime *r,xy_platform *p,const xy_runtime_config *cfg)
{
    memset(r,0,sizeof(*r));active=r;r->platform=p;r->config=*cfg;r->dirty=1;
    r->app.page=XY_HOME;r->app.mode=XY_COACH;r->app.job=XY_IDLE;return 1;
}
int xy_runtime_action(xy_runtime *r,xy_pointer_event e)
{r->app.coremark_log_visible=e==XY_ACTION_CM_LOG;r->dirty=1;return 1;}
int xy_runtime_pointer(xy_runtime *r,unsigned x,unsigned y)
{return xy_runtime_action(r,xy_pointer_action(&r->app,x,y));}
int xy_runtime_space(xy_runtime *r,uint64_t stamp){(void)r;(void)stamp;return 0;}
void xy_runtime_cancel(xy_runtime *r){r->app.cancelling=1;r->dirty=1;}
int xy_runtime_shutdown(xy_runtime *r){(void)r;return 1;}
int xy_runtime_poll(xy_runtime *r)
{
    assert(r==active);++step;
    if(step==3){r->app.job=XY_CAPTURE;r->app.token=1;r->photo_started_ms=ticks/1000000;r->dirty=1;}
    if(step==5){r->app.job=XY_RECOMMEND;r->app.current_photo_valid=1;r->dirty=1;}
    if(step==6){r->app.job=XY_CAPTURE;r->app.token=2;r->app.cancelling=1;r->dirty=1;}
    if(step==8){r->app.cancelling=0;r->app.job=XY_IDLE;r->dirty=1;}
    if(step==12){r->app.job=XY_COREMARK;r->app.coremark_origin=XY_COREMARK_REFERENCE;r->dirty=1;}
    if(step==13)assert(r->dirty && !reference_renders); /* Preserve throttled update. */
    if(step==40){r->app.job=XY_IDLE;r->dirty=1;}
    if(step==41)r->fatal=1;
    return 0;
}
int main(void)
{
    static const char *const names[]={"XINYI_COACH_WORKER","XINYI_MODELS","XINYI_ENGINE",
        "XINYI_SPEECH_WORKER","XINYI_PCM","XINYI_COREMARK"};
    for(unsigned i=0;i<sizeof(names)/sizeof(names[0]);++i)assert(!setenv(names[i],"/explicit-offboard-fixture",1));
    for(unsigned run=0;run<2;run++) {
        step=whole_compares=capture_renders=log_renders=reference_renders=photo_presents=last_present_step=next_clock_invalid=0;
        invalid_clock=run;ticks=0;memset(sleeps,0,sizeof(sleeps));
        char *args[]={"product-loop-fixture",NULL};assert(!xinyi_product_entry(1,args));
        assert(!whole_compares); /* Idle loop must not scan the 16 KiB log buffer. */
        assert(capture_renders==1 && log_renders==1 && reference_renders==1 && photo_presents==1);
        assert(sleeps[3]==50000000 && sleeps[4]==50000000 && sleeps[6]==5000000);
    }
    puts("PRODUCT_PHOTO_PRESENT_AFTER_SUBMIT_ONCE_CANCEL_AND_INVALID_CLOCK_PASS_NOT_BOARD");
    puts("PRODUCT_MAIN_LOOP_DIRTY_EVENTS_THROTTLE_RETENTION_CANCEL_AND_NO_LOG_SCAN_PASS_NOT_BOARD");
    return 0;
}
