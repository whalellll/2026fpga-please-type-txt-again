#ifndef _UAPI_LINUX_PANGO_MAC_H
#define _UAPI_LINUX_PANGO_MAC_H

#ifdef __KERNEL__
#include <linux/ioctl.h>
#include <linux/types.h>
#define PANGO_MAC_U8  __u8
#define PANGO_MAC_U16 __u16
#define PANGO_MAC_U32 __u32
#else
#include <stdint.h>
#include <sys/ioctl.h>
#define PANGO_MAC_U8  uint8_t
#define PANGO_MAC_U16 uint16_t
#define PANGO_MAC_U32 uint32_t
#endif

#define PANGO_MAC_ABI_VERSION 1u
#define PANGO_MAC_CONV_ABI_VERSION 2u
#define PANGO_MAC_CONV_COMPUTE_ABI_VERSION 3u
#define PANGO_MAC_CONV_FLAG_WINDOW_ONLY 1u
#define PANGO_MAC_CONV_FLAG_COMPUTE 2u

#define PANGO_MAC_ID          0x4d41434bu
#define PANGO_MAC_VERSION     0x00020100u

#define PANGO_MAC_FEATURE_PRIVATE_SHADOW (1u << 0)
#define PANGO_MAC_FEATURE_SERIALIZED     (1u << 1)
#define PANGO_MAC_FEATURE_POLLING        (1u << 2)
#define PANGO_MAC_FEATURE_CONV_WINDOW    (1u << 3)
#define PANGO_MAC_FEATURE_CONV_COMPUTE   (1u << 4)
#define PANGO_MAC_FEATURE_STAGEA_GATHER  (1u << 5)
#define PANGO_MAC_FEATURE_RESIDENT_MODEL (1u << 6)
#define PANGO_MAC_FEATURE_ASYNC_DENSE    (1u << 7)
#define PANGO_MAC_MODEL_ABI_VERSION 5u
#define PANGO_MAC_STAGEA_ABI_VERSION 4u
#define PANGO_MAC_STAGEA_ID 0x50464741u
#define PANGO_MAC_STAGEA_VERSION 0x00020000u
#define PANGO_MAC_STAGEA_THREAT_ROWS 45547u
#define PANGO_MAC_STAGEA_PSQ_ROWS 16536u

/* Descriptors: bit31 subtract, bit30 PSQ table, bits15:0 row ID.
 * The two immutable model tables have fixed, read-only physical windows.
 * base/output are 1024 little-endian int16 values with modulo-65536 addition.
 */
struct pango_mac_stagea_job {
    PANGO_MAC_U32 abi_version;
    PANGO_MAC_U32 terms;
    PANGO_MAC_U32 flags;
    PANGO_MAC_U32 base_offset;
    PANGO_MAC_U32 descriptor_offset;
    PANGO_MAC_U32 output_offset;
    PANGO_MAC_U32 timeout_us;
    PANGO_MAC_U32 status;
    PANGO_MAC_U32 cycles;
    PANGO_MAC_U32 error_code;
    PANGO_MAC_U32 reserved[6];
};

/* Shared validation used by the kernel and the independent negative tests. */
static inline int pango_mac_stagea_descriptor_valid(PANGO_MAC_U32 value)
{
    return !(value & 0x3fff0000u) &&
        (value & 65535u) < ((value & 0x40000000u) ?
            PANGO_MAC_STAGEA_PSQ_ROWS : PANGO_MAC_STAGEA_THREAT_ROWS);
}
static inline int pango_mac_stagea_job_valid(const struct pango_mac_stagea_job *j,
                                            PANGO_MAC_U32 scratch_bytes)
{
    PANGO_MAC_U32 descriptors;
    unsigned int i;
    if (j->abi_version != PANGO_MAC_STAGEA_ABI_VERSION || !j->terms ||
        j->terms > 256 || j->flags || j->timeout_us > 1000000u)
        return 0;
    for (i=0;i<6;i++) if (j->reserved[i]) return 0;
    descriptors=j->terms*4u;
    if ((j->base_offset | j->descriptor_offset | j->output_offset) & 3u ||
        j->base_offset > scratch_bytes || scratch_bytes-j->base_offset < 2048u ||
        j->output_offset > scratch_bytes || scratch_bytes-j->output_offset < 2048u ||
        j->descriptor_offset > scratch_bytes || scratch_bytes-j->descriptor_offset < descriptors)
        return 0;
    if ((j->output_offset < j->base_offset+2048u && j->base_offset < j->output_offset+2048u) ||
        (j->output_offset < j->descriptor_offset+descriptors && j->descriptor_offset < j->output_offset+2048u) ||
        (j->base_offset < j->descriptor_offset+descriptors && j->descriptor_offset < j->base_offset+2048u))
        return 0;
    return 1;
}

struct pango_mac_info {
	PANGO_MAC_U32 abi_version;
	PANGO_MAC_U32 device_id;
	PANGO_MAC_U32 device_version;
	PANGO_MAC_U32 scratch_bytes;
	PANGO_MAC_U32 features;
	PANGO_MAC_U32 max_pixels;
	PANGO_MAC_U32 max_channels;
	PANGO_MAC_U32 max_timeout_us;
	PANGO_MAC_U32 reserved[8];
};

/* Snapshot a range from this file's private shadow. Later shadow writes do
 * not change it. RUN_RESIDENT restores it after another client uses scratch.
 */
struct pango_mac_model {
    PANGO_MAC_U32 abi_version, offset, bytes, flags;
    PANGO_MAC_U32 reserved[12];
};
static inline int pango_mac_model_valid(const struct pango_mac_model *m,
                                       PANGO_MAC_U32 scratch_bytes)
{
    unsigned int i;
    if (m->abi_version != PANGO_MAC_MODEL_ABI_VERSION || m->flags ||
        !m->bytes || ((m->offset | m->bytes) & 3u) ||
        m->offset > scratch_bytes || m->bytes > scratch_bytes-m->offset)
        return 0;
    for (i=0;i<12;i++) if (m->reserved[i]) return 0;
    return 1;
}
static inline int pango_mac_model_contains(PANGO_MAC_U32 start,PANGO_MAC_U32 bytes,
                                         PANGO_MAC_U32 offset,PANGO_MAC_U32 length)
{
    return offset>=start && length<=bytes && offset-start<=bytes-length;
}
static inline int pango_mac_ranges_overlap(PANGO_MAC_U32 a,PANGO_MAC_U32 an,
                                         PANGO_MAC_U32 b,PANGO_MAC_U32 bn)
{
    return an && bn && (a<=b ? b-a<an : a-b<bn);
}
static inline int pango_mac_resident_sources_valid(
    PANGO_MAC_U32 start,PANGO_MAC_U32 bytes,PANGO_MAC_U32 weight,PANGO_MAC_U32 wn,
    PANGO_MAC_U32 bias,PANGO_MAC_U32 bn,PANGO_MAC_U32 input,PANGO_MAC_U32 in,
    PANGO_MAC_U32 output,PANGO_MAC_U32 on)
{
    return pango_mac_model_contains(start,bytes,weight,wn) &&
        (!bn || pango_mac_model_contains(start,bytes,bias,bn)) &&
        !pango_mac_ranges_overlap(start,bytes,input,in) &&
        !pango_mac_ranges_overlap(start,bytes,output,on);
}

/*
 * All buffer addresses are offsets in the private shadow mapping returned by
 * mmap().  The kernel copies only the validated ranges needed by this job to
 * the single physical accelerator scratch area while it owns the device.
 */
struct pango_mac_job {
	PANGO_MAC_U32 abi_version;
	PANGO_MAC_U16 pixels;
	PANGO_MAC_U16 cin;
	PANGO_MAC_U16 cout;
	PANGO_MAC_U8 out_shift;
	PANGO_MAC_U8 compute_mode;
	PANGO_MAC_U8 activation;
	PANGO_MAC_U8 output_format;
	PANGO_MAC_U8 zero_bias;
	PANGO_MAC_U8 reserved0;
	PANGO_MAC_U32 input_offset;
	PANGO_MAC_U32 weight_offset;
	PANGO_MAC_U32 bias_offset;
	PANGO_MAC_U32 output_offset;
	PANGO_MAC_U32 timeout_us;
	PANGO_MAC_U32 cycles;
	PANGO_MAC_U32 status;
	PANGO_MAC_U32 error_code;
	PANGO_MAC_U32 reserved[4];
};

/* Software-only split phase. START snapshots all inputs and reserves the
 * physical engine before returning. Only this ticket's FINISH, close, or the
 * bounded watchdog releases it. FINISH uses the saved descriptor, never the
 * caller's replacement offsets. Shadow input may be prepared while active;
 * shadow output is stable until FINISH publishes the result. The watchdog
 * retains a completed result separately. One ticket per file; no shared
 * physical mapping. This optional path accepts compute_mode=1, Cin multiple
 * of 4, Cout<=32, zero_bias=1, output_format=3, out_shift=activation=0 only. */
#define PANGO_MAC_ASYNC_RESIDENT 1u
struct pango_mac_async_job {
    struct pango_mac_job job;
    PANGO_MAC_U32 ticket, flags, reserved[2];
};

/*
 * Version-2 convolution job layout. Offsets refer to the same exclusive
 * per-open shadow mapping as the legacy job. The driver must validate every
 * range before copying to the physical engine. This descriptor does not
 * change the meaning of the legacy OUTPUT_DST register at 0x24. WINDOW_ONLY
 * returns tap/DDR counters without writing a convolution output tensor.
 * ABI version 3 with COMPUTE consumes 16 signed INT32 biases at reserved[0]
 * and 16 unsigned right-shift bytes at reserved[1] in the private shadow.
 * Values are rounded half away from zero, saturated to S8, and written as
 * compact NHWC bytes. Only Cin<=4, Cout<=16 and channel_tile=0 are accepted.
 * SiLU is applied by the CPU after this integer convolution when required.
 */
struct pango_mac_conv_job {
	PANGO_MAC_U32 abi_version;
	PANGO_MAC_U32 flags;
	PANGO_MAC_U32 model_id_lo;
	PANGO_MAC_U32 model_id_hi;
	PANGO_MAC_U32 generation;
	PANGO_MAC_U32 input_offset;
	PANGO_MAC_U32 weight_offset;
	PANGO_MAC_U32 output_offset;
	PANGO_MAC_U16 width;
	PANGO_MAC_U16 height;
	PANGO_MAC_U16 channels;
	PANGO_MAC_U16 output_channels;
	PANGO_MAC_U8 kernel;
	PANGO_MAC_U8 stride;
	PANGO_MAC_U8 padding;
	PANGO_MAC_U8 channel_tile;
	PANGO_MAC_U16 weight_lines;
	PANGO_MAC_U16 reserved0;
	PANGO_MAC_U32 timeout_us;
	PANGO_MAC_U32 cycles;
	PANGO_MAC_U32 input_ddr_bytes;
	PANGO_MAC_U32 weight_ddr_bytes;
	PANGO_MAC_U32 output_ddr_bytes;
	PANGO_MAC_U32 window_count;
	PANGO_MAC_U32 weight_reuse_count;
	PANGO_MAC_U32 stall_cycles;
	PANGO_MAC_U32 status;
	PANGO_MAC_U32 error_code;
	PANGO_MAC_U32 tap_xor;
	PANGO_MAC_U32 weight_digest;
	PANGO_MAC_U32 reserved[4];
};

#define PANGO_MAC_IOC_MAGIC    'M'
#define PANGO_MAC_IOC_GET_INFO _IOR(PANGO_MAC_IOC_MAGIC, 0x00, struct pango_mac_info)
#define PANGO_MAC_IOC_RUN      _IOWR(PANGO_MAC_IOC_MAGIC, 0x01, struct pango_mac_job)
#define PANGO_MAC_IOC_RUN_CONV _IOWR(PANGO_MAC_IOC_MAGIC, 0x02, struct pango_mac_conv_job)
#define PANGO_MAC_IOC_RUN_STAGEA _IOWR(PANGO_MAC_IOC_MAGIC, 0x03, struct pango_mac_stagea_job)
#define PANGO_MAC_IOC_REGISTER_MODEL _IOW(PANGO_MAC_IOC_MAGIC, 0x04, struct pango_mac_model)
#define PANGO_MAC_IOC_RUN_RESIDENT _IOWR(PANGO_MAC_IOC_MAGIC, 0x05, struct pango_mac_job)
#define PANGO_MAC_IOC_DENSE_START _IOWR(PANGO_MAC_IOC_MAGIC, 0x06, struct pango_mac_async_job)
#define PANGO_MAC_IOC_DENSE_FINISH _IOWR(PANGO_MAC_IOC_MAGIC, 0x07, struct pango_mac_async_job)

#undef PANGO_MAC_U8
#undef PANGO_MAC_U16
#undef PANGO_MAC_U32

#endif /* _UAPI_LINUX_PANGO_MAC_H */
