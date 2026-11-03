#ifndef XQVOICE_ACCEL_H
#define XQVOICE_ACCEL_H
#include "pango_voice_uapi.h"
#include "xqvoice_model.h"
#define XQVOICE_ACCEL_HISTORY 224u
typedef struct {
    int fd;
    struct pango_voice_stream pending;
    unsigned level_index;
    uint32_t last_end,last_sequence,last_feature_end,overflows,discontinuities;
    struct pango_voice_feature history[XQVOICE_ACCEL_HISTORY];
} xqvoice_accel_t;
int xqvoice_accel_open(xqvoice_accel_t *,const char *,const xqvoice_model_t *);
int xqvoice_accel_level(xqvoice_accel_t *,uint32_t *,uint32_t *);
void xqvoice_accel_close(xqvoice_accel_t *);
size_t xqvoice_accel_features(const xqvoice_accel_t *,uint32_t,uint32_t,int8_t *,size_t);
int xqvoice_accel_infer(xqvoice_accel_t *,const int8_t *,size_t,uint8_t *,uint16_t *);
/* Also used by the host packet/gap tests; no device access. */
int xqvoice_accel_accept(xqvoice_accel_t *,const struct pango_voice_stream *);
#endif
