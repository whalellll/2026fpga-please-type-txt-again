#ifndef MAC_ACCEL_KERNEL_H
#define MAC_ACCEL_KERNEL_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MAC_KERNEL_REG_ID             0x00u
#define MAC_KERNEL_REG_VERSION        0x04u
#define MAC_KERNEL_REG_CONTROL        0x08u
#define MAC_KERNEL_REG_STATUS         0x0cu
#define MAC_KERNEL_REG_CFG_DIMS       0x10u
#define MAC_KERNEL_REG_CFG_FORMAT     0x14u
#define MAC_KERNEL_REG_INPUT_SRC      0x18u
#define MAC_KERNEL_REG_WEIGHT_SRC     0x1cu
#define MAC_KERNEL_REG_BIAS_SRC       0x20u
#define MAC_KERNEL_REG_OUTPUT_DST     0x24u
#define MAC_KERNEL_REG_CYCLES         0x28u
#define MAC_KERNEL_REG_COMPLETED      0x2cu
#define MAC_KERNEL_REG_CAP0           0x30u
#define MAC_KERNEL_REG_CAP1           0x34u
#define MAC_KERNEL_REG_LINE_COUNTS    0x38u
#define MAC_KERNEL_REG_IO_COUNTS      0x3cu
#define MAC_KERNEL_REG_CAP2           0x40u

#define MAC_KERNEL_CONTROL_START      (1u << 0)
#define MAC_KERNEL_CONTROL_CLEAR      (1u << 1)
#define MAC_KERNEL_CONTROL_IRQ_ENABLE (1u << 8)

#define MAC_KERNEL_STATUS_BUSY        (1u << 0)
#define MAC_KERNEL_STATUS_DONE        (1u << 1)
#define MAC_KERNEL_STATUS_ERROR       (1u << 2)
#define MAC_KERNEL_STATUS_CORE_BUSY   (1u << 3)
#define MAC_KERNEL_STATUS_CORE_DONE   (1u << 4)
#define MAC_KERNEL_STATUS_ERROR_SHIFT 12u
#define MAC_KERNEL_STATUS_ERROR_MASK  (0x0fu << MAC_KERNEL_STATUS_ERROR_SHIFT)
#define MAC_KERNEL_STATUS_STATE_SHIFT 19u
#define MAC_KERNEL_STATUS_STATE_MASK  (0x1fu << MAC_KERNEL_STATUS_STATE_SHIFT)

#define MAC_KERNEL_ID                 0x4d41434bu
#define MAC_KERNEL_VERSION            0x00020100u
#define MAC_KERNEL_FORMAT_ZERO_BIAS   (1u << 30)
#define MAC_KERNEL_PCI                4u
#define MAC_KERNEL_PCO                16u
#define MAC_KERNEL_PACKED_LANES       32u
#define MAC_KERNEL_MAX_PIXELS         16u
#define MAC_KERNEL_MAX_CHANNELS       256u
#define MAC_KERNEL_MAX_BURST_BEATS    8u

typedef enum {
    MAC_KERNEL_MODE_S16_S16 = 0,
    MAC_KERNEL_MODE_S8_S8 = 1,
    MAC_KERNEL_MODE_U8_S8 = 2,
    MAC_KERNEL_MODE_U8_FP8_E4M3 = 3
} mac_kernel_compute_mode_t;

typedef enum {
    MAC_KERNEL_ACT_NONE = 0,
    MAC_KERNEL_ACT_RELU = 1,
    MAC_KERNEL_ACT_CLIPPED_RELU = 2,
    MAC_KERNEL_ACT_SQR_CLIPPED_RELU = 3
} mac_kernel_activation_t;

typedef enum {
    MAC_KERNEL_OUT_S8 = 0,
    MAC_KERNEL_OUT_U8 = 1,
    MAC_KERNEL_OUT_S16 = 2,
    MAC_KERNEL_OUT_I32 = 3
} mac_kernel_output_format_t;

typedef struct {
    uint16_t pixels;
    uint16_t cin;
    uint16_t cout;
    uint8_t out_shift;
    uint8_t compute_mode;
    uint8_t activation;
    uint8_t output_format;
    uint8_t irq_enable;
    uint8_t zero_bias;
    uint32_t input_addr;
    uint32_t weight_addr;
    uint32_t bias_addr;
    uint32_t output_addr;
} mac_kernel_job_t;

typedef struct {
    size_t input_bytes;
    size_t weight_bytes;
    size_t bias_bytes;
    size_t output_bytes;
} mac_kernel_buffer_sizes_t;

enum {
    MAC_KERNEL_OK = 0,
    MAC_KERNEL_ERR_ARGUMENT = -1,
    MAC_KERNEL_ERR_BUSY = -2,
    MAC_KERNEL_ERR_HARDWARE = -3,
    MAC_KERNEL_ERR_TIMEOUT = -4
};

uint32_t mac_kernel_read(uintptr_t base, uint32_t offset);
void mac_kernel_write(uintptr_t base, uint32_t offset, uint32_t value);

int mac_kernel_validate_job(const mac_kernel_job_t *job);
mac_kernel_buffer_sizes_t mac_kernel_buffer_sizes(
    const mac_kernel_job_t *job);
int mac_kernel_submit(uintptr_t base, const mac_kernel_job_t *job);
int mac_kernel_poll(uintptr_t base);
int mac_kernel_wait(uintptr_t base, uint32_t max_polls);
void mac_kernel_clear(uintptr_t base, int irq_enable);
uint32_t mac_kernel_cycles(uintptr_t base);
uint32_t mac_kernel_error_code(uintptr_t base);

#ifdef __cplusplus
}
#endif

#endif
