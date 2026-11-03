#include "xqvoice_features.h"

#include <limits.h>

static const int16_t goertzel_coefficients_q14[XQVOICE_FEATURE_BINS] = {
    32729, 32679, 32610, 32522, 32413, 32138, 31786, 31357, 30853, 30274,
    28899, 27246, 25330, 23170, 18205, 12540, 6393, 0, -12540, -23170
};

static int32_t approximate_log2_q8(uint64_t value)
{
    unsigned int bit = 0;
    uint64_t normalized;

    if (!value)
        return 0;
    {
        uint64_t copy = value;
        while (copy >>= 1)
            ++bit;
    }
    normalized = value << (63u - bit);
    return (int32_t)(bit * 256u + ((normalized >> 55) & 0xffu));
}

static int8_t normalize_feature(int32_t log_energy,
                                const xqvoice_model_t *model)
{
    int64_t scaled = (int64_t)(log_energy - model->feature_offset_q8) *
                     model->feature_scale_q15;
    int64_t value = scaled >= 0 ? (scaled + 16384) >> 15 :
                    -(((-scaled) + 16384) >> 15);

    if (value > 127)
        value = 127;
    if (value < -128)
        value = -128;
    return (int8_t)value;
}

size_t xqvoice_extract_features(const int16_t *samples, size_t sample_count,
                                const xqvoice_model_t *model,
                                int8_t *features, size_t feature_bytes)
{
    int16_t filtered[XQVOICE_WINDOW_SAMPLES];
    size_t frames;
    size_t frame;

    if (!samples || !model || !features || sample_count < XQVOICE_WINDOW_SAMPLES)
        return 0;
    frames = 1u + (sample_count - XQVOICE_WINDOW_SAMPLES) /
                  XQVOICE_HOP_SAMPLES;
    if (frames > XQVOICE_MAX_FRAMES ||
        feature_bytes < frames * XQVOICE_FEATURE_BINS)
        return 0;

    for (frame = 0; frame < frames; ++frame) {
        const int16_t *window = samples + frame * XQVOICE_HOP_SAMPLES;
        int32_t previous = 0;
        unsigned int sample;
        unsigned int bin;

        for (sample = 0; sample < XQVOICE_WINDOW_SAMPLES; ++sample) {
            int32_t current = window[sample];
            int32_t emphasized = current - ((31785 * previous) >> 15);
            previous = current;
            emphasized >>= 4;
            if (emphasized > INT16_MAX)
                emphasized = INT16_MAX;
            if (emphasized < INT16_MIN)
                emphasized = INT16_MIN;
            filtered[sample] = (int16_t)emphasized;
        }
        for (bin = 0; bin < XQVOICE_FEATURE_BINS; ++bin) {
            int32_t state1 = 0;
            int32_t state2 = 0;
            int32_t coefficient = goertzel_coefficients_q14[bin];
            int64_t energy;

            for (sample = 0; sample < XQVOICE_WINDOW_SAMPLES; ++sample) {
                int32_t state = filtered[sample] +
                    (int32_t)(((int64_t)coefficient * state1) >> 14) - state2;
                state2 = state1;
                state1 = state;
            }
            energy = (int64_t)state1 * state1 + (int64_t)state2 * state2 -
                     (((int64_t)coefficient * state1 * state2) >> 14);
            if (energy < 1)
                energy = 1;
            features[frame * XQVOICE_FEATURE_BINS + bin] =
                normalize_feature(approximate_log2_q8((uint64_t)energy),
                                  model);
        }
    }
    return frames;
}
