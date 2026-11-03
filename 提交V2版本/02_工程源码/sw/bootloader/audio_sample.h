#ifndef BOOTLOADER_AUDIO_SAMPLE_H
#define BOOTLOADER_AUDIO_SAMPLE_H

#include <stdint.h>

uint16_t audio_scale_pcm16(const uint8_t sample[2],uint32_t volume);
uint16_t audio_scale_sample16(uint16_t sample,uint32_t volume);
uint16_t audio_mic24_to_pcm16(uint32_t sample);

#endif
