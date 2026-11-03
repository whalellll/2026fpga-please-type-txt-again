#ifndef XY_SIGNAL_TEST_CONTROL_H
#define XY_SIGNAL_TEST_CONTROL_H
#include "runtime.h"
/* Explicit RAM test harness only; never linked by the SD product builder.
 * USR1=start, USR2=one Space, HUP=Esc. Signals carry no board/frame data. */
int xy_signal_test_attach(void);
void xy_signal_test_poll(xy_runtime *);
#endif
