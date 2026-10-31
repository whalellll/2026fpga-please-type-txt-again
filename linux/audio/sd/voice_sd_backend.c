#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include "voice_sd_backend.h"
#include "sd_linux_port.h"
#include "sd.h"
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

static int media_fd = -1, lock_fd = -1;
static uint32_t media_sectors;
static volatile uint8_t *registers;
#ifndef VOICE_SD_IMAGE_TEST
static int controller_owned;
#endif

uint32_t read_mtime_ticks32(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts)) abort();
    return (uint32_t)((uint64_t)ts.tv_sec * 1000000u + ts.tv_nsec / 1000u);
}
void console_puts(const char *s) { fputs(s, stderr); }
void console_putc(char c) { fputc(c, stderr); }
void console_dec(uint32_t v) { fprintf(stderr, "%u", v); }
void console_hex(uint32_t v) { fprintf(stderr, "%08x", v); }
volatile uint32_t *voice_sd_reg(uint32_t address)
{
    if (!registers || address < SD_BASE || address >= SD_BASE + 0x500u || (address & 3u)) abort();
    return (volatile uint32_t *)(registers + address - SD_BASE);
}

int voice_sd_open(const char *image, voice_sd_media_t *media, int writing)
{
#ifdef VOICE_SD_IMAGE_TEST
    struct stat st;
    if (!image) return -1;
    media_fd = open(image, writing ? O_RDWR : O_RDONLY);
    if (media_fd < 0 || flock(media_fd, LOCK_EX | LOCK_NB) || fstat(media_fd, &st) ||
        st.st_size < 512 || st.st_size % 512 || (uint64_t)st.st_size / 512 > UINT32_MAX) return -1;
    memset(media, 0, sizeof(*media)); media->cid[3] = 1;
    media_sectors = media->sectors = (uint32_t)(st.st_size / 512);
    return 0;
#else
    const sd_card_info_t *card;
    struct dirent *entry;
    DIR *blocks;
    int result;
    (void)writing;
    if (image) return -1;
    /* This candidate is the sole userspace owner only on the current system
     * without an SD kernel owner. Never coexist with an MMC block driver. */
    blocks = opendir("/sys/class/block");
    if (!blocks) return -1;
    while ((entry = readdir(blocks))) {
        if (!strncmp(entry->d_name, "mmcblk", 6)) { closedir(blocks); errno = EBUSY; return -1; }
    }
    closedir(blocks);
    lock_fd = open("/run/xqvoice-sd.lock", O_CREAT | O_RDWR | O_CLOEXEC, 0600);
    if (lock_fd < 0 || flock(lock_fd, LOCK_EX | LOCK_NB)) return -1;
    media_fd = open("/dev/mem", O_RDWR | O_SYNC | O_CLOEXEC);
    if (media_fd < 0) return -1;
    registers = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, media_fd, SD_BASE);
    if (registers == MAP_FAILED) { registers = NULL; return -1; }
    if (REG32(SD_BASE) != 0x53444e32u ||
        (REG32(SD_BASE + 4) != 0x00050401u && REG32(SD_BASE + 4) != 0x00050400u) ||
        (REG32(SD_BASE + 0x0c) & 0x381u)) { errno = EBUSY; return -1; }
    controller_owned = 1;
    result = sd_init();
    if (result) { fprintf(stderr, "SD initialization error=%d\n", result); return -1; }
    card = sd_card_info();
    if (!card->high_capacity || card->bus_width != 4) return -1;
    media_sectors = media->sectors = card->sector_count;
    memcpy(media->cid, card->cid, sizeof(media->cid));
    return 0;
#endif
}

void voice_sd_close(void)
{
#ifndef VOICE_SD_IMAGE_TEST
    if (registers) { if (controller_owned) sd_release(); munmap((void *)registers, 4096); registers = NULL; }
    controller_owned = 0;
#endif
    if (media_fd >= 0) { close(media_fd); media_fd = -1; }
    if (lock_fd >= 0) { close(lock_fd); lock_fd = -1; }
}

int voice_sd_read(void *user, uint32_t lba, uint32_t count, uint8_t *buffer)
{
    (void)user;
    if (!count || count > 32 || lba >= media_sectors || count > media_sectors - lba) return -1;
#ifdef VOICE_SD_IMAGE_TEST
    return pread(media_fd, buffer, (size_t)count * 512, (off_t)lba * 512) == (ssize_t)count * 512 ? 0 : -1;
#else
    return sd_read_sectors(lba, count, buffer);
#endif
}
int voice_sd_write(void *user, uint32_t lba, const uint8_t *buffer)
{
    (void)user;
    if (lba >= media_sectors) return -1;
#ifdef VOICE_SD_IMAGE_TEST
    if (pwrite(media_fd, buffer, 512, (off_t)lba * 512) != 512 || fsync(media_fd)) return -1;
    return 0;
#else
    return sd_write_sector(lba, buffer);
#endif
}
int voice_sd_write_many(void *user, uint32_t lba, uint32_t count, const uint8_t *buffer)
{
    (void)user;
    if (!count || count > 32 || lba >= media_sectors || count > media_sectors - lba) return -1;
#ifdef VOICE_SD_IMAGE_TEST
    if (pwrite(media_fd, buffer, (size_t)count * 512, (off_t)lba * 512) != (ssize_t)count * 512 || fsync(media_fd)) return -1;
    return 0;
#else
    return sd_write_sectors(lba, count, buffer, NULL, NULL);
#endif
}
