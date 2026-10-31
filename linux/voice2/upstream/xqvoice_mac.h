#ifndef XQV_MAC_H
#define XQV_MAC_H
#include <stdint.h>
int xqvoice_mac_open(void);
void xqvoice_mac_close(void);
/* Explicit immutable layer snapshot. Existing dense callers remain legacy.
 * Call once before the layer's jobs; weights must stay immutable in that layer.
 * Resident mode uses the existing driver feature, never a CPU fallback. */
int xqvoice_mac_prepare_layer(const uint8_t *weights,unsigned K,unsigned cout,unsigned job_count);
unsigned long long xqvoice_mac_resident_jobs(void);
int xqvoice_mac_dense(const uint8_t *input,const uint8_t *weights,unsigned pixels,unsigned K,unsigned cout,int32_t *accum);
/* Optional small-CNN extension. Legacy backends remain link-compatible. */
int xqvoice_mac_quant_available(void) __attribute__((weak));
int xqvoice_mac_prepare_quant(const int32_t *bias,const int32_t *multiplier,const unsigned *shift,
                             unsigned cout,int32_t lo,int32_t hi) __attribute__((weak));
int xqvoice_mac_dense_quant(const uint8_t *input,const uint8_t *weights,unsigned pixels,unsigned K,
                           unsigned cout,int32_t *quant) __attribute__((weak));
unsigned long long xqvoice_mac_jobs(void);
unsigned long long xqvoice_mac_cycles(void);
#endif
