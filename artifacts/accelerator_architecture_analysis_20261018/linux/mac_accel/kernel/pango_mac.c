// SPDX-License-Identifier: GPL-2.0
/*
 * Serialized Linux owner for the PG2L100H dense MAC v2 accelerator.
 *
 * The hardware has one register file and one 1 MiB DMA scratch aperture.  A
 * private page-backed shadows are preallocated and assigned to open files.  RUN
 * copies the validated source ranges into the physical scratch area while the
 * device mutex is held, executes one job, and copies the result back.  This
 * makes separate file descriptors safe across threads and processes without
 * exposing accelerator registers or shared physical scratch memory.
 */

#include <linux/fs.h>
#include <linux/io.h>
#include <linux/kernel.h>
#include <linux/ktime.h>
#include <linux/miscdevice.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/platform_device.h>
#include <linux/sched.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/uaccess.h>
#include <linux/vmalloc.h>

#include <uapi/linux/pango_mac.h>
#include "pango_mac_copy_chunks.h"

#define PANGO_MAC_REG_ID          0x00
#define PANGO_MAC_REG_VERSION     0x04
#define PANGO_MAC_REG_CONTROL     0x08
#define PANGO_MAC_REG_STATUS      0x0c
#define PANGO_MAC_REG_DIMS        0x10
#define PANGO_MAC_REG_FORMAT      0x14
#define PANGO_MAC_REG_INPUT       0x18
#define PANGO_MAC_REG_WEIGHT      0x1c
#define PANGO_MAC_REG_BIAS        0x20
#define PANGO_MAC_REG_OUTPUT      0x24
#define PANGO_MAC_REG_CYCLES      0x28
#define PANGO_MAC_STAGEA_BASE     0x100

#define PANGO_MAC_CONV_ID         0x40
#define PANGO_MAC_CONV_VERSION    0x44
#define PANGO_MAC_CONV_CONTROL    0x48
#define PANGO_MAC_CONV_STATUS     0x48
#define PANGO_MAC_CONV_DIMS       0x4c
#define PANGO_MAC_CONV_CONFIG     0x50
#define PANGO_MAC_CONV_TILE       0x54
#define PANGO_MAC_CONV_INPUT      0x58
#define PANGO_MAC_CONV_WEIGHT     0x5c
#define PANGO_MAC_CONV_OUTPUT     0x60
#define PANGO_MAC_CONV_LINES      0x64
#define PANGO_MAC_CONV_MODEL_LO   0x68
#define PANGO_MAC_CONV_MODEL_HI   0x6c
#define PANGO_MAC_CONV_GENERATION 0x70
#define PANGO_MAC_CONV_CYCLES     0x74
#define PANGO_MAC_CONV_COUNTER_ID 0x78
#define PANGO_MAC_CONV_COUNTER    0x7c
#define PANGO_MAC_CONV_HW_ID      0x4d434f4e
#define PANGO_MAC_CONV_HW_VERSION 0x00020000
#define PANGO_MAC_CONV_HW_COMPUTE_VERSION 0x00030000
#define PANGO_MAC_CONV_CMD_LOAD   BIT(0)
#define PANGO_MAC_CONV_CMD_ACT    BIT(1)
#define PANGO_MAC_CONV_CMD_INPUT  BIT(2)
#define PANGO_MAC_CONV_CMD_CLEAR  BIT(3)
#define PANGO_MAC_CONV_CMD_COMPUTE BIT(4)
#define PANGO_MAC_CONV_CMD_ABORT  BIT(5)
#define PANGO_MAC_CONV_WT_DONE    BIT(1)
#define PANGO_MAC_CONV_WT_ERROR   BIT(2)
#define PANGO_MAC_CONV_IN_DONE    BIT(4)
#define PANGO_MAC_CONV_IN_ERROR   BIT(5)
#define PANGO_MAC_CONV_ACTIVE     BIT(7)
#define PANGO_MAC_CONV_COMP_DONE  BIT(8)
#define PANGO_MAC_CONV_COMP_ERROR BIT(9)
#define PANGO_MAC_CONV_ERROR_SHIFT 12

#define PANGO_MAC_CONTROL_START   BIT(0)
#define PANGO_MAC_CONTROL_CLEAR   BIT(1)
#define PANGO_MAC_STATUS_BUSY     BIT(0)
#define PANGO_MAC_STATUS_DONE     BIT(1)
#define PANGO_MAC_STATUS_ERROR    BIT(2)
#define PANGO_MAC_ERROR_SHIFT     12
#define PANGO_MAC_ERROR_MASK      GENMASK(15, 12)
#define PANGO_MAC_ZERO_BIAS       BIT(30)

#define PANGO_MAC_MAX_PIXELS      16u
#define PANGO_MAC_MAX_CHANNELS    256u
#define PANGO_MAC_DEFAULT_TIMEOUT 100000u
#define PANGO_MAC_MAX_TIMEOUT     1000000u
#define PANGO_MAC_CONV_MIN_TIMEOUT 10000u
#define PANGO_MAC_POOL_CONTEXTS    8u

struct pango_mac_dev {
	struct device *dev;
	void __iomem *regs;
	u8 __iomem *scratch;
	resource_size_t scratch_bus;
	size_t scratch_bytes;
	bool stagea_supported;
	struct pango_mac_file *resident_owner;
	/* Serializes the one physical register/scratch engine across all files. */
	struct mutex run_lock;
	/* Contexts and user-mappable shadows are allocated once at probe. */
	struct mutex pool_lock;
	struct pango_mac_file *contexts;
	struct miscdevice miscdev;
};

struct pango_mac_file {
	struct pango_mac_dev *mac;
	struct page *pages;
	u8 *shadow;
	bool in_use;
	u8 *model_snapshot;
	u32 model_offset, model_bytes;
};

struct pango_mac_sizes {
	size_t input;
	size_t weight;
	size_t bias;
	size_t output;
};

struct pango_mac_conv_sizes {
	size_t input;
	size_t weight;
	size_t output;
	u32 output_width;
	u32 output_height;
};

static bool pango_mac_range_ok(const struct pango_mac_dev *mac, u32 offset,
			       size_t bytes)
{
	return offset <= mac->scratch_bytes &&
	       bytes <= mac->scratch_bytes - offset;
}

static bool pango_mac_overlap(u32 first, size_t first_bytes, u32 second,
			      size_t second_bytes)
{
	u64 first_end = (u64)first + first_bytes;
	u64 second_end = (u64)second + second_bytes;

	return first < second_end && second < first_end;
}

static int pango_mac_validate_job(const struct pango_mac_dev *mac,
				  const struct pango_mac_job *job,
				  struct pango_mac_sizes *sizes)
{
	u32 ci_tiles;
	u32 co_tiles;
	u32 co_step;

	if (job->abi_version != PANGO_MAC_ABI_VERSION || job->reserved0 ||
	    job->reserved[0] || job->reserved[1] || job->reserved[2] ||
	    job->reserved[3])
		return -EINVAL;
	if (!job->pixels || job->pixels > PANGO_MAC_MAX_PIXELS || !job->cin ||
	    job->cin > PANGO_MAC_MAX_CHANNELS || !job->cout ||
	    job->cout > PANGO_MAC_MAX_CHANNELS || job->compute_mode > 3 ||
	    job->activation > 3 || job->output_format > 3 || job->zero_bias > 1)
		return -EINVAL;
	if ((job->input_offset | job->weight_offset | job->bias_offset |
	     job->output_offset) & 3)
		return -EINVAL;
	if (job->timeout_us > PANGO_MAC_MAX_TIMEOUT)
		return -EINVAL;

	ci_tiles = (job->cin + 3u) / 4u;
	co_step = job->compute_mode == 0 ? 16u : 32u;
	co_tiles = (job->cout + co_step - 1u) / co_step;
	sizes->input = (size_t)job->pixels * ci_tiles * 8u;
	sizes->weight = (size_t)co_tiles * ci_tiles * 128u;
	sizes->bias = job->zero_bias ? 0 : (size_t)co_tiles * 192u;
	sizes->output = (size_t)job->pixels * job->cout * 4u;

	if (!pango_mac_range_ok(mac, job->input_offset, sizes->input) ||
	    !pango_mac_range_ok(mac, job->weight_offset, sizes->weight) ||
	    (!job->zero_bias &&
	     !pango_mac_range_ok(mac, job->bias_offset, sizes->bias)) ||
	    !pango_mac_range_ok(mac, job->output_offset, sizes->output))
		return -EINVAL;

	/* The engine reads sources while writing output; reject DMA aliasing. */
	if (pango_mac_overlap(job->output_offset, sizes->output,
			      job->input_offset, sizes->input) ||
	    pango_mac_overlap(job->output_offset, sizes->output,
			      job->weight_offset, sizes->weight) ||
	    (!job->zero_bias &&
	     pango_mac_overlap(job->output_offset, sizes->output,
			       job->bias_offset, sizes->bias)))
		return -EINVAL;

	return 0;
}

static int pango_mac_validate_conv_job(const struct pango_mac_dev *mac,
				       const struct pango_mac_conv_job *job,
				       struct pango_mac_conv_sizes *sizes)
{
	u32 padded_width, padded_height, tiles, needed_lines;
	int i;

	bool compute = job->abi_version == PANGO_MAC_CONV_COMPUTE_ABI_VERSION &&
		       job->flags == PANGO_MAC_CONV_FLAG_COMPUTE;

	if (!(compute || (job->abi_version == PANGO_MAC_CONV_ABI_VERSION &&
		       job->flags == PANGO_MAC_CONV_FLAG_WINDOW_ONLY)) ||
	    job->reserved0)
		return -EINVAL;
	for (i = compute ? 2 : 0; i < ARRAY_SIZE(job->reserved); i++)
		if (job->reserved[i])
			return -EINVAL;
	if (compute && (job->channels > 4 || job->output_channels > 16 ||
			job->channel_tile != 0 ||
			(job->reserved[0] | job->reserved[1]) & 3 ||
			!pango_mac_range_ok(mac, job->reserved[0], 64) ||
			!pango_mac_range_ok(mac, job->reserved[1], 16)))
		return -EINVAL;
	if (!job->width || job->width > 320 || !job->height ||
	    job->height > 320 || !job->channels || job->channels > 1024 ||
	    !job->output_channels || job->output_channels > 256 ||
	    (job->kernel != 1 && job->kernel != 3 && job->kernel != 6) ||
	    (job->stride != 1 && job->stride != 2) ||
	    job->padding >= job->kernel ||
	    (job->kernel == 1 && job->padding) ||
	    (job->timeout_us && (job->timeout_us < PANGO_MAC_CONV_MIN_TIMEOUT ||
				 job->timeout_us > PANGO_MAC_MAX_TIMEOUT)))
		return -EINVAL;
	padded_width = job->width + 2u * job->padding;
	padded_height = job->height + 2u * job->padding;
	if (padded_width < job->kernel || padded_height < job->kernel)
		return -EINVAL;
	tiles = (job->channels + 3u) / 4u;
	needed_lines = (job->channels * job->kernel * job->kernel + 3u) / 4u;
	if (job->channel_tile >= tiles || needed_lines > 32 ||
	    job->weight_lines != needed_lines)
		return -EINVAL;
	if ((job->input_offset | job->weight_offset |
	     job->output_offset) & 3)
		return -EINVAL;
	sizes->output_width = (padded_width - job->kernel) / job->stride + 1u;
	sizes->output_height = (padded_height - job->kernel) / job->stride + 1u;
	sizes->input = (size_t)job->width * job->height * tiles * 4u;
	sizes->weight = (size_t)job->weight_lines * 128u;
	sizes->output = (size_t)sizes->output_width * sizes->output_height *
			job->output_channels;
	if (!pango_mac_range_ok(mac, job->input_offset, sizes->input) ||
	    !pango_mac_range_ok(mac, job->weight_offset, sizes->weight) ||
	    !pango_mac_range_ok(mac, job->output_offset, sizes->output) ||
	    pango_mac_overlap(job->input_offset, sizes->input,
			      job->weight_offset, sizes->weight) ||
	    pango_mac_overlap(job->input_offset, sizes->input,
			      job->output_offset, sizes->output) ||
	    pango_mac_overlap(job->weight_offset, sizes->weight,
			      job->output_offset, sizes->output))
		return -EINVAL;
	if (compute && (pango_mac_overlap(job->reserved[0], 64,
					job->reserved[1], 16) ||
		pango_mac_overlap(job->reserved[0], 64,
				  job->output_offset, sizes->output) ||
		pango_mac_overlap(job->reserved[1], 16,
				  job->output_offset, sizes->output)))
		return -EINVAL;
	return 0;
}

struct pango_mac_transfer {
    u8 *normal;
    u8 __iomem *io;
    const u8 *source;
    const u8 __iomem *io_source;
};
static void pango_mac_transfer_chunk(void *opaque, unsigned offset, unsigned bytes)
{
    struct pango_mac_transfer *copy = opaque;

    if (copy->io_source)
        memcpy_fromio(copy->normal + offset, copy->io_source + offset, bytes);
    else if (copy->io)
        memcpy_toio(copy->io + offset, copy->source + offset, bytes);
    else
        memcpy(copy->normal + offset, copy->source + offset, bytes);
}
static void pango_mac_transfer_yield(void *opaque)
{
    (void)opaque;
    cond_resched();
}
/* Caller retains run_lock throughout staging, execution and result copying. */
static void pango_mac_copy_data(u8 *normal, u8 __iomem *io, const u8 *source, u32 bytes)
{
    struct pango_mac_transfer copy = {
        .normal = normal, .io = io, .source = source
    };

    pango_mac_copy_chunks(&copy, bytes, pango_mac_transfer_chunk, pango_mac_transfer_yield);
}
static void pango_mac_copy_output(u8 *normal, const u8 __iomem *io, u32 bytes)
{
    struct pango_mac_transfer copy = { .normal = normal, .io_source = io };

    pango_mac_copy_chunks(&copy, bytes, pango_mac_transfer_chunk, pango_mac_transfer_yield);
}

static int pango_mac_wait(struct pango_mac_dev *mac, struct pango_mac_job *job)
{
	ktime_t deadline;
	u32 polls = 0;
	u32 status;

	deadline = ktime_add_us(ktime_get(), job->timeout_us ? job->timeout_us :
				 PANGO_MAC_DEFAULT_TIMEOUT);
	for (;;) {
		status = readl(mac->regs + PANGO_MAC_REG_STATUS);
		job->status = status;
		job->error_code = (status & PANGO_MAC_ERROR_MASK) >>
				  PANGO_MAC_ERROR_SHIFT;
		if (status & PANGO_MAC_STATUS_ERROR)
			return -EIO;
		if (status & PANGO_MAC_STATUS_DONE)
			return 0;
		if (ktime_compare(ktime_get(), deadline) >= 0)
			return -ETIMEDOUT;
		cpu_relax();
		if (!(++polls & 0x3ff))
			cond_resched();
	}
}

static int pango_mac_conv_wait(struct pango_mac_dev *mac,
			       struct pango_mac_conv_job *job,
			       u32 done_bit, u32 error_bit)
{
	ktime_t deadline = ktime_add_us(ktime_get(), job->timeout_us ?
						job->timeout_us :
						PANGO_MAC_DEFAULT_TIMEOUT);
	u32 polls = 0;
	u32 status;

	for (;;) {
		status = readl(mac->regs + PANGO_MAC_CONV_STATUS);
		job->status = status;
		job->error_code = (status >> PANGO_MAC_CONV_ERROR_SHIFT) & 0xf;
		if (status & error_bit)
			return -EIO;
		if (status & done_bit)
			return 0;
		if (ktime_compare(ktime_get(), deadline) >= 0)
			return -ETIMEDOUT;
		cpu_relax();
		if (!(++polls & 0x3ff))
			cond_resched();
	}
}

static u32 pango_mac_conv_counter(struct pango_mac_dev *mac, u32 index)
{
	writel(index, mac->regs + PANGO_MAC_CONV_COUNTER_ID);
	return readl(mac->regs + PANGO_MAC_CONV_COUNTER);
}

static int pango_mac_run_conv(struct pango_mac_file *ctx,
			      struct pango_mac_conv_job *job)
{
	struct pango_mac_dev *mac = ctx->mac;
	struct pango_mac_conv_sizes sizes;
	u32 status;
	bool compute = job->abi_version == PANGO_MAC_CONV_COMPUTE_ABI_VERSION;
	u32 channel;
	int ret;

	ret = pango_mac_validate_conv_job(mac, job, &sizes);
	if (ret)
		return ret;
	ret = mutex_lock_interruptible(&mac->run_lock);
	if (ret)
		return ret;
	if (mac->stagea_supported &&
	    (readl(mac->regs + PANGO_MAC_STAGEA_BASE + 0x0c) & BIT(0))) {
		ret = -EBUSY;
		goto out_unlock;
	}
	status = readl(mac->regs + PANGO_MAC_CONV_VERSION);
	if (readl(mac->regs + PANGO_MAC_CONV_ID) != PANGO_MAC_CONV_HW_ID ||
	    (status != PANGO_MAC_CONV_HW_VERSION &&
	     status != PANGO_MAC_CONV_HW_COMPUTE_VERSION) ||
	    (compute && status != PANGO_MAC_CONV_HW_COMPUTE_VERSION)) {
		ret = -EOPNOTSUPP;
		goto out_unlock;
	}
	status = readl(mac->regs + PANGO_MAC_CONV_STATUS);
	if (status & (BIT(0) | BIT(3))) {
		job->status = status;
		ret = -EBUSY;
		goto out_unlock;
	}

	mac->resident_owner=NULL;
	pango_mac_copy_data(NULL, mac->scratch + job->input_offset,
		    ctx->shadow + job->input_offset, sizes.input);
	pango_mac_copy_data(NULL, mac->scratch + job->weight_offset,
		    ctx->shadow + job->weight_offset, sizes.weight);
	mb();

	writel(PANGO_MAC_CONV_CMD_CLEAR, mac->regs + PANGO_MAC_CONV_CONTROL);
	writel(((u32)job->height << 16) | job->width,
	       mac->regs + PANGO_MAC_CONV_DIMS);
	writel(((u32)job->padding << 24) | ((u32)job->stride << 20) |
	       ((u32)job->kernel << 16) | job->channels,
	       mac->regs + PANGO_MAC_CONV_CONFIG);
	writel(((u32)job->output_channels << 16) | job->channel_tile,
	       mac->regs + PANGO_MAC_CONV_TILE);
	writel((u32)mac->scratch_bus + job->input_offset,
	       mac->regs + PANGO_MAC_CONV_INPUT);
	writel((u32)mac->scratch_bus + job->weight_offset,
	       mac->regs + PANGO_MAC_CONV_WEIGHT);
	writel((u32)mac->scratch_bus + job->output_offset,
	       mac->regs + PANGO_MAC_CONV_OUTPUT);
	writel(job->weight_lines, mac->regs + PANGO_MAC_CONV_LINES);
	writel(job->model_id_lo, mac->regs + PANGO_MAC_CONV_MODEL_LO);
	writel(job->model_id_hi, mac->regs + PANGO_MAC_CONV_MODEL_HI);
	writel(job->generation, mac->regs + PANGO_MAC_CONV_GENERATION);
	if (compute)
		for (channel = 0; channel < job->output_channels; channel++) {
			u32 bias;
			u8 shift;

			memcpy(&bias, ctx->shadow + job->reserved[0] + 4 * channel, 4);
			shift = ctx->shadow[job->reserved[1] + channel];
			if (shift > 30) {
				ret = -EINVAL;
				goto out_unlock;
			}
			writel(0x20 + channel,
			       mac->regs + PANGO_MAC_CONV_COUNTER_ID);
			writel(bias, mac->regs + PANGO_MAC_CONV_COUNTER);
			writel(0x40 + channel,
			       mac->regs + PANGO_MAC_CONV_COUNTER_ID);
			writel(shift, mac->regs + PANGO_MAC_CONV_COUNTER);
		}
	wmb();
	writel(PANGO_MAC_CONV_CMD_LOAD, mac->regs + PANGO_MAC_CONV_CONTROL);
	ret = pango_mac_conv_wait(mac, job, PANGO_MAC_CONV_WT_DONE,
				  PANGO_MAC_CONV_WT_ERROR);
	if (ret)
		goto out_reset;
	writel(PANGO_MAC_CONV_CMD_ACT, mac->regs + PANGO_MAC_CONV_CONTROL);
	status = readl(mac->regs + PANGO_MAC_CONV_STATUS);
	if (!(status & PANGO_MAC_CONV_ACTIVE) ||
	    (status & PANGO_MAC_CONV_WT_ERROR)) {
		job->status = status;
		job->error_code = (status >> PANGO_MAC_CONV_ERROR_SHIFT) & 0xf;
		ret = -EIO;
		goto out_reset;
	}
	/* CLEAR drops sticky completion flags, but preserves the active bank. */
	writel(PANGO_MAC_CONV_CMD_CLEAR, mac->regs + PANGO_MAC_CONV_CONTROL);
	wmb();
	writel(compute ? PANGO_MAC_CONV_CMD_COMPUTE :
	       PANGO_MAC_CONV_CMD_INPUT, mac->regs + PANGO_MAC_CONV_CONTROL);
	ret = pango_mac_conv_wait(mac, job, compute ? PANGO_MAC_CONV_COMP_DONE :
				  PANGO_MAC_CONV_IN_DONE,
				  compute ? PANGO_MAC_CONV_COMP_ERROR :
				  PANGO_MAC_CONV_IN_ERROR);
	job->cycles = compute ? pango_mac_conv_counter(mac, 13) :
		readl(mac->regs + PANGO_MAC_CONV_CYCLES);
	job->input_ddr_bytes = pango_mac_conv_counter(mac, 0);
	job->weight_ddr_bytes = pango_mac_conv_counter(mac, 1);
	job->window_count = pango_mac_conv_counter(mac, 2);
	job->weight_reuse_count = pango_mac_conv_counter(mac, 3);
	job->stall_cycles = pango_mac_conv_counter(mac, 4);
	job->tap_xor = pango_mac_conv_counter(mac, 7);
	job->weight_digest = pango_mac_conv_counter(mac, 11);
	job->output_ddr_bytes = compute ? pango_mac_conv_counter(mac, 12) : 0;
	if (ret)
		goto out_reset;
	if (compute) {
		if (job->output_ddr_bytes != sizes.output) {
			ret = -EIO;
			goto out_reset;
		}
		pango_mac_copy_output(ctx->shadow + job->output_offset,
			      mac->scratch + job->output_offset, sizes.output);
	}
	goto out_unlock;

out_reset:
	writel(PANGO_MAC_CONV_CMD_ABORT, mac->regs + PANGO_MAC_CONV_CONTROL);
	mb();
	writel(PANGO_MAC_CONV_CMD_CLEAR, mac->regs + PANGO_MAC_CONV_CONTROL);
	mb();
out_unlock:
	mutex_unlock(&mac->run_lock);
	return ret;
}

static int pango_mac_register_model(struct pango_mac_file *ctx,
                                    const struct pango_mac_model *model)
{
    struct pango_mac_dev *mac=ctx->mac;
    u8 *snapshot;
    int ret;
    if (!pango_mac_model_valid(model,mac->scratch_bytes))
        return -EINVAL;
    ret=mutex_lock_interruptible(&mac->run_lock);
    if(ret) return ret;
    snapshot=kvmalloc(model->bytes,GFP_KERNEL);
    if(!snapshot) { ret=-ENOMEM; goto out; }
    pango_mac_copy_data(snapshot,NULL,ctx->shadow+model->offset,model->bytes);
    if(mac->resident_owner==ctx) mac->resident_owner=NULL;
    kvfree(ctx->model_snapshot);
    ctx->model_snapshot=snapshot;
    ctx->model_offset=model->offset;
    ctx->model_bytes=model->bytes;
    ret=0;
out:
    mutex_unlock(&mac->run_lock);
    return ret;
}

static void pango_mac_invalidate_range(struct pango_mac_dev *mac,u32 offset,u32 bytes)
{
    struct pango_mac_file *owner=mac->resident_owner;
    if(owner && pango_mac_ranges_overlap(owner->model_offset,owner->model_bytes,offset,bytes))
        mac->resident_owner=NULL;
}

static int pango_mac_run(struct pango_mac_file *ctx, struct pango_mac_job *job,
                         bool resident)
{
	struct pango_mac_dev *mac = ctx->mac;
	struct pango_mac_sizes sizes;
	u32 format;
	u32 status;
	int ret;

	ret = pango_mac_validate_job(mac, job, &sizes);
	if (ret)
		return ret;
	ret = mutex_lock_interruptible(&mac->run_lock);
	if (ret)
		return ret;
	if (mac->stagea_supported &&
	    (readl(mac->regs + PANGO_MAC_STAGEA_BASE + 0x0c) & BIT(0))) {
		ret = -EBUSY;
		goto out_unlock;
	}

    if(resident && (!ctx->model_snapshot || !pango_mac_resident_sources_valid(
        ctx->model_offset,ctx->model_bytes,job->weight_offset,sizes.weight,
        job->bias_offset,sizes.bias,job->input_offset,sizes.input,
        job->output_offset,sizes.output))) {
        ret=-EINVAL;goto out_unlock;
    }

	status = readl(mac->regs + PANGO_MAC_REG_STATUS);
	if (status & PANGO_MAC_STATUS_BUSY) {
		writel(PANGO_MAC_CONTROL_CLEAR, mac->regs + PANGO_MAC_REG_CONTROL);
		/* The reset must reach the device before BUSY is sampled again. */
		mb();
		status = readl(mac->regs + PANGO_MAC_REG_STATUS);
		if (status & PANGO_MAC_STATUS_BUSY) {
			job->status = status;
			ret = -EBUSY;
			goto out_unlock;
		}
	}

    if(resident) {
        if(mac->resident_owner!=ctx) {
            pango_mac_copy_data(NULL,mac->scratch+ctx->model_offset,ctx->model_snapshot,ctx->model_bytes);
            mac->resident_owner=ctx;
        }
    } else {
        mac->resident_owner=NULL;
        pango_mac_copy_data(NULL,mac->scratch+job->weight_offset,ctx->shadow+job->weight_offset,sizes.weight);
        if(!job->zero_bias)
            pango_mac_copy_data(NULL,mac->scratch+job->bias_offset,ctx->shadow+job->bias_offset,sizes.bias);
    }
    pango_mac_copy_data(NULL,mac->scratch+job->input_offset,ctx->shadow+job->input_offset,sizes.input);
	/* Publish all source data before programming and starting DMA. */
	mb();

	format = job->cout | ((u32)job->out_shift << 16) |
		 ((u32)job->output_format << 24) |
		 ((u32)job->activation << 26) |
		 ((u32)job->compute_mode << 28) |
		 (job->zero_bias ? PANGO_MAC_ZERO_BIAS : 0);
	writel(PANGO_MAC_CONTROL_CLEAR, mac->regs + PANGO_MAC_REG_CONTROL);
	writel(((u32)job->cin << 16) | job->pixels,
	       mac->regs + PANGO_MAC_REG_DIMS);
	writel(format, mac->regs + PANGO_MAC_REG_FORMAT);
	writel((u32)mac->scratch_bus + job->input_offset,
	       mac->regs + PANGO_MAC_REG_INPUT);
	writel((u32)mac->scratch_bus + job->weight_offset,
	       mac->regs + PANGO_MAC_REG_WEIGHT);
	writel((u32)mac->scratch_bus + job->bias_offset,
	       mac->regs + PANGO_MAC_REG_BIAS);
	writel((u32)mac->scratch_bus + job->output_offset,
	       mac->regs + PANGO_MAC_REG_OUTPUT);
	/* Complete descriptor writes before asserting START. */
	wmb();
	writel(PANGO_MAC_CONTROL_START, mac->regs + PANGO_MAC_REG_CONTROL);

	ret = pango_mac_wait(mac, job);
	job->cycles = readl(mac->regs + PANGO_MAC_REG_CYCLES);
	if (!ret) {
		/* DONE must be observed before copying device output to the shadow. */
		rmb();
		pango_mac_copy_output(ctx->shadow + job->output_offset,
			      mac->scratch + job->output_offset, sizes.output);
	} else {
        mac->resident_owner=NULL;
		writel(PANGO_MAC_CONTROL_CLEAR, mac->regs + PANGO_MAC_REG_CONTROL);
		/* Finish reset before another file can acquire run_lock. */
		mb();
	}

out_unlock:
	mutex_unlock(&mac->run_lock);
	return ret;
}

static int pango_mac_run_stagea(struct pango_mac_file *ctx,
				struct pango_mac_stagea_job *job)
{
	struct pango_mac_dev *mac = ctx->mac;
	u32 descriptors[256];
	void __iomem *regs = mac->regs + PANGO_MAC_STAGEA_BASE;
	ktime_t deadline;
	u32 polls = 0, i, status;
	int ret;

	if (!mac->stagea_supported)
		return -EOPNOTSUPP;
	if (!pango_mac_stagea_job_valid(job, mac->scratch_bytes))
		return -EINVAL;
	ret = mutex_lock_interruptible(&mac->run_lock);
	if (ret)
		return ret;
	/* A prior timed-out gather may still be draining its accepted burst.
	 * Block every scratch user until BUSY clears, without resetting AXI.
	 */
	if ((readl(regs + 0x0c) & BIT(0)) ||
	    (readl(mac->regs + PANGO_MAC_REG_STATUS) & PANGO_MAC_STATUS_BUSY) ||
	    (readl(mac->regs + PANGO_MAC_CONV_STATUS) & (BIT(0) | BIT(3)))) {
		ret = -EBUSY;
		goto out_unlock;
	}
	/* Snapshot the descriptors before validating and publishing them. */
	memcpy(descriptors, ctx->shadow + job->descriptor_offset, job->terms * 4);
	for (i = 0; i < job->terms; i++)
		if (!pango_mac_stagea_descriptor_valid(descriptors[i])) {
			ret = -EINVAL;
			goto out_unlock;
		}
    pango_mac_invalidate_range(mac,job->descriptor_offset,job->terms*4u);
    pango_mac_invalidate_range(mac,job->base_offset,2048u);
    pango_mac_invalidate_range(mac,job->output_offset,2048u);
	memcpy_toio(mac->scratch + job->descriptor_offset, descriptors, job->terms * 4);
	memcpy_toio(mac->scratch + job->base_offset,
		    ctx->shadow + job->base_offset, 2048);
	mb();
	writel(2, regs + 0x08);
	writel((u32)mac->scratch_bus + job->base_offset, regs + 0x10);
	writel((u32)mac->scratch_bus + job->descriptor_offset, regs + 0x14);
	writel((u32)mac->scratch_bus + job->output_offset, regs + 0x18);
	writel(job->terms, regs + 0x1c);
	wmb();
	writel(1, regs + 0x08);
	deadline = ktime_add_us(ktime_get(), job->timeout_us ?
				job->timeout_us : PANGO_MAC_DEFAULT_TIMEOUT);
	for (;;) {
		status = readl(regs + 0x0c);
		job->status = status;
		job->error_code = (status >> 8) & 0xf;
		if ((status & (BIT(0) | BIT(1))) == BIT(1)) {
			ret = (status & BIT(2)) ? -EIO : 0;
			break;
		}
		if (ktime_compare(ktime_get(), deadline) >= 0) {
			ret = -ETIMEDOUT;
			break;
		}
		cpu_relax();
		if (!(++polls & 0x3ff))
			cond_resched();
	}
	job->cycles = readl(regs + 0x20);
	if (!ret) {
		rmb();
		memcpy_fromio(ctx->shadow + job->output_offset,
			      mac->scratch + job->output_offset, 2048);
	}
out_unlock:
	mutex_unlock(&mac->run_lock);
	return ret;
}

static long pango_mac_ioctl(struct file *file, unsigned int cmd,
			    unsigned long arg)
{
	struct pango_mac_file *ctx = file->private_data;
	void __user *user = (void __user *)arg;

	if (_IOC_TYPE(cmd) != PANGO_MAC_IOC_MAGIC)
		return -ENOTTY;

	switch (cmd) {
	case PANGO_MAC_IOC_GET_INFO: {
		struct pango_mac_info info = {
			.abi_version = PANGO_MAC_ABI_VERSION,
			.device_id = readl(ctx->mac->regs + PANGO_MAC_REG_ID),
			.device_version = readl(ctx->mac->regs + PANGO_MAC_REG_VERSION),
			.scratch_bytes = ctx->mac->scratch_bytes,
			.features = PANGO_MAC_FEATURE_PRIVATE_SHADOW |
				    PANGO_MAC_FEATURE_SERIALIZED |
				    PANGO_MAC_FEATURE_POLLING | PANGO_MAC_FEATURE_RESIDENT_MODEL,
			.max_pixels = PANGO_MAC_MAX_PIXELS,
			.max_channels = PANGO_MAC_MAX_CHANNELS,
			.max_timeout_us = PANGO_MAC_MAX_TIMEOUT,
		};
		if (ctx->mac->stagea_supported)
			info.features |= PANGO_MAC_FEATURE_STAGEA_GATHER;
		if (readl(ctx->mac->regs + PANGO_MAC_CONV_ID) ==
						PANGO_MAC_CONV_HW_ID) {
			u32 conv_version = readl(ctx->mac->regs +
							  PANGO_MAC_CONV_VERSION);

			if (conv_version == PANGO_MAC_CONV_HW_VERSION ||
			    conv_version == PANGO_MAC_CONV_HW_COMPUTE_VERSION)
				info.features |= PANGO_MAC_FEATURE_CONV_WINDOW;
			if (conv_version == PANGO_MAC_CONV_HW_COMPUTE_VERSION)
				info.features |= PANGO_MAC_FEATURE_CONV_COMPUTE;
		}

		return copy_to_user(user, &info, sizeof(info)) ? -EFAULT : 0;
	}
	case PANGO_MAC_IOC_RUN_STAGEA: {
		struct pango_mac_stagea_job job;
		int ret;
		if (copy_from_user(&job, user, sizeof(job)))
			return -EFAULT;
		job.status = job.cycles = job.error_code = 0;
		ret = pango_mac_run_stagea(ctx, &job);
		if (copy_to_user(user, &job, sizeof(job)))
			return -EFAULT;
		return ret;
	}
    case PANGO_MAC_IOC_REGISTER_MODEL: {
        struct pango_mac_model model;
        if(copy_from_user(&model,user,sizeof(model))) return -EFAULT;
        return pango_mac_register_model(ctx,&model);
    }
    case PANGO_MAC_IOC_RUN_RESIDENT:
	case PANGO_MAC_IOC_RUN: {
		struct pango_mac_job job;
		int ret;

		if (copy_from_user(&job, user, sizeof(job)))
			return -EFAULT;
		job.cycles = 0;
		job.status = 0;
		job.error_code = 0;
		ret = pango_mac_run(ctx, &job, cmd==PANGO_MAC_IOC_RUN_RESIDENT);
		if (copy_to_user(user, &job, sizeof(job)))
			return -EFAULT;
		return ret;
	}
	case PANGO_MAC_IOC_RUN_CONV: {
		struct pango_mac_conv_job job;
		int ret;

		if (copy_from_user(&job, user, sizeof(job)))
			return -EFAULT;
		job.cycles = 0;
		job.input_ddr_bytes = 0;
		job.weight_ddr_bytes = 0;
		job.output_ddr_bytes = 0;
		job.window_count = 0;
		job.weight_reuse_count = 0;
		job.stall_cycles = 0;
		job.status = 0;
		job.error_code = 0;
		job.tap_xor = 0;
		job.weight_digest = 0;
		ret = pango_mac_run_conv(ctx, &job);
		if (copy_to_user(user, &job, sizeof(job)))
			return -EFAULT;
		return ret;
	}
	default:
		return -ENOTTY;
	}
}

static int pango_mac_open(struct inode *inode, struct file *file)
{
	struct miscdevice *misc = file->private_data;
	struct pango_mac_dev *mac = container_of(misc, struct pango_mac_dev, miscdev);
	struct pango_mac_file *ctx;
	unsigned int i;

	mutex_lock(&mac->pool_lock);
	for (i = 0; i < PANGO_MAC_POOL_CONTEXTS; ++i) {
		ctx = &mac->contexts[i];
		if (ctx->in_use)
			continue;
		ctx->in_use = true;
		/* Never expose bytes left by the previous owner of this slot. */
		memset(ctx->shadow, 0, mac->scratch_bytes);
		file->private_data = ctx;
		mutex_unlock(&mac->pool_lock);
		return 0;
	}
	mutex_unlock(&mac->pool_lock);
	return -EBUSY;
}

static int pango_mac_release(struct inode *inode, struct file *file)
{
	struct pango_mac_file *ctx = file->private_data;

    mutex_lock(&ctx->mac->run_lock);
    if(ctx->mac->resident_owner==ctx) ctx->mac->resident_owner=NULL;
    kvfree(ctx->model_snapshot);ctx->model_snapshot=NULL;ctx->model_bytes=0;
    mutex_unlock(&ctx->mac->run_lock);
	mutex_lock(&ctx->mac->pool_lock);
	ctx->in_use = false;
	mutex_unlock(&ctx->mac->pool_lock);
	return 0;
}

static int pango_mac_mmap(struct file *file, struct vm_area_struct *vma)
{
	struct pango_mac_file *ctx = file->private_data;
	size_t bytes = vma->vm_end - vma->vm_start;

	if (vma->vm_pgoff || !bytes || bytes > ctx->mac->scratch_bytes ||
	    !(vma->vm_flags & VM_SHARED) || (vma->vm_flags & VM_EXEC))
		return -EINVAL;
	vma->vm_flags |= VM_DONTEXPAND | VM_DONTDUMP | VM_PFNMAP;
	return remap_pfn_range(vma, vma->vm_start, page_to_pfn(ctx->pages),
			       bytes, vma->vm_page_prot);
}

static const struct file_operations pango_mac_fops = {
	.owner = THIS_MODULE,
	.open = pango_mac_open,
	.release = pango_mac_release,
	.unlocked_ioctl = pango_mac_ioctl,
	.mmap = pango_mac_mmap,
	.llseek = no_llseek,
};

static int pango_mac_probe(struct platform_device *pdev)
{
	struct device_node *memory_np;
	struct resource memory_res;
	struct pango_mac_dev *mac;
	u32 cpu_alias;
	u32 id;
	u32 version;
	int ret;
	unsigned int i;

	mac = devm_kzalloc(&pdev->dev, sizeof(*mac), GFP_KERNEL);
	if (!mac)
		return -ENOMEM;
	mac->dev = &pdev->dev;
	mac->regs = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(mac->regs))
		return PTR_ERR(mac->regs);

	memory_np = of_parse_phandle(pdev->dev.of_node, "memory-region", 0);
	if (!memory_np)
		return dev_err_probe(&pdev->dev, -EINVAL,
				     "missing memory-region\n");
	ret = of_address_to_resource(memory_np, 0, &memory_res);
	of_node_put(memory_np);
	if (ret)
		return dev_err_probe(&pdev->dev, ret,
				     "invalid memory-region\n");
	if (resource_size(&memory_res) > U32_MAX)
		return dev_err_probe(&pdev->dev, -E2BIG,
				     "scratch region exceeds ABI\n");
	ret = of_property_read_u32(pdev->dev.of_node, "pango,cpu-alias",
				   &cpu_alias);
	if (ret)
		return dev_err_probe(&pdev->dev, ret,
				     "missing pango,cpu-alias\n");

	mac->scratch = devm_ioremap(&pdev->dev, cpu_alias,
				    resource_size(&memory_res));
	if (!mac->scratch)
		return dev_err_probe(&pdev->dev, -ENOMEM,
				     "cannot map scratch alias\n");
	mac->scratch_bus = memory_res.start;
	mac->scratch_bytes = resource_size(&memory_res);
	if (mac->scratch_bus > U32_MAX ||
	    mac->scratch_bytes > U32_MAX - mac->scratch_bus ||
	    mac->scratch_bytes != 0x00100000u)
		return dev_err_probe(&pdev->dev, -EINVAL,
				     "unexpected scratch layout\n");

	id = readl(mac->regs + PANGO_MAC_REG_ID);
	version = readl(mac->regs + PANGO_MAC_REG_VERSION);
	if (id != PANGO_MAC_ID || version != PANGO_MAC_VERSION)
		return dev_err_probe(&pdev->dev, -ENODEV,
				     "ABI mismatch id=%08x version=%08x\n",
				     id, version);
	/* The new engine is optional. Older DTBs/images retain the original ABI.
	 * Enable it only when the fixed PFF1 range is explicitly reserved in DT.
	 */
	if (resource_size(platform_get_resource(pdev, IORESOURCE_MEM, 0)) >= 0x200) {
		memory_np = of_parse_phandle(pdev->dev.of_node, "memory-region", 1);
		if (memory_np) {
			ret = of_address_to_resource(memory_np, 0, &memory_res);
			of_node_put(memory_np);
			if (!ret && memory_res.start == 0x10000000 &&
			    resource_size(&memory_res) >= 68122688 &&
			    readl(mac->regs + PANGO_MAC_STAGEA_BASE) == PANGO_MAC_STAGEA_ID &&
			    readl(mac->regs + PANGO_MAC_STAGEA_BASE + 4) == PANGO_MAC_STAGEA_VERSION)
				mac->stagea_supported = true;
		}
	}

	mutex_init(&mac->run_lock);
	mutex_init(&mac->pool_lock);
	mac->contexts = devm_kcalloc(&pdev->dev, PANGO_MAC_POOL_CONTEXTS,
				     sizeof(*mac->contexts), GFP_KERNEL);
	if (!mac->contexts)
		return -ENOMEM;
	for (i = 0; i < PANGO_MAC_POOL_CONTEXTS; ++i) {
		mac->contexts[i].mac = mac;
		mac->contexts[i].pages = alloc_pages(GFP_KERNEL | __GFP_ZERO,
					     get_order(mac->scratch_bytes));
		mac->contexts[i].shadow = mac->contexts[i].pages ?
			page_address(mac->contexts[i].pages) : NULL;
		if (!mac->contexts[i].shadow) {
			ret = -ENOMEM;
			goto free_contexts;
		}
	}
	mac->miscdev.minor = MISC_DYNAMIC_MINOR;
	mac->miscdev.name = "pango-mac0";
	mac->miscdev.fops = &pango_mac_fops;
	mac->miscdev.parent = &pdev->dev;
	mac->miscdev.mode = 0600;
	ret = misc_register(&mac->miscdev);
	if (ret)
		goto free_contexts;

	platform_set_drvdata(pdev, mac);
	dev_info(&pdev->dev,
		 "dense MAC scheduler ready: /dev/%s, %u private contexts of %zu bytes\n",
		 mac->miscdev.name, PANGO_MAC_POOL_CONTEXTS, mac->scratch_bytes);
	return 0;

free_contexts:
	for (i = 0; i < PANGO_MAC_POOL_CONTEXTS; ++i)
		if (mac->contexts[i].pages)
			__free_pages(mac->contexts[i].pages,
				     get_order(mac->scratch_bytes));
	return dev_err_probe(&pdev->dev, ret,
			     "cannot allocate/register private contexts\n");
}

static int pango_mac_remove(struct platform_device *pdev)
{
	struct pango_mac_dev *mac = platform_get_drvdata(pdev);
	unsigned int i;

	misc_deregister(&mac->miscdev);
	for (i = 0; i < PANGO_MAC_POOL_CONTEXTS; ++i) {
        kvfree(mac->contexts[i].model_snapshot);
		__free_pages(mac->contexts[i].pages,
			     get_order(mac->scratch_bytes));
    }
	return 0;
}

static const struct of_device_id pango_mac_of_match[] = {
	{ .compatible = "pango,mac-accel-v2" },
	{ }
};
MODULE_DEVICE_TABLE(of, pango_mac_of_match);

static struct platform_driver pango_mac_driver = {
	.probe = pango_mac_probe,
	.remove = pango_mac_remove,
	.driver = {
		.name = "pango-mac",
		.of_match_table = pango_mac_of_match,
	},
};
module_platform_driver(pango_mac_driver);

MODULE_DESCRIPTION("Pango dense MAC v2 serialized scheduler");
MODULE_AUTHOR("SoC V2 project");
MODULE_LICENSE("GPL");
