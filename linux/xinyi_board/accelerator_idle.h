#ifndef XINYI_ACCELERATOR_IDLE_H
#define XINYI_ACCELERATOR_IDLE_H
#include <stdint.h>
typedef struct { int fd; volatile uint32_t *regs; } xy_accelerator;
/* Read-only fixed-address probe. No reset, abort, scratch or control writes.
 * Reaping a child alone cannot prove an ioctl timeout has drained DMA. */
int xy_accelerator_open(xy_accelerator *);
int xy_accelerator_idle(const xy_accelerator *);
void xy_accelerator_close(xy_accelerator *);
int xy_accelerator_words_idle(const volatile uint32_t *);
#endif
