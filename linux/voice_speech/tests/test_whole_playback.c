/* Exercise the actual shared RT/FIFO/cleanup path with explicit device mocks. */
#if !defined(XINYI_SPEECH_RT_CANDIDATE) || XINYI_SPEECH_RT_CANDIDATE != 1
#error This_candidate_fixture_requires_explicit_XINYI_SPEECH_RT_CANDIDATE_1
#endif
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
 expected_prime_samples=192;
 char directory[]="/tmp/xq-whole-playback-XXXXXX",whole[160],path[200];assert(mkdtemp(directory));
 assert(snprintf(whole,sizeof(whole),"%s/whole",directory)>0);assert(!mkdir(whole,0700));
 assert(snprintf(path,sizeof(path),"%s/22-02-27-05.pcm",whole)>0);
 xqs_phrase p={.tokens={XQS_CANNON,XQS_TWO,XQS_HORIZONTAL,XQS_FIVE},.count=4};
 pcm_clip clip;unsigned cases=0;uint32_t delta=99;int stop=0;
 unsigned opens_before=audio_opens,kernel_before=kernel_calls;
 assert(xqs_linux_prepare_whole(directory));
 assert(locked && whole_ordinary_locked && whole_samples && !realtime);
 assert(audio_opens==opens_before && (unsigned)kernel_calls==kernel_before);
 fail_prepare_lock=1;assert(!xqs_linux_prepare_whole(directory));
 assert(!locked && !whole_ordinary_locked && !whole_samples);cases++;
 assert(xqs_linux_prepare_whole(directory));
 fail_pcm_malloc=1;assert(!xqs_linux_prepare_whole(directory));
 assert(!locked && !whole_ordinary_locked && !whole_samples);cases++;
 assert(xqs_linux_prepare_whole(directory));assert(!xqs_linux_prepare_whole(NULL));
 assert(!locked && !whole_ordinary_locked && !whole_samples);cases++;
 assert(xqs_linux_prepare_whole(directory));
 unsigned locks_before=current_locks+future_locks,unlocks_before=unlocks;
 content(path,32);assert(prepare_whole(&p,directory,&clip,NULL,0));
 assert(clip.count==32 && clip.samples[0]==10000);free(clip.samples);cases++;
 rt_budget=950000;registers[0x600/4+1]=0x00020000u;
 int prior=streamed;assert(xqs_linux_play_whole(&p,directory,10,stop_now,&stop,&delta));
 assert(streamed==prior+1 && locked && !realtime && rt_budget==950000 && !delta);cases++;
 expected_first_sample=10000;
 prior=streamed;assert(xqs_linux_play_whole(&p,directory,100,stop_now,&stop,&delta));
 assert(streamed==prior+1 && locked && !realtime && rt_budget==950000 && !delta);cases++;
 assert(current_locks+future_locks==locks_before && unlocks==unlocks_before);
 expected_first_sample=1000;
 fail_stream=1;assert(!xqs_linux_play_whole(&p,directory,10,NULL,NULL,&delta));
 assert(locked && !realtime && rt_budget==950000);fail_stream=0;cases++;
 fail_enter=1;assert(!xqs_linux_play_whole(&p,directory,10,NULL,NULL,&delta));
 assert(locked && !realtime && rt_budget==950000);fail_enter=0;cases++;
 stop=1;prior=kernel_calls;assert(!xqs_linux_play_whole(&p,directory,10,stop_now,&stop,&delta));
 assert(kernel_calls==prior && !delta);stop=0;cases++;
 /* Explicit same-directory preparation rebuilds both the allocation and its
  * ordinary lock; no old-page lock is mistaken for a new allocation's lock. */
 unsigned previous_current=current_locks,previous_unlocks=unlocks;
 opens_before=audio_opens;kernel_before=(unsigned)kernel_calls;
 assert(xqs_linux_prepare_whole(directory));
 assert(current_locks==previous_current+1 && unlocks==previous_unlocks+1);
 assert(audio_opens==opens_before && (unsigned)kernel_calls==kernel_before && locked);cases++;
 /* Mixed legacy/kind8 paths retire prepared ordinary memory before retaining
  * their original per-phrase lock protection. Returning to whole is cold. */
 char legacy_path[200],move_directory[200],move_path[240];
 assert(snprintf(legacy_path,sizeof(legacy_path),"%s/welcome.pcm",directory)>0);content(legacy_path,32);
 xqs_phrase legacy={.tokens={XQS_WELCOME},.count=1};unsigned previous_future=future_locks;
 expected_prime_samples=64;
 assert(xqs_linux_play(&legacy,directory,10,NULL,NULL,&delta));
 assert(!locked && !whole_ordinary_locked && !whole_samples && future_locks==previous_future+1);
 expected_first_sample=10000;
 expected_prime_samples=192;
 assert(xqs_linux_play_whole(&p,directory,100,NULL,NULL,&delta));
 assert(locked && whole_ordinary_locked && whole_samples && !realtime && rt_budget==950000);cases++;
 assert(snprintf(move_directory,sizeof(move_directory),"%s/move",directory)>0);assert(!mkdir(move_directory,0700));
 for(unsigned i=0;i<4;i++){assert(snprintf(move_path,sizeof(move_path),"%s/%s.pcm",move_directory,xqs_names[p.tokens[i]])>0);content(move_path,32);}
 expected_stream_count=128;expected_first_sample=1000;previous_future=future_locks;
 expected_prime_samples=64;
 assert(xqs_linux_play_move(&p,directory,10,NULL,NULL,&delta));
 assert(!locked && !whole_ordinary_locked && !whole_samples && future_locks==previous_future+1);
 expected_stream_count=32;expected_first_sample=10000;
 expected_prime_samples=192;
 assert(xqs_linux_play_whole(&p,directory,100,NULL,NULL,&delta));
 assert(locked && whole_ordinary_locked && !realtime && rt_budget==950000);cases++;
 force_pcm_eof=1;prior=kernel_calls;assert(!xqs_linux_play_whole(&p,directory,100,NULL,NULL,&delta));
 assert(!locked && !whole_samples && !whole_ordinary_locked && kernel_calls==prior && !delta);
 assert(xqs_linux_play_whole(&p,directory,100,NULL,NULL,&delta));cases++;
 force_pcm_extra=1;prior=kernel_calls;assert(!xqs_linux_play_whole(&p,directory,100,NULL,NULL,&delta));
 assert(!locked && !whole_samples && !whole_ordinary_locked && kernel_calls==prior && !delta);
 assert(xqs_linux_play_whole(&p,directory,100,NULL,NULL,&delta));cases++;
 expected_first_sample=1000;
 /* Reject malformed bytes before touching any device, and recover in the
  * same process. A two-second format bound is not a one-second timing pass. */
 for(unsigned n=0;n<3;n++){
  content(path,n==0?0:n==1?XQS_WHOLE_MAX_SAMPLES+1:1);
  if(n==2){FILE *f=fopen(path,"ab");assert(f && fputc(0,f)!=EOF && !fclose(f));}
  assert(!prepare_whole(&p,directory,&clip,NULL,0));cases++;
 }
 content(path,XQS_WHOLE_MAX_SAMPLES);assert(prepare_whole(&p,directory,&clip,NULL,0));
 assert(clip.count==XQS_WHOLE_MAX_SAMPLES);free(clip.samples);cases++;
 prior=kernel_calls;assert(!xqs_linux_play_whole(&p,directory,10,NULL,NULL,&delta));
 assert(kernel_calls==prior && !delta);cases++;
 assert(!locked && !whole_ordinary_locked && !whole_samples);
 assert(!unlink(path));assert(!mkdir(path,0700));assert(!prepare_whole(&p,directory,&clip,NULL,0));assert(!rmdir(path));cases++;
 assert(!mkfifo(path,0600));assert(!prepare_whole(&p,directory,&clip,NULL,0));assert(!unlink(path));cases++;
 assert(!symlink("/dev/null",path));assert(!prepare_whole(&p,directory,&clip,NULL,0));assert(!unlink(path));cases++;
 content(path,32);
 for(unsigned i=0;i<4;i++){
  xqs_phrase bad=p;bad.tokens[i]=XQS_RED;assert(!prepare_whole(&bad,directory,&clip,NULL,0));cases++;
 }
 p.count=5;assert(!prepare_whole(&p,directory,&clip,NULL,0));p.count=4;cases++;
 assert(prepare_whole(&p,directory,&clip,NULL,0));free(clip.samples);cases++;
 assert(!xqs_linux_play_whole(&p,directory,0,NULL,NULL,&delta));
 assert(!xqs_linux_play_whole(&p,directory,101,NULL,NULL,&delta));cases+=2;
 assert(locked && !realtime && rt_budget==950000);
 assert(!unlink(path));assert(!rmdir(whole));
 assert(!unlink(legacy_path));
 for(unsigned i=0;i<4;i++){assert(snprintf(move_path,sizeof(move_path),"%s/%s.pcm",move_directory,xqs_names[p.tokens[i]])>0);assert(!unlink(move_path));}
 assert(!rmdir(move_directory));xqs_linux_release();assert(!rmdir(directory));
 assert(!locked && !whole_ordinary_locked && !whole_samples);
 printf("R17_WHOLE_PCM_RT_CLEANUP_FORMAT_CANCEL_RECOVERY_PASS cases=%u no_real_device=1 NOT_BOARD\n",cases);
 return 0;
}
