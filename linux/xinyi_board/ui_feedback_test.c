#include "../xinyi/xinyi_fb.c"
#include <assert.h>
#include <stdlib.h>

volatile uint32_t *xq_linux_video_regs;
volatile uint16_t *xq_linux_framebuffers[2];
static unsigned cases;
static void step(xy_feedback *s,xy_app *a,unsigned x,unsigned y,int down,int press,
                 uint64_t now,xy_pointer_event expected)
{
    int board=0;assert(xy_feedback_step(s,a,1,x,y,down,press,now,&board)==expected);
    assert(!board);cases++;
}
static void interactions(void)
{
    xy_app a;xy_app_init(&a,NULL);xy_feedback s={0};int board;
    step(&s,&a,150,360,0,0,0,XY_ACTION_NONE);assert(s.view.hover==XY_ACTION_START);
    step(&s,&a,150,360,1,1,5,XY_ACTION_NONE);assert(s.view.pressed==XY_ACTION_START);
    step(&s,&a,150,360,1,0,1000,XY_ACTION_NONE);assert(!s.pending); /* Holding never activates. */
    step(&s,&a,1,1,1,0,1001,XY_ACTION_NONE);assert(!s.view.pressed);
    step(&s,&a,150,360,1,0,1002,XY_ACTION_NONE);assert(s.view.pressed==XY_ACTION_START);
    step(&s,&a,150,360,0,0,1003,XY_ACTION_NONE);assert(s.view.released==XY_ACTION_START);
    step(&s,&a,150,360,0,0,1102,XY_ACTION_NONE);
    step(&s,&a,150,360,0,0,1103,XY_ACTION_START);
    step(&s,&a,150,360,0,0,1104,XY_ACTION_NONE);
    /* Drag out and release; pressing outside then entering is also inert. */
    step(&s,&a,150,360,1,1,1200,XY_ACTION_NONE);
    step(&s,&a,1,1,0,0,1201,XY_ACTION_NONE);
    assert(!xy_feedback_step(&s,&a,1,1,1,1,1,1202,&board) && !board);
    step(&s,&a,150,360,1,0,1203,XY_ACTION_NONE);
    step(&s,&a,150,360,0,0,1204,XY_ACTION_NONE);assert(!s.pending);
    /* Counter catches a full short click between two input polls. */
    step(&s,&a,150,360,0,1,2000,XY_ACTION_NONE);assert(s.view.pressed==XY_ACTION_START);
    step(&s,&a,150,360,0,0,2079,XY_ACTION_NONE);assert(s.view.pressed==XY_ACTION_START);
    step(&s,&a,150,360,0,0,2080,XY_ACTION_NONE);assert(s.view.released==XY_ACTION_START);
    step(&s,&a,150,360,0,0,2180,XY_ACTION_START);
    /* New generation, cancellation, screen switch and lost pointer invalidate capture. */
    for(unsigned control=0;control<4;control++){
        xy_feedback_reset(&s);xy_app_init(&a,NULL);
        step(&s,&a,150,360,0,1,3000,XY_ACTION_NONE);
        if(control==0)a.token++;
        if(control==1)a.cancelling=1;
        if(control==2){a.page=XY_GAME;a.mode=XY_VOICE;}
        if(control==3){assert(!xy_feedback_step(&s,&a,0,150,360,0,0,3001,&board));
            assert(!s.view.hover && !s.view.pressed && !s.view.released);}
        assert(!xy_feedback_step(&s,&a,1,150,360,0,0,3400,&board));
    }
    xy_app_init(&a,NULL);a.job=XY_COREMARK;xy_feedback_reset(&s);
    step(&s,&a,150,360,0,1,5000,XY_ACTION_NONE);assert(!s.view.hover && !s.pending);
}
static void pixels(void)
{
    xy_app a;xy_app_init(&a,NULL);
    uint32_t *guard[2];uint16_t *banks[2],*ref=malloc(VIDEO_FB_FRAME_BYTES),*before=malloc(VIDEO_FB_FRAME_BYTES);
    assert(ref && before);
    for(unsigned b=0;b<2;b++){
        guard[b]=malloc(VIDEO_FB_FRAME_BYTES+128);assert(guard[b]);
        for(unsigned i=0;i<(VIDEO_FB_FRAME_BYTES+128)/4;i++)guard[b][i]=0xcafebabe;
        banks[b]=(void *)(guard[b]+16);
    }
    for(unsigned page=0;page<4;page++){
        a.page=page<2?XY_HOME:XY_GAME;a.coremark_log_visible=page==1;a.mode=page==3?XY_VOICE:XY_COACH;
        xy_pointer_target targets[XY_POINTER_TARGETS];unsigned n=xy_pointer_targets(&a,targets,XY_POINTER_TARGETS);
        for(unsigned t=0;t<n;t++)for(unsigned phase=0;phase<5;phase++)for(unsigned b=0;b<2;b++){
            xy_feedback_view v={0};xy_pointer_event action=targets[t].action;
            if(phase==1 || phase==2)v.hover=action;
            if(phase==2)v.pressed=action;
            if(phase==3)v.released=action;
            xy_fb_feedback(&v);
            /* Warm both banks before measuring a local visual-only update. */
            xy_fb_render(&a,banks[b]);
            xy_page_cache saved[2];memcpy(saved,xy_page_caches,sizeof(saved));
            xy_fb_invalidate();xy_fb_render(&a,ref);
            assert(!memcmp(ref,banks[b],VIDEO_FB_FRAME_BYTES));
            memcpy(xy_page_caches,saved,sizeof(saved));
            memcpy(before,banks[b],VIDEO_FB_FRAME_BYTES);
            xy_fb_render(&a,banks[b]);assert(!memcmp(before,banks[b],VIDEO_FB_FRAME_BYTES));cases++;
        }
    }
    /* Feedback must change only the actual enabled button's footprint. */
    a.page=XY_HOME;a.coremark_log_visible=0;a.job=XY_IDLE;
    xy_feedback_view v={0};xy_fb_feedback(&v);xy_fb_render(&a,banks[0]);memcpy(before,banks[0],VIDEO_FB_FRAME_BYTES);
    v.hover=XY_ACTION_START;xy_fb_feedback(&v);xy_fb_render(&a,banks[0]);unsigned changed=0;
    for(unsigned i=0;i<1920*1080;i++)if(before[i]!=banks[0][i]){
        unsigned x=i%1920,y=i/1920;assert(x>=112 && x<412 && y>=336 && y<412);changed++;
    }
    assert(changed>1000);
    unsigned face=345*1920+250;uint16_t normal=before[face];
    v.pressed=XY_ACTION_START;xy_fb_feedback(&v);xy_fb_render(&a,banks[0]);
    uint16_t pressed=banks[0][face];
    assert((pressed>>11)<(normal>>11) && ((pressed>>5)&63)<((normal>>5)&63) && (pressed&31)<(normal&31));
    for(unsigned b=0;b<2;b++){
        for(unsigned i=0;i<16;i++)assert(guard[b][i]==0xcafebabe && guard[b][16+VIDEO_FB_FRAME_BYTES/4+i]==0xcafebabe);
        free(guard[b]);
    }
    free(ref);free(before);
}
int main(void)
{
    interactions();pixels();printf("UI_FEEDBACK_PASS cases=%u hover/down/release,held,drag,short-click,stale,cancel,disabled,two-bank-full-pixels,guards,local-only NOT_BOARD\n",cases);return 0;
}
