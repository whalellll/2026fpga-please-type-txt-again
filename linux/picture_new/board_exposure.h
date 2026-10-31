#ifndef XQ_BOARD_EXPOSURE_H
#define XQ_BOARD_EXPOSURE_H
#include <stddef.h>
#include <stdint.h>
#ifndef XQ_EXPOSURE_RETRY_R29
#define XQ_EXPOSURE_RETRY_R29 0
#endif
#if XQ_EXPOSURE_RETRY_R29 != 0 && XQ_EXPOSURE_RETRY_R29 != 1
#error XQ_EXPOSURE_RETRY_R29_must_be_zero_or_one
#endif
#if XQ_EXPOSURE_RETRY_R29
/* Worker-local, serial request processing only. Every request resets to160. */
void xqex_set_target(unsigned target);
#endif

/* Software photometric candidate. It changes neither the camera frame nor
 * the model/geometry contracts. Coordinates only select exposure samples;
 * they are not accepted as a board by this module. */
typedef struct {
    unsigned median, gain_q10, samples;
} xqex_plan;

int xqex_plan_rgb(const uint8_t *rgb, size_t bytes, const float corners[8],
                  xqex_plan *out);
int xqex_apply_rgb(uint8_t *rgb, size_t bytes, const xqex_plan *plan,
                   int (*cancel)(void *), void *context);
#endif
