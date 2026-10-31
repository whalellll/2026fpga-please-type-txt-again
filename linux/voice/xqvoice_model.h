#ifndef XQVOICE_MODEL_H
#define XQVOICE_MODEL_H

#include <stddef.h>
#include <stdint.h>

#define XQVOICE_MODEL_VERSION 1u
#define XQVOICE_MODEL_CLASSES 25u
#define XQVOICE_FEATURE_BINS 20u
#define XQVOICE_POOL_STATS 2u
#define XQVOICE_MODEL_INPUTS (XQVOICE_FEATURE_BINS * XQVOICE_POOL_STATS)
#define XQVOICE_MAX_FRAMES 200u

typedef struct {
    uint8_t *image;
    size_t image_bytes;
    uint32_t hidden1;
    uint32_t hidden2;
    int32_t feature_offset_q8;
    int32_t feature_scale_q15;
    uint8_t shift1;
    uint8_t shift2;
    uint8_t shift3;
    const int8_t *weight1;
    const uint8_t *bias1;
    const int8_t *weight2;
    const uint8_t *bias2;
    const int8_t *weight3;
    const uint8_t *bias3;
} xqvoice_model_t;

int xqvoice_model_load(const char *path, xqvoice_model_t *model,
                       char *error, size_t error_bytes);
void xqvoice_model_unload(xqvoice_model_t *model);
int xqvoice_model_infer_token(const xqvoice_model_t *model,
                              const int8_t *features, size_t frames,
                              uint8_t *token, uint16_t *confidence_permille,
                              char *error, size_t error_bytes);

#endif
