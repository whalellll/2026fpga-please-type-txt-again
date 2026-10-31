#define _POSIX_C_SOURCE 200809L
#include "voice_sd_backend.h"
#include "fat_camera.h"
#include "crc32_fast.h"
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static fatcam_t volume;
static uint32_t clusters[FATCAM_MAX_CLUSTERS];
static uint8_t batch_buffer[4096] __attribute__((aligned(4)));
static volatile sig_atomic_t cancelled;
static uint64_t transaction_start;
static int armed;

static uint64_t milliseconds(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts)) abort();
    return (uint64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}
static void signal_handler(int value) { (void)value; cancelled = 1; }
static int poll_operation(void *user, uint32_t done, uint32_t total, int cleanup)
{
    (void)user; (void)done; (void)total;
    if (cleanup) return 0;
    return cancelled ? FC_CANCEL : (milliseconds() - transaction_start > 180000 ? FC_TIMEOUT : 0);
}
static int write_one(void *user, uint32_t lba, const uint8_t *data)
{
    return armed ? voice_sd_write(user, lba, data) : -1;
}
static int write_many(void *user, uint32_t lba, uint32_t count, const uint8_t *data)
{
    return armed ? voice_sd_write_many(user, lba, count, data) : -1;
}
static uint8_t *read_file(const char *path, size_t maximum, size_t *bytes)
{
    FILE *file = fopen(path, "rb");
    long length;
    uint8_t *buffer;
    if (!file) return NULL;
    if (fseek(file, 0, SEEK_END) || (length = ftell(file)) < 1 ||
        (unsigned long)length > maximum || fseek(file, 0, SEEK_SET)) { fclose(file); return NULL; }
    buffer = malloc((size_t)length + 1);
    if (!buffer) { fclose(file); return NULL; }
    if (fread(buffer, 1, (size_t)length, file) != (size_t)length || ferror(file)) { free(buffer); fclose(file); return NULL; }
    buffer[length] = 0; *bytes = (size_t)length; fclose(file); return buffer;
}
static uint32_t le32(const uint8_t *p) { return p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static int valid_wav(const uint8_t *p, size_t bytes)
{
    return bytes >= 32044 && bytes <= 1920044 && !memcmp(p, "RIFF", 4) &&
        le32(p + 4) == bytes - 8 && !memcmp(p + 8, "WAVEfmt ", 8) && le32(p + 16) == 16 &&
        p[20] == 1 && !p[21] && p[22] == 1 && !p[23] && le32(p + 24) == 16000 &&
        le32(p + 28) == 32000 && p[32] == 2 && !p[33] && p[34] == 16 && !p[35] &&
        !memcmp(p + 36, "data", 4) && le32(p + 40) == bytes - 44 && (bytes - 44) % 32000 == 0;
}
static int number(const char *text, uint32_t *value)
{
    char *end; unsigned long parsed;
    if (!text[0] || text[0] == '-') return -1;
    errno = 0; parsed = strtoul(text, &end, 0);
    if (errno || *end || parsed > UINT32_MAX) return -1;
    *value = (uint32_t)parsed; return 0;
}
static const char *boot_names[] = {"Image", "rootfs.cpio", "fw_jump.bin", "soc.dtb", "vaimage.bin", "vafs.bin", "va.dtb"};
static int print_boot(int crc)
{
    unsigned i; int missing = 0;
    putchar('[');
    for (i = 0; i < sizeof(boot_names) / sizeof(boot_names[0]); i++) {
        fat_ro_file_t file;
        int result = fat_ro_find(&volume.volume, boot_names[i], &file);
        if (i) putchar(',');
        if (result == FAT_RO_ERR_NOT_FOUND) { printf("{\"name\":\"%s\",\"present\":false}", boot_names[i]); if (i < 4) missing++; }
        else if (result) return -1;
        else {
            printf("{\"name\":\"%s\",\"present\":true,\"bytes\":%u", boot_names[i], file.size);
            if (crc) {
                uint8_t *data;
                if (file.size > 32u * 1024u * 1024u || !(data = malloc(file.size ? file.size : 1))) return -1;
                result = fat_ro_load(&volume.volume, &file, data, file.size, NULL, NULL);
                if (!result) printf(",\"crc32\":\"%08x\"", crc32_fast(0xffffffffu, data, file.size) ^ 0xffffffffu);
                free(data); if (result) return -1;
            }
            putchar('}');
        }
    }
    putchar(']'); return missing;
}

int main(int argc, char **argv)
{
    const char *image = NULL, *wav_path = NULL, *meta_path = NULL, *expected_cid = NULL;
    uint32_t expected_partition = 0, expected_volume = 0;
    int has_partition = 0, has_volume = 0, info = 0, boot_crc = 0, result = 1, i, error, started = 0;
    voice_sd_media_t media;
    char cid[33], wav_name[13], metadata[8192];
    uint8_t *wav = NULL, *request = NULL;
    size_t wav_bytes = 0, request_bytes = 0;
    uint32_t wav_crc, metadata_crc;
    int metadata_bytes;
    transaction_start = milliseconds();
    signal(SIGINT, signal_handler); signal(SIGTERM, signal_handler);
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--info")) info = 1;
        else if (!strcmp(argv[i], "--boot-crc")) { info = 1; boot_crc = 1; }
#ifdef VOICE_SD_IMAGE_TEST
        else if (!strcmp(argv[i], "--image") && i + 1 < argc) image = argv[++i];
#endif
        else if (!strcmp(argv[i], "--save") && i + 1 < argc) wav_path = argv[++i];
        else if (!strcmp(argv[i], "--metadata") && i + 1 < argc) meta_path = argv[++i];
        else if (!strcmp(argv[i], "--expect-cid") && i + 1 < argc) expected_cid = argv[++i];
        else if (!strcmp(argv[i], "--expect-partition") && i + 1 < argc) { has_partition = 1; if (number(argv[++i], &expected_partition)) goto finish; }
        else if (!strcmp(argv[i], "--expect-volume") && i + 1 < argc) { has_volume = 1; if (number(argv[++i], &expected_volume)) goto finish; }
        else { fputs("Bad argument; use --info, --boot-crc, or --save WAV --metadata JSON --expect-cid CID --expect-partition LBA --expect-volume SERIAL\n", stderr); goto finish; }
    }
    if ((info && wav_path) || (!info && (!wav_path || !meta_path || !expected_cid || !has_partition || !has_volume))) goto finish;
    if (!info) {
        wav = read_file(wav_path, 1920044, &wav_bytes); request = read_file(meta_path, 4096, &request_bytes);
        if (!wav || !valid_wav(wav, wav_bytes) || !request || request[0] != '{' ||
            !memchr(request, '}', request_bytes) || memchr(request, 0, request_bytes)) {
            fputs("Require canonical 1..60s 16kHz mono S16 WAV and JSON request\n", stderr); goto finish;
        }
    }
    if (voice_sd_open(image, &media, !info)) { perror("open exclusive SD"); goto finish; }
    snprintf(cid, sizeof(cid), "%08x%08x%08x%08x", media.cid[0], media.cid[1], media.cid[2], media.cid[3]);
    error = fatcam_open(&volume, voice_sd_read, write_one, NULL, media.sectors, clusters, poll_operation);
    if (error) { fprintf(stderr, "SD filesystem: %s\n", fatcam_error(error)); goto finish; }
    if (info) {
        printf("{\"cid\":\"%s\",\"sectors\":%u,\"partition_lba\":%u,\"volume_serial\":%u,\"fat_type\":%u,\"boot_files\":",
               cid, media.sectors, volume.volume.partition_lba, volume.volume.volume_serial, volume.volume.fat_type);
        if (print_boot(boot_crc) < 0) goto finish;
        puts("}"); result = 0; goto finish;
    }
    if (strcmp(cid, expected_cid) || volume.volume.partition_lba != expected_partition || volume.volume.volume_serial != expected_volume) {
        fputs("CID/partition/volume mismatch; no media writes\n", stderr); goto finish;
    }
    for (i = 0; i < 4; i++) {
        fat_ro_file_t file;
        if (fat_ro_find(&volume.volume, boot_names[i], &file)) { fputs("Shared boot card requires four original boot files; no writes\n", stderr); goto finish; }
    }
    wav_crc = crc32_fast(0xffffffffu, wav, (uint32_t)wav_bytes) ^ 0xffffffffu;
    metadata_bytes = snprintf(metadata, sizeof(metadata),
        "{\"schema\":1,\"transport\":\"board SD FAT32\",\"cid\":\"%s\",\"sample_rate\":16000,\"samples\":%u,\"wav_crc32\":\"%08x\",\"labels_confirmed\":false,\"request\":%s}\n",
        cid, (unsigned)(wav_bytes - 44) / 2, wav_crc, request);
    if (metadata_bytes < 0 || (size_t)metadata_bytes >= sizeof(metadata)) goto finish;
    metadata_crc = crc32_fast(0xffffffffu, metadata, (uint32_t)metadata_bytes) ^ 0xffffffffu;
    error = fatcam_set_batch(&volume, write_many, batch_buffer, 8);
    if (error) goto finish;
    armed = started = 1;
    error = fatcam_begin(&volume, (uint32_t)wav_bytes, (uint32_t)metadata_bytes);
    if (!error) error = fatcam_write(&volume, 0, wav, (uint32_t)wav_bytes);
    if (!error) error = fatcam_write(&volume, 1, (const uint8_t *)metadata, (uint32_t)metadata_bytes);
    if (!error) error = fatcam_finish(&volume, 0, wav_crc);
    if (!error) error = fatcam_finish(&volume, 1, metadata_crc);
    if (!error) error = fatcam_commit(&volume);
    if (error) {
        int cleanup = fatcam_abort(&volume);
        fprintf(stderr, "SD save failed=%s cleanup=%s\n", fatcam_error(error), cleanup ? "REPAIR_REQUIRED" : "complete");
        started = 0; goto finish;
    }
    started = 0; fatcam_name(volume.id, wav_name);
    printf("{\"status\":\"SD_WAV_JSON_READBACK_COMMIT_PASS\",\"cid\":\"%s\",\"wav\":\"VOICE/%s\",\"json\":\"VOICE/REC%05u.JSON\",\"wav_bytes\":%u,\"wav_crc32\":\"%08x\",\"metadata_crc32\":\"%08x\",\"elapsed_ms\":%llu}\n",
           cid, wav_name, volume.id, (unsigned)wav_bytes, wav_crc, metadata_crc, (unsigned long long)(milliseconds() - transaction_start));
    result = 0;
finish:
    if (started && fatcam_abort(&volume)) fputs("FAT REPAIR REQUIRED\n", stderr);
    armed = 0; voice_sd_close(); free(wav); free(request); return result;
}
