#include <stdio.h>
#include "soc.h"

/* Download/boot ranges are physical DDR only. Limits are exclusive; an
 * invalid starting address must have zero available bytes. Link the actual
 * runtime.c implementation so loaders and these checks share one contract. */
int main(void)
{
    static const struct {
        uint32_t address, length;
        int valid;
        uint32_t limit;
    } cases[] = {
        {0x00000000u, 1u, 1, 0x02000000u},
        {0x01000000u, 0x01000000u, 1, 0x02000000u},
        {0x01fffffcu, 4u, 1, 0x02000000u},
        {0x01fffffcu, 5u, 0, 0x02000000u},
        {0x01ffffffu, 1u, 1, 0x02000000u},
        {0x01ffffffu, 2u, 0, 0x02000000u},
        {0x02000000u, 1u, 0, 0x02000000u},
        {0x0200bff8u, 8u, 0, 0x0200bff8u},
        {0x0200ffffu, 1u, 0, 0x0200ffffu},
        {0x02010000u, 4u, 1, 0x1b000000u},
        {0x01ffffffu, 0x10002u, 0, 0x02000000u},
        {0x0c000000u, 8u, 1, 0x1b000000u},
        {0x10000000u, 8u, 1, 0x1b000000u},
        {0x1afffffcu, 4u, 1, 0x1b000000u},
        {0x1afffffcu, 5u, 0, 0x1b000000u},
        {0x1b000000u, 4u, 0, 0x1b000000u},
        {0x1b600000u, 4u, 0, 0x1b600000u},
        {0x1b7fffffu, 1u, 0, 0x1b7fffffu},
        {0x1affffffu, 0x800002u, 0, 0x1b000000u},
        {0x1b800000u, 4u, 1, 0x1c000000u},
        {0x1bfffffcu, 4u, 1, 0x1c000000u},
        {0x1bfffffcu, 5u, 0, 0x1c000000u},
        {0x1c000000u, 1u, 0, 0x1c000000u},
        {0x00000000u, 0u, 0, 0x02000000u},
        {0x00000004u, 0xfffffffcu, 0, 0x02000000u},
        {0x80000000u, 4u, 0, 0x80000000u},
        {0x81fffffcu, 4u, 0, 0x81fffffcu},
        {0x82000000u, 4u, 0, 0x82000000u},
        {0x82010000u, 4u, 0, 0x82010000u},
        {0x9b000000u, 4u, 0, 0x9b000000u},
        {0xfffffffcu, 8u, 0, 0xfffffffcu}
    };
    size_t i;
    int failed = 0;
    for (i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        int valid = ddr_range_valid(cases[i].address, cases[i].length);
        uint32_t limit = ddr_contiguous_limit(cases[i].address);
        if (valid != cases[i].valid || limit != cases[i].limit) {
            fprintf(stderr, "DDR range case %u: address=%08x length=%08x "
                    "valid=%d expected=%d limit=%08x expected=%08x\n",
                    (unsigned)i, cases[i].address, cases[i].length, valid,
                    cases[i].valid, limit, cases[i].limit);
            failed = 1;
        }
    }
    /* Entry alignment is stricter than data alignment, but uses the same
     * CLINT/DMA exclusion and physical-address policy. */
    if (!ddr_range_valid(0x00100001u, 4u) ||
        !ddr_range_valid(0x00100002u, 4u) ||
        !ddr_entry_valid(0x00100000u) ||
        ddr_entry_valid(0x00100001u) || ddr_entry_valid(0x00100002u) ||
        !ddr_entry_valid(0x01fffffcu) || ddr_entry_valid(0x02000000u) ||
        ddr_entry_valid(0x0200fffcu) || !ddr_entry_valid(0x02010000u) ||
        ddr_entry_valid(0x1b000000u) || !ddr_entry_valid(0x1b800000u) ||
        ddr_entry_valid(0x82010000u) || !ddr_entry_valid(0x1bfffffcu) ||
        ddr_entry_valid(0x1c000000u)) {
        fputs("DDR entry/alignment contract failed\n", stderr);
        failed = 1;
    }
    if (failed) return 1;
    printf("BOOTLOADER_DDR_RANGE_PASS cases=%u\n",
           (unsigned)(sizeof(cases) / sizeof(cases[0])));
    return 0;
}
