# SoC V2.1 架构：CPU V3.5 + NNUE 加速与稳定 ABI

2026-10-25现役硬件源码已同步main P3 CPU60/SYS49.5/1080p30、sbit`6565ad37…`。
V321图像选择main矩形空间分块/halo快路径，专用NNUE启用batch；软件排空检查覆盖第五路batch。
本产品的32位aperture安全搬运和严格后端策略保留，详见
[当前离线说明](PictureNew_离线完成与main同步_20261025.md)。以下CPU80和9ba02f10描述是历史版本，
不代表本轮PN04板验已完成。

2026-10-23 当前源码硬件已切到origin/main107c2f20的CPU80MHz、SYS/MAC49.5MHz，
CPU实现fefd9305，卷积34338722位流30d8f0d5。当前PC主线为r14标准QAT FP32，
原生整数仅功能联调。软件存储/分派与精确语义见
[CPU80接口笔记](CPU80_PICTURE_INTERFACE_NOTES_20261023.md)。
只有一MiB staging可用，第二MiB隔离；per-fd快照不代表多个物理权重区。
CPU80主线没有旧E8后台相机扩展，软件检测后使用基线相机路径；显示保持待板测。
旧E8图像/语音/SD验收不转移到新硬件，本次未上板。
以下E8架构与已发布V2.1内容保留各自历史范围。

Picture_new 的现役架构和验证边界见 [续接检查点](PICTURE_NEW_CHECKPOINT_20261020.md)，
SD 命名与加载地址见 [启动契约](PICTURE_SD_NAMESPACE.md)。冻结 ROM 经公共选择器加载 PN01BOOT，
再校验本分支六个独立载荷；选择器搬到 0x01400000，分支启动器仍在 0x01000000。

board192 → 几何/棋线精修 → ROI640 detector → RGB32 classifier → 自动方向/FEN 为三模型链。
原始 int8/bias/shift/LUT 无损打包；整数 MAC 通过共享 `/dev/pango-mac0`，其余图操作、
精修及方向在 RV32 宿主执行，`full_integer_pipeline=false`。驱动 features=0x67 有实板证据，
不能归属于历史 features=0x07 内核。严格 IPC 绑定 token、硬件帧号、输入 CRC、backend 和有效态；
错误/不确定盘面不落子。piece_fit 参考数值已板测，生产者和回退状态机尚未启用。

后台捕获使用私有 bank 0x1b800000/0x1ba00000，DTS 预留 4 MiB no-map；
GUI 双缓冲和快照地址不变。CAM3 0x24[0] 为能力，0x28/0x2c 为 bank 地址，
CONTROL bit3 请求后台，STATUS bit13 为 DDR 提交确认。模式仅在会话和 writer 空闲时切换，
HOLD 锁定完整 bank/frame 并排空已接收写入，异常停止仍须排空；零模式保持旧预览。
该 E8 已完成专属物理及板测，用户确认实拍识别期间保持对弈页；不沿用旧位流验收。

Linux 保留 snapshot@1b600000 的 2 MiB 和 CLINT 的 64 KiB no-map；相机拷贝仅对齐整字访问。
CPU/SYS 频率、HDMI 时序、硬件 ID 和已发布产物保持原身份。以下历史硬件结果不描述本轮模型验收。

V6.5 已完成 63.642857 MHz 的完整 PDS/双角 STA、实际 CRAM 加载和板测 3+1，
CoreMark/MHz 均值5.262385177991809，较基线提高3.79154449%；[证据及范围](validation/v6_5-board-results-20261009/README.md)。
实际 CPU 来源读 `rtl/cpu/source.json`，时钟意图读
`config/clocks.json`。外设、地址 ABI、SYS/TIMEBASE 49.5 MHz 及 CPU/SYS CDC 保持完整。
时钟生成支持合法 div12..18，并按较快周期收紧 CDC 物理约束。

最终 SoC 实现为 `7ad9f204d5ad802b1eae8e5cb62890634a7bf275`，继续导入 CPU 实现
`e698e3bb78947fd4f7a0b5095e1cdc85a81e4502`。CPU 将 ROB 结果写入与分配控制隔离，
采用哈希索引的 64 组后备 BTB 与 4 项 ALU 保留站，未新增流水级。run838e 使用 div14/seed5；
59.4 MHz 对照实现4b4f4637/run75f8也已完成物理检查与板测，同频均值5.268805379729176 CoreMark/MHz。
CPU 文档提交不改变导入身份；run738/run906等历史结果各自绑定原实现。

UART 局部修复只把 TX FIFO 四位 `wr_ptr` 写地址接入两颗
`GTP_LUT6D`（`PAP_DONT_TOUCH`、INIT `CCCCCCCC_AAAAAAAA`）；固定 I2/I3/I4=0、
I5=1 使 Z5=I0、Z=I1。地址值、FIFO 容量、读口、写数据/使能、波特率状态与 RX 逻辑不变，
无新增寄存器或周期。普通 RTL/厂商模型与原版逐周期对照通过；run838e 同轮 ADS 合同
沿四个写指针 FF 的唯一 Q 网验证两颗 pad 到四个 `GTP_RAM32X2DP` 的16个低位 WADDR、
最高位0与无旁路，且绑定真实 VM/RTL/检查器。最终 SYS hold slow/fast 为 +0.173/+0.132 ns，
它是域级最差值，不是 UART 专属 slack；PNR 导出声明不独立证明 pad 全连接或 INIT。
同轮 ADS 总资源为49,332 LUT/37,933 FF/4,530 LUTRAM/140 DRM，不能把总量差直接归因于
两颗 pad。完整范围及187条既有外部 I/O 未约束信息见[验证记录](Validation.md)。

## V6.1 基线结构与仍适用的接口契约

V6.1 使用 PG2L100H-6-FBG676，集成为自研 CPU V3.1、RV32IMA、机器态配置、
CLINT 和 128 KiB boot BRAM。该版本主树 CPU 为 59.4 MHz，SYS/TIMEBASE 各 49.5 MHz；
V6.1 div15 已完成全量 PDS 和双角最终 STA，该版 div14 更高候选最终 CPU setup 失败。2026-10-08 的[实板 CoreMark 3+1 测试](validation/v6_1-board-coremark-20261008/README.md)已通过；其他外设整体验收尚未完成。
HDMI 保留 1280×720p60 / 74.25 MHz。旧 VexRiscv 的 M/S/U、Sv32 和 Linux
启动能力不属于本 CPU 的已验收功能。

`src/main` 负责 CPU 优化；本仓库集成 `rtl/cpu/CoreTop.sv`，由
`scripts/sync_cpu.ps1` 从 `src/cpu/generated/core/CoreTop.sv` 同步。
`rtl/cpu_top.v` 包装层维持 32 位 AXI 数据、4 位 ID、复位向量 `0x1c000000`，
并经 `rtl/soc/axi_cpu_sys_cdc.v` 的五条独立 AXI 通道跨入 SYS 域。
CLINT 路由在 SYS 域，中断电平同步回 CPU。初始化文件和哈希契约见 [BUILD](BUILD.md)。

`rtl/soc/soc_top.v` 把 PLL CLKOUT3 接 CPU CoreTop/缓存/mcycle，把 CLKOUT1
接 SYS AXI、CLINT、BRAM 和外设。两域各自异步置位、同步释放复位，PLL lock
失效时共同清空跨域事务。CPU↔SYS 用通用 AXI CDC；原 DDR 专用 CDC 保留在
SYS↔DDR 原生端口。当前配置读 `config/clocks.json`；V6.1 当时 VCO 为 891 MHz，CPU 除以
15，SYS 与 CLINT TIMEBASE 固定 49.5 MHz。CPU_HZ 寄存器按精确分频取最近
整数 Hz（半数向上）；TIMEBASE_HZ 用于超时和 CoreMark 计时。外设分频不跟随
CPU 提频。约束使用 `pds/soc.fdc`；59.4 MHz 是 V6.1 已测试 18→14 档位中最高的完整最终 STA PASS，不代表实板最高频率。

下图保留 V6.1 CPU 标识与接口关系；当前 V3.5 的验收状态见页首。

```text
CPU V3.1 -> CPU/SYS AXI CDC -> boot BRAM -> soc> console / debug / CoreMark
SD / TFTP / XMODEM -> DDR（传输/调试入口保留）
CPU + MAC AXI -> 仲裁 / CDC -> DDR native ports
CMOS2 -> line buffer -> frame writer -> FB0 / FB1 -> HDMI DMA
CH9350L -> keyboard -> LiteUART RX（物理串口优先）
         -> mouse -> HDMI overlay（camera 模式绕过）
Space -> hold + drain -> 独立快照 DDR -> CAMP UDP -> PC PNG + JSON -> SAVED
                                     -> PNG 编码 -> FAT32 /CAMERA PNG + JSON
FB HDMI scanout -> 独立 camera_sd HUD（不写源像素）-> HDMI
```

| 地址 | 用途 |
|---|---|
| `0x00000000–0x3fffffff` / `0x80000000–0xbfffffff` | DDR 缓存窗口 / 同一 DDR 非缓存别名 |
| `0x02000000–0x0200ffff` | CLINT，设备属性 |
| `0x1c000000–0x1c01ffff` | 完整 128 KiB boot BRAM，指令与数据均可缓存；不保留旧 DMA carve-out |
| `0x1fe00000–0x1fefffff` | 整个集成外设窗口，设备属性 |
| `0x1fe001e0` | LiteUART |
| `0x1fe00200` | SPI Flash |
| `0x1fe00300` | SYS_ID `0x53563300`、CAPS `0x1f`、SYS_HZ `+0x08`、CPU_HZ `+0x14`、TIMEBASE_HZ `+0x18` |
| `0x1fe00400` / `0x1fe00600` | HID / AUD1 |
| `0x1fe01000` |100 Mbps Ethernet MAC |
| `0x1fe10000` / `0x1fe10080` | 密集 MAC / 象棋稀疏评估器 |
| `0x1fe11000` | framebuffer DMA |
| `0x1fe12000` | camera，版本 `0x00010003`；HUD commit0x20、文本0x30–0x4c |
| `0x1fe13000` | SDN2，版本 `0x00050401`；COMMAND bit12 显式 CMD24/CMD25 写入 |
| `0x1b000000–0x1b0fffff` | 加速器 DDR 暂存区 |
| `0x1b100000–0x1b1fffff` | 保护区 |
| `0x1b200000` / `0x1b400000` | FB0 / FB1，各2 MiB |
| `0x1b600000` / CPU `0x9b600000` | camera 独立快照，1,843,200字节 |

`CAPS` bit 0（`SYS_CAP_LINUX_BASE`）保留历史的“Linux SoC 基础能力”平台标识和寄存器 ABI。
它不表示当前 CPU 支持 S 态、Sv32，也不证明 Linux 能启动；`info` 只是原样显示该寄存器。

低 DDR 窗口需允许 CPU 访问，高地址别名必须维持非缓存语义；DMA/相机复制依赖此契约。
这些地址由 MMIO 优先译码和 CPU PMA 共同解释，不能把包含 CLINT/ROM/MMIO 的地址段
一概当作普通缓存 RAM。修改 PMA 后重新跑缓存、异常和集成回归。
当前 CPU 的设备窗口仅为整个 CLINT 与 `0x1fe00000–0x1fefffff`，禁止从中取指；
原 CPU 的 PLIC `0x0c000000–0x0fffffff`、UART `0x10000000–0x10000fff`，以及
旧 `0x1fc*` / `0x1fd*` / `0x1ff*` / `0x1d01*` / `0x1d02*` / `0x1d03*`
保留窗口在本 SoC 中均按 DDR 解释，允许缓存和取指。高 DDR 别名始终允许取指、
数据访问非缓存。当前 SoC 的 MAC、视频与相机 DMA 只连接 DDR，不能写入本地 boot BRAM；原 CPU 的 `1c018000–1c01bfff` 特例已经移除，避免生产 CoreMark 工作区和其他 BSS 被错误地当作不可缓存设备内存。

以下为保留的历史 Linux 内存布局，不表示本轮已可启动 Linux：DTB 使用448 MiB DDR，
顶部6 MiB 加速器/FB 区 reserved-memory/no-map。
快照位于其后，处于 Linux RAM 范围内；它仅供 bootloader 临时使用，
启动 Linux 前 camera 命令已退出，不要求 Linux 为其永久保留内存。
完整锁定过程与协议见 [camera](OV5640_BOOTLOADER_CAMERA.md)。
SD 写入、目录提交、CID 故障恢复及 HDMI HUD 见[SD 拍照](CAMERA_SD_PNG.md)。
FAT 簇工作区在快照槽内 CPU0x9b7d0000，占24 KiB，不增加 Linux no-map 区域。
SD 数据暂存使用 boot BRAM 内八个扇区；原始快照与簇工作区仍走非缓存别名。

CPU/MAC 仲裁公平；MAC 最大8-beat burst。HDMI DMA 与 camera 使用 DDR native
端口仲裁，停止时排空已接受 burst。HDMI 文本为 UART 镜像，支持 clear、非破坏性 BS、
CSI 光标/行清除；framebuffer 为裸机接口，无 Linux fbdev/DRM。
CH9350L 是外接 USB Host 串口桥，无 FPGA 原生 USB 或 Linux evdev。
支持范围见 [硬件说明](SUPPORTED_HARDWARE.md)。

本次 CPU 配置未建立 S 态 / Sv32 / MMU 平台验收，Linux 启动未测试。
实际随包 Image 的 IKCONFIG 关闭 C 扩展且启用 MMU；OpenSBI 原始 BIN 缺完整 ISA 构建记录，
不能仅凭禁用 C 就推断启动兼容。证据见 [Linux ISA 审计](linux_isa_evidence.json)。
