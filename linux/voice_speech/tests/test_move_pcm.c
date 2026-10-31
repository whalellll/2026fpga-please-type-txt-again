#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <string.h>
static unsigned device_attempts;
static int deny_device(const char *path,int flags,...)
{
    (void)flags;assert(!strcmp(path,"/run/xqvoice-audio.lock"));
    device_attempts++;errno=EACCES;return -1;
}
#define open deny_device
#include "xq_speech_linux.c"
#undef open
static int stopped(void *c){return *(int *)c;}
int main(int argc,char **argv)
{
    assert(argc==3);char path[512];xqs_phrase p={.count=4};unsigned cases=0,max_samples=0;
    for(unsigned t=0;t<XQS_COUNT;t++)if(xqs_move_token(t)){
        for(unsigned j=0;j<4;j++)p.tokens[j]=(uint8_t)t;
        assert(prepare_move(&p,argv[1],path));
        unsigned n=pcm_cache[t].count;assert(n && n<=3840);
        if(n>max_samples)max_samples=n;
        cases++;
    }
    for(unsigned i=XQS_KING_RED;i<=XQS_PAWN_BLACK;i++)
      for(unsigned j=1;j<=9;j++)for(unsigned k=XQS_FORWARD;k<=XQS_HORIZONTAL;k++)
        for(unsigned l=1;l<=9;l++){
            p=(xqs_phrase){.tokens={i,j,k,l},.count=4};assert(prepare_move(&p,argv[1],path));cases++;
        }
    p=(xqs_phrase){.tokens={XQS_CANNON,XQS_TWO,XQS_HORIZONTAL,XQS_FIVE},.count=4};
    uint32_t delta=99;int stop=1;
    assert(!xqs_linux_play_move(&p,argv[1],100,stopped,&stop,&delta) && !device_attempts && !delta);
    stop=0;assert(!xqs_linux_play_move(&p,argv[1],100,stopped,&stop,&delta) && device_attempts==1);
    unsigned attempts=device_attempts;
    p.tokens[0]=XQS_BLACK;assert(!xqs_linux_play_move(&p,argv[1],100,NULL,NULL,&delta));
    p.tokens[0]=XQS_RED;assert(!xqs_linux_play_move(&p,argv[1],100,NULL,NULL,&delta));
    p.tokens[0]=XQS_CANNON;p.count=5;assert(!xqs_linux_play_move(&p,argv[1],100,NULL,NULL,&delta));
    p.count=4;assert(!xqs_linux_play_move(&p,argv[2],100,NULL,NULL,&delta));
    assert(device_attempts==attempts); /* Over-budget input fails before audio ownership. */
    assert(prepare_move(&p,argv[1],path)); /* Same-process bad-bank recovery. */
    assert(!prepare_move(&p,"/nonexistent/move-pcm-test",path));
    assert(prepare_move(&p,argv[1],path));xqs_linux_release();
    assert(max_samples*4+64<=16000);
    printf("MOVE_PCM_PASS cases=%u max_token_samples=%u max_four_plus_prime_us=%llu side-prefix/count/oversize/missing/cancel/recovery,no_device NOT_BOARD\n",
        cases,max_samples,(unsigned long long)(max_samples*4+64)*1000000u/16000u);return 0;
}
