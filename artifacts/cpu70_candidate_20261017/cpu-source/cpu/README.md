# CPU V3.5 开发工程（候选）

本轮正式性能使用 performance_soc 集成板测，仅运行短 RTL CoreMark。
**不执行本文旧版 `run_coremark_release.ps1` 长仿真命令。** 当前尚未正式验收；
新事实见[候选记录](handoff/validation/v3_5/candidate-search/README.md)。下文 V3.1
分数、2600 次长测和 PDS 结果是历史证据，不构成 V3.5 验收。
源码包 schema 3 校验当前短固件、生成物及集成板测 receipt；未达标使用
`package_handoff.ps1 -Candidate`，文件名带 candidate。

首选 C1 不增加流水级：ROB 结果有效位保持清除优先，使分配控制不再进入
结果 bank/owner 的写使能；后备 BTB 改为 64 组两路哈希索引，
每个 ALU 保留站由 3 项增到 4 项，MEM RS2、RAS2 和缓存保持。
独立平台本轮十次短测由 1,994,149 mcycle 降到 1,922,718，CRC 一致，
短测每 MHz 估值改善 3.7151%。这是约 0.04 秒的 RTL 筛选，
不能作为正式 CoreMark 或集成板测分数。当前进展和全部验收缺口见
[V3.5 验证记录](handoff/V3_5_VALIDATION.md)。

正式比较使用 V6.1 集成板测基线 5.070148251157226 CoreMark/MHz；
最终 CPU 频率须高于 59.4 MHz，最终频率下三次 performance 均值须至少
5.120849733668798，另做 validation 和新 CPU 的 59.4 MHz 同频板测。
独立平台使用 CPU mcycle，集成板测使用 SYS CLINT mtime；
SYS/TIMEBASE 固定 49.5 MHz。Linux 启动及全部外设全面验收不作新增目标。

## V3.1 开发背景与共用工具说明

本目录用于 CPU 架构、主频、资源和 CoreMark 验证。`coremark_test_soc` 是配套的 CPU/BRAM/UART 性能测试基座；完整 FPGA SoC 的 DDR、console、debug 和外设集成由独立仓库 `performance_soc` 的 `linux` 分支负责。发布身份由仓库根目录 `VERSION` 给出。

本轮 V3.1 的当前证据见 [V3.1 验证记录](handoff/V3_1_VALIDATION.md)。
[V3 历史验证](handoff/VALIDATION.md) 保留原始结论，不代表本版整机时序或成绩。
源仓 49.5 MHz 测试工程的三次正式性能运行均通过至少十目标秒及 CRC 检查，
均值为 5.052514868 CoreMark/MHz；验证运行和完整 SoC 成绩分别记录。
完整 SoC 主树以新快照在 CPU 59.4 MHz、SYS/TIMEBASE 49.5 MHz 完成布线，
slow/fast 最终 STA 全部通过并生成同轮位流。div14 的 63.642857 MHz 已布线，
但最终 CPU slow setup −2.246 ns、7 个端点失败；49.5–63.642857 MHz 搜索范围内
最高已测通过档位为 59.4 MHz。集成 SoC 本轮采用 10 次迭代 RTL 短测，
性能种子估值约 5.025 CoreMark/MHz；目标计时只有 0.033504 秒，官方端口因
不足 10 秒拒绝，故无正式集成 SoC 成绩。短测固定次数固件不同于位流中的生产
固件，不使用本测试工程的正式分数代替集成结果。
[接口、地址与时钟契约](handoff/ARCHITECTURE_INTERFACE_CLOCKS.md) 和
[版本变化](../CHANGELOG.md) 分别说明可复用边界与本版改动。

## 当前契约

- 硬件与固件统一 **RV32IMA**，C 扩展及其配置开关退出当前源码。统一地址属性后的对比支持选择 IMA；具体输入与结果见 VALIDATION，后续修改仍须重新验证。
- 软件统一 `-march=rv32ima_zicsr_zifencei -mabi=ilp32`。Zicsr/Zifencei 是当前工具链中 CSR 与指令同步的显式名称，不表示支持 C、浮点或 Linux 启动。
- 比赛构建使用 GCC 16.2.0/O2，实际 target 为 `riscv32-unknown-elf`；显式选择默认 RV32IMA/ILP32 libgcc，核验 ELF32、soft-float 与无 C。它在已验证的 14.2/16.2 候选中性能更高且完整固件能保留 16 KiB 栈。固件完整参数、运行库、源码和二进制哈希在各自 `manifest.json`。
- 综合模块为 `CoreTop`。向集成仓库原样交付 `generated/core/CoreTop.sv`；逻辑修改从 Chisel 源码重新导出，不手改生成文件。

## 文件布局

| 路径 | 作用 |
| --- | --- |
| `src/main/scala/e91c/` | CPU 的 Chisel 源码 |
| `src/test/scala/e91c/` | CSR、地址属性和其他单元测试 |
| `generated/core/CoreTop.sv` | 当前综合 RTL，向集成仓库交付的 CPU 文件 |
| `generated/sim/CoreTop.sv` | 当前带观察探针的仿真 RTL，由 Emit 同步刷新 |
| `coremark_test_soc/rtl/`、`ip/` | CPU 性能测试和历史 DMA 综合实验外围 |
| `coremark_test_soc/pds/coremark_test_soc.pds` | 可移植的 CPU 测试基座 PDS 工程 |
| `coremark_test_soc/sw/` | 自包含 CoreMark 与移植层源码 |
| `coremark_test_soc/sim/` | 测试台、当前 IMA 固件与历史对照输入 |
| `scripts/meminit/` | 三个 CPU RAM 初始化源文件 |
| `scripts/` | 环境、导出、回归、固件、PDS、打包和 DOCX 导出入口 |
| `handoff/` | 新电脑教程、AI 接手说明、证据与发布状态 |
| `evidence/v15/`、`design/` | 历史实验资料，不能作为新 RTL 的验收结果 |

原生 Bash 回归由本项目的 Windows Job Object 启动器管理整棵进程树；普通阶段默认
总限时 5400 秒，单次正式 CoreMark 重放默认 14400 秒，3+1 批量入口本轮设为
28800 秒安全上限。可在本机配置中设置 `SimulationTimeoutSeconds`（最多 86400 秒）。
日志保存在 `work/logs/newpc-native/`。结束入口打印的 PowerShell 进程会关闭 job；
阻塞原生调用期间 Ctrl+C 可能延后处理，具体见交接指南。

## 新电脑入口

完整步骤见 [NEW_COMPUTER_GUIDE](handoff/NEW_COMPUTER_GUIDE.md)，下一位 AI 的任务说明见 [CODEX_HANDOVER](handoff/CODEX_HANDOVER.md)。复制整个 `src` 文件夹或获取已共享的 `main`，不需要原电脑的 work、工具缓存或绝对路径。

在 `cpu` 下准备 `toolchain.local.json`。原生 Windows 路线使用 `toolchain.native.example.json`；已有 WSL 环境可使用 `toolchain.newpc.example.json`。

```powershell
Copy-Item .\toolchain.native.example.json .\toolchain.local.json
# 按本机安装位置编辑配置，然后逐步执行：
.\scripts\newpc.ps1 -Stage Doctor
.\scripts\newpc.ps1 -Stage Emit
.\scripts\newpc.ps1 -Stage Unit
.\scripts\newpc.ps1 -Stage Functional
# 本轮仅使用 iterations=10、evidence_class=calibration 的固件。
# manifest 不符合时先用 build_coremark.ps1 重编，禁止重放旧长测ROM。
.\scripts\newpc.ps1 -Stage CoreMark
.\scripts\newpc.ps1 -Stage PdsPrepare
.\scripts\newpc.ps1 -Stage PdsCheck
.\scripts\newpc.ps1 -Stage PdsSynthesis
```

Emit 更新 `generated/core/CoreTop.sv`、`work/handoff-probes/CoreTop.sv` 和 `generated/sim/CoreTop.sv`，同时生成每份导出的 `emit-config.json`，由 schema 2 清单绑定实际参数和输入哈希。源码变化后重跑。本轮 `newpc CoreMark` 只重放十次校准短固件；正式分数由集成 SoC 最终频率下的本轮板测 3+1 提供，不运行旧版长仿真批量入口。

PDS 准备与打开不依赖 Java/WSL。该工程 top 为 `coremark_soc_top`，只有测试输入时钟约束，没有板级管脚；其综合结果不证明完整 SoC 布线时序。`Synthesis` 阶段保留完整 DMA 实验；当前测试基座使用 `PdsSynthesis`。

## 送入集成仓库

在 `performance_soc` 根目录执行：

```powershell
.\scripts\sync_cpu.ps1 -SourceRepo '..\src'
.\scripts\sync_cpu.ps1 -SourceRepo '..\src' -Check
.\scripts\prepare_pds_project.ps1
.\scripts\run_all_tests.ps1
```

同步目标是 `rtl/cpu/CoreTop.sv`、`rtl/cpu/emit-config.json` 和 `rtl/cpu/meminit/`，初始化输入取自受 Git 跟踪的本目录 `scripts/meminit/`，无需先 Java/Emit 生成缓存。同目录 `source.json` 记录来源与哈希。`rtl/cpu_top.v` 是集成包装层，保留 AXI、复位向量、CLINT 和中断映射，由集成仓库维护；不能用测试基座顶层替换它。准备/构建脚本将初始化文件放入 `pds/scripts/meminit/`。

## 证据、清理与文档

`work/`、PDS 数据库、临时 ROM 副本、sbt 缓存和 `toolchain.local.json` 不入 Git。`.pds`、真实约束、初始化源、固件清单和可复建源码必须入 Git。`package_handoff.ps1` 按 Git 输入清单生成源码包及新哈希清单；`VerifyPackage` 检查相应包清单，不代替回归。

Markdown 是权威文档；修改后重建 DOCX，不单独编辑导出文件：

```powershell
python .\scripts\export_handoff_docx.py
```

输出 `handoff/新电脑开发与集成指南.docx`。不同 CPU、固件、频率或编译参数的历史数据必须保留来源，不混写为本轮成绩。
