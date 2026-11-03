#ifndef XQV_DECODE_H
#define XQV_DECODE_H
#include <stdint.h>
int xqvoice_decode(const int32_t *logits_q8,unsigned frames,char text[32]);
#endif
