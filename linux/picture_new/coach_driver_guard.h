#ifndef XQCOACH_DRIVER_GUARD_H
#define XQCOACH_DRIVER_GUARD_H
/* Single-threaded coach worker only. No reset: a timeout with unproven DMA
 * drain must never be erased by a new request. The parent must recover it. */
int xqcoach_driver_quiescent(void);
#endif
