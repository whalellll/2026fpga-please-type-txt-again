#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include "pango_mac_uapi.h"

#define INPUT_OFFSET  0x00000u
#define WEIGHT_OFFSET 0x70000u
#define OUTPUT_OFFSET 0x80000u

struct case_shape {
	const char *name;
	uint16_t width, height, channels, output_channels;
	uint8_t kernel, stride, padding, channel_tile;
};

static const struct case_shape cases[] = {
	{ "pointwise", 8, 7, 3, 4, 1, 1, 0, 0 },
	{ "tail_tile", 7, 7, 5, 8, 3, 1, 1, 1 },
	{ "six_by_six", 7, 7, 3, 16, 6, 1, 2, 0 },
	{ "first_layer", 320, 320, 3, 16, 6, 2, 2, 0 },
};

static uint32_t reference_tap_xor(const uint8_t *input,
				  const struct case_shape *shape)
{
	uint32_t tiles = (shape->channels + 3u) / 4u;
	uint32_t ow = (shape->width + 2u * shape->padding - shape->kernel) /
		shape->stride + 1u;
	uint32_t oh = (shape->height + 2u * shape->padding - shape->kernel) /
		shape->stride + 1u;
	uint32_t check = 0, ox, oy, kx, ky, lane;

	for (oy = 0; oy < oh; ++oy)
		for (ox = 0; ox < ow; ++ox)
			for (ky = 0; ky < shape->kernel; ++ky)
				for (kx = 0; kx < shape->kernel; ++kx) {
					int x = (int)(ox * shape->stride + kx) -
						shape->padding;
					int y = (int)(oy * shape->stride + ky) -
						shape->padding;
					uint32_t word = 0;

					if (x >= 0 && x < shape->width &&
					    y >= 0 && y < shape->height)
						for (lane = 0; lane < 4; ++lane) {
							uint32_t channel =
								shape->channel_tile * 4u + lane;
							if (channel < shape->channels)
								word |= (uint32_t)input[
									((uint32_t)y * shape->width + x) *
									tiles * 4u + channel] <<
									(8u * lane);
						}
					check ^= word;
				}
	return check;
}

static int run_case(int fd, uint8_t *shadow, const struct case_shape *shape,
		    unsigned case_index)
{
	struct pango_mac_conv_job job = {0};
	uint32_t tiles = (shape->channels + 3u) / 4u;
	uint32_t input_bytes = (uint32_t)shape->width * shape->height * tiles * 4u;
	uint32_t line_count =
		((uint32_t)shape->channels * shape->kernel * shape->kernel + 3u) / 4u;
	uint32_t ow = (shape->width + 2u * shape->padding - shape->kernel) /
		shape->stride + 1u;
	uint32_t oh = (shape->height + 2u * shape->padding - shape->kernel) /
		shape->stride + 1u;
	uint32_t windows = ow * oh;
	uint32_t taps = windows * shape->kernel * shape->kernel;
	uint32_t expected_xor;
	uint32_t i;

	for (i = 0; i < input_bytes; ++i)
		shadow[INPUT_OFFSET + i] = (uint8_t)((i * 37u +
			(i >> 4) * 19u + (i >> 9) * 7u +
			case_index * 13u) & 255u);
	for (i = 0; i < line_count * 128u; ++i)
		shadow[WEIGHT_OFFSET + i] = (uint8_t)((i * 29u + case_index) & 255u);
	expected_xor = reference_tap_xor(shadow + INPUT_OFFSET, shape);

	job.abi_version = PANGO_MAC_CONV_ABI_VERSION;
	job.flags = PANGO_MAC_CONV_FLAG_WINDOW_ONLY;
	job.model_id_lo = 0x4d434f4eu;
	job.model_id_hi = case_index;
	job.generation = case_index + 1u;
	job.input_offset = INPUT_OFFSET;
	job.weight_offset = WEIGHT_OFFSET;
	job.output_offset = OUTPUT_OFFSET;
	job.width = shape->width;
	job.height = shape->height;
	job.channels = shape->channels;
	job.output_channels = shape->output_channels;
	job.kernel = shape->kernel;
	job.stride = shape->stride;
	job.padding = shape->padding;
	job.channel_tile = shape->channel_tile;
	job.weight_lines = line_count;
	job.timeout_us = 1000000u;
	if (ioctl(fd, PANGO_MAC_IOC_RUN_CONV, &job)) {
		fprintf(stderr, "%s ioctl failed errno=%d status=%08" PRIx32
			" error=%" PRIu32 "\n", shape->name, errno,
			job.status, job.error_code);
		return 1;
	}
	printf("%s taps=%" PRIu32 " input=%" PRIu32 " weight=%" PRIu32
		" output=%" PRIu32 " reuse=%" PRIu32 " cycles=%" PRIu32
		" stalls=%" PRIu32 " tap_xor=%08" PRIx32
		" weight_digest=%08" PRIx32 "\n", shape->name,
		job.window_count, job.input_ddr_bytes, job.weight_ddr_bytes,
		job.output_ddr_bytes, job.weight_reuse_count, job.cycles,
		job.stall_cycles, job.tap_xor, job.weight_digest);
	if (job.window_count != taps ||
	    job.input_ddr_bytes != (uint32_t)shape->width * shape->height * 4u ||
	    job.weight_ddr_bytes != line_count * 128u ||
	    job.output_ddr_bytes != 0 || job.weight_reuse_count != windows ||
	    job.tap_xor != expected_xor || !job.weight_digest || !job.cycles) {
		fprintf(stderr, "%s counter/checksum mismatch: expected taps=%" PRIu32
			" windows=%" PRIu32 " tap_xor=%08" PRIx32 "\n",
			shape->name, taps, windows, expected_xor);
		return 1;
	}
	return 0;
}

int main(void)
{
	struct pango_mac_info info = {0};
	uint8_t *shadow;
	unsigned i;
	int fd = open("/dev/pango-mac0", O_RDWR);

	if (fd < 0 || ioctl(fd, PANGO_MAC_IOC_GET_INFO, &info) ||
	    !(info.features & PANGO_MAC_FEATURE_CONV_WINDOW) ||
	    info.scratch_bytes != 0x100000u) {
		fprintf(stderr, "convolution window device unavailable\n");
		return 1;
	}
	shadow = mmap(NULL, info.scratch_bytes, PROT_READ | PROT_WRITE,
		      MAP_SHARED, fd, 0);
	if (shadow == MAP_FAILED)
		return 1;
	for (i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i)
		if (run_case(fd, shadow, &cases[i], i))
			return 1;
	puts("PANGO_MAC_CONV_WINDOW_BOARD_PASS");
	munmap(shadow, info.scratch_bytes);
	close(fd);
	return 0;
}
