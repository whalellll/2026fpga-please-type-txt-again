#include "xq_speech.h"
#include "xiangqi_pikafish_link.h"
#include <string.h>
const char *const xqs_names[XQS_COUNT]={
 "zero","one","two","three","four","five","six","seven","eight","nine",
 "ten","hundred","thousand","point","red","black","king_red","king_black",
 "advisor","elephant","knight","rook","cannon","pawn_red","pawn_black",
 "forward","backward","horizontal","front","rear","middle",
 "welcome","newgame","winrate","percent","think","seconds"
};
static int add(xqs_phrase *p,unsigned t)
{
 if (p->count>=sizeof(p->tokens) || t>=XQS_COUNT) return 0;
 p->tokens[p->count++]=(uint8_t)t; return 1;
}
static int number(xqs_phrase *p,unsigned value)
{
 unsigned scale=1000, previous=0, zero=0;
 if (value>9999) return 0;
 if (!value) return add(p,XQS_ZERO);
 while (scale>=10) {
  unsigned digit=value/scale;
  if (digit) {
   if (zero && !add(p,XQS_ZERO)) return 0;
   if (!(scale==10 && digit==1 && !previous) && !add(p,digit)) return 0;
   if (!add(p,scale==1000?XQS_THOUSAND:scale==100?XQS_HUNDRED:XQS_TEN)) return 0;
   previous=1; zero=0;
  } else if (previous) zero=1;
  value%=scale; scale/=10;
 }
 if (value) { if (zero && !add(p,XQS_ZERO)) return 0; return add(p,value); }
 return 1;
}
int xqs_move_phrase(const xq_search_board_t *b,const char *iccs,xqs_phrase *p)
{
 static const unsigned pieces[8]={0,XQS_KING_RED,XQS_ADVISOR,XQS_ELEPHANT,
                                  XQS_KNIGHT,XQS_ROOK,XQS_CANNON,XQS_PAWN_RED};
 xq_search_board_t checked;
 xq_search_move_t m;
 unsigned type,side,from_file,to_file,from_rank,to_rank,source,target,count=0,front=0,r;
 int advance;
 if (!b || !iccs || strlen(iccs)!=4 || !p || !xq_pikafish_parse_move(iccs,&m)) return 0;
 checked=*b;
 if (!xq_pikafish_apply_move(&checked,iccs,NULL)) return 0;
 p->count=0;
 type=b->squares[m.from]&7u; side=(b->squares[m.from]&SIDE_BLACK)!=0;
 from_file=m.from%9; to_file=m.to%9; from_rank=m.from/9; to_rank=m.to/9;
 source=side?from_file+1:9-from_file;
 for (r=0; r<10; ++r) if (b->squares[r*9+from_file]==b->squares[m.from]) {
  ++count; if (side?r<from_rank:r>from_rank) ++front;
 }
 if (!add(p,side?XQS_BLACK:XQS_RED)) return 0;
 if (count>1) {
  /* Multi-file stacked pawns need a richer notation dialect. Reject rather
   * than speak an ambiguous move. ICCS remains visible on the GUI. */
  if (type==PIECE_P) {
   unsigned file;
   for (file=0; file<9; ++file) if (file!=from_file) {
    unsigned n=0;
    for (r=0; r<10; ++r) if (b->squares[r*9+file]==b->squares[m.from]) ++n;
    if (n>1) return 0;
   }
  }
  if (!add(p,count<=3?(front==0?XQS_FRONT:front==count-1?XQS_REAR:XQS_MIDDLE):front+1)) return 0;
 }
 if (!add(p,side && type==PIECE_K?XQS_KING_BLACK:
            side && type==PIECE_P?XQS_PAWN_BLACK:pieces[type])) return 0;
 if (count==1 && !add(p,source)) return 0;
 advance=side?(int)from_rank-(int)to_rank:(int)to_rank-(int)from_rank;
 if (!add(p,!advance?XQS_HORIZONTAL:advance>0?XQS_FORWARD:XQS_BACKWARD)) return 0;
 target=!advance || type==PIECE_N || type==PIECE_B || type==PIECE_A
       ? (side?to_file+1:9-to_file) : (unsigned)(advance<0?-advance:advance);
 return add(p,target);
}
int xqs_numbers_phrase(uint32_t rate,uint32_t ms,xqs_phrase *p)
{
 if (!p || rate>1000 || ms>9999999) return 0;
 p->count=0;
 return add(p,XQS_RED) && add(p,XQS_WINRATE) && add(p,XQS_PERCENT) &&
        number(p,rate/10) && add(p,XQS_POINT) && add(p,rate%10) &&
        add(p,XQS_THINK) && number(p,ms/1000) && add(p,XQS_POINT) &&
        add(p,(ms/100)%10) && add(p,(ms/10)%10) && add(p,ms%10) && add(p,XQS_SECONDS);
}
int xqs_stream(xqs_io *io,const int16_t *samples,unsigned n,uint32_t *delta)
{
 uint32_t before;
 unsigned i;
 uint64_t last;
 if (!io || !io->status || !io->underflows || !io->write || !io->now_us ||
     !samples || !n || n>480000 || !delta) return 0;
 /* Prepare the clock before the baseline: the FIFO is intentionally empty
  * during that syscall, before any audio has been submitted. */
 last=io->now_us(io->context); before=io->underflows(io->context);
 for (i=0; i<n; ++i) {
  unsigned spins=0;
  while (io->status(io->context)&256u) {
   if (++spins%64==0 &&
       (spins>=1000000 || io->now_us(io->context)-last>=100000 ||
        (io->cancel && io->cancel(io->context)))) {
    *delta=io->underflows(io->context)-before; return 0;
   }
  }
  io->write(io->context,(uint16_t)samples[i]);
  if (i%16==15) last=io->now_us(io->context);
  if (i%256==255 && io->cancel && io->cancel(io->context)) {
   *delta=io->underflows(io->context)-before; return 0;
  }
 }
 *delta=io->underflows(io->context)-before;
 return 1;
}
