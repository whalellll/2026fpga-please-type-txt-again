#ifndef XQ_HWC_DETECTOR_ADAPTER_H
#define XQ_HWC_DETECTOR_ADAPTER_H
#include "xq_mac.h"
typedef struct xi8_model xqih_detector;
/* Only the checked frozen r14 detector/XQINT81 pair is accepted. Caller has
 * already validated the source pack CRC; the derived pack is SHA-bound here. */
xqih_detector *xqih_open(const char *source_pack,const uint32_t source_header[10]);
void xqih_close(xqih_detector *);
/* Input is the existing normalized NCHW boundary; only three final detection
 * heads leave the integer HWC graph as F32. No CPU convolution fallback. */
int xqih_detect(xqih_detector *,const xqm_transport *,const float *,
                float *output[3],xqm_stats *);
#endif
