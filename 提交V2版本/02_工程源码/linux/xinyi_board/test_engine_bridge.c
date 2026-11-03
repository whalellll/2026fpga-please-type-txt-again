#define _POSIX_C_SOURCE 200809L
#include "engine_bridge.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static void position(xq_search_board_t *b)
{
    static const unsigned back[]={PIECE_R,PIECE_N,PIECE_B,PIECE_A,PIECE_K,PIECE_A,PIECE_B,PIECE_N,PIECE_R};
    memset(b,0,sizeof(*b));
    for(unsigned i=0;i<9;i++){b->squares[i]=(uint8_t)back[i];b->squares[81+i]=(uint8_t)(back[i]|SIDE_BLACK);}
    b->squares[19]=b->squares[25]=PIECE_C;
    b->squares[64]=b->squares[70]=PIECE_C|SIDE_BLACK;
    for(unsigned i=0;i<9;i+=2){b->squares[27+i]=PIECE_P;b->squares[54+i]=PIECE_P|SIDE_BLACK;}
}
static xy_engine_state wait_state(xy_engine *e)
{
    for(unsigned n=0;n<5000;n++){
        xy_engine_state state=xy_engine_poll(e);
        if(state==XY_ENGINE_DONE || state==XY_ENGINE_FAILED || state==XY_ENGINE_STOPPED)return state;
        const struct timespec t={0,1000000};nanosleep(&t,NULL);
    }
    assert(!"engine child timeout");return XY_ENGINE_FAILED;
}
int main(int argc,char **argv)
{
    assert(argc==2);xy_engine e;xy_engine_reply reply;xq_search_board_t b;
    position(&b);char text[128];
    assert(xy_engine_notation(&b,"h2e2",text,sizeof(text)) && !strcmp(text,"炮二平五"));
    xy_engine_init(&e);assert(!xy_engine_start(&e,argv[1],0,1,&b,128));
    assert(setenv("XY_ENGINE_TEST","valid",1)==0);
    assert(xy_engine_start(&e,argv[1],11,21,&b,128));
    assert(wait_state(&e)==XY_ENGINE_DONE);
    assert(xy_engine_take(&e,&reply) && reply.token==11 && reply.revision==21 &&
           !strcmp(reply.iccs,"h2e2") && !strcmp(reply.notation,"炮二平五") && reply.red_win_permille==600);
    assert(!xy_engine_take(&e,&reply));
    assert(xy_engine_start(&e,argv[1],12,22,&b,128));assert(wait_state(&e)==XY_ENGINE_DONE);
    assert(xy_engine_take(&e,&reply) && reply.token==12);
    b.side=1;assert(xy_engine_start(&e,argv[1],13,23,&b,128));assert(wait_state(&e)==XY_ENGINE_DONE);
    assert(xy_engine_take(&e,&reply) && !strcmp(reply.iccs,"b9c7") &&
           !strcmp(reply.notation,"马二进三") && reply.red_win_permille==400);
    b.side=0;assert(xy_engine_dispose(&e));
    static const char *const bad[]={"wrong-token","wrong-crc","wrong-revision","illegal","malformed","exit","long-line","unsolicited"};
    for(unsigned i=0;i<sizeof(bad)/sizeof(bad[0]);i++){
        xy_engine_init(&e);assert(!setenv("XY_ENGINE_TEST",bad[i],1));
        assert(xy_engine_start(&e,argv[1],30+i,51,&b,128));
        assert(wait_state(&e)==XY_ENGINE_FAILED && e.pid<=0 && !xy_engine_take(&e,&reply));
    }
    xy_engine_init(&e);assert(!setenv("XY_ENGINE_TEST","hang",1));
    assert(xy_engine_start(&e,argv[1],50,60,&b,128));
    assert(xy_engine_cancel(&e));assert(wait_state(&e)==XY_ENGINE_STOPPED && e.pid<=0);
    assert(!xy_engine_take(&e,&reply));
    xy_engine_init(&e);e.timeout_ms=50;assert(!setenv("XY_ENGINE_TEST","hang",1));
    assert(xy_engine_start(&e,argv[1],51,61,&b,128));assert(wait_state(&e)==XY_ENGINE_FAILED);
    puts("XINYI_ENGINE_BRIDGE_IDENTITY_LEGALITY_CANCEL_AND_REUSE_PASS no_real_engine=1");return 0;
}
