#include "audio_sample.h"

uint16_t audio_scale_pcm16(const uint8_t sample[2],uint32_t volume){
 uint32_t raw=(uint32_t)sample[0]|((uint32_t)sample[1]<<8);
 return audio_scale_sample16((uint16_t)raw,volume);
}

uint16_t audio_scale_sample16(uint16_t sample,uint32_t volume){
 uint32_t raw=sample;
 int32_t signed_sample=(raw&0x8000u)?(int32_t)raw-65536:(int32_t)raw;
 if(volume>100u)volume=100u;
 return (uint16_t)(signed_sample*(int32_t)volume/100);
}

/* Preserve the high 16 bits of the microphone's signed 24-bit I2S word. */
uint16_t audio_mic24_to_pcm16(uint32_t sample){
 return (uint16_t)((sample>>8)&0xffffu);
}
