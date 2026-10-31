#ifndef XQV_FRONTEND_H
#define XQV_FRONTEND_H
#include <stddef.h>
#include <stdint.h>
int xqvoice_frontend(const int16_t *pcm,size_t samples,int8_t *output,size_t capacity,unsigned *frames);
int xqvoice_wav_features(const uint8_t *wav,size_t bytes,uint8_t **input,size_t *input_bytes);
int xqvoice_wav_pcm(const uint8_t *wav,size_t bytes,int16_t **pcm,size_t *samples);
#endif
