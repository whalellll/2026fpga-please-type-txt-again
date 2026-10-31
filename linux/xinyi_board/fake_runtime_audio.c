/* Linked only to the real speech_worker in runtime integration tests. */
#define _POSIX_C_SOURCE 200809L
#include "speech_task.h"
#include <assert.h>
#if XINYI_BATTLE_R17
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#endif
#include <string.h>
#include <time.h>
static char prepared[512];
int xqs_linux_prepare(const char *directory)
{
#if XINYI_BATTLE_R17
    if(getenv("XY_AUDIO_PREPARE_CRASH"))_exit(9);
    const char *delay=getenv("XY_AUDIO_PREPARE_DELAY_MS");
    if(delay){unsigned ms=(unsigned)strtoul(delay,NULL,10);assert(ms<=2000);
        const struct timespec t={ms/1000,(long)(ms%1000)*1000000};nanosleep(&t,NULL);}
    const char *path=getenv("XY_AUDIO_PREPARED_MARKER");
    if(path){FILE *f=fopen(path,"a");assert(f);assert(fprintf(f,"%ld\n",(long)getpid())>0 && !fclose(f));}
#endif
    assert(strlen(directory)<sizeof(prepared));strcpy(prepared,directory);return 1;
}
void xqs_linux_release(void){assert(prepared[0]);prepared[0]=0;}
int xqs_linux_play(const xqs_phrase *p,const char *directory,unsigned volume,
                   int (*cancel)(void *),void *context,uint32_t *underflows)
{
    assert(p->count==5 && volume==100 && !strcmp(directory,prepared));*underflows=0;
#if XINYI_BATTLE_R17
    const char *path=getenv("XY_AUDIO_PLAYED_MARKER");
    if(path){FILE *f=fopen(path,"a");assert(f);assert(fprintf(f,"%ld\n",(long)getpid())>0 && !fclose(f));}
#endif
    for(unsigned i=0;i<160;i++){
        const struct timespec t={0,2000000};nanosleep(&t,NULL);
        if(cancel(context))return 0;
    }
    return 1;
}
#if XINYI_COACH_MOVE_AUDIO
int xqs_linux_play_move(const xqs_phrase *p,const char *directory,unsigned volume,
                   int (*cancel)(void *),void *context,uint32_t *underflows)
{
    assert(p->count==4);
    for(unsigned i=0;i<4;i++)assert(p->tokens[i]!=XQS_RED && p->tokens[i]!=XQS_BLACK);
    xqs_phrase compatible=*p;compatible.count=5;
    return xqs_linux_play(&compatible,directory,volume,cancel,context,underflows);
}
#endif
#if XINYI_BATTLE_R17
int xqs_linux_prepare_whole(const char *directory)
{return xqs_linux_prepare(directory);}
int xqs_linux_play_whole(const xqs_phrase *p,const char *directory,unsigned volume,
                   int (*cancel)(void *),void *context,uint32_t *underflows)
{return xqs_linux_play_move(p,directory,volume,cancel,context,underflows);}
#endif
