/* Preserve P3 whole-layer jobs with private CPU transpose locality. Oversized
 * layers use rectangular spatial tiles with halo instead of many tiny matrix
 * submissions. r14 graph/weights, raw I32, ties-even S16/LUT and error guards
 * remain unchanged. The upstream overlay and its math source stay immutable;
 * this private loop ordering needs its own board performance measurement. */
#include "vision32_locality.c"
