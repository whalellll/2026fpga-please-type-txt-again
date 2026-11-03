#ifndef XQ_MAC_H
#define XQ_MAC_H
#include <stddef.h>
#include <stdint.h>
#include "pango_mac_uapi.h"
/* Frozen SoC compact bank: ceil(cin/4)*ceil(cout/32) <= 64 for S8.
 * GET_INFO's independent channel maxima do not describe this joint limit. */
#define XQM_WEIGHT_BANK_LINES 64u
/* One file/context owns ordinary RAM shadow. No /dev/mem fallback exists.
 * A transport is not reentrant: callers serialize pack/submit/collect and
 * close for the whole matrix call, or open one context per worker. The ROI
 * pipeline itself rejects concurrent runs on the same pipeline context.
 */
typedef struct {
    uint8_t *shadow;
    size_t bytes;
    void *context;
    int (*submit)(void *,struct pango_mac_job *); /* 1=success; bounded by driver */
    int (*cancelled)(void *);
} xqm_transport;
typedef struct { uint64_t jobs,cycles; } xqm_stats;
/* A: row-major M*K signed bytes. B: output-major N*K signed bytes.
 * Every K segment is unshifted I32. Sum in I64, add bias exactly once,
 * reject I32 overflow; quantization/activation are deliberately absent.
 * Output is row-major M*N I32; undefined on error, never publish on failure.
 * Input/weights/bias/output live outside shadow; output cannot alias sources.
 */
int xqm_matrix(const xqm_transport *,const int8_t *a,size_t a_bytes,
               const int8_t *b,size_t b_bytes,const int32_t *bias,size_t bias_count,
               unsigned m,unsigned k,unsigned n,int32_t *output,size_t output_values,
               xqm_stats *);
typedef struct {
    int fd;xqm_transport io;
    unsigned features,conv_enabled;
    unsigned parameter_sequence;
    uint64_t parameter_upload_bytes,parameter_saved_bytes;
    void *resident_cache;
    void (*resident_free)(void *);
} xqm_linux;
int xqm_linux_open(xqm_linux *);
void xqv_parameters_begin(const xqm_transport *,struct pango_vision32_job *);
int xqv_exact_available(const xqm_transport *);
void xqm_linux_close(xqm_linux *);
#endif
