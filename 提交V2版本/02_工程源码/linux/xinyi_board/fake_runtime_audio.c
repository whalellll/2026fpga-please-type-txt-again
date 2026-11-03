/* Linked only to the real speech_worker in runtime integration tests. */
#define _POSIX_C_SOURCE 200809L
#include "speech_task.h"
#include <assert.h>
#include <string.h>
#include <time.h>
static char prepared[512];
int xqs_linux_prepare(const char *directory)
{assert(strlen(directory)<sizeof(prepared));strcpy(prepared,directory);return 1;}
void xqs_linux_release(void){assert(prepared[0]);prepared[0]=0;}
int xqs_linux_play(const xqs_phrase *p,const char *directory,unsigned volume,
                   int (*cancel)(void *),void *context,uint32_t *underflows)
{
    assert(p->count==5 && volume==100 && !strcmp(directory,prepared));*underflows=0;
    for(unsigned i=0;i<160;i++){
        const struct timespec t={0,2000000};nanosleep(&t,NULL);
        if(cancel(context))return 0;
    }
    return 1;
}
