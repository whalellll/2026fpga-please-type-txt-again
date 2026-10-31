#ifndef XQ_WHOLE_SPEECH_H
#define XQ_WHOLE_SPEECH_H
#include "xq_move_speech.h"
/* Format/allocation bound only, never a one-second latency certificate. */
#define XQS_WHOLE_MAX_SAMPLES 32000u
static inline int xqs_whole_tokens(const xqs_phrase *p)
{
    if(!p || p->count!=4 || p->tokens[2]<XQS_FORWARD || p->tokens[2]>XQS_HORIZONTAL ||
       p->tokens[3]<XQS_ONE || p->tokens[3]>XQS_NINE)return 0;
    unsigned first=p->tokens[0],second=p->tokens[1];
    int piece=first>=XQS_KING_RED && first<=XQS_PAWN_BLACK;
    int digit=first>=XQS_ONE && first<=XQS_NINE;
    int prefix=first>=XQS_FRONT && first<=XQS_MIDDLE;
    return (piece && second>=XQS_ONE && second<=XQS_NINE) ||
        ((digit || prefix) && second>=XQS_KING_RED && second<=XQS_PAWN_BLACK);
}
int xqs_linux_prepare_whole(const char *directory);
int xqs_linux_play_whole(const xqs_phrase *,const char *directory,unsigned volume,
    int (*cancel)(void *),void *context,uint32_t *underflows);
#endif
