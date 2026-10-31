/* Static inference parameter counts, independently audited from the frozen
 * exported tensor descriptors. Packed copies/requant metadata are excluded.
 * Image: 427164 + 1778107 + 128927 = 2334198 weights+bias.
 * ASR: 11664 + 118 = 11782 for balanced24 and voice_4.
 * Full PFF1 NNUE: feature/PSQT 64567344 + MLP 560144 = 65127488.
 * Evidence: model-metrics-{frozen,voice}-r01 in the private r17 build root. */
#ifndef XINYI_BATTLE_METRICS_R17_H
#define XINYI_BATTLE_METRICS_R17_H
#define XY17_IMAGE_PARAMETERS "参数量：2,334,198"
#define XY17_VOICE_PARAMETERS "参数量：11,782（权重+bias）"
#define XY17_PIKAFISH_PARAMETERS "参数量：65,127,488"
#endif
