/* Read-only validation of a captured request against every snapshot word. */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include "camera.h"
#include "crc32_fast.h"
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#define FRAME_BYTES (1280u * 720u * 2u)

int main(int argc, char **argv)
{
    char magic[32], backend[64];
    unsigned long long token;
    unsigned frame, expected, held, lit = 0;
    uint32_t words[1024], file_crc = 0xffffffffu, snapshot_crc = 0xffffffffu;
    size_t count, total = 0;
    FILE *request = NULL, *raw = NULL, *reservation = NULL;
    int fd = -1, okay = 0;
    unsigned char reg[9];
    static const unsigned char required[8] = {0x1b, 0x60, 0, 0, 0, 0x20, 0, 0};
    volatile uint32_t *camera = MAP_FAILED, *snapshot = MAP_FAILED;
    if (argc != 3) return 2;
    request = fopen(argv[1], "r");
    raw = fopen(argv[2], "rb");
    reservation = fopen("/proc/device-tree/reserved-memory/snapshot@1b600000/reg", "rb");
    if (!request || !raw || !reservation || fread(reg, 1, sizeof(reg), reservation) != 8 ||
        memcmp(reg, required, 8) || access("/proc/device-tree/reserved-memory/snapshot@1b600000/no-map", F_OK)) goto done;
    if (fscanf(request, "%31s %llu %u %x %63s", magic, &token, &frame, &expected, backend) != 5 ||
        strcmp(magic, "XQ_MODEL_REQUEST_V1") || !token ||
        strcmp(backend, "rv32-driver-quantized-mac")) goto done;
    fd = open("/dev/mem", O_RDONLY | O_SYNC | O_CLOEXEC);
    if (fd < 0) goto done;
    camera = mmap(NULL, 4096, PROT_READ, MAP_SHARED, fd, (off_t)0x1fe12000u);
    snapshot = mmap(NULL, FRAME_BYTES, PROT_READ, MAP_SHARED, fd, (off_t)0x9b600000u);
    if (camera == MAP_FAILED || snapshot == MAP_FAILED ||
        camera[0] != CAMERA_ID_VALUE || camera[1] != CAMERA_VERSION_VALUE) goto done;
    held = camera[CAMERA_REG_SNAPSHOT_FRAME_COUNT / 4u];
    if (held != frame) goto done;
    while ((count = fread(words, 1, sizeof(words), raw)) != 0) {
        if ((count & 3u) || count > FRAME_BYTES - total) goto done;
        file_crc = crc32_fast(file_crc, words, (uint32_t)count);
        for (unsigned i = 0; i < count / 4u; ++i) {
            uint32_t word = snapshot[total / 4u + i];
            if (word != words[i]) goto done;
            snapshot_crc = crc32_fast(snapshot_crc, &word, 4);
            lit += (word & 65535u) != 0;
            lit += (word >> 16) != 0;
        }
        total += count;
    }
    if (ferror(raw) || total != FRAME_BYTES || (file_crc ^ 0xffffffffu) != expected ||
        (snapshot_crc ^ 0xffffffffu) != expected || lit <= 1280 ||
        camera[CAMERA_REG_SNAPSHOT_FRAME_COUNT / 4u] != held) goto done;
    printf("XQ_CAPTURE_IDENTITY_PASS bytes=%u words=%u token=%llu frame=%u crc=%08x full_word_compare=1 snapshot_frame_stable=1 lit=%u\n",
           FRAME_BYTES, FRAME_BYTES / 4u, token, frame, expected, lit);
    okay = 1;
done:
    if (camera != MAP_FAILED) munmap((void *)camera, 4096);
    if (snapshot != MAP_FAILED) munmap((void *)snapshot, FRAME_BYTES);
    if (fd >= 0) close(fd);
    if (request) fclose(request);
    if (raw) fclose(raw);
    if (reservation) fclose(reservation);
    if (!okay) fputs("XQ_CAPTURE_IDENTITY_FAIL\n", stderr);
    return okay ? 0 : 1;
}
