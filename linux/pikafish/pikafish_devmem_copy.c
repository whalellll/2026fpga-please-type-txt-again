#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

static int parse_u32(const char* text, uint32_t* value) {
    char* end = NULL;
    errno = 0;
    const unsigned long parsed = strtoul(text, &end, 0);
    if (errno != 0 || end == text || *end != '\0' || parsed > UINT32_MAX)
        return 0;
    *value = (uint32_t) parsed;
    return 1;
}

int main(int argc, char** argv) {
    uint32_t physical = 0;
    uint32_t bytes = 0;
    if (argc != 4 || !parse_u32(argv[1], &physical)
        || !parse_u32(argv[2], &bytes) || bytes == 0
        || (physical & 4095u) != 0u) {
        fprintf(stderr, "usage: %s <page-aligned-physical> <bytes> <output>\n",
                argv[0]);
        return 2;
    }

    const int memory = open("/dev/mem", O_RDONLY | O_SYNC | O_CLOEXEC);
    if (memory < 0) {
        perror("open /dev/mem");
        return 1;
    }
    const void* mapping = mmap(NULL, bytes, PROT_READ, MAP_SHARED, memory,
                               (off_t) physical);
    close(memory);
    if (mapping == MAP_FAILED) {
        perror("mmap /dev/mem");
        return 1;
    }

    const int output = open(argv[3], O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC,
                            S_IRUSR | S_IWUSR | S_IXUSR);
    if (output < 0) {
        perror("open output");
        munmap((void*) mapping, bytes);
        return 1;
    }
    const uint8_t* cursor = (const uint8_t*) mapping;
    size_t remaining = bytes;
    while (remaining != 0) {
        const ssize_t written = write(output, cursor, remaining);
        if (written < 0) {
            if (errno == EINTR)
                continue;
            perror("write output");
            close(output);
            munmap((void*) mapping, bytes);
            return 1;
        }
        if (written == 0) {
            fprintf(stderr, "write output: short write\n");
            close(output);
            munmap((void*) mapping, bytes);
            return 1;
        }
        cursor += (size_t) written;
        remaining -= (size_t) written;
    }
    if (close(output) != 0) {
        perror("close output");
        munmap((void*) mapping, bytes);
        return 1;
    }
    munmap((void*) mapping, bytes);
    printf("PIKAFISH_DEVMEM_COPY_PASS physical=0x%08x bytes=%u\n",
           physical, bytes);
    return 0;
}
