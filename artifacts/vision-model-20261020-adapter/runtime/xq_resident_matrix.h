#ifndef XQ_RESIDENT_MATRIX_H
#define XQ_RESIDENT_MATRIX_H
#include "xq_mac.h"
typedef struct {const int8_t *weight;unsigned k,n;} xqn_resident_layer;
/* Optional counter-only instrumentation for one single-threaded native worker.
 * ioctl_ns includes driver copies, waiting and hardware busy; it is not additive
 * with job cycles. No tensor observer, hashes or per-job logging is installed. */
typedef struct {
    unsigned enabled,clock_failures;
    uint64_t ioctl_ns,calls,runs,registrations,errors,cycles;
} xqn_resident_profile;
void xqn_resident_profile_reset(void);
void xqn_resident_profile_read(xqn_resident_profile *);
/* Pin a complete immutable model in one fd snapshot. Other clients may evict
 * physical scratch; RUN_RESIDENT restores it under the driver's mutex. */
int xqn_resident_prepare(const xqm_transport *,const xqn_resident_layer *,unsigned);
/* Pointwise NCHW input gathered directly into the per-job IN shadow slot.
 * first is a batch/spatial row; no intermediate im2col buffer or copy. */
int xqn_resident_pointwise(const xqm_transport *,const int8_t *,size_t,const int8_t *,size_t,
                          const int32_t *,size_t,unsigned,unsigned,unsigned,unsigned,unsigned,
                          int32_t *,size_t,xqm_stats *);
#endif
