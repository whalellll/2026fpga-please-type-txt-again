/* Display-only, source-bound measurement values. Each value applies only to
 * the named operator scope below, never to full recognition or game latency.
 * CPU60 bounded operator receipts select 37.64x / 2.35x / 7.83x. The voice_4
 * candidate has different weights and keeps its own unmeasured value. After any
 * edit, regenerate the independent r17 home cache with
 * scripts/prepare_xinyi_battle_home_r17.py; stale cache values fail compilation.
 * Historical target/resource identities stay in evidence, not visible labels. */
#ifndef XINYI_BATTLE_SPEEDUPS_R17_H
#define XINYI_BATTLE_SPEEDUPS_R17_H
#ifndef XY17_IMAGE_SPEEDUP
#define XY17_IMAGE_SPEEDUP "37.64×"
#endif
#ifndef XY17_VOICE_SPEEDUP
#define XY17_VOICE_SPEEDUP "2.35×"
#endif
#ifndef XY17_NNUE_SPEEDUP
#define XY17_NNUE_SPEEDUP "7.83×"
#endif
#ifndef XY17_VOICE4_SPEEDUP
#define XY17_VOICE4_SPEEDUP "待测"
#endif
#if XINYI_ASR_VOICE4
#define XY17_ACTIVE_VOICE_SPEEDUP XY17_VOICE4_SPEEDUP
#else
#define XY17_ACTIVE_VOICE_SPEEDUP XY17_VOICE_SPEEDUP
#endif
#define XY17_IMAGE_SPEEDUP_SCOPE "卷积算子"
#define XY17_VOICE_SPEEDUP_SCOPE "语音CNN"
#define XY17_NNUE_SPEEDUP_SCOPE "NNUE MLP"
#endif
