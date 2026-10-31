#ifndef PICTURE_GRAPH_PROFILE_H
#define PICTURE_GRAPH_PROFILE_H
#include <stdint.h>
/* Bounded, in-memory counters. No per-element clock calls or logging.
 * Submit includes the mock's CPU dot product on host/QEMU. Kernel copies and
 * hardware waits cannot be separated by this userspace instrument. */
enum xqg_phase {
    XQG_QUANTIZE, XQG_DEQUANTIZE, XQG_REQUANTIZE,
    XQG_FP32_3, XQG_FP32_4, XQG_FP32_5, XQG_FP32_6, XQG_FP32_7,
    XQG_FP32_8, XQG_FP32_9, XQG_FP32_10, XQG_FP32_11,
    XQG_WEIGHT_LAYOUT, XQG_INPUT_LAYOUT, XQG_OUTPUT_LAYOUT_REQUANT,
    XQG_STAGING_ZERO, XQG_SUBMIT, XQG_INTEGER_GAP, XQG_PHASES
};
typedef struct { uint64_t wall, cpu; } xqg_mark;
typedef struct {
    uint64_t wall[XQG_PHASES], cpu[XQG_PHASES];
    uint64_t calls[XQG_PHASES], values[XQG_PHASES];
    uint64_t clock_failures;
} xqg_profile;
#ifdef XQ_GRAPH_PROFILE
void xqg_profile_reset(void);
void xqg_profile_read(xqg_profile *);
xqg_mark xqg_begin(void);
void xqg_end(enum xqg_phase, xqg_mark, uint64_t);
void xqg_profile_report(unsigned model,int okay,xqg_mark start);
#else
static inline xqg_mark xqg_begin(void) { xqg_mark m={0,0};return m; }
static inline void xqg_end(enum xqg_phase p,xqg_mark m,uint64_t n)
{ (void)p;(void)m;(void)n; }
#endif
#endif
