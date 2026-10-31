#include "mac_accel_kernel.h"

static uint32_t pack_dims(const mac_kernel_job_t *job)
{
    return ((uint32_t)job->cin << 16) | job->pixels;
}

static uint32_t pack_format(const mac_kernel_job_t *job)
{
    return (uint32_t)job->cout |
           ((uint32_t)job->out_shift << 16) |
           ((uint32_t)(job->output_format & 3u) << 24) |
           ((uint32_t)(job->activation & 3u) << 26) |
           ((uint32_t)(job->compute_mode & 3u) << 28) |
           (job->zero_bias != 0u ? MAC_KERNEL_FORMAT_ZERO_BIAS : 0u);
}

static uint32_t cin_tiles(uint16_t cin)
{
    return ((uint32_t)cin + 3u) / 4u;
}

static uint32_t cout_tiles(uint16_t cout, uint8_t mode)
{
    uint32_t step = mode == MAC_KERNEL_MODE_S16_S16 ? 16u : 32u;
    return ((uint32_t)cout + step - 1u) / step;
}

uint32_t mac_kernel_read(uintptr_t base, uint32_t offset)
{
    return *(volatile uint32_t *)(base + offset);
}

void mac_kernel_write(uintptr_t base, uint32_t offset, uint32_t value)
{
    *(volatile uint32_t *)(base + offset) = value;
}

int mac_kernel_validate_job(const mac_kernel_job_t *job)
{
    if (job == NULL)
        return MAC_KERNEL_ERR_ARGUMENT;
    if (job->pixels == 0u || job->pixels > MAC_KERNEL_MAX_PIXELS ||
        job->cin == 0u || job->cin > MAC_KERNEL_MAX_CHANNELS ||
        job->cout == 0u || job->cout > MAC_KERNEL_MAX_CHANNELS)
        return MAC_KERNEL_ERR_ARGUMENT;
    if (job->compute_mode > MAC_KERNEL_MODE_U8_FP8_E4M3 ||
        job->activation > MAC_KERNEL_ACT_SQR_CLIPPED_RELU ||
        job->output_format > MAC_KERNEL_OUT_I32)
        return MAC_KERNEL_ERR_ARGUMENT;
    if (((job->input_addr | job->weight_addr | job->bias_addr |
          job->output_addr) & 3u) != 0u)
        return MAC_KERNEL_ERR_ARGUMENT;
    return MAC_KERNEL_OK;
}

mac_kernel_buffer_sizes_t mac_kernel_buffer_sizes(
    const mac_kernel_job_t *job)
{
    mac_kernel_buffer_sizes_t sizes = {0u, 0u, 0u, 0u};
    uint32_t ci;
    uint32_t co;

    if (mac_kernel_validate_job(job) != MAC_KERNEL_OK)
        return sizes;

    ci = cin_tiles(job->cin);
    co = cout_tiles(job->cout, job->compute_mode);
    sizes.input_bytes = (size_t)job->pixels * ci * 8u;
    sizes.weight_bytes = (size_t)co * ci * 128u;
    sizes.bias_bytes = job->zero_bias != 0u ? 0u : (size_t)co * 192u;
    sizes.output_bytes = (size_t)job->pixels * job->cout * 4u;
    return sizes;
}

void mac_kernel_clear(uintptr_t base, int irq_enable)
{
    uint32_t control = MAC_KERNEL_CONTROL_CLEAR;
    if (irq_enable)
        control |= MAC_KERNEL_CONTROL_IRQ_ENABLE;
    mac_kernel_write(base, MAC_KERNEL_REG_CONTROL, control);
}

int mac_kernel_submit(uintptr_t base, const mac_kernel_job_t *job)
{
    uint32_t status;
    uint32_t control;
    int result = mac_kernel_validate_job(job);

    if (result != MAC_KERNEL_OK)
        return result;

    status = mac_kernel_read(base, MAC_KERNEL_REG_STATUS);
    if ((status & MAC_KERNEL_STATUS_BUSY) != 0u)
        return MAC_KERNEL_ERR_BUSY;

    mac_kernel_clear(base, job->irq_enable != 0u);
    mac_kernel_write(base, MAC_KERNEL_REG_CFG_DIMS, pack_dims(job));
    mac_kernel_write(base, MAC_KERNEL_REG_CFG_FORMAT, pack_format(job));
    mac_kernel_write(base, MAC_KERNEL_REG_INPUT_SRC, job->input_addr);
    mac_kernel_write(base, MAC_KERNEL_REG_WEIGHT_SRC, job->weight_addr);
    mac_kernel_write(base, MAC_KERNEL_REG_BIAS_SRC, job->bias_addr);
    mac_kernel_write(base, MAC_KERNEL_REG_OUTPUT_DST, job->output_addr);

    control = MAC_KERNEL_CONTROL_START;
    if (job->irq_enable != 0u)
        control |= MAC_KERNEL_CONTROL_IRQ_ENABLE;
    mac_kernel_write(base, MAC_KERNEL_REG_CONTROL, control);

    status = mac_kernel_read(base, MAC_KERNEL_REG_STATUS);
    if ((status & MAC_KERNEL_STATUS_ERROR) != 0u)
        return MAC_KERNEL_ERR_HARDWARE;
    return MAC_KERNEL_OK;
}

int mac_kernel_poll(uintptr_t base)
{
    uint32_t status = mac_kernel_read(base, MAC_KERNEL_REG_STATUS);
    if ((status & MAC_KERNEL_STATUS_ERROR) != 0u)
        return MAC_KERNEL_ERR_HARDWARE;
    if ((status & MAC_KERNEL_STATUS_DONE) != 0u)
        return MAC_KERNEL_OK;
    return MAC_KERNEL_ERR_BUSY;
}

int mac_kernel_wait(uintptr_t base, uint32_t max_polls)
{
    uint32_t poll;
    for (poll = 0u; poll < max_polls; ++poll) {
        int result = mac_kernel_poll(base);
        if (result != MAC_KERNEL_ERR_BUSY)
            return result;
    }
    return MAC_KERNEL_ERR_TIMEOUT;
}

uint32_t mac_kernel_cycles(uintptr_t base)
{
    return mac_kernel_read(base, MAC_KERNEL_REG_CYCLES);
}

uint32_t mac_kernel_error_code(uintptr_t base)
{
    uint32_t status = mac_kernel_read(base, MAC_KERNEL_REG_STATUS);
    return (status & MAC_KERNEL_STATUS_ERROR_MASK) >>
           MAC_KERNEL_STATUS_ERROR_SHIFT;
}
