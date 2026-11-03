#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#define PFF1_HEADER_BYTES 4096u
#define PFF1_SECTION_COUNT 6u
#define STREAM_BUFFER_BYTES (64u * 1024u)

struct pff1_section {
    char name[5];
    uint64_t offset;
    uint64_t size;
    uint32_t crc32;
};

static uint32_t crc_table[256];

static uint32_t get_u32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint64_t get_u64(const uint8_t *p)
{
    return (uint64_t)get_u32(p) | ((uint64_t)get_u32(p + 4) << 32);
}

static void init_crc_table(void)
{
    uint32_t i;
    for (i = 0; i < 256u; ++i) {
        uint32_t value = i;
        unsigned int bit;
        for (bit = 0; bit < 8u; ++bit)
            value = (value >> 1) ^
                    (0xedb88320u & (0u - (value & 1u)));
        crc_table[i] = value;
    }
}

static uint32_t update_crc(uint32_t crc, const uint8_t *data, size_t bytes)
{
    size_t i;
    for (i = 0; i < bytes; ++i)
        crc = crc_table[(crc ^ data[i]) & 0xffu] ^ (crc >> 8);
    return crc;
}

static int read_at(int fd, void *destination, size_t bytes, uint64_t offset)
{
    uint8_t *out = (uint8_t *)destination;
    while (bytes != 0u) {
        ssize_t count = pread(fd, out, bytes, (off_t)offset);
        if (count < 0 && errno == EINTR)
            continue;
        if (count <= 0)
            return 0;
        out += (size_t)count;
        bytes -= (size_t)count;
        offset += (uint64_t)count;
    }
    return 1;
}

static int stream_crc(int fd, const struct pff1_section *section,
                      uint32_t *actual_out)
{
    uint8_t *buffer = (uint8_t *)malloc(STREAM_BUFFER_BYTES);
    uint64_t offset = section->offset;
    uint64_t left = section->size;
    uint32_t crc = 0xffffffffu;
    if (buffer == NULL)
        return 0;
    while (left != 0u) {
        size_t count = left > STREAM_BUFFER_BYTES ? STREAM_BUFFER_BYTES :
                       (size_t)left;
        if (!read_at(fd, buffer, count, offset)) {
            free(buffer);
            return 0;
        }
        crc = update_crc(crc, buffer, count);
        offset += count;
        left -= count;
    }
    free(buffer);
    *actual_out = crc ^ 0xffffffffu;
    return 1;
}

static uint32_t memory_crc(const uint8_t *data, size_t bytes)
{
    return update_crc(0xffffffffu, data, bytes) ^ 0xffffffffu;
}

static int probe_destination(int fd, const struct pff1_section *section)
{
    uint8_t *mapping;
    uint64_t offset = section->offset;
    uint64_t left = section->size;
    uint32_t first;
    uint32_t second;

    if (section->size > (uint64_t)SIZE_MAX)
        return 0;
    mapping = (uint8_t *)mmap(NULL, (size_t)section->size,
                              PROT_READ | PROT_WRITE,
                              MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mapping == MAP_FAILED) {
        printf("PFF1_PROBE_DEST_ALLOC_FAILED errno=%d\n", errno);
        return 0;
    }
    while (left != 0u) {
        size_t count = left > (1u << 20) ? (1u << 20) : (size_t)left;
        if (!read_at(fd, mapping + (size_t)(offset - section->offset),
                     count, offset)) {
            printf("PFF1_PROBE_DEST_READ_FAILED errno=%d\n", errno);
            munmap(mapping, (size_t)section->size);
            return 0;
        }
        offset += count;
        left -= count;
    }
    printf("PFF1_PROBE_DEST_VA address=%p bytes=%llu\n", (void *)mapping,
           (unsigned long long)section->size);
    first = memory_crc(mapping, (size_t)section->size);
    second = memory_crc(mapping, (size_t)section->size);
    printf("PFF1_PROBE_DEST_CRC first=%08x second=%08x expected=%08x "
           "status=%s\n", first, second, section->crc32,
           first == section->crc32 && second == section->crc32 ?
           "PASS" : "FAIL");
    munmap(mapping, (size_t)section->size);
    return first == section->crc32 && second == section->crc32;
}

int main(int argc, char **argv)
{
    const char *path = argc > 1 ? argv[1] : "/opt/pikafish/pikafish.nnue";
    uint8_t header[PFF1_HEADER_BYTES];
    struct pff1_section sections[PFF1_SECTION_COUNT];
    struct stat st;
    uint32_t actual;
    unsigned int i;
    int fd;
    int passed = 1;

    setvbuf(stdout, NULL, _IOLBF, 0);
    init_crc_table();
    fd = open(path, O_RDONLY);
    if (fd < 0 || fstat(fd, &st) != 0 ||
        !read_at(fd, header, sizeof(header), 0u)) {
        printf("PFF1_PROBE_OPEN_FAILED errno=%d\n", errno);
        if (fd >= 0)
            close(fd);
        return 1;
    }
    if (memcmp(header, "PFF1", 4) != 0 ||
        get_u32(header + 8) != PFF1_HEADER_BYTES ||
        get_u32(header + 52) != PFF1_SECTION_COUNT ||
        get_u64(header + 56) != (uint64_t)st.st_size) {
        printf("PFF1_PROBE_HEADER_FAILED bytes=%lld\n", (long long)st.st_size);
        close(fd);
        return 1;
    }
    for (i = 0; i < PFF1_SECTION_COUNT; ++i) {
        const uint8_t *descriptor = header + 104u + i * 32u;
        memcpy(sections[i].name, descriptor, 4u);
        sections[i].name[4] = '\0';
        sections[i].offset = get_u64(descriptor + 8);
        sections[i].size = get_u64(descriptor + 16);
        sections[i].crc32 = get_u32(descriptor + 24);
    }

    printf("PFF1_PROBE_START path=%s bytes=%lld\n", path,
           (long long)st.st_size);
    for (i = 0; i < 2u; ++i) {
        int ok = stream_crc(fd, &sections[i], &actual);
        printf("PFF1_PROBE_STREAM name=%s bytes=%llu actual=%08x "
               "expected=%08x status=%s\n", sections[i].name,
               (unsigned long long)sections[i].size, ok ? actual : 0u,
               sections[i].crc32,
               ok && actual == sections[i].crc32 ? "PASS" : "FAIL");
        if (!ok || actual != sections[i].crc32)
            passed = 0;
    }
    if (!probe_destination(fd, &sections[1]))
        passed = 0;
    close(fd);
    printf("PFF1_LINUX_PROBE_%s\n", passed ? "PASS" : "FAIL");
    return passed ? 0 : 1;
}
