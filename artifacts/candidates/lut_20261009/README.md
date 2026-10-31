# LUT 优化候选：2026-10-09

这是 `feature/nnue-gather-10ms` 的已上板开发候选。PG2L100H-6-FBG676，系统时钟
49.5 MHz；整机 34,206 LUT / 28,934 FF / 191 APM / 150 DRM。
原生四角最终时序通过：慢角 setup/hold +0.862/+0.137 ns，快角 +3.081/+0.100 ns。

`soc_v2_top.sbit` SHA-256：
`2e5087a4336399002f51258cb8525be6dfc025fcef401e0df2de912bac071ead`。
`candidate.json` 记录位流、时序、资源报告和有效约束的逐文件哈希；`soc_v2_top.rtr`
为完整原生最终报告，`accepted_ddr_actual.pcf` 为核对过的实际布局。
`stage2_sources.sha256` 保留构建时原始字节哈希；`source_inputs.json` 同时记录仅将
CRLF 转成 LF 后的哈希，供 Git 跨平台检出核对。换行归一不改变原始构建记录。

匹配源码重新构建的参数为：

```powershell
./scripts/build_mac_conv_stage2_soc_candidate.ps1 `
  -OutputDir build/vision/lut_snapshot_rebuild `
  -PlacementSeed 1 -RouteSeed 1 -PlacementDecongestion 2 `
  -HoldThresholdPs 100 -HoldFixIterations 12 -OptimizeMultiCornerTiming `
  -ExtraPlacementPcf pds/yolo_incremental_ddr.pcf
```

重新构建仍须复核最终时序和实际约束位置；不保证位流逐字节可重现。
已测卷积、训练权重六个特征块、NNUE 整数、resident 双 fd、context 池和调度；
详细范围见 [LUT 板测记录](../../../docs/YOLOv5n_LUT_Board_20261009.md)和
[Pikafish 瓶颈报告](../../../docs/Pikafish_Bottleneck_20261009.md)。
NNUE 10 ms、完整 YOLO 30 fps、真实语音识别及并发无丢样仍待完成。
本目录与根目录生产位流分开，完整 SoC 发布仍按 TODO 门槛进行。
