#ifndef XINYI_LINUX_XMODEM_PORT_H
#define XINYI_LINUX_XMODEM_PORT_H
#include <stdint.h>
#define TIMEBASE_HZ 1000000u
uint32_t read_mtime_ticks32(void);
int console_getc_timeout(uint32_t);
void console_putc(char);
void console_puts(const char *);
#endif
