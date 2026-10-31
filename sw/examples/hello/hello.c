#include <stdint.h>
#define UART (*(volatile uint32_t *)0x1fe001e0u)
static void puts(const char*s){while(*s){if(*s=='\n')UART='\r';UART=(uint8_t)*s++;}}
int main(void){puts("Hello from a TFTP/XMODEM-loaded binary!\n");return 0;}
