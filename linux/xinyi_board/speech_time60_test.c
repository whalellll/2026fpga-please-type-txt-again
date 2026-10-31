/* Numeric-only actual conversion seam. Explicit mocks satisfy unused playback
 * dependencies; no playback/device/syscall preparation is invoked here. */
#if !defined(XINYI_SPEECH_RT_CANDIDATE) || XINYI_SPEECH_RT_CANDIDATE != 1
#error This_candidate_numeric_seam_requires_explicit_XINYI_SPEECH_RT_CANDIDATE_1
#endif
#define main unused_legacy_audio_checks
#include "../voice_speech/tests/test_speech_linux.c"
#undef main
__attribute__((noinline)) uint64_t seam60(uint32_t ticks,uint32_t start)
{return playback_elapsed_us((uint32_t)(ticks-start),60000000u);}
__attribute__((noinline)) uint64_t seam_dynamic(uint32_t ticks,uint32_t start,uint32_t hz)
{return playback_elapsed_us((uint32_t)(ticks-start),hz);}
static uint32_t random_state=0x26010360u;
static uint32_t random32(void)
{uint32_t x=random_state;x^=x<<13;x^=x>>17;x^=x<<5;random_state=x;return x;}
int main(void)
{
 static const uint32_t edge[]={0,1,59,60,61,UINT32_MAX-1,UINT32_MAX,0x80000000u};
 static const uint32_t hz[]={1000000u,49500000u,60000000u,75000000u,100000000u};
 unsigned checked=0,wrong_clock=0,round_up=0;
 for(unsigned i=0;i<sizeof(edge)/sizeof(edge[0]);i++)
  for(unsigned j=0;j<sizeof(hz)/sizeof(hz[0]);j++){
   uint64_t expected=(uint64_t)edge[i]*1000000u/hz[j];
   assert(playback_elapsed_us(edge[i],hz[j])==expected);++checked;
  }
 for(unsigned i=0;i<1000000u;i++){
  uint32_t ticks=random32(),start=random32(),elapsed=(uint32_t)(ticks-start);
  uint32_t clock=i&1u?60000000u:1000000u+random32()%99000001u;
  uint64_t expected=(uint64_t)elapsed*1000000u/clock;
  assert(seam_dynamic(ticks,start,clock)==expected);
  assert(seam60(ticks,start)==(uint64_t)elapsed*1000000u/60000000u);
  wrong_clock+=elapsed/59u!=seam60(ticks,start);
  round_up+=((uint64_t)elapsed+59u)/60u!=seam60(ticks,start);
  ++checked;
 }
 assert(seam60(16u,0xfffffff0u)==0);
 assert(seam60(59u,UINT32_MAX)==1);
 assert(wrong_clock && round_up);
 printf("R18_ACTUAL_TIME60_EXACT_PASS cases=%u wrong_clock_differences=%u roundup_differences=%u wrap=PASS NUMERIC_ONLY_NOT_BOARD\n",checked,wrong_clock,round_up);
 return 0;
}
