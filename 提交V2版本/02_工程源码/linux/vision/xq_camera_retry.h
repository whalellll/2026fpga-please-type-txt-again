#ifndef XQ_CAMERA_RETRY_H
#define XQ_CAMERA_RETRY_H
#include "xq_camera.h"
/* Startup recovery only. Retry SCCB NACK after a confirmed drain/reset;
 * never mask DDR/frame errors, cancellation, or an unsafe stop. Successful
 * return keeps the sensor running. Deadline excludes the final safe drain
 * (it has its own 2 s bound). Observer runs once per attempt, not per poll. */
typedef void (*xqc_start_observer)(void *, unsigned, int, uint32_t);
int xqc_start_retry(xqc_camera *, unsigned total_ms, unsigned max_attempts,
                    xqc_start_observer, void *);
/* One user capture request: no attempt/time cap, but every hardware wait is
 * bounded and poll can cancel. Confirm new publications before HOLD; publish
 * only the verified RAM copy. ID/mode/DDR/argument/unsafe-drain errors fail.
 * Caller owns the camera for the complete operation. */
int xqc_capture_until_ready(xqc_camera *, uint32_t *, size_t, xqv_frame *,
                           xqc_start_observer, void *);
#endif
