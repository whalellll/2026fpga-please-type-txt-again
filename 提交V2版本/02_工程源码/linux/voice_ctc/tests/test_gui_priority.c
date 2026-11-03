#include "xqvoice_gui_flow.h"
#include "xiangqi_fb_gui.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void setup(xqvoice_session *s,xq_search_board_t *b,xq_mouse_input_t *m) {
    static const uint8_t back[9]={PIECE_R,PIECE_N,PIECE_B,PIECE_A,PIECE_K,PIECE_A,PIECE_B,PIECE_N,PIECE_R};
    memset(b,0,sizeof(*b));for(unsigned i=0;i<9;i++){b->squares[i]=back[i];b->squares[81+i]=back[i]|SIDE_BLACK;}
    for(unsigned i=0;i<9;i+=2){b->squares[27+i]=PIECE_P;b->squares[54+i]=PIECE_P|SIDE_BLACK;}
    b->squares[19]=b->squares[25]=PIECE_C;b->squares[64]=b->squares[70]=PIECE_C|SIDE_BLACK;
    xqvoice_session_init(s);xq_mouse_input_init(m,0);s->state=XQV_READY;s->request=s->next_request=1;s->revision=5;s->snapshot=*b;
    assert(xqvoice_phrase("马二进三",&s->command));strcpy(s->pending_phrase,"马二进三");
}
int main(void) {
    xqvoice_session s;xq_search_board_t b,before;xq_mouse_input_t m;int origin;
    setup(&s,&b,&m);assert(xqvoice_gui_input(&s,&b,5,&m,0,0,0,1,&origin)==XQ_MOUSE_ACTION_MOVED && origin);
    assert(b.side==1 && b.squares[1]==0 && b.squares[20]==PIECE_N);
    before=b;assert(xqvoice_gui_input(&s,&b,5,&m,0,0,0,0,&origin)==XQ_MOUSE_ACTION_NONE && !origin && !memcmp(&b,&before,sizeof(b)));
    setup(&s,&b,&m);before=b;
    assert(xqvoice_gui_input(&s,&b,5,&m,1000,610,1,1,&origin)==XQ_MOUSE_ACTION_RESTART && !origin);
    assert(!memcmp(&b,&before,sizeof(b)) && !s.request && s.state==XQV_IDLE);
    setup(&s,&b,&m);before=b;
    assert(xqvoice_gui_input(&s,&b,5,&m,224,456,1,1,&origin)==XQ_MOUSE_ACTION_SELECTED && !origin);
    assert(!memcmp(&b,&before,sizeof(b)) && !s.request && m.selected_square==29);
    assert(!xqvoice_gui_listen_ready(&b,&m,1));
    setup(&s,&b,&m);before=b;
    assert(xqvoice_gui_input(&s,&b,5,&m,0,0,0,0,&origin)==XQ_MOUSE_ACTION_NONE && !origin && !s.request);
    assert(!memcmp(&b,&before,sizeof(b)));
    setup(&s,&b,&m);before=b;
    assert(xqvoice_gui_input(&s,&b,6,&m,224,456,1,1,&origin)==XQ_MOUSE_ACTION_SELECTED && !origin && !s.request);
    assert(!memcmp(&b,&before,sizeof(b)));
    puts("GUI_PRIORITY_PASS restart/mouse-selection precede ready-voice,disabled/stale cancel,legal once-only");return 0;
}
