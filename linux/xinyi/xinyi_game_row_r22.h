/* Exact R21 RLE runs, visited in framebuffer row order. No allocation. */
#ifndef XINYI_GAME_ROW_R22_H
#define XINYI_GAME_ROW_R22_H
static void xy22_row_half(volatile uint32_t *out,unsigned width,const xy15_run **cursor,
    unsigned *remaining,uint32_t *value)
{
    unsigned at=0;
    while(at<width){
        if(!*remaining){*remaining=(*cursor)->count;*value=(*cursor)->value;(*cursor)++;}
        unsigned count=*remaining<width-at?*remaining:width-at;
        xy15_template_fill(out+at,count,*value);at+=count;*remaining-=count;
    }
}
static void xy22_game_rows(volatile uint16_t *fb,unsigned mode)
{
    const xy15_run *left=xy21_game_left,*right=xy21_game_right[mode];
    unsigned nl=0,nr=0;uint32_t vl=0,vr=0;
    volatile uint32_t *out=(volatile uint32_t *)(uintptr_t)fb;
    for(unsigned row=0;row<1080;row++){
        xy22_row_half(out,479,&left,&nl,&vl);
        xy22_row_half(out+479,481,&right,&nr,&vr);out+=960;
    }
}
#endif
