/* Fail closed when a batch trial is booted with an older driver/bitstream. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
#include "pango_mac_uapi.h"

int main(void)
{
    struct pango_mac_info info = {0};
    const unsigned required = PANGO_MAC_FEATURE_PRIVATE_SHADOW |
        PANGO_MAC_FEATURE_SERIALIZED | PANGO_MAC_FEATURE_STAGEA_GATHER |
        PANGO_MAC_FEATURE_RESIDENT_MODEL | PANGO_MAC_FEATURE_NNUE_PIPELINE |
        PANGO_MAC_FEATURE_PIKAFISH_DEDICATED | PANGO_MAC_FEATURE_NNUE_BATCH;
    int fd = open("/dev/pango-mac0", O_RDWR | O_CLOEXEC);
    if (fd < 0) { perror("PIKAFISH_BATCH_CAPABILITY_FAIL open"); return 1; }
    if (ioctl(fd, PANGO_MAC_IOC_GET_INFO, &info) < 0) {
        perror("PIKAFISH_BATCH_CAPABILITY_FAIL ioctl"); close(fd); return 1;
    }
    if (info.abi_version != PANGO_MAC_ABI_VERSION ||
        info.device_id != PANGO_MAC_PIKAFISH_ID ||
        info.device_version != PANGO_MAC_PIKAFISH_VERSION ||
        (info.features & required) != required ||
        (info.features & PANGO_MAC_FEATURE_DENSE) || info.scratch_bytes < 0x100000u) {
        fprintf(stderr, "PIKAFISH_BATCH_CAPABILITY_FAIL abi=%u id=%08x version=%08x features=%08x scratch=%u\n",
            info.abi_version, info.device_id, info.device_version,
            info.features, info.scratch_bytes);
        close(fd);
        return 1;
    }
    /* count=0 must fail validation before allocation, lock or any job start.
     * It also distinguishes this ioctl from the independent VISION32 ABI. */
    {
        struct pango_mac_batch invalid = {0};
        int rc, saved_errno;
        invalid.abi_version = PANGO_MAC_BATCH_ABI_VERSION;
        errno = 0;
        rc = ioctl(fd, PANGO_MAC_IOC_RUN_BATCH, &invalid);
        saved_errno = errno;
        close(fd);
        if (rc != -1 || saved_errno != EINVAL) {
            fprintf(stderr, "PIKAFISH_BATCH_CAPABILITY_FAIL batch-abi rc=%d errno=%d\n",
                rc, saved_errno);
            return 1;
        }
    }
    printf("PIKAFISH_BATCH_CAPABILITY_PASS id=%08x features=%08x\n",
        info.device_id, info.features);
    return 0;
}
