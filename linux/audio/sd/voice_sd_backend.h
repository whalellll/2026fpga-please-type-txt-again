#ifndef VOICE_SD_BACKEND_H
#define VOICE_SD_BACKEND_H
#include <stdint.h>
typedef struct { uint32_t sectors, cid[4]; } voice_sd_media_t;
int voice_sd_open(const char *image, voice_sd_media_t *media, int writing);
void voice_sd_close(void);
int voice_sd_read(void *user, uint32_t lba, uint32_t count, uint8_t *buffer);
int voice_sd_write(void *user, uint32_t lba, const uint8_t *buffer);
int voice_sd_write_many(void *user, uint32_t lba, uint32_t count, const uint8_t *buffer);
#endif
