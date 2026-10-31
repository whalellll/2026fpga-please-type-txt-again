#ifndef XQ_MOVE_SPEECH_H
#define XQ_MOVE_SPEECH_H
#include "xq_speech.h"
/* Four move syllables, <=240 ms each; the original 4 ms FIFO prime remains.
 * This bounds PCM duration, not process startup, device latency or audibility. */
static inline int xqs_move_token(unsigned t)
{return (t>=XQS_ONE && t<=XQS_NINE) || (t>=XQS_KING_RED && t<=XQS_MIDDLE);}
int xqs_linux_play_move(const xqs_phrase *,const char *directory,unsigned volume,
    int (*cancel)(void *),void *context,uint32_t *underflows);
#endif
