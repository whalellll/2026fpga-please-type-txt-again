#ifndef XQVOICE_ANNOUNCE_H
#define XQVOICE_ANNOUNCE_H
#include "xq_speech.h"
typedef struct {
    const char *directory;
    unsigned mode,volume;
    int (*cancel)(void *);
    void *context;
} xqvoice_announcer;
/* mode: 0 off, 1 committed moves only, 2 moves plus prompts/statistics. */
void xqvoice_announce_init(xqvoice_announcer *,const char *,unsigned,unsigned,
                         int (*)(void *),void *);
void xqvoice_announce_prompt(xqvoice_announcer *,xqs_token,int capture_busy);
void xqvoice_announce_move(xqvoice_announcer *,const xq_search_board_t *,const char *,int capture_busy);
void xqvoice_announce_numbers(xqvoice_announcer *,uint32_t,uint32_t,int capture_busy);
#endif
