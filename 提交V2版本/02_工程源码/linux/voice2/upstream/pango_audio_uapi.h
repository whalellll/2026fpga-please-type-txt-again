/* SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note */
#ifndef PANGO_AUDIO_UAPI_H
#define PANGO_AUDIO_UAPI_H

#ifdef __KERNEL__
#include <linux/ioctl.h>
#include <linux/types.h>
#define PANGO_AUDIO_U32 __u32
#else
#include <stdint.h>
#include <sys/ioctl.h>
#define PANGO_AUDIO_U32 uint32_t
#endif

#define PANGO_AUDIO_ABI_VERSION 1u
#define PANGO_AUDIO_ID          0x41554431u
#define PANGO_AUDIO_VERSION     0x00020000u

#define PANGO_AUDIO_FORMAT_S16_LE 1u
#define PANGO_AUDIO_FEATURE_POLLING (1u << 0)
#define PANGO_AUDIO_FEATURE_EXCLUSIVE_READER (1u << 1)
#define PANGO_AUDIO_FEATURE_CAPTURE_FIFO (1u << 2)

struct pango_audio_info {
	PANGO_AUDIO_U32 abi_version;
	PANGO_AUDIO_U32 device_id;
	PANGO_AUDIO_U32 device_version;
	PANGO_AUDIO_U32 sample_rate_hz;
	PANGO_AUDIO_U32 sample_format;
	PANGO_AUDIO_U32 channels;
	PANGO_AUDIO_U32 fifo_samples;
	PANGO_AUDIO_U32 features;
	PANGO_AUDIO_U32 reserved[8];
};

struct pango_audio_stats {
	PANGO_AUDIO_U32 abi_version;
	PANGO_AUDIO_U32 fifo_level;
	PANGO_AUDIO_U32 microphone_samples;
	PANGO_AUDIO_U32 fifo_overflows;
	PANGO_AUDIO_U32 playback_underflows;
	PANGO_AUDIO_U32 reserved[3];
};

#define PANGO_AUDIO_IOC_MAGIC 'A'
#define PANGO_AUDIO_IOC_GET_INFO \
	_IOR(PANGO_AUDIO_IOC_MAGIC, 0x00, struct pango_audio_info)
#define PANGO_AUDIO_IOC_GET_STATS \
	_IOR(PANGO_AUDIO_IOC_MAGIC, 0x01, struct pango_audio_stats)
#define PANGO_AUDIO_IOC_CLEAR _IO(PANGO_AUDIO_IOC_MAGIC, 0x02)

#undef PANGO_AUDIO_U32

#endif
