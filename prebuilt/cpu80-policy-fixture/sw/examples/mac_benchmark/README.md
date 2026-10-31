# MAC 加速器瓶颈压力测试

`mac_benchmark.bin` 是针对 SOC_linux V6.5 集成、固定 49.5 MHz SYS 域和 MAC ABI `0x00020100` 的 RV32IMA
裸机测试程序。发布位流由本轮 `soc_top` 工程原生生成。程序启动时会检查稳定系统 ID 和 49.5 MHz 系统时钟；
只有要让 RTL 优化生效时才需要重新生成并下载位流。程序只访问为 MAC 预留的 1 MiB
DDR 暂存窗口，不擦写 Flash。

当前 SoC 还同时包含 HID MMIO `0x1fe00400-0x1fe00427`、同一 MAC 窗口高半区的
象棋稀疏评估器 `0x1fe10080-0x1fe100ff`，以及 framebuffer DMA
`0x1fe11000-0x1fe110ff`。本程序只测试密集 MAC 的低半区
`0x1fe10000-0x1fe1007f`，不能单独证明合并后的 HID、稀疏评估器、framebuffer 或
整套 SOC_linux V6.5 已通过实板验收。启动版本取自 `bootloader/release_version.h`，
应先运行当前版本 bootloader 构建，再构建和装载本例程。

## 覆盖范围

- CPU 对非缓存 DDR 的顺序写、顺序读和复制带宽；
- MAC DMA 的输入、权重、偏置读取阶段和输出写回阶段；
- MAC 核心计算阶段以及端到端有效 MAC 吞吐；
- tiny、输入密集、权重密集、输出密集和最大计算量矩阵；
- 最大任务连续运行 32 次的最小、最大、平均周期；
- CPU 与 MAC DMA 同时访问不同 DDR 区域时的仲裁压力和减速比例；
- 每次任务的全量结果校验。输入和权重均为 1，I32 输出必须等于 `Cin`。

当前密集 MAC 接口只支持一次提交完整的“DMA 读入、计算、DMA 写回”任务，没有独立 DMA
命令。程序通过状态寄存器公开的 DMA FSM 状态和 SYS 49.5 MHz CLINT 计时器测量各阶段；
`hw_total` 则来自硬件自身的 `CYCLES` 寄存器。很短的 tiny 用例会受到软件采样粒度
影响，判断瓶颈应以 `max_compute`、`max_bias_dma` 和重复统计为主。

## 构建

```powershell
cd D:\projects\performance_soc
.\scripts\build_mac_benchmark_wsl.ps1
```

输出文件：

- `artifacts/mac_benchmark.elf`
- `artifacts/mac_benchmark.bin`
- `artifacts/mac_benchmark.disasm.txt`
- `linux/boot/mac_benchmark.bin`

## 在已有位流上运行

串口/XMODEM 自动运行：

```powershell
.\scripts\serial_mac_benchmark.ps1 -PortName COM17
```

也可以启动仓库 TFTP 服务后，在 bootloader 中运行：

```text
tftp 192.168.1.2 mac_benchmark.bin 0x01000000
boot 0x01000000
```

成功结束标志为 `MAC_STRESS_PASS`，串口脚本同时保存
`artifacts/board_mac_benchmark.log`。

## 报告字段

| 前缀 | 含义 |
|---|---|
| `CPU_MEM_*` | CPU 非缓存 DDR 带宽和校验结果 |
| `MAC_PHASE` | input、weight、bias、compute、output 分阶段周期 |
| `MAC_RATES` | DMA 读写带宽、核心及端到端 MAC/cycle |
| `MAC_BOTTLENECK` | 当前形状占比最大的阶段 |
| `MAC_REPEAT` | 连续压力测试的平均、最小、最大周期及 MMAC/s |
| `DDR_CONTENTION` | CPU 制造 DDR 流量后的 MAC 减速倍数 |

判读建议：`weight_heavy` 的 DMA 读比例高而 `max_compute` 的计算比例上升，说明拆分
正常；若 `DDR_CONTENTION slowdown` 明显大于 `1.000`，共享 DDR/仲裁是实际瓶颈；若
`max_compute` 中 `COMPUTE` 长期占主导，则应优先扩展计算阵列或提高 MAC 时钟。

## RTL 优化结果

零等待存储模型用于隔离 RTL 本身的控制开销。输入 DMA 跨 64-bit 输入行合并 burst、
`zero_bias` 直接整行清零、输出 BRAM 读等待缩短后，结果如下：

| U8×S8 任务 | 优化前 | 优化后 | 周期减少 | 核心等待/优化后总周期 |
|---|---:|---:|---:|---:|
| `1x32x128` | 2,244 | 1,790 | 20.2% | 326/1,790（18.2%） |
| `1x32x256` | 4,460 | 3,558 | 20.2% | 650/3,558（18.3%） |
| `16x256x256` | 56,844 | 47,500 | 16.4% | 17,538/47,500（36.9%） |

完整 SoC 的固定自测由 241 降到 161 周期，减少 33.2%。虽然控制开销已经下降，H256
单像素任务仍有约 81.7% 的周期位于 DMA/装载/写回路径；其中 8 KiB 权重流量是主要
下限。实际 DDR 的等待与争用只会进一步放大数据搬运占比，应以实板生成的
`artifacts/board_mac_benchmark.log` 做最终判断。完整分析见
`docs/MAC加速完整SoC说明.md`。

以下是合并前 27 MHz MAC 功能位流在 2026-09-13 的历史记录，并非当前 49.5 MHz
组合 V3 的实板结果：当时通过 `MAC_STRESS_PASS`，H256 平均 6,813 周期、
32.464 MMAC/s，最大任务平均 76,521 周期、369.984 MMAC/s；两项 MMAC/s 都按
27 MHz 换算。权重密集 DMA 读约
41.34 MiB/s，输出密集 DMA 写约 31.85 MiB/s。CPU/MAC 并发时最大任务减速
1.376 倍，说明下一步应优先减少象棋搜索中的重复权重打包和传输。当前 V3 必须用
重新构建的 49.5 MHz 测试程序和组合位流重测，不能把这些历史吞吐数字按频率缩放后
当作实测值。

与本基准分开的 `xiangqi_fb_demo.bin` 只是自动换页的非交互棋盘显示，不读取 HID；
`xiangqi_service.bin` 是预编译串口服务，而仓库缺少对应服务端源文件，无法从当前源码
复现构建。
