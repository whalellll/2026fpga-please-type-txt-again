#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include "pf_mlp_mac_pack.h"

static uint32_t read_le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint32_t crc32_bytes(const uint8_t *data, size_t bytes) {
    uint32_t crc = 0xffffffffu;
    size_t i;
    for (i = 0; i < bytes; ++i) {
        unsigned int bit;
        crc ^= data[i];
        for (bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return crc ^ 0xffffffffu;
}

static int validate_pack(const uint8_t *data, size_t bytes, uint32_t *crc_out) {
    uint32_t expected_crc;
    uint32_t actual_crc;
    uint32_t stack;
    if (bytes != PF_STAGEB_PACK_USED_BYTES ||
        read_le32(data + PF_STAGEB_H_MAGIC) != PF_STAGEB_PACK_MAGIC ||
        read_le32(data + PF_STAGEB_H_VERSION) != PF_STAGEB_PACK_VERSION ||
        read_le32(data + PF_STAGEB_H_HEADER_BYTES) != PF_STAGEB_HEADER_BYTES ||
        read_le32(data + PF_STAGEB_H_USED_BYTES) != PF_STAGEB_PACK_USED_BYTES ||
        read_le32(data + PF_STAGEB_H_STACK_COUNT) != PF_STAGEB_STACK_COUNT ||
        read_le32(data + PF_STAGEB_H_STACK_SLOT_BYTES) != PF_STAGEB_STACK_SLOT_BYTES ||
        read_le32(data + PF_STAGEB_H_STACK_BASE) != PF_STAGEB_STACK_BASE ||
        read_le32(data + PF_STAGEB_H_FC0_OFFSET) != PF_STAGEB_FC0_PACKED_OFFSET ||
        read_le32(data + PF_STAGEB_H_FC0_TILE_BYTES) != PF_STAGEB_FC0_TILE_BYTES ||
        read_le32(data + PF_STAGEB_H_FC0_TILE_COUNT) != PF_STAGEB_FC0_TILE_COUNT ||
        read_le32(data + PF_STAGEB_H_FLAGS) != (PF_STAGEB_FLAG_MAC_NATIVE_FC0 |
                                                PF_STAGEB_FLAG_ROW_MAJOR_TAIL) ||
        crc32_bytes(data, PF_STAGEB_H_HEADER_CRC32) !=
            read_le32(data + PF_STAGEB_H_HEADER_CRC32))
        return 0;
    for (stack = 0; stack < PF_STAGEB_STACK_COUNT; ++stack) {
        const uint8_t *slot = data + pf_stageb_stack_offset(stack);
        if (read_le32(slot + 0) != PF_STAGEB_STACK_MAGIC ||
            read_le32(slot + 4) != stack ||
            read_le32(slot + 8) != PF_STAGEB_STACK_SLOT_BYTES ||
            read_le32(slot + 12) != PF_STAGEB_FC0_PACKED_OFFSET ||
            read_le32(slot + 16) != PF_STAGEB_FC0_PACKED_BYTES)
            return 0;
        if (crc32_bytes(slot + PF_STAGEB_STACK_HEADER_BYTES,
                        PF_STAGEB_STACK_DATA_END -
                            PF_STAGEB_STACK_HEADER_BYTES) !=
                read_le32(slot + PF_STAGEB_S_DATA_CRC32) ||
            crc32_bytes(slot + PF_STAGEB_FC0_PACKED_OFFSET,
                        PF_STAGEB_FC0_PACKED_BYTES +
                            PF_STAGEB_FC0_BIAS_BYTES) !=
                read_le32(slot + PF_STAGEB_S_FC0_CRC32))
            return 0;
    }
    expected_crc = read_le32(data + PF_STAGEB_H_PAYLOAD_CRC32);
    actual_crc = crc32_bytes(data + PF_STAGEB_HEADER_BYTES,
                             bytes - PF_STAGEB_HEADER_BYTES);
    if (actual_crc != expected_crc)
        return 0;
    *crc_out = actual_crc;
    return 1;
}

int main(int argc, char **argv) {
    const char *path = argc > 1 ? argv[1] : "/opt/pikafish/stageb-mac.bin";
    int verify_only = argc > 2 && strcmp(argv[2], "--verify-only") == 0;
    struct stat st;
    uint8_t *source;
    uint8_t *ddr;
    uint32_t crc;
    int input_fd;
    int mem_fd;
    int result = 1;

    input_fd = open(path, O_RDONLY);
    if (input_fd < 0 || fstat(input_fd, &st) != 0) {
        perror("pikafish-stageb-load: open/stat");
        if (input_fd >= 0)
            close(input_fd);
        return 1;
    }
    if (st.st_size != (off_t)PF_STAGEB_PACK_USED_BYTES) {
        fprintf(stderr, "pikafish-stageb-load: wrong pack size %ld\n",
                (long)st.st_size);
        close(input_fd);
        return 1;
    }
    source = mmap(NULL, (size_t)st.st_size, PROT_READ, MAP_PRIVATE, input_fd, 0);
    close(input_fd);
    if (source == MAP_FAILED) {
        perror("pikafish-stageb-load: mmap pack");
        return 1;
    }
    if (!validate_pack(source, (size_t)st.st_size, &crc)) {
        fprintf(stderr, "pikafish-stageb-load: invalid pack or CRC\n");
        munmap(source, (size_t)st.st_size);
        return 1;
    }
    if (verify_only) {
        printf("PIKAFISH_STAGEB_PACK_VERIFIED bytes=%u crc32=%08x\n",
               (unsigned int)PF_STAGEB_PACK_USED_BYTES, (unsigned int)crc);
        munmap(source, (size_t)st.st_size);
        return 0;
    }

    mem_fd = open("/dev/mem", O_RDWR | O_SYNC);
    if (mem_fd < 0) {
        perror("pikafish-stageb-load: open /dev/mem");
        munmap(source, (size_t)st.st_size);
        return 1;
    }
    ddr = mmap(NULL, PF_STAGEB_PACK_USED_BYTES, PROT_READ | PROT_WRITE, MAP_SHARED,
               mem_fd, (off_t)PF_STAGEB_DDR_CPU_ALIAS);
    close(mem_fd);
    if (ddr == MAP_FAILED) {
        perror("pikafish-stageb-load: mmap accelerator DDR");
        munmap(source, (size_t)st.st_size);
        return 1;
    }

    memcpy(ddr, source, (size_t)st.st_size);
    __sync_synchronize();
    if (memcmp(ddr, source, (size_t)st.st_size) != 0) {
        fprintf(stderr, "pikafish-stageb-load: DDR readback mismatch\n");
    } else {
        printf("PIKAFISH_STAGEB_DDR_READY bytes=%u crc32=%08x\n",
               (unsigned int)PF_STAGEB_PACK_USED_BYTES, (unsigned int)crc);
        result = 0;
    }
    munmap(ddr, PF_STAGEB_PACK_USED_BYTES);
    munmap(source, (size_t)st.st_size);
    return result;
}
