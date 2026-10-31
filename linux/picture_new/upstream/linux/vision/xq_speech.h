#ifndef XQ_SPEECH_H
#define XQ_SPEECH_H
#include "xq_vision.h"
typedef enum {
 XQS_ZERO,XQS_ONE,XQS_TWO,XQS_THREE,XQS_FOUR,XQS_FIVE,XQS_SIX,XQS_SEVEN,XQS_EIGHT,XQS_NINE,
 XQS_TEN,XQS_HUNDRED,XQS_THOUSAND,XQS_POINT,XQS_RED,XQS_BLACK,XQS_KING_RED,XQS_KING_BLACK,
 XQS_ADVISOR,XQS_ELEPHANT,XQS_KNIGHT,XQS_ROOK,XQS_CANNON,XQS_PAWN_RED,XQS_PAWN_BLACK,
 XQS_FORWARD,XQS_BACKWARD,XQS_HORIZONTAL,XQS_FRONT,XQS_REAR,XQS_MIDDLE,
 XQS_WELCOME,XQS_NEWGAME,XQS_WINRATE,XQS_PERCENT,XQS_THINK,XQS_SECONDS,XQS_COUNT
} xqs_token;
typedef struct { uint8_t tokens[96]; unsigned count; } xqs_phrase;
extern const char *const xqs_names[XQS_COUNT];
int xqs_move_phrase(const xq_search_board_t *,const char *iccs,xqs_phrase *);
int xqs_numbers_phrase(uint32_t win_permille,uint32_t milliseconds,xqs_phrase *);
typedef struct {
 void *context;
 uint32_t (*status)(void *);
 uint32_t (*underflows)(void *);
 void (*write)(void *,uint32_t sample);
 uint64_t (*now_us)(void *);
 int (*cancel)(void *);
} xqs_io;
/* Poll before every write; no write at FIFO-full. Bounded stalled FIFO.
 * delta counts interior underflows, excluding intentional idle afterward. */
int xqs_stream(xqs_io *,const int16_t *,unsigned samples,uint32_t *delta);
/* Linux playback: load/concatenate PCM before SCHED_FIFO+mlockall, prefill,
 * stream through 32-bit AUD1 accesses, then restore scheduling/locks. */
int xqs_linux_play(const xqs_phrase *,const char *directory,unsigned volume,
                    int (*cancel)(void *),void *context,uint32_t *underflows);
#endif
