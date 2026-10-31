# CPU V3.5 开发候选

当前 VERSION=3.5.0，**尚未完成发布验收**。本轮修改与短测见
[候选记录](cpu/handoff/validation/v3_5/candidate-search/README.md)。正式成绩必须来自
performance_soc 集成板测：CPU >59.4 MHz，SYS/TIMEBASE=49.5 MHz，三次 performance
均值至少 5.120849733668798 CoreMark/MHz，并通过完整 STA、RTL 与板级验收。
新 CPU 另做 59.4 MHz 对照；RTL CoreMark 仅跑短测。

V6.1 集成板测基线为 5.070148251157226 CoreMark/MHz；独立 CPU V3.1 的
5.052514868 是另一平台的历史仿真成绩。下面旧版本数值和“无实板”描述保留其
历史适用范围，不表示当前候选已验证。未达标只交付明确的 candidate 包，不建 V3.5 tag。

## V3.1 历史背景和通用目录

根目录 [VERSION](VERSION) 是当前 CPU 发布版本的唯一来源。`cpu/` 保存 Chisel
源码、生成 RTL 和独立的 `coremark_test_soc` 性能测试平台；完整板级集成由
`performance_soc/linux` 维护。当前发布证据见 [V3.1 验证记录](cpu/handoff/V3_1_VALIDATION.md)；
[V3 历史记录](cpu/handoff/VALIDATION.md) 保留原始输入与当时结论。
[版本变化](CHANGELOG.md) 与 [CPU 接口/时钟契约](cpu/handoff/ARCHITECTURE_INTERFACE_CLOCKS.md)
分别记录本版迁移和测试平台边界。

| 入口 | 用途 |
| --- | --- |
| [CPU 源码](cpu/src/main/scala/e91c) | Chisel 微架构；修改后重新生成 RTL |
| [综合 RTL](cpu/generated/core/CoreTop.sv) | `CoreTop`，交给集成 SoC 的 CPU 源文件 |
| [仿真 RTL](cpu/generated/sim/CoreTop.sv) | 同一配置的仿真导出 |
| [coremark_test_soc](cpu/coremark_test_soc) | CPU 优化用的可控测试平台，不是 performance_soc |
| [脚本](cpu/scripts) | 生成、回归、IMA 固件构建、PDS、交付检查 |
| [新电脑指南](cpu/handoff/NEW_COMPUTER_GUIDE.md) | 从本文件夹继续开发所需的工具与步骤 |
| [V3.1 验证记录](cpu/handoff/V3_1_VALIDATION.md) | 本次输入、测试、正式分数和限制 |
| [AI 接手说明](cpu/handoff/CODEX_HANDOVER.md) | 当前状态、约束与下一步 |

CPU 与当前固件统一为 **RV32IMA**，包含明确列出的 Zicsr、Zifencei 支持。
完整编译参数含 `-march=rv32ima_zicsr_zifencei -mabi=ilp32`；CoreMark 使用 `-O2`，
比赛构建采用实际 target 为 `riscv32-unknown-elf` 的 GCC 16.2.0，并显式链接经核验的 RV32IMA/ILP32 无 C 运行库。
GCC 16.2/O2 是已选的构建配置；完整编译命令、libgcc 身份、固定官方 CoreMark
输入和各次计时结果应以本次固件 manifest 与 V3.1 验证记录为准。V3 的
5.014670/MHz 是约 0.0403 秒短仿真历史校准值，不能作为 V3.1 正式成绩。
本版源仓 49.5 MHz 测试工程的 3 次正式性能均值为 5.052514868 CoreMark/MHz，
每次目标计时 10.395863 秒；验证例单独报告，原始结果见 V3.1 验证记录。
完整 SoC 主树在 CPU 59.4 MHz、SYS/TIMEBASE 49.5 MHz 下以新快照完成布线，
slow/fast 最终 STA 全部通过并生成同轮位流。更高的 div14 档位 63.642857 MHz
虽完成布线，但最终 CPU slow setup 为 −2.246 ns，7 个端点失败；因此在
49.5–63.642857 MHz 搜索范围内，59.4 MHz 是完整 SoC STA 通过的最高已测档位。
完整 SoC 已按本轮决定采用 59.4 MHz、10 次迭代的集成 RTL 短测：性能种子
CoreMark/MHz 折算估值约 5.025。目标计时仅 0.033504 秒，官方端口因不足
10 秒明确拒绝，因此不是正式成绩；短测另编固定次数固件，与同轮位流的生产
固件不同。这里的源仓 5.052514868 正式分数不作为完整 SoC 分数。

`performance_soc/linux` 负责 DDR、console、debug 和外设集成；其中
`rtl/cpu_top.v` 的 `cpu_core_top` 为兼容适配层，
`rtl/cpu/CoreTop.sv` 来自本仓库综合 RTL。必须使用其 CPU 同步脚本同步
RTL、初始化文件与哈希，不能只替换同名文件后假定所有功能兼容。

`.pds`、约束和必要初始化输入纳入 Git；PDS 数据库和 `work` 由脚本生成。
在 `cpu` 运行 `.\scripts\newpc.ps1 -Stage PdsPrepare` 后打开
`coremark_test_soc/pds/coremark_test_soc.pds`，无需把旧电脑的 `work` 拷到新电脑。

当前没有接板条件，Linux 启动也未测试；发布配置未启用 S 态/Sv32，不能宣称
可启动 Linux。CPU 测试 SoC 的 PDS 工程只有测试时钟
约束；完整 SoC 的最终布线时序必须由集成仓库独立签核。源仓正式 CoreMark
每次至少 10 秒，已完成三次性能与一次验证；完整 SoC 本轮只报告非正式短测估值。
