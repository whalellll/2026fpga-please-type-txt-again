#ifndef XINYI_UI_FEEDBACK_H
#define XINYI_UI_FEEDBACK_H
#include "../xinyi/xinyi_product.h"
#include <string.h>

typedef struct { xy_pointer_event hover,pressed,released; } xy_feedback_view;
typedef struct {
    xy_feedback_view view;
    xy_pointer_event armed,pending;
    uint64_t pressed_until,release_at,activate_at;
    unsigned token;
    int page,mode,job,log,down,initialized;
} xy_feedback;
static inline void xy_feedback_reset(xy_feedback *s) { memset(s,0,sizeof(*s)); }
/* Snapshot only enabled buttons. Never infer a release from an unstable HID
 * sample. A quick counter-only click gets two visible, bounded phases. */
static inline xy_pointer_event xy_feedback_step(xy_feedback *s,const xy_app *a,
    int valid,unsigned x,unsigned y,int down,int press,uint64_t now,int *board_press)
{
    xy_pointer_event hit=valid?xy_pointer_action(a,x,y):XY_ACTION_NONE;
    xy_pointer_event result=XY_ACTION_NONE;
    *board_press=0;
    if(!s->initialized || s->page!=(int)a->page || s->mode!=(int)a->mode ||
       s->job!=(int)a->job || s->token!=a->token || s->log!=a->coremark_log_visible ||
       a->cancelling || a->navigation_pending) {
        xy_feedback_reset(s);s->initialized=1;s->page=a->page;s->mode=a->mode;
        s->job=a->job;s->token=a->token;s->log=a->coremark_log_visible;
        /* A held button entering another screen cannot arm that screen. */
        s->down=down && !press;
    }
    s->view.hover=hit;
#if XINYI_HOME_R13
    /* Feedback never owns an action deadline. A complete counter-only click
     * acts now; its short visual phases continue only while this view lives. */
    if(!valid){s->armed=s->pending=XY_ACTION_NONE;s->view=(xy_feedback_view){0};s->down=down;return result;}
    if(s->pending){
        if(now>=s->release_at){s->pending=XY_ACTION_NONE;s->view.pressed=s->view.released=XY_ACTION_NONE;}
        else if(now>=s->pressed_until){s->view.pressed=XY_ACTION_NONE;s->view.released=s->pending;}
    }
    if(press || (down && !s->down)){
        s->armed=hit;s->pending=XY_ACTION_NONE;s->view.pressed=s->view.released=XY_ACTION_NONE;
        if(!hit)*board_press=press && a->page==XY_GAME && (a->mode==XY_VOICE
#if XINYI_BATTLE_R17
            || a->mode==XY_KEYBOARD
#endif
            );
        if(hit && !down){
            result=hit;s->armed=XY_ACTION_NONE;s->pending=hit;
            s->view.pressed=hit;s->pressed_until=now+40;s->release_at=now+140;
        }
    }
    if(s->armed && s->down && !down){
        if(hit==s->armed){result=hit;s->pending=hit;s->view.released=hit;
            s->pressed_until=now;s->release_at=now+100;}
        s->armed=XY_ACTION_NONE;s->view.pressed=XY_ACTION_NONE;
    }
    if(down)s->view.pressed=hit==s->armed?hit:XY_ACTION_NONE;
    s->down=down;return result;
#else
    if(s->pending && !valid) {
        s->pending=XY_ACTION_NONE;s->activate_at=s->release_at=0;
        s->view.pressed=s->view.released=XY_ACTION_NONE;
    }
    if(s->pending) {
        if(now>=s->activate_at) {
            result=s->pending;s->pending=XY_ACTION_NONE;
            s->view.pressed=s->view.released=XY_ACTION_NONE;
        } else if(now>=s->release_at) {
            s->view.pressed=XY_ACTION_NONE;s->view.released=s->pending;
        }
        s->down=down;return result;
    }
    if(valid && (press || (down && !s->down))) {
        s->armed=hit;s->view.released=XY_ACTION_NONE;
        if(!hit)*board_press=press && a->page==XY_GAME && (a->mode==XY_VOICE
#if XINYI_BATTLE_R17
            || a->mode==XY_KEYBOARD
#endif
            );
        if(hit && !down) { /* Press and release both occurred between polls. */
            s->pending=hit;s->view.pressed=hit;
            s->release_at=now+80;s->activate_at=now+180;
        }
    }
    if(s->armed && s->down && !down && valid) {
        if(hit==s->armed) {
            s->pending=hit;s->view.released=hit;
            s->release_at=now;s->activate_at=now+100;
        }
        s->armed=XY_ACTION_NONE;
    }
    if(!valid){s->armed=XY_ACTION_NONE;s->view.hover=XY_ACTION_NONE;}
    if(!s->pending)s->view.pressed=down && hit==s->armed?s->armed:XY_ACTION_NONE;
    else if(now>=s->release_at)s->view.pressed=XY_ACTION_NONE;
    s->down=down;return result;
#endif
}
/* Separate UI state: recognition/app packet layouts remain unchanged. */
void xy_fb_feedback(const xy_feedback_view *);
#endif
