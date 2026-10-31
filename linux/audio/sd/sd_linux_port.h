#ifndef VOICE_SD_LINUX_PORT_H
#define VOICE_SD_LINUX_PORT_H
#include <stddef.h>
#include <stdint.h>
#define SD_BASE 0x1fe13000u
#define SYS_CLOCK_HZ 49500000u
/* Native driver's deadlines use Linux monotonic microseconds, not CSR clocks. */
#define TIMEBASE_HZ 1000000u
volatile uint32_t *voice_sd_reg(uint32_t address);
#define REG32(address) (*voice_sd_reg((uint32_t)(address)))
uint32_t read_mtime_ticks32(void);
void console_puts(const char *text);
void console_putc(char value);
void console_dec(uint32_t value);
void console_hex(uint32_t value);
#endif
