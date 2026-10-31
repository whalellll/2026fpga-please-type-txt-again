#ifndef XQ_WHOLE_BANK_H
#define XQ_WHOLE_BANK_H
#include <stdint.h>
/* Immutable SD sidecar, loaded/CRC-checked by the paired bootloader into an
 * exact DT reserved-memory/no-map range. Never map a guessed DDR address.
 * Single-threaded preparation/playback caller; no device access in release. */
#define XQ_WHOLE_BANK_CONFIG_NAME "whole-bank.cfg"
#define XQ_WHOLE_BANK_DT_NODE "/sys/firmware/devicetree/base/reserved-memory/xinyi-whole-voice@4000000"
#define XQ_WHOLE_BANK_BASE 0x04000000u
#define XQ_WHOLE_BANK_LIMIT 0x0f000000u
#define XQ_WHOLE_BANK_ENTRIES 5103u
#define XQ_WHOLE_BANK_MAX_SAMPLES 15360u
/* 0: descriptor absent (file bank may be used); 1: ready; -1: present but
 * invalid/unavailable (must not silently fall back). Replaces any old bank. */
int xq_whole_bank_prepare(const char *config_directory);
/* 1: allocated complete ordinary-RAM S16 samples, caller frees; 0: not ready
 * or no key; -1: invalid key/read/bounds/CRC. fd and map are released before
 * return, including failure. No file/mmap data survives into RT playback. */
int xq_whole_bank_load(const uint8_t tokens[4],int16_t **samples,unsigned *count);
/* Same complete copy/CRC/close/unmap contract into caller-owned ordinary RAM.
 * capacity is S16 samples; no allocation. count=0 on failure, and destination
 * may then contain partial/unverified bytes which must never be played. */
int xq_whole_bank_load_into(const uint8_t tokens[4],int16_t *samples,unsigned capacity,unsigned *count);
void xq_whole_bank_release(void);
#endif
