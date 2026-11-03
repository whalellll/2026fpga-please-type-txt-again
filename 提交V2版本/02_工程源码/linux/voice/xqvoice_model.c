#include "xqvoice_model.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define XQVOICE_MODEL_HEADER_BYTES 128u
#define XQVOICE_MODEL_MAX_BYTES (1024u * 1024u)
#define XQVOICE_MODEL_MODE_TOKEN 1u

static void set_error(char *output, size_t output_bytes, const char *message)
{
    if (output && output_bytes)
        (void)snprintf(output, output_bytes, "%s", message);
}

static uint32_t read_le32(const uint8_t *input)
{
    return (uint32_t)input[0] | ((uint32_t)input[1] << 8) |
           ((uint32_t)input[2] << 16) | ((uint32_t)input[3] << 24);
}

static int32_t read_le32s(const uint8_t *input)
{
    return (int32_t)read_le32(input);
}

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

static int add_product(size_t *value, size_t left, size_t right)
{
    size_t product;
    if (left && right > SIZE_MAX / left)
        return 0;
    product = left * right;
    if (*value > SIZE_MAX - product)
        return 0;
    *value += product;
    return 1;
}

int xqvoice_model_load(const char *path, xqvoice_model_t *model,
                       char *error, size_t error_bytes)
{
    uint8_t header[XQVOICE_MODEL_HEADER_BYTES];
    uint32_t payload_crc;
    uint32_t expected_crc;
    uint32_t total_bytes;
    size_t expected = XQVOICE_MODEL_HEADER_BYTES;
    size_t offset;
    long length;
    FILE *input;

    if (!path || !model) {
        set_error(error, error_bytes, "bad model arguments");
        return 0;
    }
    memset(model, 0, sizeof(*model));
    input = fopen(path, "rb");
    if (!input) {
        set_error(error, error_bytes, "cannot open model");
        return 0;
    }
    if (fseek(input, 0, SEEK_END) != 0 || (length = ftell(input)) < 0 ||
        fseek(input, 0, SEEK_SET) != 0 ||
        (unsigned long)length < XQVOICE_MODEL_HEADER_BYTES ||
        (unsigned long)length > XQVOICE_MODEL_MAX_BYTES ||
        fread(header, 1, sizeof(header), input) != sizeof(header)) {
        fclose(input);
        set_error(error, error_bytes, "bad model length/header");
        return 0;
    }
    total_bytes = read_le32(header + 12);
    if (memcmp(header, "XQT1", 4) != 0 ||
        read_le32(header + 4) != XQVOICE_MODEL_VERSION ||
        read_le32(header + 8) != XQVOICE_MODEL_HEADER_BYTES ||
        total_bytes != (uint32_t)length || read_le32(header + 20) != 16000u ||
        read_le32(header + 24) != XQVOICE_FEATURE_BINS ||
        read_le32(header + 28) != XQVOICE_POOL_STATS ||
        read_le32(header + 40) != XQVOICE_MODEL_CLASSES ||
        read_le32(header + 64) != XQVOICE_MODEL_MODE_TOKEN) {
        fclose(input);
        set_error(error, error_bytes, "unsupported XQT1 model contract");
        return 0;
    }
    model->hidden1 = read_le32(header + 32);
    model->hidden2 = read_le32(header + 36);
    if (!model->hidden1 || model->hidden1 > 256u ||
        !model->hidden2 || model->hidden2 > 256u ||
        read_le32(header + 52) > 30u || read_le32(header + 56) > 30u ||
        read_le32(header + 60) > 30u ||
        !add_product(&expected, model->hidden1, XQVOICE_MODEL_INPUTS) ||
        !add_product(&expected, model->hidden1, 4u) ||
        !add_product(&expected, model->hidden2, model->hidden1) ||
        !add_product(&expected, model->hidden2, 4u) ||
        !add_product(&expected, XQVOICE_MODEL_CLASSES, model->hidden2) ||
        !add_product(&expected, XQVOICE_MODEL_CLASSES, 4u) ||
        expected != (size_t)length) {
        fclose(input);
        set_error(error, error_bytes, "bad XQT1 dimensions/length");
        return 0;
    }
    model->image = (uint8_t *)malloc((size_t)length);
    if (!model->image) {
        fclose(input);
        set_error(error, error_bytes, "out of memory");
        return 0;
    }
    memcpy(model->image, header, sizeof(header));
    if (fread(model->image + sizeof(header), 1,
              (size_t)length - sizeof(header), input) !=
        (size_t)length - sizeof(header) || fclose(input) != 0) {
        xqvoice_model_unload(model);
        set_error(error, error_bytes, "truncated model payload");
        return 0;
    }
    expected_crc = read_le32(header + 16);
    payload_crc = crc32_bytes(model->image + XQVOICE_MODEL_HEADER_BYTES,
                              (size_t)length - XQVOICE_MODEL_HEADER_BYTES);
    if (payload_crc != expected_crc) {
        xqvoice_model_unload(model);
        set_error(error, error_bytes, "model payload CRC mismatch");
        return 0;
    }
    model->image_bytes = (size_t)length;
    model->feature_offset_q8 = read_le32s(header + 44);
    model->feature_scale_q15 = read_le32s(header + 48);
    model->shift1 = (uint8_t)read_le32(header + 52);
    model->shift2 = (uint8_t)read_le32(header + 56);
    model->shift3 = (uint8_t)read_le32(header + 60);
    offset = XQVOICE_MODEL_HEADER_BYTES;
    model->weight1 = (const int8_t *)(model->image + offset);
    offset += model->hidden1 * XQVOICE_MODEL_INPUTS;
    model->bias1 = model->image + offset;
    offset += model->hidden1 * 4u;
    model->weight2 = (const int8_t *)(model->image + offset);
    offset += model->hidden2 * model->hidden1;
    model->bias2 = model->image + offset;
    offset += model->hidden2 * 4u;
    model->weight3 = (const int8_t *)(model->image + offset);
    offset += XQVOICE_MODEL_CLASSES * model->hidden2;
    model->bias3 = model->image + offset;
    set_error(error, error_bytes, "ok");
    return 1;
}

void xqvoice_model_unload(xqvoice_model_t *model)
{
    if (!model)
        return;
    free(model->image);
    memset(model, 0, sizeof(*model));
}

static int8_t requantize(int64_t value, uint8_t shift, int relu)
{
    int64_t rounded;
    if (shift) {
        int64_t mask = ((int64_t)1 << shift) - 1;
        rounded = value >= 0 ? value >> shift : -(((-value) + mask) >> shift);
    } else {
        rounded = value;
    }
    if (relu && rounded < 0)
        rounded = 0;
    if (rounded > 127)
        rounded = 127;
    if (rounded < -128)
        rounded = -128;
    return (int8_t)rounded;
}

static void dense(const int8_t *input, uint32_t inputs,
                  const int8_t *weights, const uint8_t *biases,
                  uint32_t outputs, uint8_t shift, int relu, int8_t *output)
{
    uint32_t out;
    for (out = 0; out < outputs; ++out) {
        int64_t accumulator = read_le32s(biases + out * 4u);
        uint32_t in;
        for (in = 0; in < inputs; ++in)
            accumulator += (int32_t)input[in] * weights[out * inputs + in];
        output[out] = requantize(accumulator, shift, relu);
    }
}

int xqvoice_model_infer_token(const xqvoice_model_t *model,
                              const int8_t *features, size_t frames,
                              uint8_t *token, uint16_t *confidence_permille,
                              char *error, size_t error_bytes)
{
    int64_t sums[XQVOICE_FEATURE_BINS] = {0};
    int8_t pooled[XQVOICE_MODEL_INPUTS];
    int8_t hidden1[256];
    int8_t hidden2[256];
    int8_t logits[XQVOICE_MODEL_CLASSES];
    unsigned int bin;
    size_t frame;
    uint8_t best = 0;
    int best_value = -129;
    int second_value = -129;

    if (!model || !model->image || !features || !frames ||
        frames > XQVOICE_MAX_FRAMES || !token || !confidence_permille) {
        set_error(error, error_bytes, "bad inference arguments");
        return 0;
    }
    for (bin = 0; bin < XQVOICE_FEATURE_BINS; ++bin)
        pooled[XQVOICE_FEATURE_BINS + bin] = -128;
    for (frame = 0; frame < frames; ++frame) {
        for (bin = 0; bin < XQVOICE_FEATURE_BINS; ++bin) {
            int8_t value = features[frame * XQVOICE_FEATURE_BINS + bin];
            sums[bin] += value;
            if (value > pooled[XQVOICE_FEATURE_BINS + bin])
                pooled[XQVOICE_FEATURE_BINS + bin] = value;
        }
    }
    for (bin = 0; bin < XQVOICE_FEATURE_BINS; ++bin)
        pooled[bin] = (int8_t)(sums[bin] / (int64_t)frames);
    dense(pooled, XQVOICE_MODEL_INPUTS, model->weight1, model->bias1,
          model->hidden1, model->shift1, 1, hidden1);
    dense(hidden1, model->hidden1, model->weight2, model->bias2,
          model->hidden2, model->shift2, 1, hidden2);
    dense(hidden2, model->hidden2, model->weight3, model->bias3,
          XQVOICE_MODEL_CLASSES, model->shift3, 0, logits);
    for (bin = 0; bin < XQVOICE_MODEL_CLASSES; ++bin) {
        int value = logits[bin];
        if (value > best_value) {
            second_value = best_value;
            best_value = value;
            best = (uint8_t)bin;
        } else if (value > second_value) {
            second_value = value;
        }
    }
    if (!best) {
        set_error(error, error_bytes, "classifier selected blank");
        return 0;
    }
    *token = best;
    *confidence_permille = (uint16_t)((best_value - second_value) * 1000u / 255u);
    set_error(error, error_bytes, "ok");
    return 1;
}
