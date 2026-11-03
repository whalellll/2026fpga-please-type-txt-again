#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "pango_mac_uapi.h"

#define INPUT_OFFSET  0x0000u
#define WEIGHT_OFFSET 0x1000u
#define OUTPUT_OFFSET 0x3000u
#define BIAS_OFFSET   0x4000u
#define SHIFT_OFFSET  0x4040u
#define INPUT_BYTES   196u
#define WEIGHT_BYTES  3456u
#define OUTPUT_BYTES  144u

struct shape_case {
	const char *name;
	unsigned width, height, kernel, stride, padding, seed;
};

static const struct shape_case extra_cases[] = {
	{"pointwise", 5, 4, 1, 1, 0, 17},
	{"three_by_three", 5, 5, 3, 2, 1, 53},
};

static int8_t signed_byte(uint8_t value)
{
	return value < 128 ? (int8_t)value : (int8_t)((int)value - 256);
}

static uint8_t requant(int32_t value, unsigned shift)
{
	int64_t magnitude = value < 0 ? -(int64_t)value : value;
	int64_t rounded = (magnitude + (1LL << (shift - 1))) >> shift;

	if (value < 0)
		rounded = -rounded;
	if (rounded > 127)
		return 127;
	if (rounded < -128)
		return 128;
	return (uint8_t)rounded;
}

static void fill_case(uint8_t *input, uint8_t *weight,
		      int32_t *bias, uint8_t *shift, uint8_t *expected)
{
	unsigned i, oc, scalar, oy, ox, ky, kx, ci;

	for (i = 0; i < INPUT_BYTES; ++i)
		input[i] = (uint8_t)(i * 29u + (i / 7u) * 13u + 34u);
	memset(weight, 0, WEIGHT_BYTES);
	for (oc = 0; oc < 16; ++oc) {
		bias[oc] = (int32_t)oc * 13 - 50;
		shift[oc] = (uint8_t)(oc % 4 + 2);
		for (scalar = 0; scalar < 108; ++scalar) {
			unsigned tap = scalar / 3;
			unsigned channel = scalar % 3;
			unsigned logical = ((oc * 3 + channel) * 6 + tap / 6) * 6 + tap % 6;
			int w = (int)((logical * 11u + (logical / 108u) * 3u) & 15u) - 8;

			weight[(scalar / 4) * 128 + oc * 4 + scalar % 4] =
				(uint8_t)w;
		}
	}
	for (oy = 0; oy < 3; ++oy)
		for (ox = 0; ox < 3; ++ox)
			for (oc = 0; oc < 16; ++oc) {
				int32_t sum = bias[oc];

				for (ky = 0; ky < 6; ++ky)
					for (kx = 0; kx < 6; ++kx)
						for (ci = 0; ci < 3; ++ci) {
							int x = (int)(ox * 2 + kx) - 2;
							int y = (int)(oy * 2 + ky) - 2;
							unsigned scalar_id = (ky * 6 + kx) * 3 + ci;
							int a = x < 0 || x >= 7 || y < 0 || y >= 7 ? 0 :
								signed_byte(input[(y * 7 + x) * 4 + ci]);
							int w = signed_byte(weight[(scalar_id / 4) * 128 +
								oc * 4 + scalar_id % 4]);

							sum += a * w;
						}
				expected[(oy * 3 + ox) * 16 + oc] =
					requant(sum, shift[oc]);
			}
}

static uint32_t crc32_bytes(const uint8_t *data, unsigned bytes)
{
	uint32_t crc = 0xffffffffu;
	unsigned i, bit;

	for (i = 0; i < bytes; ++i) {
		crc ^= data[i];
		for (bit = 0; bit < 8; ++bit)
			crc = (crc >> 1) ^ ((crc & 1u) ? 0xedb88320u : 0u);
	}
	return ~crc;
}

static unsigned fill_shape_case(const struct shape_case *shape,
		uint8_t *input, uint8_t *weight, int32_t *bias,
		uint8_t *shift, uint8_t *expected)
{
	unsigned input_bytes = shape->width * shape->height * 4u;
	unsigned lines = (3u * shape->kernel * shape->kernel + 3u) / 4u;
	unsigned out_width = (shape->width + 2u * shape->padding -
			      shape->kernel) / shape->stride + 1u;
	unsigned out_height = (shape->height + 2u * shape->padding -
			       shape->kernel) / shape->stride + 1u;
	unsigned i, scalar, oc, oy, ox, ky, kx, ci;

	for (i = 0; i < input_bytes; ++i)
		input[i] = (uint8_t)((int)((i * 7u + (i / 11u) * 3u +
					shape->seed) % 15u) - 7);
	memset(weight, 0, lines * 128u);
	for (oc = 0; oc < 16; ++oc) {
		bias[oc] = (int32_t)oc * 3 - 20 + (int32_t)(shape->seed / 3u);
		shift[oc] = (uint8_t)(2u + oc % 4u);
		for (scalar = 0; scalar < 3u * shape->kernel * shape->kernel;
		     ++scalar)
			weight[(scalar / 4u) * 128u + oc * 4u + scalar % 4u] =
				(uint8_t)((int)((scalar * 5u + oc * 3u +
					shape->seed) % 11u) - 5);
	}
	for (oy = 0; oy < out_height; ++oy)
		for (ox = 0; ox < out_width; ++ox)
			for (oc = 0; oc < 16; ++oc) {
				int32_t sum = bias[oc];

				for (ky = 0; ky < shape->kernel; ++ky)
					for (kx = 0; kx < shape->kernel; ++kx)
						for (ci = 0; ci < 3; ++ci) {
							int x = (int)(ox * shape->stride + kx) -
								(int)shape->padding;
							int y = (int)(oy * shape->stride + ky) -
								(int)shape->padding;
							unsigned index =
								(ky * shape->kernel + kx) * 3u + ci;
							int a = x < 0 || x >= (int)shape->width ||
								y < 0 || y >= (int)shape->height ? 0 :
								signed_byte(input[(y * shape->width + x) *
										 4u + ci]);
							int w = signed_byte(weight[(index / 4u) * 128u +
									oc * 4u + index % 4u]);

							sum += a * w;
						}
				expected[(oy * out_width + ox) * 16u + oc] =
					requant(sum, shift[oc]);
			}
	return out_width * out_height * 16u;
}

static int run_shape_case(const struct shape_case *shape, int fd,
			  uint8_t *shadow, int oracle_only)
{
	uint8_t input[100], weight[896], expected[320], shift[16];
	int32_t bias[16];
	struct pango_mac_conv_job job = {0};
	unsigned bytes, input_bytes, weight_bytes, windows, i;

	bytes = fill_shape_case(shape, input, weight, bias, shift, expected);
	if (oracle_only) {
		printf("PANGO_MAC_CONV_ORACLE_PASS case=%s bytes=%u crc32=%08x\n",
		       shape->name, bytes, crc32_bytes(expected, bytes));
		return 0;
	}
	input_bytes = shape->width * shape->height * 4u;
	weight_bytes = ((3u * shape->kernel * shape->kernel + 3u) / 4u) *
		128u;
	windows = (bytes / 16u) * shape->kernel * shape->kernel;
	memcpy(shadow + INPUT_OFFSET, input, input_bytes);
	memcpy(shadow + WEIGHT_OFFSET, weight, weight_bytes);
	memcpy(shadow + BIAS_OFFSET, bias, sizeof(bias));
	memcpy(shadow + SHIFT_OFFSET, shift, sizeof(shift));
	memset(shadow + OUTPUT_OFFSET, 0xa5, bytes);
	job.abi_version = PANGO_MAC_CONV_COMPUTE_ABI_VERSION;
	job.flags = PANGO_MAC_CONV_FLAG_COMPUTE;
	job.model_id_lo = 0x4d434f4e;
	job.generation = shape->seed;
	job.input_offset = INPUT_OFFSET;
	job.weight_offset = WEIGHT_OFFSET;
	job.output_offset = OUTPUT_OFFSET;
	job.width = shape->width;
	job.height = shape->height;
	job.channels = 3;
	job.output_channels = 16;
	job.kernel = shape->kernel;
	job.stride = shape->stride;
	job.padding = shape->padding;
	job.weight_lines = weight_bytes / 128u;
	job.timeout_us = 1000000;
	job.reserved[0] = BIAS_OFFSET;
	job.reserved[1] = SHIFT_OFFSET;
	if (ioctl(fd, PANGO_MAC_IOC_RUN_CONV, &job)) {
		fprintf(stderr, "%s ioctl failed errno=%d status=%08x error=%u\n",
			shape->name, errno, job.status, job.error_code);
		return 1;
	}
	for (i = 0; i < bytes; ++i)
		if (shadow[OUTPUT_OFFSET + i] != expected[i]) {
			fprintf(stderr, "%s mismatch byte=%u actual=%02x expected=%02x\n",
				shape->name, i, shadow[OUTPUT_OFFSET + i],
				expected[i]);
			return 1;
		}
	if (job.input_ddr_bytes != input_bytes ||
	    job.weight_ddr_bytes != weight_bytes ||
	    job.output_ddr_bytes != bytes || job.window_count != windows ||
	    job.weight_reuse_count != bytes / 16u || !job.cycles) {
		fprintf(stderr, "%s counter mismatch in=%u weight=%u out=%u windows=%u reuse=%u cycles=%u\n",
			shape->name, job.input_ddr_bytes, job.weight_ddr_bytes,
			job.output_ddr_bytes, job.window_count,
			job.weight_reuse_count, job.cycles);
		return 1;
	}
	printf("PANGO_MAC_CONV_SHAPE_BOARD_PASS case=%s bytes=%u crc32=%08x input=%u weight=%u windows=%u cycles=%u\n",
	       shape->name, bytes, crc32_bytes(expected, bytes),
	       job.input_ddr_bytes, job.weight_ddr_bytes,
	       job.window_count, job.cycles);
	return 0;
}

int main(int argc, char **argv)
{
	uint8_t input[INPUT_BYTES], weight[WEIGHT_BYTES], shift[16];
	uint8_t expected[OUTPUT_BYTES], *shadow;
	int32_t bias[16];
	struct pango_mac_conv_job job = {0};
	struct pango_mac_info info = {0};
	unsigned i;
	int fd;

	fill_case(input, weight, bias, shift, expected);
	if (argc == 2 && !strcmp(argv[1], "--oracle-shapes")) {
		for (i = 0; i < sizeof(extra_cases) / sizeof(extra_cases[0]); ++i)
			if (run_shape_case(&extra_cases[i], -1, NULL, 1))
				return 2;
		return 0;
	}
	if (argc == 2 && !strcmp(argv[1], "--oracle-only")) {
		FILE *file = fopen("sim/vectors/yolo_compute_first_kernel_expected.hex", "r");
		unsigned value;

		if (!file) return 2;
		for (i = 0; i < OUTPUT_BYTES; ++i)
			if (fscanf(file, "%x", &value) != 1 || value != expected[i]) {
				fprintf(stderr, "CPU oracle mismatch byte=%u\n", i);
				return 2;
			}
		fclose(file);
		puts("PANGO_MAC_CONV_COMPUTE_ORACLE_PASS bytes=144");
		return 0;
	}
	fd = open("/dev/pango-mac0", O_RDWR);
	if (fd < 0 || ioctl(fd, PANGO_MAC_IOC_GET_INFO, &info) ||
	    !(info.features & PANGO_MAC_FEATURE_CONV_COMPUTE)) {
		fprintf(stderr, "compute device unavailable errno=%d\n", errno);
		return 2;
	}
	shadow = mmap(NULL, info.scratch_bytes, PROT_READ | PROT_WRITE,
		      MAP_SHARED, fd, 0);
	if (shadow == MAP_FAILED) {
		perror("mmap");
		return 2;
	}
	memcpy(shadow + INPUT_OFFSET, input, INPUT_BYTES);
	memcpy(shadow + WEIGHT_OFFSET, weight, WEIGHT_BYTES);
	memcpy(shadow + BIAS_OFFSET, bias, sizeof(bias));
	memcpy(shadow + SHIFT_OFFSET, shift, sizeof(shift));
	memset(shadow + OUTPUT_OFFSET, 0xa5, OUTPUT_BYTES);
	job.abi_version = PANGO_MAC_CONV_COMPUTE_ABI_VERSION;
	job.flags = PANGO_MAC_CONV_FLAG_COMPUTE;
	job.model_id_lo = 0x4d434f4e;
	job.generation = 1;
	job.input_offset = INPUT_OFFSET;
	job.weight_offset = WEIGHT_OFFSET;
	job.output_offset = OUTPUT_OFFSET;
	job.width = 7;
	job.height = 7;
	job.channels = 3;
	job.output_channels = 16;
	job.kernel = 6;
	job.stride = 2;
	job.padding = 2;
	job.weight_lines = 27;
	job.timeout_us = 1000000;
	job.reserved[0] = BIAS_OFFSET;
	job.reserved[1] = SHIFT_OFFSET;
	if (ioctl(fd, PANGO_MAC_IOC_RUN_CONV, &job)) {
		fprintf(stderr, "compute ioctl failed errno=%d status=%08x error=%u\n",
			errno, job.status, job.error_code);
		return 1;
	}
	for (i = 0; i < OUTPUT_BYTES; ++i)
		if (shadow[OUTPUT_OFFSET + i] != expected[i]) {
			fprintf(stderr, "compute mismatch byte=%u actual=%02x expected=%02x\n",
				i, shadow[OUTPUT_OFFSET + i], expected[i]);
			return 1;
		}
	if (job.input_ddr_bytes != INPUT_BYTES ||
	    job.weight_ddr_bytes != WEIGHT_BYTES ||
	    job.output_ddr_bytes != OUTPUT_BYTES ||
	    job.window_count != 324 || job.weight_reuse_count != 9 ||
	    !job.cycles) {
		fprintf(stderr, "compute counter mismatch in=%u weight=%u out=%u windows=%u reuse=%u cycles=%u\n",
			job.input_ddr_bytes, job.weight_ddr_bytes,
			job.output_ddr_bytes, job.window_count,
			job.weight_reuse_count, job.cycles);
		return 1;
	}
	printf("PANGO_MAC_CONV_COMPUTE_BOARD_PASS bytes=%u cycles=%u windows=%u\n",
	       job.output_ddr_bytes, job.cycles, job.window_count);
	for (i = 0; i < sizeof(extra_cases) / sizeof(extra_cases[0]); ++i)
		if (run_shape_case(&extra_cases[i], fd, shadow, 0))
			return 1;
	munmap(shadow, info.scratch_bytes);
	close(fd);
	return 0;
}
