#ifndef XIANGQI_SPARSE_EVAL_H
#define XIANGQI_SPARSE_EVAL_H

#include <stdint.h>

#define XQ_SPARSE_ID                    0x58515345u
#define XQ_SPARSE_VERSION               0x00010000u
#define XQ_SPARSE_SCORE_DIVISOR         66064384u
#define XQ_SPARSE_MAX_CHILDREN          16u
#define XQ_SPARSE_INVALID_ROW           0xffffffffu

#define XQ_SPARSE_REG_ID                0x80u
#define XQ_SPARSE_REG_VERSION           0x84u
#define XQ_SPARSE_REG_CONTROL           0x88u
#define XQ_SPARSE_REG_STATUS            0x8cu
#define XQ_SPARSE_REG_CHILD_COUNT       0x90u
#define XQ_SPARSE_REG_MODEL_BASE        0x94u
#define XQ_SPARSE_REG_PARENT_BASE       0x98u
#define XQ_SPARSE_REG_OUTPUT_WEIGHT     0x9cu
#define XQ_SPARSE_REG_DESCRIPTOR        0xa0u
#define XQ_SPARSE_REG_BIAS_LO           0xa4u
#define XQ_SPARSE_REG_BIAS_HI           0xa8u
#define XQ_SPARSE_REG_CYCLES            0xacu
#define XQ_SPARSE_REG_COMPLETED         0xb0u
#define XQ_SPARSE_REG_MODEL_ROWS        0xb4u
#define XQ_SPARSE_REG_DIVISOR           0xb8u
#define XQ_SPARSE_REG_RESULT(n)         (0xc0u + ((n) * 4u))

#define XQ_SPARSE_CONTROL_START         (1u << 0)
#define XQ_SPARSE_CONTROL_CLEAR         (1u << 1)
#define XQ_SPARSE_CONTROL_IRQ_ENABLE    (1u << 8)
#define XQ_SPARSE_STATUS_BUSY           (1u << 0)
#define XQ_SPARSE_STATUS_DONE           (1u << 1)
#define XQ_SPARSE_STATUS_ERROR          (1u << 2)
#define XQ_SPARSE_STATUS_ERROR_SHIFT    16u
#define XQ_SPARSE_STATUS_ERROR_MASK     0x000f0000u

#define XQ_SPARSE_ERR_NONE              0u
#define XQ_SPARSE_ERR_CONFIG            1u
#define XQ_SPARSE_ERR_DDR_RANGE         2u
#define XQ_SPARSE_ERR_DDR_READ          3u
#define XQ_SPARSE_ERR_ROW_ID            4u

// Each descriptor is exactly one aligned eight-word AXI burst.
typedef struct {
    uint32_t child_side;
    uint32_t red_remove_from;
    uint32_t red_add_to;
    uint32_t red_remove_capture;
    uint32_t black_remove_from;
    uint32_t black_add_to;
    uint32_t black_remove_capture;
    uint32_t reserved;
} xq_sparse_descriptor_t;

static inline void xq_sparse_write(uint32_t base, uint32_t offset,
                                   uint32_t value)
{
    *(volatile uint32_t *)(base + offset) = value;
}

static inline uint32_t xq_sparse_read(uint32_t base, uint32_t offset)
{
    return *(volatile uint32_t *)(base + offset);
}

static inline uint32_t xq_sparse_error_code(uint32_t status)
{
    return (status & XQ_SPARSE_STATUS_ERROR_MASK) >>
           XQ_SPARSE_STATUS_ERROR_SHIFT;
}

#endif
