/* Exercise the actual shared RT/FIFO/cleanup path with explicit device mocks. */
#define _GNU_SOURCE
#include "../xq_whole_speech.h"
#define main legacy_audio_checks
#include "test_speech_linux.c"
#undef main
#include <sys/stat.h>
static int stop_now(void *p){return *(int *)p;}
static void content(const char *path,unsigned count)
{
 FILE *f=fopen(path,"wb");assert(f);
 for(unsigned i=0;i<count;i++){assert(fputc(0x10,f)!=EOF);assert(fputc(0x27,f)!=EOF);}
 assert(!fclose(f));
}
int main(void)
{
 assert(!legacy_audio_checks());
 char directory[]="/tmp/xq-whole-playback-XXXXXX",whole[160],path[200];assert(mkdtemp(directory));
 assert(snprintf(whole,sizeof(whole),"%s/whole",directory)>0);assert(!mkdir(whole,0700));
 assert(snprintf(path,sizeof(path),"%s/22-02-27-05.pcm",whole)>0);
 xqs_phrase p={.tokens={XQS_CANNON,XQS_TWO,XQS_HORIZONTAL,XQS_FIVE},.count=4};
 pcm_clip clip;unsigned cases=0;uint32_t delta=99;int stop=0;
 assert(xqs_linux_prepare_whole(directory));
 content(path,32);assert(prepare_whole(&p,directory,&clip));
 assert(clip.count==32 && clip.samples[0]==10000);free(clip.samples);cases++;
 rt_budget=950000;registers[0x600/4+1]=0x00020000u;
 int prior=streamed;assert(xqs_linux_play_whole(&p,directory,10,stop_now,&stop,&delta));
 assert(streamed==prior+1 && !locked && !realtime && rt_budget==950000 && !delta);cases++;
 expected_first_sample=10000;
 prior=streamed;assert(xqs_linux_play_whole(&p,directory,100,stop_now,&stop,&delta));
 assert(streamed==prior+1 && !locked && !realtime && rt_budget==950000 && !delta);cases++;
 expected_first_sample=1000;
 fail_stream=1;assert(!xqs_linux_play_whole(&p,directory,10,NULL,NULL,&delta));
 assert(!locked && !realtime && rt_budget==950000);fail_stream=0;cases++;
 fail_enter=1;assert(!xqs_linux_play_whole(&p,directory,10,NULL,NULL,&delta));
 assert(!locked && !realtime && rt_budget==950000);fail_enter=0;cases++;
 stop=1;prior=kernel_calls;assert(!xqs_linux_play_whole(&p,directory,10,stop_now,&stop,&delta));
 assert(kernel_calls==prior && !delta);stop=0;cases++;
 /* Reject malformed bytes before touching any device, and recover in the
  * same process. A two-second format bound is not a one-second timing pass. */
 for(unsigned n=0;n<3;n++){
  content(path,n==0?0:n==1?XQS_WHOLE_MAX_SAMPLES+1:1);
  if(n==2){FILE *f=fopen(path,"ab");assert(f && fputc(0,f)!=EOF && !fclose(f));}
  assert(!prepare_whole(&p,directory,&clip));cases++;
 }
 content(path,XQS_WHOLE_MAX_SAMPLES);assert(prepare_whole(&p,directory,&clip));
 assert(clip.count==XQS_WHOLE_MAX_SAMPLES);free(clip.samples);cases++;
 prior=kernel_calls;assert(!xqs_linux_play_whole(&p,directory,10,NULL,NULL,&delta));
 assert(kernel_calls==prior && !delta);cases++;
 assert(!unlink(path));assert(!mkdir(path,0700));assert(!prepare_whole(&p,directory,&clip));assert(!rmdir(path));cases++;
 assert(!mkfifo(path,0600));assert(!prepare_whole(&p,directory,&clip));assert(!unlink(path));cases++;
 assert(!symlink("/dev/null",path));assert(!prepare_whole(&p,directory,&clip));assert(!unlink(path));cases++;
 content(path,32);
 for(unsigned i=0;i<4;i++){
  xqs_phrase bad=p;bad.tokens[i]=XQS_RED;assert(!prepare_whole(&bad,directory,&clip));cases++;
 }
 p.count=5;assert(!prepare_whole(&p,directory,&clip));p.count=4;cases++;
 assert(prepare_whole(&p,directory,&clip));free(clip.samples);cases++;
 assert(!xqs_linux_play_whole(&p,directory,0,NULL,NULL,&delta));
 assert(!xqs_linux_play_whole(&p,directory,101,NULL,NULL,&delta));cases+=2;
 assert(!locked && !realtime && rt_budget==950000);
 assert(!unlink(path));assert(!rmdir(whole));xqs_linux_release();assert(!rmdir(directory));
 printf("R17_WHOLE_PCM_RT_CLEANUP_FORMAT_CANCEL_RECOVERY_PASS cases=%u no_real_device=1 NOT_BOARD\n",cases);
 return 0;
}
