#ifndef SOC_AUDIO_H
#define SOC_AUDIO_H

#include <stdint.h>

#define AUDIO_BASE        0x1fe00600u
#define AUDIO_ID          0x00u
#define AUDIO_VERSION     0x04u
#define AUDIO_CONTROL     0x08u
#define AUDIO_PLAYBACK    0x0cu
#define AUDIO_STATUS      0x10u
#define AUDIO_MIC_SAMPLE  0x14u
#define AUDIO_MIC_COUNT   0x18u
#define AUDIO_UNDERFLOWS  0x1cu
#define AUDIO_ID_VALUE    0x41554431u

#define AUDIO_ERR_NO_HARDWARE (-10)
#define AUDIO_ERR_STALLED     (-11)
#define AUDIO_ERR_DROPPED     (-12)

uint32_t audio_get_volume(void);
int audio_set_volume(uint32_t volume);
int cmd_debug_speaker(void);
int cmd_debug_mic(void);

#endif
