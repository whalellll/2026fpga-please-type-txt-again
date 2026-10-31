#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "xq_speech.h"
typedef struct { unsigned reads,writes,full,stalled,startup_idle; uint64_t us; uint32_t underflows; } fake;
static uint32_t status(void *p) { fake *f=p; f->full=f->stalled || ++f->reads%3==0; return f->full?256:0; }
static uint32_t underflows(void *p) { return ((fake *)p)->underflows; }
static void sample(void *p,uint32_t value)
{ fake *f=p; (void)value; assert(!f->full); ++f->writes; if (f->writes==17) f->underflows+=2; }
static uint64_t now(void *p)
{ fake *f=p; if(!f->writes){f->underflows+=f->startup_idle;f->startup_idle=0;} return f->us+=10000; }
static int cancel(void *p) { (void)p; return 0; }
int main(void)
{
 const char *opening="rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1";
 const uint8_t red[]={XQS_RED,XQS_CANNON,XQS_TWO,XQS_HORIZONTAL,XQS_FIVE};
 const uint8_t black[]={XQS_BLACK,XQS_KNIGHT,XQS_TWO,XQS_FORWARD,XQS_THREE};
 xq_search_board_t b;
 xqs_phrase phrase;
 fake f={0};
 int16_t pcm[100]={0}; uint32_t delta;
 xqs_io io={&f,status,underflows,sample,now,cancel};
 assert(xqv_parse_fen(opening,&b));
 assert(xqs_move_phrase(&b,"h2e2",&phrase));
 assert(phrase.count==sizeof(red) && !memcmp(phrase.tokens,red,sizeof(red)));
 b.side=1;
 assert(xqs_move_phrase(&b,"b9c7",&phrase));
 assert(phrase.count==sizeof(black) && !memcmp(phrase.tokens,black,sizeof(black)));
 assert(!xqs_move_phrase(&b,"b9b8",&phrase));
 b.side=0; b.squares[0]=b.squares[8]=0;
 b.squares[3*9+4]=PIECE_R; b.squares[5*9+4]=PIECE_R;
 assert(xqs_move_phrase(&b,"e5d5",&phrase));
 assert(phrase.tokens[1]==XQS_FRONT && phrase.tokens[2]==XQS_ROOK && phrase.tokens[4]==XQS_SIX);
 assert(xqs_numbers_phrase(533,6701,&phrase));
 assert(phrase.tokens[3]==XQS_FIVE && phrase.tokens[4]==XQS_TEN && phrase.tokens[5]==XQS_THREE);
 assert(!xqs_numbers_phrase(0xffffffffu,1000,&phrase));
 assert(!xqs_numbers_phrase(500,0xffffffffu,&phrase));
 assert(xqs_stream(&io,pcm,100,&delta) && f.writes==100 && delta==2);
 memset(&f,0,sizeof(f));f.startup_idle=5;
 assert(xqs_stream(&io,pcm,100,&delta) && f.writes==100 && delta==2);
 f.stalled=1; f.writes=0;
 assert(!xqs_stream(&io,pcm,100,&delta) && f.writes==0);
 puts("XQ_SPEECH_TEST_PASS Chinese-files legal-moves exact-WDL numbers not-full bounded-stall underflows");
 return 0;
}
