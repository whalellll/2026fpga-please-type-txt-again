#ifndef SOC_H
#define SOC_H
#include <stdint.h>
#include <stddef.h>

#define REG32(a) (*(volatile uint32_t *)(uintptr_t)(a))
#define REG8(a)  (*(volatile uint8_t *)(uintptr_t)(a))
#define UART_BASE 0x1fe001e0u
#define SPI_BASE  0x1fe00200u
#define SYS_BASE  0x1fe00300u
#define SYS_CLOCK_HZ 49500000u
#define CPU_CLOCK_HZ 80000000u
#define TIMEBASE_HZ 49500000u
#define SYS_HZ_REG (SYS_BASE+0x08u)
#define CPU_HZ_REG (SYS_BASE+0x14u)
#define TIMEBASE_HZ_REG (SYS_BASE+0x18u)
#define SYS_ID_VALUE 0x53563300u
#define SYS_CAP_LINUX_BASE (1u << 0)
#define SYS_CAP_XQ_FB_ACCEL (1u << 1)
#define SYS_CAP_CH9350  (1u << 2)
#define SYS_CAP_CAMERA  (1u << 3)
#define SYS_CAP_MICRO_SD (1u << 4)
#define CLINT_BASE  0x02000000u
#define CLINT_END   0x02010000u
#define CLINT_MTIME (CLINT_BASE+0xbff8u)
#define ETH_BASE  0x1fe01000u
#define MAC_BASE  0x1fe10000u
#define MAC_DDR_BASE 0x1b000000u
#define MAC_DDR_BYTES 0x00100000u
#define MAC_DDR_CPU_ALIAS 0x9b000000u
#define FB_REG_BASE 0x1fe11000u
#define CAMERA_BASE 0x1fe12000u
#define SD_BASE     0x1fe13000u
#define FB0_DDR_BASE 0x1b200000u
#define FB1_DDR_BASE 0x1b400000u
#define FB0_CPU_ALIAS 0x9b200000u
#define FB1_CPU_ALIAS 0x9b400000u
#define CAMERA_SNAPSHOT_CPU_ALIAS 0x9b600000u
#define FB_SLOT_BYTES 0x00200000u
#define FB_FRAME_BYTES 0x001c2000u
#define FB_STRIDE_BYTES 0x00000a00u
#define DDR_DMA_RESERVED_BASE 0x1b000000u
#define DDR_DMA_RESERVED_END  0x1b800000u
#define ETH_RXBUF (ETH_BASE+0x1000u)
#define ETH_TXBUF (ETH_BASE+0x2000u)

/* Keep downloaded programs below the boot BRAM/MMIO apertures. */
#define DDR_SAFE_LIMIT 0x1c000000u

#define FLASH_HEADER_ADDR  0x00800000u
#define FLASH_PAYLOAD_ADDR 0x00801000u
/* The detected board device reports density code 0x18 (128 Mbit / 16 MiB).
 * Never let software updates cross the physical end of that device. */
#define FLASH_LIMIT_ADDR   0x01000000u
#define IMAGE_MAGIC        0x49325653u /* "SV2I" compatibility-format magic */

typedef struct {
 uint32_t magic,version,load_addr,entry_addr,length,crc32,flags,header_crc32;
} image_header_t;

uint32_t read_mtime_ticks32(void);
void delay_cycles(uint32_t timebase_ticks);
void console_putc(char c);
int console_getc_timeout(uint32_t cycles);
void console_puts(const char *s);
void console_hex(uint32_t v);
void console_dec(uint32_t v);
uint32_t parse_u32(const char *s,int *ok);
uint32_t crc32_update(uint32_t crc,const void *data,uint32_t len);
int ddr_range_valid(uint32_t address,uint32_t len);
int ddr_entry_valid(uint32_t address);
uint32_t ddr_contiguous_limit(uint32_t address);
int ddr_wait_ready(void);
uint32_t xmodem_receive(uint32_t address,uint32_t limit);

int flash_read(uint32_t address,void *dst,uint32_t len);
uint32_t flash_read_jedec_id(void);
int flash_write_image(uint32_t ram,uint32_t len,uint32_t load,uint32_t entry,uint32_t flags);
int flash_read_header(image_header_t *out);
int flash_load_image(image_header_t *out);

void eth_init(void);
void eth_set_ip(uint32_t ip);
int tftp_get(uint32_t server_ip,const char *filename,uint32_t address,uint32_t limit,uint32_t *length);
/* 0 saved by PC, 1 Esc cancellation, negative transport/receiver failure. */
int camera_transfer(uint32_t frame,const uint8_t *pixels,uint32_t frame_crc);
uint32_t parse_ip(const char *s,int *ok);
void jump_to(uint32_t entry,uint32_t arg0,uint32_t arg1);
#endif
