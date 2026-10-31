/* Real main loop with explicit off-board platform/runtime events. */
#define _POSIX_C_SOURCE 200809L
#include "runtime.h"
#include <assert.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#if XINYI_UI_FEEDBACK
#include "ui_feedback.h"
static unsigned interactive,action_count,down_renders,release_renders;
static xy_feedback_view shown_feedback;
void xy_fb_feedback(const xy_feedback_view *v){shown_feedback=*v;}
#endif

static xy_runtime *active;
static unsigned step,whole_compares,capture_renders,log_renders,reference_renders;
static unsigned photo_presents,last_present_step,invalid_clock,next_clock_invalid;
static uint64_t ticks;
static long sleeps[64];
static uint16_t pixels[2][16];
static uint32_t regs[16];
#if XINYI_HOME_R13
static unsigned exit_case,shutdown_count,close_count,restore_count;
#if XINYI_BATTLE_R17
static unsigned restart_case,restart_home_renders,restart_game_renders;
#if XINYI_TEST_IDLE_NAV
static unsigned nav_case,nav_source_renders,nav_target_renders;
#endif
#endif
#endif
#if XINYI_GUI_DOUBLE_BUFFER
static unsigned front_page,pending_page,pending_until,flip_pending,last_draw_page,blocked_draws;
int xy_platform_gui_back_page(xy_platform *p,unsigned *page)
{
    (void)p;
    if(flip_pending){++blocked_draws;return 2;}
    *page=front_page^1u;return 1;
}
int xy_platform_gui_initial_idle(xy_platform *p){assert(p==(xy_platform *)regs);return 0;}
#endif
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
int xy_platform_close(xy_platform *p){(void)p;
#if XINYI_HOME_R13
 if(exit_case)close_count++;
#endif
 return 1;}
uint32_t xy_platform_cpu_hz(const xy_platform *p){return p?XINYI_CPU_HZ:0;}
volatile uint16_t *xy_platform_pixels(xy_platform *p,unsigned page){(void)p;assert(page<2);return pixels[page];}
volatile uint32_t *xy_platform_video_regs(xy_platform *p){(void)p;return regs;}
int xy_platform_present(xy_platform *p,unsigned page)
{(void)p;(void)page;last_present_step=step;ticks+=17000000;
#if XINYI_GUI_DOUBLE_BUFFER
 assert(page==last_draw_page && page!=front_page && !flip_pending);
 pending_page=page;pending_until=step+2;flip_pending=1;
#endif
 if(step==5 && invalid_clock)next_clock_invalid=1;
 return 1;}
int xy_platform_take_invalidation(xy_platform *p){(void)p;return 0;}
int xy_platform_terminal_attach(xy_platform *p,int fd){(void)p;(void)fd;return 1;}
int xy_platform_terminal_key(xy_platform *p){(void)p;return 0;}
void xy_platform_terminal_restore(xy_platform *p){(void)p;
#if XINYI_HOME_R13
 if(exit_case)restore_count++;
#endif
}
int xy_platform_read_input(xy_platform *p,xy_platform_input *out)
{
    (void)p;memset(out,0,sizeof(*out));
#if XINYI_TEST_IDLE_NAV
    if(nav_case)return 1;
#endif
    out->left_click=step==9 || step==10;
#if XINYI_UI_FEEDBACK
    if(interactive){out->mouse_sample=out->mouse_valid=1;out->mouse_x=out->mouse_y=100;
        out->left_down=step>=3 && step<=8;out->left_click=step==3;}
#endif
    return 1;
}
int xq_fb_gui_init(void){return 1;}
void xy_fb_invalidate(void){}
void xy_fb_render(const xy_app *a,volatile uint16_t *fb)
{
#if XINYI_TEST_IDLE_NAV
    if(nav_case){
        if(active->navigation_requested && a->page==XY_GAME){
            ++nav_source_renders;
            if(nav_case==1){fputs("R21_IDLE_NAV_UNNECESSARY_OLD_PAGE_RENDER\n",stderr);assert(0);}
        }
        nav_target_renders+=a->page==XY_HOME && step>=8;
    }
#endif
#if XINYI_BATTLE_R17
    if(restart_case){
        restart_home_renders+=a->page==XY_HOME && active->restart_requested;
        assert(!(a->page==XY_HOME && active->restart_requested));
        restart_game_renders+=a->page==XY_GAME && step>=10;
    }
#endif
#if XINYI_GUI_DOUBLE_BUFFER
    assert(fb!=pixels[front_page]); /* Red on the original live-page renderer. */
    unsigned saved[16];for(unsigned i=0;i<16;i++)saved[i]=pixels[front_page][i];
    for(unsigned row=0;row<16;row++){
        fb[row]=(uint16_t)(step+row);
        for(unsigned i=0;i<16;i++)assert(pixels[front_page][i]==saved[i]);
    }
    last_draw_page=fb==pixels[1];
#else
    (void)fb;
#endif
#if XINYI_UI_FEEDBACK
    if(interactive){down_renders+=shown_feedback.pressed!=0;release_renders+=shown_feedback.released!=0;}
#endif
    if(a->job==XY_CAPTURE && !a->cancelling)++capture_renders;
    if(a->coremark_log_visible)++log_renders;
    if(a->job==XY_COREMARK)++reference_renders;
}
xy_pointer_event xy_pointer_action(const xy_app *a,unsigned x,unsigned y)
{(void)a;(void)x;(void)y;
#if XINYI_BATTLE_R17
 if(restart_case)return XY_ACTION_RESTART;
#endif
#if XINYI_HOME_R13
 if(exit_case)return XY_ACTION_EXIT;
#endif
#if XINYI_UI_FEEDBACK
 if(interactive)return XY_ACTION_CM_LOG;
#endif
 return step==9?XY_ACTION_CM_LOG:XY_ACTION_CM_LOG_CLOSE;}
int xy_runtime_init(xy_runtime *r,xy_platform *p,const xy_runtime_config *cfg)
{
    memset(r,0,sizeof(*r));active=r;r->platform=p;r->config=*cfg;r->dirty=1;
    r->app.page=XY_HOME;r->app.mode=XY_COACH;r->app.job=XY_IDLE;
#if XINYI_BATTLE_R17
 if(restart_case){r->app.page=XY_GAME;r->app.mode=XY_VOICE;}
#if XINYI_TEST_IDLE_NAV
 if(nav_case){r->app.page=XY_GAME;r->app.mode=XY_COACH;}
#endif
#endif
 return 1;
}
int xy_runtime_action(xy_runtime *r,xy_pointer_event e)
{
#if XINYI_BATTLE_R17
 if(restart_case){assert(e==XY_ACTION_RESTART && step==9);r->restart_requested=1;r->app.page=XY_HOME;r->dirty=1;action_count++;return 1;}
#endif
#if XINYI_HOME_R13
 if(exit_case){assert(e==XY_ACTION_EXIT && step==9);action_count++;r->exit_requested=1;return 1;}
#endif
#if XINYI_UI_FEEDBACK
 if(interactive){assert(step>8);action_count++;}
#endif
 r->app.coremark_log_visible=e==XY_ACTION_CM_LOG;r->dirty=1;return 1;}
int xy_runtime_pointer(xy_runtime *r,unsigned x,unsigned y)
{return xy_runtime_action(r,xy_pointer_action(&r->app,x,y));}
int xy_runtime_space(xy_runtime *r,uint64_t stamp){(void)r;(void)stamp;return 0;}
#if XINYI_BATTLE_R17
static unsigned scanout_polls,render_submits;
int xy_runtime_key(xy_runtime *r,int key){(void)r;(void)key;return 0;}
void xy_runtime_frame_submitted(xy_runtime *r,unsigned page,uint32_t frame)
{
    assert(r==active && last_present_step==step && page==last_draw_page && frame==regs[9]);
    render_submits++;
}
int xy_runtime_display_ack(xy_runtime *r,uint32_t status,uint32_t frame,uint64_t now)
{
    assert(r==active && status==regs[3] && frame==regs[9] && now==ticks/1000000u);
    scanout_polls++;return 0;
}
#endif
void xy_runtime_cancel(xy_runtime *r){r->app.cancelling=1;r->dirty=1;}
int xy_runtime_shutdown(xy_runtime *r){(void)r;
#if XINYI_HOME_R13
 if(exit_case)shutdown_count++;
#endif
 return 1;}
int xy_runtime_poll(xy_runtime *r)
{
    assert(r==active);++step;
#if XINYI_BATTLE_R17
 if(restart_case && step==10){r->restart_requested=0;r->app.page=XY_GAME;r->dirty=1;}
#endif
#if XINYI_GUI_DOUBLE_BUFFER
    if(flip_pending && step>=pending_until){front_page=pending_page;flip_pending=0;}
#if XINYI_BATTLE_R17
    regs[3]=2u|(front_page<<2);regs[9]++;
#endif
#if XINYI_TEST_IDLE_NAV
    if(nav_case){
        if(step==3){r->navigation_requested=1;r->destination_page=XY_HOME;r->destination_mode=XY_COACH;
            r->app.cancelling=nav_case==2;r->speech.pid=1234;r->dirty=1;
            strcpy(r->app.message,"正在安全停止，请稍后");}
        if(step==8){assert(r->dirty || nav_case==2);r->app.page=XY_HOME;r->app.cancelling=0;
            r->navigation_requested=0;r->speech.pid=0;r->dirty=1;}
        if(step==12)r->fatal=1;
        return 0;
    }
#endif
    if(step==7
#if XINYI_UI_FEEDBACK
       && !interactive
#endif
       )assert(r->dirty); /* A delayed flip must not lose the new state. */
#endif
#if XINYI_UI_FEEDBACK
    if(interactive){if(step==40)r->fatal=1;return 0;}
#endif
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
#if XINYI_GUI_DOUBLE_BUFFER
        front_page=pending_page=pending_until=flip_pending=last_draw_page=blocked_draws=0;
#endif
        char *args[]={"product-loop-fixture",NULL};assert(!xinyi_product_entry(1,args));
        assert(!whole_compares); /* Idle loop must not scan the 16 KiB log buffer. */
        assert(capture_renders==1 && log_renders==!XINYI_UI_FEEDBACK && reference_renders==1 && photo_presents==1);
        assert(sleeps[3]==50000000 && sleeps[4]==50000000 && sleeps[6]==5000000);
#if XINYI_GUI_DOUBLE_BUFFER
        assert(blocked_draws>0);
#endif
    }
#if XINYI_UI_FEEDBACK
    interactive=1;step=0;ticks=0;invalid_clock=next_clock_invalid=0;
    front_page=pending_page=pending_until=flip_pending=last_draw_page=blocked_draws=0;
    char *ui_args[]={"product-loop-feedback-fixture",NULL};assert(!xinyi_product_entry(1,ui_args));
    assert(action_count==1 && down_renders && release_renders);
    puts("PRODUCT_REAL_MAIN_UI_DOWN_RELEASE_PRESENT_BEFORE_SINGLE_ACTION_PASS_NOT_BOARD");
#if XINYI_HOME_R13
    exit_case=1;step=0;ticks=0;action_count=0;
    front_page=pending_page=pending_until=flip_pending=last_draw_page=blocked_draws=0;
    assert(!xinyi_product_entry(1,ui_args));
    assert(step==9 && action_count==1 && shutdown_count==1 && restore_count==1 && close_count==1);
    puts("PRODUCT_R13_REAL_MAIN_EXIT_ON_RELEASE_SHUTDOWN_TERMINAL_PLATFORM_ONCE_PASS_NOT_BOARD");
#if XINYI_BATTLE_R17
    exit_case=0;restart_case=1;step=0;ticks=0;action_count=0;front_page=pending_page=pending_until=flip_pending=last_draw_page=blocked_draws=0;
    assert(!xinyi_product_entry(1,ui_args));
    assert(action_count==1 && !restart_home_renders && restart_game_renders);
    puts("PRODUCT_R17_RESTART_INTERNAL_HOME_NEVER_RENDERED_DIRTY_PRESERVED_GAME_RETURN_PASS_NOT_BOARD");
#endif
#endif
#endif
#if XINYI_TEST_IDLE_NAV
    interactive=exit_case=restart_case=0;
    for(nav_case=1;nav_case<=2;nav_case++){
        step=0;ticks=0;invalid_clock=next_clock_invalid=0;nav_source_renders=nav_target_renders=0;
        front_page=pending_page=pending_until=flip_pending=last_draw_page=blocked_draws=0;
        char *nav_args[]={"idle-navigation-fixture",NULL};assert(!xinyi_product_entry(1,nav_args));
        assert(nav_target_renders && (nav_case==1?!nav_source_renders:nav_source_renders>0));
    }
    nav_case=0;
    puts("PRODUCT_R21_IDLE_NAV_COALESCED_CANCEL_VISIBLE_DIRTY_AND_TARGET_PASS");
#endif
    puts("PRODUCT_PHOTO_PRESENT_AFTER_SUBMIT_ONCE_CANCEL_AND_INVALID_CLOCK_PASS_NOT_BOARD");
    puts("PRODUCT_MAIN_LOOP_DIRTY_EVENTS_THROTTLE_RETENTION_CANCEL_AND_NO_LOG_SCAN_PASS_NOT_BOARD");
#if XINYI_BATTLE_R17
    assert(scanout_polls && render_submits && scanout_polls>render_submits);
    puts("PRODUCT_R17_REAL_MAIN_REG_STATUS_FRAME_TIME_AND_SUBMIT_AFTER_PRESENT_PASS_NOT_BOARD");
#endif
#if XINYI_GUI_DOUBLE_BUFFER
    puts("PRODUCT_BACK_PAGE_RENDER_FRONT_UNCHANGED_DELAYED_FLIP_DIRTY_RETAINED_PASS_NOT_BOARD");
#endif
    return 0;
}
