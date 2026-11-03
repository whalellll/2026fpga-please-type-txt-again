#include "xqvoice_announce.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned calls,fail,underflow,stopped;
static xqs_phrase last;
int xqs_linux_play(const xqs_phrase *p,const char *dir,unsigned volume,
                  int (*cancel)(void *),void *context,uint32_t *delta)
{
    (void)cancel;(void)context;assert(!strcmp(dir,"/pcm") && volume==100);
    calls++;last=*p;*delta=underflow;return !fail;
}
static int cancelled(void *p){(void)p;return stopped;}
int main(void)
{
    static const uint8_t back[9]={5,4,3,2,1,2,3,4,5};
    xq_search_board_t board;xqvoice_announcer s;unsigned i;
    memset(&board,0,sizeof(board));
    for(i=0;i<9;i++){board.squares[i]=back[i];board.squares[81+i]=back[i]|SIDE_BLACK;}
    board.squares[19]=board.squares[25]=PIECE_C;board.squares[64]=board.squares[70]=PIECE_C|SIDE_BLACK;
    for(i=0;i<9;i+=2){board.squares[27+i]=PIECE_P;board.squares[54+i]=PIECE_P|SIDE_BLACK;}
    xqvoice_announce_init(&s,"/pcm",2,100,cancelled,NULL);
    xqvoice_announce_prompt(&s,XQS_WELCOME,1);assert(calls==0);
    xqvoice_announce_move(&s,&board,"h2e2",1);assert(calls==0);
    xqvoice_announce_prompt(&s,XQS_WELCOME,0);assert(calls==1 && last.tokens[0]==XQS_WELCOME);
    xqvoice_announce_move(&s,&board,"h2e2",0);assert(calls==2 && last.tokens[1]==XQS_CANNON);
    xqvoice_announce_move(&s,&board,"h2i3",0);assert(calls==2);
    xqvoice_announce_numbers(&s,533,6701,0);assert(calls==3);
    underflow=3;xqvoice_announce_prompt(&s,XQS_NEWGAME,0);assert(calls==4 && s.mode==1);
    xqvoice_announce_numbers(&s,533,6701,0);assert(calls==4);
    xqvoice_announce_prompt(&s,XQS_NEWGAME,0);assert(calls==4);
    fail=1;xqvoice_announce_move(&s,&board,"h2e2",0);assert(calls==5 && !s.mode);
    xqvoice_announce_move(&s,&board,"h2e2",0);assert(calls==5);
    xqvoice_announce_init(&s,"/pcm",2,100,cancelled,NULL);stopped=1;
    xqvoice_announce_move(&s,&board,"h2e2",0);assert(calls==5);
    puts("ANNOUNCER_PASS capture-busy legal-notation stats full-to-moves-to-off cancellation");
    return 0;
}
