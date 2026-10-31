# 加速器优化候选：32 位权重写入与 AXI 读请求直发

日期：2026-10-17。状态：RTL 仿真与整机 ADS 综合通过，未布局布线、未上板。

本页记录已封存的两项组合候选。后续加入输出 bank 首次读取重叠的版本正在
[CPU 70 MHz 优化](CPU_70MHz_Optimization_20261017.md)中独立构建与验收；
该版本的时钟、资源和最终时序以新记录为准，不继承本页候选的输入身份。

## 当前配置与目标

工程为 `performance_soc_voice_hw`，CPU 59.4 MHz、SYS 49.5 MHz，PG2L100H。
启用 dense、sparse 与 PFF1 gather；卷积关闭，当前权重 bank 为 64 行，FP8 关闭。
目标是保留算术、公开寄存器、内存布局及单事务顺序，减少提交后的硬件周期与中间寄存器。
板上仍运行原语音候选位流 `78487ddbd5cfe0cf88fab2d952a2d8f82c81565e870d859518b7ed5c2aa4d1b5`，未替换。

## 实现

1. `MacAccelCore.v` 的 compact 权重 RAM 增加可选按字写入。DMA 的每个 32 位 DDR 权重字直接写入对应 RAM bank；省去 1024 位整行拼接寄存器。读取仍是一拍，保持 read enable、复位输出与同址旧值语义，并保留已有物理 identity LUT。
2. `mac_accel_dma_kernel.v` 仅在 64 行配置启用该路径。默认直接调用 core 仍使用旧宽写接口，1024 行 DMA 保留原路径。权重最后一个字的可见时刻不变。
3. `mac_accel_axi_master32.v` 接收新读命令时同步发出 AR；ARREADY 低则锁存地址和长度继续等待，AR 负载在背压期间稳定，仍只允许一个在途事务。写路径和错误汇总规则不变。

没有新增 Verilog function；新增生成循环为 32 次，未更改 CPU、模型整数规则或公开硬件 ABI。

## 整机资源

三次均为 PDS 2022.2-SP6.4、同器件、同 `soc_top` 参数的 ADS 综合。
基线与仅按字版本恰有两个 RTL 输入不同；组合版本恰有上述三个 RTL 输入不同，全部其他声明输入逐哈希相同。

| 资源 | 基线 | 仅按字写入 | 两项组合 | 组合减基线 |
|---|---:|---:|---:|---:|
| LUT | 43128 | 43174 | 43148 | +20 |
| 寄存器 | 35509 | 34522 | 34521 | -988 |
| 其中 LUTRAM | 4436 | 4436 | 4436 | +0 |
| DRM36K 等效 | 120.5 | 120.5 | 120.5 | +0 |
| APM / DSP | 177 | 177 | 177 | +0 |

这是用少量 LUT 换取寄存器和延迟的取舍；没有减少块 RAM 或 DSP。
当前较紧的 DRM/APM 预算仍在，不能据此增加一组大卷积阵列。
整机 ADS 映射不是最终布局资源或 STA；两处原有权重 identity LUT 也不能证明新布线的 hold 通过。

## 相同工作量的周期

以下计数来自 RTL 的真实作业周期寄存器及共享 AXI RAM 模型。基线/候选使用相同测试输入，输出与 DDR 传输字节数相同；仅按字版本周期完全一致。

| 用例 | 原周期 | 组合周期 | 周期减少 |
|---|---:|---:|---:|
| S16 small | 132 | 127 | 3.79% |
| DDR bias | 239 | 228 | 4.60% |
| Packed tail | 409 | 392 | 4.16% |
| Pikafish 256x32 | 5051 | 4779 | 5.39% |
| Max Cout packed | 1290 | 1257 | 2.56% |
| Max Cout S16 | 1962 | 1897 | 3.31% |
| Max pixels | 933 | 925 | 0.86% |
| Sparse | 1211 | 1162 | 4.05% |
| Concurrent gather | 3703 | 3538 | 4.46% |
| Max S16 output | 13788 | 13720 | 0.49% |

256→32 U8S8 作业减少的 272 拍对应 256 个权重读 burst 加 16 个输入读 burst，各省一拍。
DDR 等待、缓存、CPU 打包、ioctl 与整盘搜索未按这些比例测量，不能将约 5.4% 硬件周期减少直接称为 Pikafish 整体提速。
当前 XQT1 语音分类由 CPU 的 `xqvoice_model.c` 整数 dense 执行，未接入该 MAC；本次没有语音识别加速数据。

## 验证范围

- 新测试先在旧实现失败，然后实现：按字 bank 测试验证 4096 次字写入与 134 次读检查；AXI 测试验证 32 组正常读、144 个响应字、地址/响应背压、早/缺失 RLAST、复位恢复及独立 AW/W 握手。
- 完整真实 core+DMA+AXI+仲裁器测试分别比较 64 行和 1024 行配置，覆盖尾通道、256 输入、256 输出、16 像素、最大 4096 输出、DDR/零 bias 切换、scratch 边界与越界拒绝，以及 dense/gather/CPU 并发。结果与流量一致，周期未增加。
- DMA 输出流 15 组用例验证 W 背压、4 KiB/32 B 边界、写错误及下一作业恢复；bias、lane、输出布局、FP8 exhaustive 回归通过。
- 四项音频 RTL 回归、三项 voice 硬件契约检查、CPU 来源及全时钟配置检查通过；组合 ADS 的 CPU 控制锥审计通过。
- 未跑全套 SoC/CPU 软件回归、RTL CoreMark、PnR、双角 STA、实板同负载对照或 Linux 并发压力。本候选不是正式 BoardRelease。

## 兼容性与容量

Pikafish 当前 FC0 的 256→32 U8S8 需要 64 行，容量没有缩减。
64 行仍不是通用 YOLO 大层容量；1024 行配置与 FP8 通用路径保留并回归，但本轮整机资源只对应 64 行、FP8 关闭配置。
语音的 40→64→32→25 模型、GUI 及显示用途保持现有状态；仅音频相关仿真通过，尚无新位流的实板共存结论。

## 复现与下一步

```bash
python3 scripts/test_mac_weight_word.py --output build/mac-dma-check \
  --baseline build/mac-weight-word-20261017/synth/original
```

不提供 `--baseline` 时运行候选功能测试；baseline 目录需要三个优化前的原 RTL 文件。
整机资源脚本 `scripts/check_mac_weight_word_synth.ps1` 从声明的 PDS 输入建立隔离目录，分别以 `baseline`、`candidate`（仅按字）与 `combined` 综合；仅 ADS、不路由、不写板。
每次最多 600 秒，日志给出 owner PID，结束该 owner 会关闭其 Windows 子任务。

后续验收应先完成完整相关回归与资源/CPU/CDC 门禁，再用相同候选做受预算约束的 PnR 和 slow/fast STA；通过后才进行易失 CRAM 板测，复测 Stage A/B 黄金结果、dense、GUI 与录音并发及实测时间。
阶段性资料：[结果及哈希](validation/mac-optimization-20261017/results.json)、[仿真明细](validation/mac-optimization-20261017/simulation.json)、三组 `.snr` 与输入清单。

2026-10-18 补充：集成相同 MAC/音频源码的 CPU 70.875 MHz 候选
`4b7d86bb5f2a4e638b43359196ea52b3` 已通过正常完整构建及正式双角 STA，
SYS/MAC 仍为 49.5 MHz，38 个仿真输入哈希逐项相同。CPU setup WNS +0.166 ns，
hold 慢/快角 +0.069/+0.052 ns。该结果不回填为旧独立 MAC ZIP 的物理验收，
新位流的实板性能尚待连接板卡后测量。详见
[CPU 候选最终结果](CPU_70MHz_Optimization_20261017.md)。
