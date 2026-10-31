#ifndef CPU80_PAYLOADS_H
#define CPU80_PAYLOADS_H
#include "fat_ro.h"
typedef struct { const char *name; uint32_t address, bytes, crc32; fat_ro_file_t file; } payload_t;
static payload_t payloads[] = {
 {"fw_jump.bin",0x18000000u,266448u,0x832fdcbeu,{0}},
 {"Image",0x00400000u,7480856u,0x3d9edf93u,{0}},
 {"rootfs.cpio",0x03000000u,12146576u,0xd4a2af01u,{0}},
 {"soc.dtb",0x1a000000u,2523u,0xfd0acb92u,{0}},
 {"pikafish.pff",0x10000000u,68122688u,0x80322636u,{0}},
 {"pikafish.atk",0x15000000u,34603072u,0xcba1dd72u,{0}},
};
#define PAYLOAD_COUNT (sizeof(payloads)/sizeof(payloads[0]))
#endif
