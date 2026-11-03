/* Offline file inference probe for experimental pilot model validation. */
#include "xqvoice_features.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    xqvoice_model_t model;
    unsigned char bytes[XQVOICE_MAX_SAMPLES * 2u + 2u];
    int16_t samples[XQVOICE_MAX_SAMPLES];
    int8_t features[XQVOICE_MAX_FRAMES * XQVOICE_FEATURE_BINS];
    size_t count, i, frames;
    uint8_t token;
    uint16_t score;
    char error[128];
    FILE *input, *output;
    if (argc != 4) return 2;
    if (!xqvoice_model_load(argv[1], &model, error, sizeof(error))) {
        fprintf(stderr, "%s\n", error); return 3;
    }
    input = fopen(argv[2], "rb");
    if (!input) return 4;
    count = fread(bytes, 1, sizeof(bytes), input);
    if (ferror(input) || count < 800 || count > XQVOICE_MAX_SAMPLES * 2u || (count & 1u)) return 5;
    fclose(input);
    for (i = 0; i < count / 2u; ++i)
        samples[i] = (int16_t)((uint16_t)bytes[i * 2u] | ((uint16_t)bytes[i * 2u + 1u] << 8));
    frames = xqvoice_extract_features(samples, count / 2u, &model, features, sizeof(features));
    if (!frames || !xqvoice_model_infer_token(&model, features, frames,
                                             &token, &score, error, sizeof(error))) return 6;
    output = fopen(argv[3], "wb");
    if (!output || fwrite(features, XQVOICE_FEATURE_BINS, frames, output) != frames) return 7;
    if (fclose(output)) return 8;
    printf("{\"token\":%u,\"score\":%u,\"frames\":%zu}\n", token, score, frames);
    xqvoice_model_unload(&model);
    return 0;
}
