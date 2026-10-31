#ifndef XINYI_CLOCK_CONTRACT_H
#define XINYI_CLOCK_CONTRACT_H
/* The build binds one exact board clock; another supported clock still fails
 * its MMIO identity check. Preserve the historical CPU60 build default. */
#ifndef XINYI_CPU_HZ
#define XINYI_CPU_HZ 60000000u
#endif
#if XINYI_CPU_HZ != 60000000u && XINYI_CPU_HZ != 70000000u && XINYI_CPU_HZ != 75000000u
#error "Unreviewed Xinyi CPU clock"
#endif
#endif
