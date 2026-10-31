/* Offline-only hook: save EXACT original-daemon VAD segments before features. */
#include "xqvoice_features.h"
#include <stdio.h>
#include <stdlib.h>

size_t pilot_capture_features(const int16_t *samples, size_t count,
                              const xqvoice_model_t *model,
                              int8_t *features, size_t bytes)
{
    static unsigned int sequence;
    const char *prefix = getenv("XQVOICE_SEGMENT_PREFIX");
    char path[1024];
    FILE *output;
    if (!prefix || snprintf(path, sizeof(path), "%s-%03u.pcm", prefix, sequence++) >= (int)sizeof(path))
        exit(30);
    output = fopen(path, "wb");
    if (!output || fwrite(samples, sizeof(samples[0]), count, output) != count) exit(31);
    if (fclose(output)) exit(32);
    printf("OFFLINE_EXACT_VAD_SEGMENT samples=%zu\n", count);
    return xqvoice_extract_features(samples, count, model, features, bytes);
}
