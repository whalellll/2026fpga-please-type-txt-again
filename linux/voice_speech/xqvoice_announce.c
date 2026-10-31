#define _POSIX_C_SOURCE 200809L
#include "xqvoice_announce.h"
#include <stdio.h>
#include <time.h>
static uint64_t speech_us(void)
{
    struct timespec t;
    if(clock_gettime(CLOCK_MONOTONIC,&t))return 0;
    return (uint64_t)t.tv_sec*1000000u+(uint64_t)t.tv_nsec/1000u;
}
static void say(xqvoice_announcer *s,const xqs_phrase *phrase,int move,int busy)
{
    uint32_t underflows=0;int okay;
    uint64_t started,finished;
    if(!s || !s->mode || busy || (!move && s->mode<2) ||
       (s->cancel && s->cancel(s->context)))return;
    started=speech_us();
    okay=xqs_linux_play(phrase,s->directory,s->volume,s->cancel,s->context,&underflows);
    finished=speech_us();
    printf("XQVOICE_SPEECH mode=%u okay=%d underflows=%u volume=%u kind=%s elapsed_us=%llu tokens=%u\n",
           s->mode,okay,underflows,s->volume,move?"move":phrase->count==1?"prompt":"stats",
           (unsigned long long)(finished-started),phrase->count);
    if(!okay || underflows>2u){
        s->mode=s->mode==2?1:0;
        printf("XQVOICE_SPEECH_DEGRADED next=%u\n",s->mode);
    }
}
void xqvoice_announce_init(xqvoice_announcer *s,const char *dir,unsigned mode,unsigned volume,
                         int (*cancel)(void *),void *context)
{
    s->directory=dir;s->mode=dir && *dir && mode<=2?mode:0;
    s->volume=volume>=1 && volume<=100?volume:100;s->cancel=cancel;s->context=context;
}
void xqvoice_announce_prompt(xqvoice_announcer *s,xqs_token token,int busy)
{
    xqs_phrase p={{0},1};
    if(token!=XQS_WELCOME && token!=XQS_NEWGAME)return;
    p.tokens[0]=(uint8_t)token;say(s,&p,0,busy);
}
void xqvoice_announce_move(xqvoice_announcer *s,const xq_search_board_t *before,const char *move,int busy)
{
    xqs_phrase p;
    if(busy || !s || !s->mode)return;
    if(xqs_move_phrase(before,move,&p))say(s,&p,1,0);
    else puts("XQVOICE_SPEECH_SKIP ambiguous-or-illegal-notation");
}
void xqvoice_announce_numbers(xqvoice_announcer *s,uint32_t rate,uint32_t ms,int busy)
{
    xqs_phrase p;
    if(!busy && s && s->mode==2 && xqs_numbers_phrase(rate,ms,&p))say(s,&p,0,0);
}
