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
#define PANGO_MAC_PIKAFISH_ID 0x50464e31u
#define PANGO_MAC_PIKAFISH_VERSION 0x00010000u
static inline int pango_mac_device_valid(PANGO_MAC_U32 id,PANGO_MAC_U32 version)
{
    return (id==PANGO_MAC_ID && version==PANGO_MAC_VERSION) ||
           (id==PANGO_MAC_PIKAFISH_ID && version==PANGO_MAC_PIKAFISH_VERSION);
}

#define PANGO_MAC_FEATURE_PRIVATE_SHADOW (1u << 0)
#define PANGO_MAC_FEATURE_SERIALIZED     (1u << 1)
#define PANGO_MAC_FEATURE_POLLING        (1u << 2)
#define PANGO_MAC_FEATURE_CONV_WINDOW    (1u << 3)
#define PANGO_MAC_FEATURE_CONV_COMPUTE   (1u << 4)
#define PANGO_MAC_FEATURE_STAGEA_GATHER  (1u << 5)
#define PANGO_MAC_FEATURE_RESIDENT_MODEL (1u << 6)
#define PANGO_MAC_FEATURE_NNUE_PIPELINE (1u << 7)
#define PANGO_MAC_FEATURE_PIKAFISH_DEDICATED (1u << 8)
#define PANGO_MAC_FEATURE_DENSE (1u << 9)
#define PANGO_MAC_FEATURE_NNUE_BATCH (1u << 11)
#define PANGO_MAC_BATCH_ABI_VERSION 1u
#define PANGO_MAC_BATCH_BASE 0x80u
#define PANGO_MAC_BATCH_ID 0x50464231u
#define PANGO_MAC_BATCH_SLOTS 8u
#define PANGO_MAC_BATCH_EXTERNAL 0xffffffffu
#define PANGO_MAC_BATCH_EVALUATE 1u
#define PANGO_MAC_BATCH_COPYOUT_MASK 2u
#define PANGO_MAC_BATCH_RESIDENT 4u
#define PANGO_MAC_BATCH_RESIDENT_PARENT(slot) (0x80000000u | (slot))
static inline int pango_mac_batch_parent_resident(PANGO_MAC_U32 parent)
{
    return (parent & ~7u)==0x80000000u;
}
#define PANGO_MAC_FEATURE_BATCH_COPYOUT_MASK (1u << 14)
#define PANGO_MAC_FEATURE_BATCH_RESIDENT (1u << 15)
/* Fixed per-open shadow layout. The driver constructs physical addresses;
 * users never submit a physical pointer or arbitrary export destination. */
#define PANGO_MAC_BATCH_LIST 0x000c0000u
#define PANGO_MAC_BATCH_INPUT 0x000c1000u
#define PANGO_MAC_BATCH_DESCRIPTORS 0x000c5000u
#define PANGO_MAC_BATCH_OUTPUT 0x000c8000u
#define PANGO_MAC_BATCH_CONTEXT 0x000f0000u
struct pango_mac_batch_update {
    PANGO_MAC_U32 parent,terms;
};
struct pango_mac_batch {
    PANGO_MAC_U32 abi_version,count,flags,bucket,first,second,timeout_us;
    struct pango_mac_batch_update update[PANGO_MAC_BATCH_SLOTS];
    PANGO_MAC_U32 status,cycles,jobs,score,external_read_words;
    PANGO_MAC_U32 local_read_words,local_write_words,export_words;
    PANGO_MAC_U32 reserved[5];
};
static inline int pango_mac_batch_valid(const struct pango_mac_batch *b)
{
    unsigned int i;
    if(b->abi_version!=PANGO_MAC_BATCH_ABI_VERSION || !b->count || b->count>8u ||
       (b->flags & ~(PANGO_MAC_BATCH_EVALUATE|PANGO_MAC_BATCH_COPYOUT_MASK|PANGO_MAC_BATCH_RESIDENT)) || b->timeout_us>1000000u)return 0;
    if(b->flags & PANGO_MAC_BATCH_EVALUATE) {
        if(b->bucket>=16u || b->first>=b->count || b->second>=b->count)return 0;
    } else if(b->bucket || b->first || b->second)return 0;
    for(i=0;i<8u;i++) {
        if(i<b->count) {
            PANGO_MAC_U32 parent=b->update[i].parent;
            if(b->update[i].terms>256u)return 0;
            if(pango_mac_batch_parent_resident(parent)){
                if(!(b->flags&PANGO_MAC_BATCH_RESIDENT) || (parent&7u)<i)return 0;
            }else if(parent!=PANGO_MAC_BATCH_EXTERNAL && parent>=i)return 0;
        } else if(b->update[i].parent || b->update[i].terms)return 0;
    }
    if(b->flags&PANGO_MAC_BATCH_COPYOUT_MASK){if(b->reserved[0]&~((1u<<b->count)-1u))return 0;}
    else if(b->reserved[0])return 0;
    if(!(b->flags&PANGO_MAC_BATCH_RESIDENT) && b->reserved[1])return 0;
    for(i=2;i<5u;i++)if(b->reserved[i])return 0;
    return 1;
}
#define PANGO_MAC_NNUE_ABI_VERSION 6u
#define PANGO_MAC_NNUE_BASE 0x180u
#define PANGO_MAC_NNUE_ID 0x4e4e5031u
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

/* New ioctls preserve the old StageA layout and its strict reserved fields.
 * Tags are assigned by the kernel, never supplied by clients at upload time.
 */
struct pango_mac_stagea_link {
    struct pango_mac_stagea_job job;
    PANGO_MAC_U32 view;
    PANGO_MAC_U32 tag;
    PANGO_MAC_U32 reserved[2];
};
struct pango_mac_nnue_upload {
    PANGO_MAC_U32 abi_version,view,source_offset,tag;
    PANGO_MAC_U32 reserved[4];
};
struct pango_mac_nnue_job {
    PANGO_MAC_U32 abi_version,bucket,tag0,tag1,first_view,timeout_us;
    PANGO_MAC_U32 score,cycles,jobs,status;
    PANGO_MAC_U32 reserved[2];
};
/* Per-open completed-job counters; read outside timed evaluate intervals. */
struct pango_mac_nnue_cache_stats {
    PANGO_MAC_U32 abi_version,runs,hits,read_words,model_restores,errors;
    PANGO_MAC_U32 reserved[2];
};
static inline int pango_mac_nnue_upload_valid(const struct pango_mac_nnue_upload *j,
                                             PANGO_MAC_U32 bytes)
{
    unsigned int i;
    if(j->abi_version!=PANGO_MAC_NNUE_ABI_VERSION || j->view>1 || j->tag ||
       (j->source_offset&3u) || j->source_offset>bytes || bytes-j->source_offset<2048u)return 0;
    for(i=0;i<4;i++)if(j->reserved[i])return 0;
    return 1;
}
static inline int pango_mac_nnue_job_valid(const struct pango_mac_nnue_job *j)
{
    return j->abi_version==PANGO_MAC_NNUE_ABI_VERSION && j->bucket<16u &&
        j->tag0 && j->tag1 && j->first_view<2u && j->timeout_us<=1000000u &&
        !j->reserved[0] && !j->reserved[1];
}

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
#define PANGO_MAC_IOC_RUN_STAGEA_LINK _IOWR(PANGO_MAC_IOC_MAGIC, 0x06, struct pango_mac_stagea_link)
#define PANGO_MAC_IOC_NNUE_UPLOAD _IOWR(PANGO_MAC_IOC_MAGIC, 0x07, struct pango_mac_nnue_upload)
#define PANGO_MAC_IOC_RUN_NNUE _IOWR(PANGO_MAC_IOC_MAGIC, 0x08, struct pango_mac_nnue_job)
#define PANGO_MAC_IOC_NNUE_CACHE_STATS _IOR(PANGO_MAC_IOC_MAGIC, 0x09, struct pango_mac_nnue_cache_stats)
#define PANGO_MAC_IOC_RUN_BATCH _IOWR(PANGO_MAC_IOC_MAGIC, 0x0b, struct pango_mac_batch)

/* V321 whole-layer ABI: offsets within the existing private shadow. */
#define PANGO_MAC_FEATURE_VISION32 (1u << 10)
#define PANGO_MAC_FEATURE_VISION32_EXACT (1u << 12)
#define PANGO_MAC_FEATURE_VISION32_REUSE (1u << 13)
/* Explicit immutable-parameter opt-in. Cookie0 disables reuse; never wraps.
 * weights/params/LUT must remain immutable for this fd+model_generation.
 * frame_id returns1 for a driver cache hit,0 for a full upload.
 * Old clients leave reserved[0]=0 and always retain their original behavior. */
#define PANGO_VISION32_REUSE_PARAMS 0x56525031u
#define PANGO_VISION32_ABI 1u
#define PANGO_VISION32_ID 0x56333231u
#define PANGO_VISION32_EXACT_VERSION 0x00010001u
#define PANGO_VISION32_RAW_I32 2u
#define PANGO_VISION32_EXACT_S16 4u
#define PANGO_VISION32_EXACT_LUT 5u
struct pango_vision32_job {
    PANGO_MAC_U32 abi_version;
    /* Five byte OFFSETS within this fd's private shadow, never physical. */
    PANGO_MAC_U32 input,weights,output,params,lut;
    PANGO_MAC_U32 width,height,cin,cout,kernel,stride,padding;
    PANGO_MAC_U32 flags,timeout_cycles,model_generation,frame_id;
    PANGO_MAC_U32 timeout_us,status,cycles,read_bytes,write_bytes,mac_cycles,error;
    PANGO_MAC_U32 reserved[4];
};
/* Legacy modes0/1 use half-away S8 quant; RAW_I32=2 bypasses postprocessing.
 * EXACT_S16=4: I32 bias overflow rejects, ties-even shift, saturate S16.
 * EXACT_LUT=5: same pre-value, signed-byte LUT[pre+32768], sign-extend to S16.
 * Exact modes require scale=1, shift0..62, and the independent EXACT feature.
 * Existing ioctl size, parameter triples, modes and offset units are retained.
 */
static inline int pango_vision32_sizes(const struct pango_vision32_job *j,
    PANGO_MAC_U32 bytes,PANGO_MAC_U32 sizes[5])
{
    PANGO_MAC_U32 ow,oh,k,groups,offsets[5],i;
    unsigned long long count;
    if(j->abi_version!=PANGO_VISION32_ABI || !j->width || j->width>640 ||
       !j->height || j->height>640 || !j->cin || j->cin>512 || !j->cout || j->cout>256 ||
       (j->kernel!=1 && j->kernel!=3 && j->kernel!=6) ||
       (j->stride!=1 && j->stride!=2) || j->padding>=j->kernel ||
       j->width+2*j->padding<j->kernel || j->height+2*j->padding<j->kernel ||
       (j->flags>2 && j->flags!=4 && j->flags!=5) || j->timeout_cycles<16 || j->timeout_us>1000000u ||
       (j->reserved[0] && (j->reserved[0]!=PANGO_VISION32_REUSE_PARAMS || !j->model_generation)) || j->reserved[1] || j->reserved[2] || j->reserved[3])return 0;
    k=j->cin*j->kernel*j->kernel;if(k>1152)return 0;
    ow=(j->width+2*j->padding-j->kernel)/j->stride+1;
    oh=(j->height+2*j->padding-j->kernel)/j->stride+1;
    if(!ow || ow>640 || !oh || oh>640)return 0;
    groups=(j->cout+7)/8;
    count=(unsigned long long)j->width*j->height*((j->cin+3)&~3u);
    if(count>bytes)return 0;
    sizes[0]=(PANGO_MAC_U32)count;
    sizes[1]=groups*k*8;
    count=(unsigned long long)ow*oh*j->cout*(j->flags==2?4:(j->flags&4)?2:1);
    if(count>bytes)return 0;
    sizes[2]=(PANGO_MAC_U32)count;
    sizes[3]=groups*8*12;sizes[4]=(j->flags&1)?((j->flags&4)?65536:256):0;
    offsets[0]=j->input;offsets[1]=j->weights;offsets[2]=j->output;offsets[3]=j->params;offsets[4]=j->lut;
    for(i=0;i<5;i++) {
        if((offsets[i]&3u) || offsets[i]>bytes || sizes[i]>bytes-offsets[i])return 0;
        if(i!=2 && sizes[i] && j->output<offsets[i]+sizes[i] && offsets[i]<j->output+sizes[2])return 0;
    }
    return 1;
}
#define PANGO_MAC_IOC_RUN_VISION32 _IOWR(PANGO_MAC_IOC_MAGIC,0x0a,struct pango_vision32_job)


#undef PANGO_MAC_U8
#undef PANGO_MAC_U16
#undef PANGO_MAC_U32

#endif /* _UAPI_LINUX_PANGO_MAC_H */
