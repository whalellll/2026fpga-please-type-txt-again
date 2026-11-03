# HWC 验收 kit（T4a → 训练侧 T4b）

这是 **Linux x86_64 / WSL** 的功能验收工具。`integer-host` 为静态 ELF，无
FPGA/驱动依赖；图执行、算子、打包代码来自 aa134da/da0f914，硬件调用连接到
独立标量 CPU oracle，模拟 exact4/5 的点积、ties-even S16 与 LUT。
程序打印的时间不代表实板速度。运行脚本需要 Python ≥3.9；PNG 解码另需 Pillow。
RGB565、RGB8、原始 NCHW F32 路径无需 Pillow。无需 PyTorch/NumPy。

```sh
chmod +x integer-host hwc-convert
python3 selftest.py
# 推荐：保留训练侧既有、同一帧的 ROI/letterbox/归一化，只替换检测器。
python3 convert.py --format nchw-f32 --input detector-input.f32 --output frame.hwc8
./integer-host models/detector.xqi frame.hwc8 1 frame.heads.f32
# 原始相机文件是 1280x720、小端 RGB565；ROI 必须来自当前帧。
python3 convert.py --format rgb565 --input frame.rgb565 --roi X0 Y0 X1 Y1 --output frame.hwc8
# RGB8 PNG：不做 ICC/gamma 转换，不支持透明、调色板或灰度的隐式转换。
python3 convert.py --format png --input frame.png --roi X0 Y0 X1 Y1 --output frame.hwc8
```

输入原始图像限宽≤1280、高≤720，RGB565 固定1280×720。PNG 只负责无损 RGB8
解码，resize 在 C 内完成。ROI 为半开区间 `[x0,x1)×[y0,y1)`；不能沿用上一帧
几何。全图检测时显式使用 `0 0 W H`。裁剪后采用产品现有 OpenCV 字节语义
resize、禁止放大、填充114、居中 letterbox 至640×640，再以精确 F32
`pixel/255.f` 归一化、冻结的 `xqi_quantize` ties-even/saturating S8 量化。
`nchw-f32` 接受恰好 `3*640*640*4` 字节的小端 F32，顺序RGB、NCHW，不再
resize/crop/归一化；用于保持训练侧已有预处理不变。拒绝 NaN/Inf。

`models/detector.xqm` 是当前 working-r14 原始包，SHA256
`d65b4b8686520ae1546d0a207c1bcb9f30efe0d40e7f5c8245c4dd11ff9ca09d`。
`models/detector.xqi` 是该包的 HWC 派生，SHA256
`d72d039041b41310f037344772eb75ce895ec6fe678bbb31ed547a7ad7453942`。
运行器和转换器均拒绝其他 XQI SHA。`expected.json` 记录输入指数及三个合成
用例的输入/全头 SHA、头值 CRC；`SHA256SUMS.txt` 覆盖 kit 的全部其他文件。
这不是 r24b `candidate_r19_detrecal` 的重新导出，不能沿用其 S16 157/178
验收。训练报告须注明实际 XQM/XQI 身份、原 runner/模型/预处理身份与差异。

`.hwc8` 文件共1,638,440字节：40字节头 +640×640×4字节主体。头为
小端 `<8s6IiI>`：magic=`XQHWC81\0`、version=1、width=640、height=640、
channels=3、pitch=4、body_bytes=1638400、有符号量化指数、主体 CRC32。
主体为按行排列的 HWC4 **signed INT8 RGB**，第四通道固定0。
整数值代表 `q*2**exponent`，不能把 unsigned RGB 字节直接填进去。

输出 `frame.heads.f32` 共1,915,248字节，是顺序连接的三条记录；每条先放
4个小端U32维度 `N,C,H,W`，紧接小端 IEEE754 F32 NCHW 张量。维度依次
`1,57,80,80`、`1,57,40,40`、`1,57,20,20`。通道为3 anchor×19，19项为
`tx,ty,tw,th,obj,14 classes`；值是 **raw logits**，尚未 sigmoid/解码/NMS。
程序 `output_crc` 只拼接三头的 F32 值，**不含维度**；输出 SHA 包含维度。
固定输入 CRC 应为 `97265de4`，完整输出 SHA
`e7c03029168e2ef7493733d9edd114c8326b2adec8653e374a4ea8aeec6887a9`。

后处理入口见 `reference/xq_native_worker.c` 的 `detector_boxes` 与
`reference/native_parameters.h`。步幅8/16/32；YOLO 解码为
`xy=(sigmoid(txy)*2+grid-.5)*stride`、
`wh=(sigmoid(twh)*2)**2*anchor`、
`score=sigmoid(obj)*sigmoid(class)`。14类编号为红K/A/B/N/R/C/P，
再黑K/A/B/N/R/C/P。产品参考解码是多标签、阈值`.001`、class-aware
NMS `.6`、稳定分数/原顺序、prelimit30000、max300；随后还需当前帧
letterbox/ROI 逆变换及原分类器/几何链。训练侧须保持其既有后处理、
board/cls/几何/FEN不变；若 runner 与该参考不同，先明确差异，不能顺手改阈值。
合成输入无可验收的真实棋盘，不能用于质量统计。

T4b 由训练侧接入本后端，运行 CAMERA_v2 全178帧与dev37抽查，交回逐帧
结果、汇总、相对 FP32 的 FEN 一致率和与 S16 的差异归因，门槛≥156/178。
工程侧仅运行本包合成自检，不接触 CAMERA_v2/game2 帧。该指标是与 FP32
一致率，不能称为真实标签准确率。此 kit 不建立实板时延或产品识别验收。

源码和构建输入在 `source/`，构建命令见 `build-commands.json`，来源、编译器
与已通过的独立全图比对见 `provenance.json`。失败应原样回交，勿改模型、
scale/LUT、阈值或几何 guard 来获得通过。
