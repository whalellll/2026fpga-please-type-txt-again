#ifndef XQVOICE_FEATURES_H
#define XQVOICE_FEATURES_H

#include <stddef.h>
#include <stdint.h>

#include "xqvoice_model.h"

#define XQVOICE_WINDOW_SAMPLES 400u
#define XQVOICE_HOP_SAMPLES 160u
#define XQVOICE_MAX_SAMPLES \
    (XQVOICE_WINDOW_SAMPLES + (XQVOICE_MAX_FRAMES - 1u) * XQVOICE_HOP_SAMPLES)

size_t xqvoice_extract_features(const int16_t *samples, size_t sample_count,
                                const xqvoice_model_t *model,
                                int8_t *features, size_t feature_bytes);

#endif
