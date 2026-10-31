#ifndef XQVOICE_PROFILE_H
#define XQVOICE_PROFILE_H
#include <stdint.h>
enum {
 XQVP_MODEL_READ,XQVP_INPUT_READ,XQVP_MODEL_CHECK,XQVP_CAPTURE,XQVP_FEATURE,
 XQVP_WINDOW,XQVP_FFT,XQVP_POWER,XQVP_MEL_QUANT,XQVP_MAC_OPEN,XQVP_CNN,
 XQVP_LAYER0,XQVP_LAYER1,XQVP_LAYER2,XQVP_LAYER3,XQVP_LAYER4,
 XQVP_PACK,XQVP_MAC_WAIT,XQVP_REQUANT,XQVP_TRACE,XQVP_DECODE,XQVP_COUNT
};
#ifdef XQVOICE_PROFILE_ENABLED
void xqvp_init(void);
void xqvp_reset(void);
uint64_t xqvp_now(void);
void xqvp_add(unsigned stage,uint64_t ticks);
void xqvp_capture_ended(void);
void xqvp_mac(uint64_t jobs,uint64_t cycles);
void xqvp_emit(int status);
#else
static inline void xqvp_init(void) {}
static inline void xqvp_reset(void) {}
static inline uint64_t xqvp_now(void) {return 0;}
static inline void xqvp_add(unsigned s,uint64_t t) {(void)s;(void)t;}
static inline void xqvp_capture_ended(void) {}
static inline void xqvp_mac(uint64_t j,uint64_t c) {(void)j;(void)c;}
static inline void xqvp_emit(int s) {(void)s;}
#endif
#endif
