#ifndef PANGO_VOICE_UAPI_H
#define PANGO_VOICE_UAPI_H
#ifdef __KERNEL__
#include <linux/types.h>
#include <linux/ioctl.h>
#define PV_U32 __u32
#define PV_U16 __u16
#define PV_U8 __u8
#define PV_S16 __s16
#define PV_S8 __s8
#else
#include <stdint.h>
#include <sys/ioctl.h>
#define PV_U32 uint32_t
#define PV_U16 uint16_t
#define PV_U8 uint8_t
#define PV_S16 int16_t
#define PV_S8 int8_t
#endif
#define PANGO_VOICE_ABI 1u
#define PANGO_VOICE_ID 0x56434531u
#define PANGO_VOICE_VERSION 0x00010000u
#define PANGO_VOICE_MODEL_BYTES 6020u
#define PANGO_VOICE_FEATURE_CNN_TILE (1u << 5)
#define PANGO_VOICE_FEATURE_CNN_QUANT (1u << 6)
#define PANGO_VOICE_CNN_ID 0x56434e31u
#define PANGO_VOICE_CNN_ABI 1u
struct pango_voice_cnn_model {
    PV_U32 abi_version,k,cout,generation,flags,reserved[3];
    PV_U8 weights[8192]; /* compact output-major signed8, K divisible by4 */
};
struct pango_voice_cnn_tile {
    PV_U32 abi_version,generation,pixels,cycles,status,timeout_us,reserved[2];
    PV_U8 input[4096]; /* compact pixel-major signed8 */
    PV_U32 output[512]; /* unbiased signed32, pixel-major */
};
/* Separate opt-in epilogue, scoped to the current resident layer generation.
 * Raw CNN_TILE keeps its original unbiased I32 output semantics. */
struct pango_voice_cnn_quant {
    PV_U32 abi_version,generation,cout,clamp_lo,clamp_hi,reserved[3];
    PV_U32 bias[32],multiplier[32],shift[32];
};
struct pango_voice_info {
    PV_U32 abi_version,device_id,device_version,sample_rate,features;
    PV_U32 window_samples,hop_samples,queue_frames,model_bytes;
    PV_U32 reserved[7];
};
struct pango_voice_model { PV_U8 image[PANGO_VOICE_MODEL_BYTES]; };
struct pango_voice_mode { PV_U32 value; };
struct pango_voice_frame {
    PV_S16 samples[400];PV_S8 features[20];
    PV_U32 cycles,timeout_us,reserved[2];
};
struct pango_voice_infer {
    PV_S8 input[40],outputs[121];PV_U8 token;PV_U16 confidence;
    PV_U32 cycles,status,timeout_us,flags,reserved[2];
};
struct pango_voice_feature { PV_U32 end_sample,sequence;PV_S8 values[20]; };
struct pango_voice_level { PV_U32 end_sample,mean_absolute; };
struct pango_voice_stream {
    PV_U32 abi_version,timeout_us,feature_count,level_count,overflows,capture_count;
    struct pango_voice_feature frames[16];
    struct pango_voice_level levels[16];
    PV_U32 reserved[2];
};
#define PANGO_VOICE_IOC_INFO _IOR('V',0,struct pango_voice_info)
#define PANGO_VOICE_IOC_MODEL _IOW('V',1,struct pango_voice_model)
#define PANGO_VOICE_IOC_FRAME _IOWR('V',2,struct pango_voice_frame)
#define PANGO_VOICE_IOC_INFER _IOWR('V',3,struct pango_voice_infer)
#define PANGO_VOICE_IOC_MODE _IOW('V',4,struct pango_voice_mode)
#define PANGO_VOICE_IOC_STREAM _IOWR('V',5,struct pango_voice_stream)
#define PANGO_VOICE_IOC_CNN_MODEL _IOWR('V',6,struct pango_voice_cnn_model)
#define PANGO_VOICE_IOC_CNN_TILE _IOWR('V',7,struct pango_voice_cnn_tile)
#define PANGO_VOICE_IOC_CNN_QUANT _IOW('V',8,struct pango_voice_cnn_quant)
#define PANGO_VOICE_IOC_CNN_QTILE _IOWR('V',9,struct pango_voice_cnn_tile)
#undef PV_U32
#undef PV_U16
#undef PV_U8
#undef PV_S16
#undef PV_S8
#endif
