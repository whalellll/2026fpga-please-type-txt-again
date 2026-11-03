/* SPDX-License-Identifier: GPL-2.0 */
#ifndef PANGO_MAC_IO32_ORDERED_H
#define PANGO_MAC_IO32_ORDERED_H
/* All aperture addresses are word aligned; the reserved aperture size is a
 * multiple of four. The caller validates the logical range before entry.
 * Never use memcpy_toio/fromio on V3.5: their byte transactions may stall.
 * A compact byte tail preserves neighbours with one aligned read/modify/write.
 */
#if 0
/* Scratch is RAM through the default devm_ioremap mapping, not a register
 * FIFO. Keep full normal-memory/I/O barriers around each bounded copy while
 * retaining ordered, word-only device accesses inside it. The caller keeps
 * run_lock and the existing DMA START/DONE barriers. */
#define pango_io32_read readl_relaxed
#define pango_io32_write writel_relaxed
#else
#define pango_io32_read readl
#define pango_io32_write writel
#endif
static inline void pango_mac_toio32_ordered(void __iomem *target, const void *source,
                                  unsigned bytes)
{
    const u8 *src = source;
    u8 __iomem *dst = target;
    unsigned i = 0, j;
    u32 word;
#if 0
    if (bytes)
        mb();
    if (!((unsigned long)src & 3)) {
        for (; bytes - i >= 4; i += 4) {
            memcpy(&word, __builtin_assume_aligned(src + i, 4), 4);
            pango_io32_write(word, dst + i);
        }
    } else
#endif
    for (; bytes - i >= 4; i += 4) {
        memcpy(&word, src + i, 4);
        pango_io32_write(word, dst + i);
    }
    if (i < bytes) {
        word = pango_io32_read(dst + i);
        for (j = 0; i + j < bytes; ++j)
            word = (word & ~(0xffu << (8u*j))) | ((u32)src[i+j] << (8u*j));
        pango_io32_write(word, dst + i);
    }
#if 0
    if (bytes)
        mb();
#endif
}
static inline void pango_mac_fromio32_ordered(void *target, const void __iomem *source,
                                    unsigned bytes)
{
    u8 *dst = target;
    const u8 __iomem *src = source;
    unsigned i = 0, j;
    u32 word;
#if 0
    if (bytes)
        mb();
    if (!((unsigned long)dst & 3)) {
        for (; bytes - i >= 4; i += 4) {
            word = pango_io32_read(src + i);
            memcpy(__builtin_assume_aligned(dst + i, 4), &word, 4);
        }
    } else
#endif
    for (; bytes - i >= 4; i += 4) {
        word = pango_io32_read(src + i);
        memcpy(dst + i, &word, 4);
    }
    if (i < bytes) {
        word = pango_io32_read(src + i);
        for (j = 0; i + j < bytes; ++j)
            dst[i+j] = (u8)(word >> (8u*j));
    }
#if 0
    if (bytes)
        mb();
#endif
}
#undef pango_io32_read
#undef pango_io32_write
#endif

/* SPDX-License-Identifier: GPL-2.0 */
#ifndef PANGO_MAC_IO32_BULK_H
#define PANGO_MAC_IO32_BULK_H
/* All aperture addresses are word aligned; the reserved aperture size is a
 * multiple of four. The caller validates the logical range before entry.
 * Never use memcpy_toio/fromio on V3.5: their byte transactions may stall.
 * A compact byte tail preserves neighbours with one aligned read/modify/write.
 */
#if 1
/* Scratch is RAM through the default devm_ioremap mapping, not a register
 * FIFO. Keep full normal-memory/I/O barriers around each bounded copy while
 * retaining ordered, word-only device accesses inside it. The caller keeps
 * run_lock and the existing DMA START/DONE barriers. */
#define pango_io32_read readl_relaxed
#define pango_io32_write writel_relaxed
#else
#define pango_io32_read readl
#define pango_io32_write writel
#endif
static inline void pango_mac_toio32_bulk(void __iomem *target, const void *source,
                                  unsigned bytes)
{
    const u8 *src = source;
    u8 __iomem *dst = target;
    unsigned i = 0, j;
    u32 word;
#if 1
    if (bytes)
        mb();
    if (!((unsigned long)src & 3)) {
        for (; bytes - i >= 4; i += 4) {
            memcpy(&word, __builtin_assume_aligned(src + i, 4), 4);
            pango_io32_write(word, dst + i);
        }
    } else
#endif
    for (; bytes - i >= 4; i += 4) {
        memcpy(&word, src + i, 4);
        pango_io32_write(word, dst + i);
    }
    if (i < bytes) {
        word = pango_io32_read(dst + i);
        for (j = 0; i + j < bytes; ++j)
            word = (word & ~(0xffu << (8u*j))) | ((u32)src[i+j] << (8u*j));
        pango_io32_write(word, dst + i);
    }
#if 1
    if (bytes)
        mb();
#endif
}
static inline void pango_mac_fromio32_bulk(void *target, const void __iomem *source,
                                    unsigned bytes)
{
    u8 *dst = target;
    const u8 __iomem *src = source;
    unsigned i = 0, j;
    u32 word;
#if 1
    if (bytes)
        mb();
    if (!((unsigned long)dst & 3)) {
        for (; bytes - i >= 4; i += 4) {
            word = pango_io32_read(src + i);
            memcpy(__builtin_assume_aligned(dst + i, 4), &word, 4);
        }
    } else
#endif
    for (; bytes - i >= 4; i += 4) {
        word = pango_io32_read(src + i);
        memcpy(dst + i, &word, 4);
    }
    if (i < bytes) {
        word = pango_io32_read(src + i);
        for (j = 0; i + j < bytes; ++j)
            dst[i+j] = (u8)(word >> (8u*j));
    }
#if 1
    if (bytes)
        mb();
#endif
}
#undef pango_io32_read
#undef pango_io32_write
#endif

/* SPDX-License-Identifier: GPL-2.0 */
#ifndef PANGO_MAC_IO32_UNROLLED_H
#define PANGO_MAC_IO32_UNROLLED_H
/* All aperture addresses are word aligned; the reserved aperture size is a
 * multiple of four. The caller validates the logical range before entry.
 * Never use memcpy_toio/fromio on V3.5: their byte transactions may stall.
 * A compact byte tail preserves neighbours with one aligned read/modify/write.
 */
#if 1
/* Scratch is RAM through the default devm_ioremap mapping, not a register
 * FIFO. Keep full normal-memory/I/O barriers around each bounded copy while
 * retaining ordered, word-only device accesses inside it. The caller keeps
 * run_lock and the existing DMA START/DONE barriers. */
#define pango_io32_read readl_relaxed
#define pango_io32_write writel_relaxed
#else
#define pango_io32_read readl
#define pango_io32_write writel
#endif
static inline void pango_mac_toio32_unrolled(void __iomem *target, const void *source,
                                  unsigned bytes)
{
    const u8 *src = source;
    u8 __iomem *dst = target;
    unsigned i = 0, j;
    u32 word;
#if 1
    if (bytes)
        mb();
    if (!((unsigned long)src & 3)) {
        for (; bytes - i >= 16; i += 16) {
            u32 w0, w1, w2, w3;
            memcpy(&w0, __builtin_assume_aligned(src+i,4),4);
            memcpy(&w1, __builtin_assume_aligned(src+i+4,4),4);
            memcpy(&w2, __builtin_assume_aligned(src+i+8,4),4);
            memcpy(&w3, __builtin_assume_aligned(src+i+12,4),4);
            pango_io32_write(w0,dst+i);
            pango_io32_write(w1,dst+i+4);
            pango_io32_write(w2,dst+i+8);
            pango_io32_write(w3,dst+i+12);
        }
        for (; bytes - i >= 4; i += 4) {
            memcpy(&word, __builtin_assume_aligned(src + i, 4), 4);
            pango_io32_write(word, dst + i);
        }
    } else
#endif
    for (; bytes - i >= 4; i += 4) {
        memcpy(&word, src + i, 4);
        pango_io32_write(word, dst + i);
    }
    if (i < bytes) {
        word = pango_io32_read(dst + i);
        for (j = 0; i + j < bytes; ++j)
            word = (word & ~(0xffu << (8u*j))) | ((u32)src[i+j] << (8u*j));
        pango_io32_write(word, dst + i);
    }
#if 1
    if (bytes)
        mb();
#endif
}
static inline void pango_mac_fromio32_unrolled(void *target, const void __iomem *source,
                                    unsigned bytes)
{
    u8 *dst = target;
    const u8 __iomem *src = source;
    unsigned i = 0, j;
    u32 word;
#if 1
    if (bytes)
        mb();
    if (!((unsigned long)dst & 3)) {
        for (; bytes - i >= 16; i += 16) {
            u32 w0=pango_io32_read(src+i);
            u32 w1=pango_io32_read(src+i+4);
            u32 w2=pango_io32_read(src+i+8);
            u32 w3=pango_io32_read(src+i+12);
            memcpy(__builtin_assume_aligned(dst+i,4),&w0,4);
            memcpy(__builtin_assume_aligned(dst+i+4,4),&w1,4);
            memcpy(__builtin_assume_aligned(dst+i+8,4),&w2,4);
            memcpy(__builtin_assume_aligned(dst+i+12,4),&w3,4);
        }
        for (; bytes - i >= 4; i += 4) {
            word = pango_io32_read(src + i);
            memcpy(__builtin_assume_aligned(dst + i, 4), &word, 4);
        }
    } else
#endif
    for (; bytes - i >= 4; i += 4) {
        word = pango_io32_read(src + i);
        memcpy(dst + i, &word, 4);
    }
    if (i < bytes) {
        word = pango_io32_read(src + i);
        for (j = 0; i + j < bytes; ++j)
            dst[i+j] = (u8)(word >> (8u*j));
    }
#if 1
    if (bytes)
        mb();
#endif
}
#undef pango_io32_read
#undef pango_io32_write
#endif
