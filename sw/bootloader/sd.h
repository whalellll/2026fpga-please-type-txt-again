#ifndef SOC_SD_H
#define SOC_SD_H

#include <stdint.h>

#define SD_OK                 0
#define SD_ERR_NO_CARD       -1
#define SD_ERR_TIMEOUT       -2
#define SD_ERR_PROTOCOL      -3
#define SD_ERR_UNSUPPORTED   -4
#define SD_ERR_IO            -5
#define SD_ERR_CRC           -6
#define SD_ERR_REMOVED       -7
#define SD_ERR_ABORTED       -100

typedef struct {
 uint32_t ocr;
 uint32_t sector_count;
 uint32_t transfer_hz;
 uint32_t cid[4]; /* Stable media identity for explicit writer recovery. */
 uint16_t rca;
 uint8_t version2;
 uint8_t high_capacity;
 uint8_t bus_width;
} sd_card_info_t;

int sd_card_present(void);
int sd_card_raw_present(void);
int sd_init(void);
int sd_read_sectors(uint32_t lba,uint32_t count,uint8_t *buffer);
int sd_read_sector(uint32_t lba,uint8_t *buffer);
/* Explicit bootloader-only write. Returns after CRC status, DAT0 programming
 * busy and CMD13 READY_FOR_DATA/TRAN status; never retries an uncertain write. */
int sd_write_sector(uint32_t lba,const uint8_t *buffer);
/* Contiguous reserved data only: native CMD25 batches of at most32 sectors.
 * A nonzero poll result requests a graceful stop after the current block;
 * SD_ERR_ABORTED is returned only after CMD12/busy/CMD13 drain succeeds.
 * Old single-block hardware uses the same bounded CMD24 fallback. */
typedef int (*sd_write_poll_fn)(void *);
int sd_write_sectors(uint32_t lba,uint32_t count,const uint8_t *buffer,
                     sd_write_poll_fn poll,void *user);
void sd_release(void);
const sd_card_info_t *sd_card_info(void);

int sd_boot_linux(void);
int sd_boot_xiangqi(void);
int sd_benchmark(void);
int sd_verify_boot_files(void); /* Read-only integrity check; never starts Linux. */
void sd_print_info(void);

#endif
