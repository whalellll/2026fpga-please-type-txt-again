/* Same immutable R21 runs and R22 row order. Keep both stream cursors local
 * for the complete frame; no per-run or per-row state publication. */
#ifndef XINYI_GAME_ROW_SCALAR_R23_H
#define XINYI_GAME_ROW_SCALAR_R23_H
static void xy23_game_rows(volatile uint16_t *fb,unsigned mode)
{
    const xy15_run *left=xy21_game_left,*right=xy21_game_right[mode];
    unsigned nl=0,nr=0;uint32_t vl=0,vr=0;
    volatile uint32_t *out=(volatile uint32_t *)(uintptr_t)fb;
    for(unsigned row=0;row<1080;row++){
        unsigned at=0;
        while(at<479){
            if(!nl){nl=left->count;vl=left->value;left++;}
            unsigned count=nl<479u-at?nl:479u-at;
            xy15_template_fill(out+at,count,vl);at+=count;nl-=count;
        }
        while(at<960){
            if(!nr){nr=right->count;vr=right->value;right++;}
            unsigned count=nr<960u-at?nr:960u-at;
            xy15_template_fill(out+at,count,vr);at+=count;nr-=count;
        }
        out+=960;
    }
}
#endif
