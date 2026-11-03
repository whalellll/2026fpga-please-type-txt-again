#define _GNU_SOURCE
#include "xq_camera.h"
#include "png_rgb565.h"
#include "crc32_fast.h"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <unistd.h>

static volatile sig_atomic_t cancelled;
static void signal_stop(int ignored) { (void)ignored; cancelled = 1; }
static int cancel(void *ignored) { (void)ignored; return cancelled != 0; }
static int write_png(void *file, const uint8_t *p, uint32_t bytes)
{
    return fwrite(p, 1, bytes, file) == bytes ? 0 : -1;
}
static int sync_close(FILE *file)
{
    int r = fflush(file);
    if (!r) r = fsync(fileno(file));
    if (fclose(file)) r = -1;
    return r;
}
static int file_crc(int dir, const char *name, uint32_t expected)
{
    uint8_t buffer[4096];
    uint32_t crc = 0xffffffffu;
    ssize_t n;
    int fd = openat(dir, name, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return 0;
    while ((n = read(fd, buffer, sizeof(buffer))) > 0)
        crc = crc32_fast(crc, buffer, (uint32_t)n);
    close(fd);
    return n == 0 && (crc ^ 0xffffffffu) == expected;
}
static int save(int dir, const xqv_frame *frame, unsigned index)
{
    char png[48], json[48], metadata[512];
    const char *png_part = ".camera_png.part", *json_part = ".camera_json.part";
    uint32_t raw_crc, png_crc, json_crc;
    int pfd = -1, jfd = -1, plen, okay = 0, png_linked = 0, json_linked = 0;
    FILE *file;
    raw_crc = crc32_fast(0xffffffffu, frame->rgb565, XQV_FRAME_BYTES) ^ 0xffffffffu;
    snprintf(png, sizeof(png), "CMOS2_%03u_%010u.png", index, frame->frame_id);
    snprintf(json, sizeof(json), "CMOS2_%03u_%010u.json", index, frame->frame_id);
    pfd = openat(dir, png_part, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (pfd < 0) return 0;
    file = fdopen(pfd, "wb");
    if (!file) { close(pfd); goto done; }
    {
        int r = png565_encode((const uint8_t *)frame->rgb565, write_png, file, NULL, &png_crc);
        if (sync_close(file) || r) goto done;
    }
    plen = snprintf(metadata, sizeof(metadata),
        "{\n  \"captured_at\":null,\n  \"clock\":\"CLOCK_MONOTONIC\",\n"
        "  \"uptime_ms\":%llu,\n  \"frame\":%u,\n  \"width\":1280,\n"
        "  \"height\":720,\n  \"source\":\"CMOS2\",\n"
        "  \"pixel_format\":\"RGB565LE\",\n  \"row_order\":\"top-to-bottom\",\n"
        "  \"raw_crc32\":\"%08x\",\n  \"png_crc32\":\"%08x\"\n}\n",
        (unsigned long long)frame->captured_ms, frame->frame_id, raw_crc, png_crc);
    if (plen < 0 || (size_t)plen >= sizeof(metadata)) goto done;
    jfd = openat(dir, json_part, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (jfd < 0) goto done;
    file = fdopen(jfd, "wb");
    if (!file) { close(jfd); goto done; }
    {
        int r = fwrite(metadata, 1, (size_t)plen, file) != (size_t)plen;
        if (sync_close(file) || r) goto done;
    }
    json_crc = crc32_fast(0xffffffffu, metadata, (uint32_t)plen) ^ 0xffffffffu;
    if (!file_crc(dir, png_part, png_crc) || !file_crc(dir, json_part, json_crc)) goto done;
    /* renameat2 NOREPLACE also works on FAT32, which has no hard links.
     * No fallback to replacing rename: refuse unsupported filesystems. */
    if (syscall(SYS_renameat2, dir, png_part, dir, png, 1u)) goto done;
    png_linked = 1;
    if (syscall(SYS_renameat2, dir, json_part, dir, json, 1u)) goto done;
    json_linked = 1;
    if (fsync(dir)) goto done;
    okay = 1;
done:
    if (!okay) {
        if (png_linked) unlinkat(dir, png, 0);
        if (json_linked) unlinkat(dir, json, 0);
    }
    if (pfd >= 0) unlinkat(dir, png_part, 0);
    if (jfd >= 0) unlinkat(dir, json_part, 0);
    if (!okay) (void)fsync(dir);
    if (okay)
        printf("XQ_CAMERA_PNG_SAVED frame=%u raw_crc32=%08x png_crc32=%08x file=%s\n",
                frame->frame_id, raw_crc, png_crc, png);
    return okay;
}
int main(int argc, char **argv)
{
    xqc_linux camera;
    xqv_frame frame;
    uint32_t *ram;
    unsigned i, count = 1;
    int dir, result = 1;
    if (argc != 2 && argc != 3) {
        fputs("usage: xq-camera-capture NEW_DIRECTORY [count:1..20]\n", stderr);
        return 2;
    }
    if (argc == 3) {
        char *end;
        unsigned long value = strtoul(argv[2], &end, 10);
        if (*end || value < 1 || value > 20) return 2;
        count = (unsigned)value;
    }
    /* A new directory is mandatory. Existing files, especially the SD boot
     * files, cannot be selected as outputs or overwritten by this tool. */
    if (mkdir(argv[1], 0700)) { perror("create new capture directory"); return 2; }
    dir = open(argv[1], O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (dir < 0) return 2;
    ram = malloc(XQV_FRAME_BYTES);
    if (!ram) { close(dir); return 2; }
    signal(SIGINT, signal_stop);
    signal(SIGTERM, signal_stop);
    if (!xqc_linux_open(&camera, cancel, NULL)) {
        perror("camera exclusive owner /dev/mem");
        goto done;
    }
    for (i = 0; i < count && !cancelled; ++i) {
        int r = xqc_capture(&camera.io, ram, XQV_FRAME_BYTES, &frame);
        if (r || !save(dir, &frame, i + 1)) {
            fprintf(stderr, "XQ_CAMERA_CAPTURE_FAIL index=%u code=%d\n", i + 1, r);
            break;
        }
    }
    result = i != count;
    if (xqc_linux_close(&camera)) result = 1;
done:
    free(ram);
    close(dir);
    return result;
}
