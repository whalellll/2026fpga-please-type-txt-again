#define _POSIX_C_SOURCE 200809L

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "xqvoice_features.h"
#include "xqvoice_model.h"

#define HEADER_BYTES 128u
#define INPUTS XQVOICE_MODEL_INPUTS
#define PAYLOAD_BYTES (INPUTS + 4u + 1u + 4u + 25u + 100u)

static uint32_t crc32_bytes(const uint8_t *data, size_t bytes)
{
    uint32_t crc = 0xffffffffu;
    size_t index;
    for (index = 0; index < bytes; ++index) {
        unsigned int bit;
        crc ^= data[index];
        for (bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

static void put_u32(uint8_t *output, uint32_t value)
{
    output[0] = (uint8_t)value;
    output[1] = (uint8_t)(value >> 8);
    output[2] = (uint8_t)(value >> 16);
    output[3] = (uint8_t)(value >> 24);
}

static int write_test_model(const char *path, int corrupt)
{
    uint8_t image[HEADER_BYTES + PAYLOAD_BYTES];
    uint8_t *payload = image + HEADER_BYTES;
    FILE *output;

    memset(image, 0, sizeof(image));
    memcpy(image, "XQT1", 4);
    put_u32(image + 4, 1);
    put_u32(image + 8, HEADER_BYTES);
    put_u32(image + 12, sizeof(image));
    put_u32(image + 20, 16000);
    put_u32(image + 24, 20);
    put_u32(image + 28, XQVOICE_POOL_STATS);
    put_u32(image + 32, 1);
    put_u32(image + 36, 1);
    put_u32(image + 40, 25);
    put_u32(image + 44, 0);
    put_u32(image + 48, 32768);
    put_u32(image + 64, 1);
    put_u32(payload + INPUTS + 4u + 1u + 4u + 25u + 22u * 4u, 100);
    put_u32(image + 16, crc32_bytes(payload, PAYLOAD_BYTES));
    if (corrupt)
        payload[0] ^= 1u;
    output = fopen(path, "wb");
    if (!output)
        return 0;
    if (fwrite(image, 1, sizeof(image), output) != sizeof(image)) {
        fclose(output);
        return 0;
    }
    return fclose(output) == 0;
}

int main(void)
{
    char path[] = "/tmp/xqvoice-model-XXXXXX";
    char error[128];
    xqvoice_model_t model;
    uint8_t token = 0;
    uint16_t confidence = 0;
    int16_t samples[560] = {0};
    int8_t features[40];
    int fd = mkstemp(path);
    size_t frames;

    if (fd < 0)
        return 1;
    close(fd);
    if (!write_test_model(path, 0) ||
        !xqvoice_model_load(path, &model, error, sizeof(error))) {
        fprintf(stderr, "XQVOICE_MODEL_FAIL load=%s\n", error);
        unlink(path);
        return 1;
    }
    frames = xqvoice_extract_features(samples, 560, &model, features,
                                      sizeof(features));
    if (frames != 2 || !xqvoice_model_infer_token(
                            &model, features, frames, &token, &confidence,
                            error, sizeof(error)) || token != 22) {
        fprintf(stderr, "XQVOICE_MODEL_FAIL inference=%s frames=%u\n", error,
                (unsigned int)frames);
        xqvoice_model_unload(&model);
        unlink(path);
        return 1;
    }
    xqvoice_model_unload(&model);
    if (!write_test_model(path, 1) ||
        xqvoice_model_load(path, &model, error, sizeof(error))) {
        fprintf(stderr, "XQVOICE_MODEL_FAIL corrupt model accepted\n");
        xqvoice_model_unload(&model);
        unlink(path);
        return 1;
    }
    unlink(path);
    puts("XQVOICE_MODEL_PASS cpu=int8 token-mlp=3 pool=mean-max crc=reject");
    return 0;
}
