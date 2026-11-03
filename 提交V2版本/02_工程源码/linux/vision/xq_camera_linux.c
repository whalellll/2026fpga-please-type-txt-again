#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64
#include "xq_camera.h"
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

static uint64_t now_ms(void *ignored)
{
    struct timespec t;
    (void)ignored;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) return 0;
    return (uint64_t)t.tv_sec * 1000u + (uint64_t)t.tv_nsec / 1000000u;
}
static int poll(void *p, int waiting)
{
    xqc_linux *c = p;
    const struct timespec pause = {0, 1000000};
    int cancelled = c->cancel && c->cancel(c->cancel_context);
    if (waiting) (void)nanosleep(&pause, NULL);
    return cancelled;
}
static const uint32_t physical[8] = {
    0x1fe12000u, 0x1fe11000u, 0x1fe00000u,
    0x9b200000u, 0x9b400000u, 0x9b600000u,0x9b800000u,0x9ba00000u
};
static const size_t lengths[8] = {
    4096,4096,4096,XQV_FRAME_BYTES,XQV_FRAME_BYTES,XQV_FRAME_BYTES,XQV_FRAME_BYTES,XQV_FRAME_BYTES
};
static int reserved_snapshot(void)
{
    static const unsigned char expected[8] = {0x1b, 0x60, 0, 0, 0, 0x20, 0, 0};
    unsigned char reg[9];
    int fd = open("/proc/device-tree/reserved-memory/snapshot@1b600000/reg", O_RDONLY | O_CLOEXEC);
    ssize_t count;
    if (fd < 0) return 0;
    count = read(fd, reg, sizeof(reg));
    close(fd);
    if (count != 8 || memcmp(reg, expected, 8)) return 0;
    return access("/proc/device-tree/reserved-memory/snapshot@1b600000/no-map", F_OK) == 0;
}
static int reserved_background(void)
{
    static const unsigned char expected[8]={0x1b,0x80,0,0,0,0x40,0,0};
    unsigned char reg[9];ssize_t count;
    int fd=open("/proc/device-tree/reserved-memory/camera-capture@1b800000/reg",O_RDONLY|O_CLOEXEC);
    if(fd<0)return 0;
    count=read(fd,reg,sizeof(reg));close(fd);
    return count==8 && !memcmp(reg,expected,8) &&
        access("/proc/device-tree/reserved-memory/camera-capture@1b800000/no-map",F_OK)==0;
}
int xqc_linux_open(xqc_linux *c, int (*cancel)(void *), void *context)
{
    unsigned i;
    memset(c, 0, sizeof(*c));
    c->fd = c->lock_fd = -1;
    c->cancel = cancel;
    c->cancel_context = context;
    if (!reserved_snapshot()) { errno = ENXIO; return 0; }
    c->lock_fd = open("/run/xq-camera.lock", O_CREAT | O_RDWR | O_CLOEXEC, 0600);
    if (c->lock_fd < 0 || flock(c->lock_fd, LOCK_EX | LOCK_NB)) goto failed;
    c->fd = open("/dev/mem", O_RDWR | O_SYNC | O_CLOEXEC);
    if (c->fd < 0) goto failed;
    for (i = 0; i < 6; ++i) {
        c->maps[i] = mmap(NULL, lengths[i], PROT_READ | PROT_WRITE,
                          MAP_SHARED, c->fd, (off_t)physical[i]);
        if (c->maps[i] == MAP_FAILED) {
            c->maps[i] = NULL;
            goto failed;
        }
    }
    if (((volatile uint32_t *)c->maps[0])[0] != CAMERA_ID_VALUE ||
        ((volatile uint32_t *)c->maps[0])[1] != CAMERA_VERSION_VALUE ||
        !(((volatile uint32_t *)c->maps[2])[(0x300u + 12u) / 4u] & 8u)) {
        errno = ENODEV;
        goto failed;
    }
    c->io.camera = c->maps[0];
    c->io.fb = c->maps[1];
    c->io.sys = (volatile uint32_t *)c->maps[2] + 0x300u / 4u;
    c->io.banks[0] = c->maps[3];
    c->io.banks[1] = c->maps[4];
    c->io.snapshot = c->maps[5];
    c->io.now_ms = now_ms;
    c->io.poll = poll;
    c->io.context = c;
    if(c->io.camera[CAMERA_REG_CAPABILITIES/4u]&CAMERA_CAP_BACKGROUND_CAPTURE) {
        if(!reserved_background() ||
           c->io.camera[CAMERA_REG_BACKGROUND_FB0/4u]!=CAMERA_BACKGROUND_FB0_PHYS ||
           c->io.camera[CAMERA_REG_BACKGROUND_FB1/4u]!=CAMERA_BACKGROUND_FB1_PHYS) {
            errno=ENXIO;goto failed;
        }
        for(i=6;i<8;++i) {
            c->maps[i]=mmap(NULL,lengths[i],PROT_READ|PROT_WRITE,MAP_SHARED,c->fd,(off_t)physical[i]);
            if(c->maps[i]==MAP_FAILED){c->maps[i]=NULL;goto failed;}
        }
        c->io.banks[0]=c->maps[6];c->io.banks[1]=c->maps[7];
        c->io.background=1;
    }
    return 1;
failed:
    {
        int saved = errno;
        (void)xqc_linux_close(c);
        errno = saved;
    }
    return 0;
}
int xqc_linux_close(xqc_linux *c)
{
    unsigned i;
    int r = c->io.camera && c->io.camera[0] == CAMERA_ID_VALUE &&
        c->io.camera[1] == CAMERA_VERSION_VALUE ? xqc_stop(&c->io) : XQC_OK;
    for (i = 0; i < 8; ++i) {
        if (c->maps[i]) munmap(c->maps[i], lengths[i]);
        c->maps[i] = NULL;
    }
    if (c->fd >= 0) close(c->fd);
    if (c->lock_fd >= 0) close(c->lock_fd);
    c->fd = c->lock_fd = -1;
    c->io.camera = NULL;
    return r;
}
