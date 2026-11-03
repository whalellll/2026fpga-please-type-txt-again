#define _POSIX_C_SOURCE 200809L
#include "xqvoice_session.c"
#include <assert.h>

static void position(xq_search_board_t *b) {
    static const uint8_t back[9]={5,4,3,2,1,2,3,4,5};
    memset(b,0,sizeof(*b));
    for(unsigned i=0;i<9;i++){b->squares[i]=back[i];b->squares[81+i]=back[i]|SIDE_BLACK;}
    for(unsigned i=0;i<9;i+=2){b->squares[27+i]=PIECE_P;b->squares[54+i]=PIECE_P|SIDE_BLACK;}
    b->squares[19]=b->squares[25]=PIECE_C;b->squares[64]=b->squares[70]=PIECE_C|SIDE_BLACK;
}
static void poll_for(xqvoice_session *s,xq_search_board_t *b,int state) {
    struct timespec delay={0,1000000};uint64_t limit=now_ms()+1500;
    do {(void)xqvoice_session_poll(s,b,8,1);if(s->state==state)return;nanosleep(&delay,NULL);}while(now_ms()<limit);
    fprintf(stderr,"state=%d expected=%d error=%s\n",s->state,state,s->error?s->error:"none");assert(0);
}
int main(int argc,char **argv) {
    xqvoice_session s;xq_search_board_t b,before;xq_search_move_t move;
    assert(argc==3);position(&b);before=b;xqvoice_session_init(&s);
    assert(!setenv("XQVOICE_RUNTIME",argv[1],1) && !setenv("XQVOICE_MODEL",argv[2],1));
    assert(!setenv("XQVOICE_AUDIO_DEVICE","idle",1));
    assert(xqvoice_session_start(&s,&b,8,1));
    for(unsigned i=0;i<1000 && !s.listening_ready;i++) {
        struct timespec delay={0,1000000};(void)xqvoice_session_poll(&s,&b,8,1);nanosleep(&delay,NULL);
        assert(s.state!=XQV_ERROR);
    }
    assert(s.listening_ready && s.worker_ready && s.worker_busy);
    assert(xqvoice_session_pause(&s));assert(!s.worker_busy && !s.request && !memcmp(&b,&before,sizeof(b)));
    assert(!setenv("XQVOICE_AUDIO_DEVICE","late",1));s.next_start_ms=0;
    assert(xqvoice_session_start(&s,&b,8,1));
    for(unsigned i=0;i<1000 && !s.listening_ready;i++) {
        struct timespec delay={0,1000000};(void)xqvoice_session_poll(&s,&b,8,1);nanosleep(&delay,NULL);
    }
    assert(s.listening_ready && xqvoice_session_pause(&s));
    assert(!s.request && !memcmp(&b,&before,sizeof(b)) && !xqvoice_session_apply(&s,&b,8,1,&move));
    assert(!setenv("XQVOICE_AUDIO_DEVICE","legal",1));s.next_start_ms=0;
    assert(xqvoice_session_start(&s,&b,8,1));poll_for(&s,&b,XQV_READY);
    assert(xqvoice_session_apply(&s,&b,8,1,&move));assert(!xqvoice_session_apply(&s,&b,8,1,&move));
    assert(s.worker_starts==1);xqvoice_session_close(&s);
    puts("WORKER_CHANNEL_PASS stderr isolated, resident reuse, cancel/late-result no commit, legal once");return 0;
}
