/* Capture diagnostic: AUD1 v2 -> S16_LE PCM -> WAV, no recognition model. */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "pango_audio_uapi.h"
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static void put_le32(unsigned char *p, uint32_t value)
{
    p[0] = (unsigned char)value; p[1] = (unsigned char)(value >> 8);
    p[2] = (unsigned char)(value >> 16); p[3] = (unsigned char)(value >> 24);
}

static void make_wav_header(unsigned char header[44], uint32_t bytes)
{
    memset(header, 0, 44);
    memcpy(header, "RIFF", 4); put_le32(header + 4, bytes + 36);
    memcpy(header + 8, "WAVEfmt ", 8); put_le32(header + 16, 16);
    header[20] = 1; header[22] = 1;
    put_le32(header + 24, 16000); put_le32(header + 28, 32000);
    header[32] = 2; header[34] = 16;
    memcpy(header + 36, "data", 4); put_le32(header + 40, bytes);
}

static uint64_t monotonic_ms(void)
{
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value)) return UINT64_MAX;
    return (uint64_t)value.tv_sec * 1000 + (uint64_t)value.tv_nsec / 1000000;
}

static int write_all(int fd, const unsigned char *data, size_t bytes)
{
    while (bytes) {
        ssize_t n = write(fd, data, bytes);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        data += n; bytes -= (size_t)n;
    }
    return 0;
}

int main(int argc, char **argv)
{
    struct pango_audio_info info;
    struct pango_audio_stats stats;
    unsigned char header[44], *pcm = NULL;
    size_t bytes, done = 0, i;
    uint64_t started, now, elapsed, absolute_sum = 0;
    unsigned long seconds = 2;
    unsigned peak = 0, clipped = 0, nonzero = 0;
    int fd = -1, out = -1, result = 1;
    char *end;
    if (argc == 2 && !strcmp(argv[1], "--help")) {
        puts("usage: xqaudio-capture OUTPUT.wav [SECONDS:1..60] [DEVICE]");
        return 0;
    }
    if (argc < 2 || argc > 4) return 2;
    if (argc >= 3) {
        errno = 0; seconds = strtoul(argv[2], &end, 10);
        if (errno || !argv[2][0] || *end || seconds < 1 || seconds > 60) {
            fputs("seconds must be 1..60\n", stderr); return 2;
        }
    }
    bytes = seconds * 32000;
    pcm = malloc(bytes);
    if (!pcm) { perror("allocate capture"); goto finish; }
    memset(pcm, 0, bytes); /* Fault pages in before the FIFO clear epoch. */
    fd = open(argc == 4 ? argv[3] : "/dev/pango-audio0", O_RDONLY | O_NONBLOCK);
    if (fd < 0) { perror("open audio"); goto finish; }
    memset(&info, 0, sizeof(info));
    if (ioctl(fd, PANGO_AUDIO_IOC_GET_INFO, &info) ||
        info.abi_version != PANGO_AUDIO_ABI_VERSION ||
        info.device_id != PANGO_AUDIO_ID || info.device_version != PANGO_AUDIO_VERSION ||
        info.sample_rate_hz != 16000 || info.channels != 1 ||
        info.sample_format != PANGO_AUDIO_FORMAT_S16_LE ||
        !(info.features & PANGO_AUDIO_FEATURE_CAPTURE_FIFO)) {
        fputs("audio ABI/format mismatch\n", stderr); goto finish;
    }
    if (monotonic_ms() == UINT64_MAX || ioctl(fd, PANGO_AUDIO_IOC_CLEAR)) {
        perror("prepare capture"); goto finish;
    }
    started = monotonic_ms();
    if (started == UINT64_MAX) goto finish;
    while (done < bytes) {
        size_t wanted = bytes - done;
        ssize_t n;
        if (wanted > 256) wanted = 256;
        n = read(fd, pcm + done, wanted);
        if (n > 0) {
            if (((size_t)n & 1) || (size_t)n > wanted) {
                fputs("invalid PCM read length\n", stderr); goto finish;
            }
            done += (size_t)n;
        } else if (n < 0 && errno != EAGAIN && errno != EINTR) {
            perror("read audio"); goto finish;
        } else if (!n) {
            fputs("unexpected audio EOF\n", stderr); goto finish;
        } else if (errno == EAGAIN) {
            usleep(250);
        }
        now = monotonic_ms();
        if (now == UINT64_MAX || now - started > seconds * 1000 + 5000) {
            fputs("capture timeout\n", stderr); goto finish;
        }
    }
    now = monotonic_ms();
    if (now == UINT64_MAX) goto finish;
    elapsed = now - started;
    memset(&stats, 0, sizeof(stats));
    if (ioctl(fd, PANGO_AUDIO_IOC_GET_STATS, &stats)) {
        perror("audio stats"); goto finish;
    }
    if (stats.abi_version != PANGO_AUDIO_ABI_VERSION || stats.fifo_overflows) {
        fprintf(stderr, "capture invalid: overflows=%u; no WAV published\n",
                stats.fifo_overflows); goto finish;
    }
    for (i = 0; i < bytes; i += 2) {
        int value = (int16_t)((uint16_t)pcm[i] | (uint16_t)pcm[i + 1] << 8);
        unsigned magnitude = value < 0 ? (unsigned)-value : (unsigned)value;
        if (magnitude > peak) peak = magnitude;
        absolute_sum += magnitude;
        nonzero += value != 0;
        clipped += value == -32768 || value == 32767;
    }
    // Publish only after capture, so file I/O cannot stall the FIFO reader.
    out = open(argv[1], O_WRONLY | O_CREAT | O_EXCL, 0600);
    if (out < 0) { perror("create output (existing files preserved)"); goto finish; }
    make_wav_header(header, (uint32_t)bytes);
    if (write_all(out, header, sizeof(header)) || write_all(out, pcm, bytes) || fsync(out)) {
        perror("write WAV (partial file may remain)"); goto finish;
    }
    if (close(out)) { out = -1; perror("close WAV"); goto finish; }
    out = -1;
    printf("PCM_TRANSPORT_PASS samples=%zu elapsed_ms=%llu fifo_samples=%u "
           "mic_count=%u overflows=%u peak=%u mean_abs=%llu nonzero=%u clipped=%u\n",
           bytes / 2, (unsigned long long)elapsed, info.fifo_samples,
           stats.microphone_samples, stats.fifo_overflows, peak,
           (unsigned long long)(absolute_sum / (bytes / 2)), nonzero, clipped);
    puts("Acoustic quality and speech recognition require separate acceptance.");
    result = 0;
finish:
    if (out >= 0) close(out);
    if (fd >= 0) close(fd);
    free(pcm);
    return result;
}
