#ifndef CRC32_FAST_H
#define CRC32_FAST_H
#include <stdint.h>
/* Same reflected IEEE CRC as runtime.c. Initial0xffffffff, final xor0xffffffff. */
uint32_t crc32_fast(uint32_t crc,const void *bytes,uint32_t count);
#endif
