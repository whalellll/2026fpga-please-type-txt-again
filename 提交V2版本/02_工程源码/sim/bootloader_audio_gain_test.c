#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "audio_sample.h"

static void check(const uint8_t sample[2],uint32_t volume,int expected){
 int actual=(int16_t)audio_scale_pcm16(sample,volume);
 if(actual!=expected){
  fprintf(stderr,"SPEAKER_GAIN_REPRO_FAIL volume=%u got=%d want=%d\n",
          volume,actual,expected);
  exit(1);
 }
}

int main(void){
 const uint8_t positive[]={0xff,0x7f};
 const uint8_t negative[]={0x00,0x80};
 const uint8_t middle[]={0x34,0x12};
 check(positive,25u,8191);
 check(negative,25u,-8192);
 check(middle,50u,2330);
 check(positive,100u,32767);
 check(negative,100u,-32768);
 check(positive,0u,0);
 check(positive,200u,32767);
 if(audio_mic24_to_pcm16(0x007fffffu)!=0x7fffu||
    audio_mic24_to_pcm16(0x00800000u)!=0x8000u||
    audio_mic24_to_pcm16(0x00ff0000u)!=0xff00u||
    (int16_t)audio_scale_sample16(audio_mic24_to_pcm16(0x00800000u),10u)!=-3276){
  fputs("MIC_LOOPBACK_CONVERSION_FAIL\n",stderr);
  return 1;
 }
 puts("BOOTLOADER_AUDIO_GAIN_PASS");
 return 0;
}
