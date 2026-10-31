/* User-specified presentation values; these do not configure the CPU clock
 * or replace measured CoreMark results on the benchmark page. The LUT
 * denominator is the existing CPU-core reference, including LUTRAM. */
#ifndef XINYI_UI_COPY_R20_H
#define XINYI_UI_COPY_R20_H
#define XY20_CM_PER_MHZ "5.278"
#define XY20_CPU_FREQUENCY "80 MHz"
#define XY20_CM_SCORE 316.729078
#define XY20_CPU_CORE_LUTS 20125
#define XY20_CM_PER_LUT "0.015738"
#define XY20_IMAGE_MODEL "模型：棋盘四角定位192×192\nYOLOv5n识别640×640\n棋子分类32×32"
#define XY20_IMAGE_ACCELERATOR "加速器：32 个int8×int8 PE卷积加速器"
#define XY20_IMAGE_ACCELERATOR_WRAP "加速器：32 个int8×int8 PE\n卷积加速器"
#define XY20_VOICE_MODEL "模型：CNN频谱特征提取+\nCTC语音对齐文字"
#define XY20_VOICE_ACCELERATOR "加速器：微型语音 NPU"
#define XY20_NNUE_MODEL "模型：开源中国象棋引擎Pikafish\n+NNUE局面评估"
#define XY20_NNUE_ACCELERATOR "加速器：NNUE评估专用硬件加速\n（特征变换层 + NNUE MLP\n多层感知机层）"
#define XY20_CPU_NOTE "cpu指标百分比由ILA实测"
#endif
