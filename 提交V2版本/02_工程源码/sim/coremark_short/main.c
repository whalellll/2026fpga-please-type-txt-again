#include <stdint.h>

/* Isolated integration firmware. Production CoreMark sources and port are
 * compiled unchanged with ITERATIONS=10; a short run must still be rejected. */
int coremark_command(int validation);

int main(void)
{
    int result = coremark_command(VALIDATION_RUN);
    *(volatile uint32_t *)0x1fe003fcu =
        result == 1 ? 0xc04e0001u : 0xc04e0000u;
    for (;;) {
        __asm__ volatile ("nop");
    }
}
