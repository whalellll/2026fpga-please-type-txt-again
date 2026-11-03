# SoC v2 CoreMark 方法与验收边界

<!-- CPU80_APPROVED_20261022_BEGIN -->
## 2026-10-22 当前批准版本

当前CPU80卷积、ROM地址零SD启动修复及Linux采音调度修复已完成本轮功能板测，
用户批准提交。硬件34338722/run44aa982f，软件实现71c8c3f；原720p GUI，1080p不在本次验收范围。
CoreMark/MHz为5.259846，比同会话父版5.279876下降0.020030，在用户规定0.05范围内；
用户明确允许CoreMark总分下降。legacy dense延迟约增加0.451%，如实保留；官方NNUE和resident更快。
完整实板范围、性能全样本、八启动文件哈希及限制见[本版板测记录](CPU80_Audio_Service_Board_20261022.md)。
按2026-10-23用户最新指示，已先推送main（a36730d），随后完成独立ZIP与包哈希绑定实卡验收；以下历史章节保持各自原版本范围。
<!-- CPU80_APPROVED_20261022_END -->


V6.5在最终63.642857 MHz下的三次performance均值为 **5.262385177991809 CoreMark/MHz**，
较V6.1受控基线 **5.070148251157226** 提高 **3.79154449%**，超过门槛
**5.120849733668798**。总吞吐量为334.9132273618522 CoreMark。59.4 MHz新CPU对照
单独完成，不能替代最终频率结果。SYS/TIMEBASE=49.5 MHz，固定GCC16.2.0/O2/RV32IMA。

本轮RTL仅十次短测；正式计分来自重新扫描唯一JTAG目标后实际加载到CRAM的位流。
program_cram记录时间、ID、位流及源码/固件/PDS快照哈希；measure_coremark保留
完整UART、ticks、iterations、种子/CRC和PASS/DONE。每次>=10秒，连续三次performance
全部纳入均值/中位数/范围，validation单列。新CPU还需59.4 MHz同频对照。

BoardRelease按显式版本清单选当前证据，拒绝旧证据、错位流、离线日志冒充板测及
短时间运行；crcfinal用未改官方源码按实际模式/迭代次数复核。host参考程序仅用于
CRC正确性，不产生CPU成绩。CPU_HZ只是配置值，还须与PLL、STA、固件和加载身份一致。
历史V3.1独立CPU平台mcycle分数不作为集成板测基线。
本轮推广、create_delivery和verify_delivery均显式指定
`-PythonPath 'D:\LJL\WORK\msys64\mingw64\bin\python3.exe'`（实测3.14.4）；
直接执行verify_board_release.py/receipt回放也使用该解释器。Python需至少3.11的ISO时间
解析支持；默认Anaconda3.9.7不能解析本轮七位小数时间，原失败保留，不修改冻结脚本默认值。

## V6.5 当前板测结果

两份构建均经唯一JTAG目标确认与真实CRAM加载：最终7ad9f204/run838e为63.642857 MHz，
同频4b4f4637/run75f8为59.4 MHz，CPU实现均为e698e3b。每份先完成串口和DDR/MAC自测，
再重新加载同一位流，连续执行performance三次及validation一次。两次编排失败均发生在
性能测量前，原始记录保留；没有删除较低分的有效运行。

| 集成SoC平台 | CPU MHz | CoreMark均值 | CoreMark/MHz均值 | 每MHz相对基线 |
|---|---:|---:|---:|---:|
| V6.1受控基线 | 59.4 | 301.16680611873926 | 5.070148251157226 | 基线 |
| 新CPU同频对照run75f8 | 59.4 | 312.9670395559131 | 5.268805379729176 | +3.91817199% |
| V6.5最终run838e | 63.642857 | 334.9132273618522 | 5.262385177991809 | +3.79154449% |

| 最终performance | iterations | 完整ticks | CoreMark/MHz |
|---|---:|---:|---:|
| 1 | 6000 | 887440125 | 5.258570742608453 |
| 2 | 6000 | 887643341 | 5.257366851740724 |
| 3 | 6000 | 885310896 | 5.271217939626249 |

最终中位数5.258570742608453、范围5.257366851740724–5.271217939626249。
validation为6000迭代、889370226 ticks，单独通过、不计入均值；最终各次约17.9秒。
实际6000迭代的performance/validation crcfinal为a14c/18e1，正常官方源码oracle已复核。
同频每次4000迭代，performance ticks为633512414/632934619/631519735，
validation为632796708；同频中位5.266473397520595，范围5.261670110435015–5.278272631231918。
[完整八次记录、计算和来源](validation/v6_5-board-results-20261009/README.md)保留原始UART。
[本轮显式清单](validation/v6_5-board-release-20261009.json)已通过BoardRelease。

频率由冻结PLL（891 MHz/14）、STA、固件整数Hz和实际加载位流共同关联，未独立仪器测频。
63.642857 MHz是本轮最高完整验证频率，不是物理极限；独立CPU测试平台没有新正式成绩。

## V6.5 短RTL与历史开发测试的范围

初轮集成div14十次performance/validation分别为1,489,479/1,491,559 ticks、
CRC通过，见[初轮短测](validation/v6_5-development-20261008/initial-short-pilot/archive.json)。
短测固件与生产ROM及实际运行身份分别记录；这些数值不能填入正式成绩表，
也不能替代修复后的输入验证。本轮正式成绩来自上文实际板测，独立CPU仍无新正式分数。

div13 UART修复短测的模型SHA256为
`2f69813ea491810a799b79c02d7239c1650d1a43c41ed962a26e711c954ec943`，
十次performance/validation分别为1,383,982/1,385,358 ticks，与修复前短测相同。
两者约0.028秒，仅作周期复现，不能计为正式分数。div13实现603d7ae7的完整RTL回归
已通过；[短测兼容性绑定](validation/v6_5-development-20261008/uart-alias-div13-short-binding.json)
仅证明8份模型输入、27份pilot固件源码及相关生产固件字节未变，不把原338/193库存
改写为新回归，也未推广到最终位流。控制树全RTL、物理检查及本轮同频板测均已PASS；
主树UART修复div14的本轮十次短测已由独立新模型运行：performance/validation为
1,489,479/1,491,559 ticks，各约0.030秒，保留官方too-short/FAIL/DONE输出；
[本轮33项归档](validation/v6_5-uart-repaired-div14-short-20261009/archive_manifest.json)已核验，
模型SHA256为`44394b8c73713b262f65b16640b0b0f0849e26f47404850eb0cdb0d96b4e547f`。
不能借用div13结果或当作正式成绩。本配置完整RTL回归已PASS（335.884秒、338 source/194 test）；
run838e终态身份复核确认8份模型输入、27份pilot固件源码及355项冻结输入匹配7ad9f204，
但原始短测的PDS字段和too-short状态不改写，也未将其推广为已通过BoardRelease。
连接、构建与预算现状集中见[开发检查点](validation/v6_5-development-20261008/README.md)。

## V6.1 历史实板结果与可复现方法

2026-10-08 已在连接的开发板上通过生产 console 完成 **3 次性能 + 1 次验证种子**测量，四次均为 4000 迭代、CLINT 计时超过 13 秒，全部 CRC、`COREMARK_PASS` 和 `COREMARK_DONE` 检查通过。CPU_HZ=59,400,000，SYS_HZ=TIMEBASE_HZ=49,500,000；GCC 16.2.0 `-O2 -march=rv32ima_zicsr_zifencei -mabi=ilp32`，工作区位于 boot BRAM。

三次性能均值为 **301.166806119 CoreMark / 5.070148251 CoreMark/MHz**，范围 **5.067289256–5.071634155 CoreMark/MHz**，中位数 5.071521343。验证种子单独通过，不计入性能均值。[板测记录](validation/v6_1-board-coremark-20261008/README.md)保留各次 ticks、全部 CRC、原始串口、解析结果、计算公式和镜像身份范围；用户先前提供的两次性能结果单列作复核，不混入这组三次均值。59.4 MHz 已有实际 CoreMark 运行通过证据，未进行实板极限频率搜索、Linux 启动或其他外设功能验收。

## V6.1 于 2026-10-05 发布时的历史 RTL Pilot

V6.1 最初依用户 2026-10-05 的选择使用主树 59.4 MHz 双时钟集成 SoC 的 **Pilot 短测**。当时启动的 3 次性能加 1 次验证 Long 仿真已停止，没有形成四例正式 RTL 结果。以下 Pilot 仍只作短时估值；2026-10-08 板测作为独立证据补录。[发布短测证据](validation/v6_1-short-pilot/release_evidence.json)保留原始 UART、JSON 与输入哈希。

| 短测模式 | 迭代 | `PORT_TICKS64` | SYS CLINT 目标计时 | CoreMark/MHz 短时估值 | CRC seed/final | 判定 |
|---|---:|---:|---:|---:|---|---|
| 性能 `(0,0,0x66)` | 10 | 1,658,460 | 0.03350424242424242 秒 | 5.024741828764838 | `e9f5` / `fcaf` | `PILOT_PASS_NOT_A_SCORE` |
| 验证 `(0x3415,0x3415,0x66)` | 10 | 1,660,157 | 0.03353852525252525 秒 | 5.019605575456619 | `18f2` / `c64e` | `PILOT_PASS_NOT_A_SCORE` |

该 Pilot 的 CPU 为 59,400,000 Hz，SYS/TIMEBASE 均为 49,500,000 Hz，`TOTAL_DATA_SIZE=2000` B。两份原始 UART 都明确输出 `ERROR! Must execute for at least 10 secs for a valid result!` 和 `COREMARK_FAIL`；Pilot 检查器的 `PILOT_PASS_NOT_A_SCORE` 只表示短测流程及预期拒绝行为通过，**不表示官方 CoreMark PASS**。仿真使用从生产 bootloader 源码另编的 fixed-ten 固件 SHA-256 `212defe1c704999c13b9812ba0ac3dabc3ca55f96ccfe96acd3f4ef269c303e8` 和 ROM SHA-256 `ca893d7a41e35fe87c9ff6ab51291a7b4875d126fb9f5ef01d7b8bb8a4c62fd5`；它们**与本轮位流所绑定的生产 bootloader BIN `f6617eac7af1296cb8fa5c26acfc23398b5a879f801492869cb077512bc86159` 及生产 ROM 不同**。Pilot `summary.json` 的 `final_timing`、PDS 快照和已发布位流字段均为 `null`，不能把短测说成生产固件与位流同一运行输入。CLINT 仅在进入 console 前的 PHY 等待阶段加速；CoreMark 命令期间计时尺度为 1。主机 Verilator C++ 15 条实际编译命令均使用 `-Os`；目标 GCC 16.2.0 中 6 个 CoreMark 对象使用 `-O2`。

仿真结果的 `observed_cpu_cycles_timer_release_to_prompt` 是 CPU 时钟边沿实测数，范围为恢复真实 CLINT 计时器后到 CoreMark 命令完成并返回 `soc>` 提示符；它包含串口输入和输出开销，不是 CoreMark 计时区间内的精确 CPU 周期数。上表短时估值按固件报告的 `PORT_TICKS64` 计算。

## V6.1 测量方法与复现记录

以下保留 V6.1 当时的命令与输入身份；公式及计时规则仍适用。V6.5 必须使用
页首范围和 [BoardRelease](BOARD_RELEASE.md) 的本轮加载、短测、板测及身份契约。

在生产 `soc>` console 执行 `coremark` 三次性能种子 `(0,0,0x66)`，再执行 `coremark validate` 验证种子 `(0x3415,0x3415,0x66)`。工作区 `TOTAL_DATA_SIZE=2000` B。每次运行自动校准并要求 CLINT 计时至少 10 秒、CRC 正确、输出 `Correct operation validated.`、`COREMARK_PASS` 与 `COREMARK_DONE`。三次性能报告逐项列出并预先按均值/范围汇总，验证运行单列。板测可用 `scripts/measure_coremark.ps1 -Port COM5 -CpuHz 59400000 -TimeoutSeconds 90 -OutputDirectory <全新目录>`；串口号以现场枚举为准。脚本只采集串口并记录所给本地位流/固件文件哈希，不编程、不读回 FPGA。

CLINT `mtime` 在 SYS 域按 `TIMEBASE_HZ` 递增；CPU CSR `mcycle` 在 CPU 域递增。两者不是同一个计数器。秒数 = `PORT_TICKS64 / TIMEBASE_HZ`；绝对 `iterations/s = iterations × TIMEBASE_HZ / PORT_TICKS64`；`CoreMark/MHz = iterations × TIMEBASE_HZ × 1,000,000 / (PORT_TICKS64 × CPU_HZ)`。正式记录还应列出 CPU_HZ、SYS_HZ、TIMEBASE_HZ、PLL 精确分频、可观测 CPU 周期、种子、迭代数与全部 CRC。整数 CPU_HZ 寄存器按 `nearest_half_up` 从 `891,000,000 / CPU_DIVISOR` 得到，不用显示的舍入 MHz 反推时长。

`scripts/run_coremark_production_sim.ps1 -Kind Pilot` 测双时钟模型速度，pilot 的独立 ROM/十次迭代不是正式成绩。`-Kind Long -PreflightOnly` 校验同一冻结 RTL、生产 ROM、最终 PDS 快照/STA/位流与编译器输入。本轮 V6.5 不执行 Long；未来若另行要求补测正式 Long，应执行四次有界仿真并保留 UART、模型参数、输入/输出 SHA、每次计时和 CRC；每路 `MaxCycles` 上界和四路共享主机墙钟 timeout 须从 pilot 估计，且不得降低 10 秒目标或加速 CLINT。

V6.1 当时的主树 div15 已通过全量 PDS 和最终双角 STA；该版更高的 div14 候选最终 CPU setup 失败。Pilot 的两例短时估值均不足 10 秒，仍不能作为正式 RTL 仿真成绩；V6.1 集成 SoC 的实板结果见上方历史小节；V6.5 本轮正式板测结果见页首，不沿用这些历史估值。

正式入口从空目录构建 Verilator 模型，并显式传 `-CFLAGS '-Os'`；`model.json` 记录实际 C++ 编译命令、生成 Makefile、`verilated.mk`、构建脚本和日志的哈希。复用已验证模型可传 `-ReuseModel -ReuseModelDirectory <目录>`，仍逐项校验源文件与模型哈希。汇总分别记录主机 C++ 优化和从 GCC `build_commands` 实际 argv 得出的目标固件优化；`SIM_CLOCK_QUANTIZATION` 记录仿真波形的 CPU/SYS 半周期。正式分数只由目标 `mtime` ticks、TIMEBASE_HZ 与 CPU_HZ 计算，主机墙上时间单列。

Verilator 模型覆盖集成 CPU、CDC、CLINT、ROM 及仿真的 DDR/外设行为；它不等同真实 FPGA 外设时序或实板验收。CPU 源仓 `coremark_test_soc` 单独使用 mcycle 测量，不能借它的成绩填写此完整 SoC。V6.0 的 [短时结果](COREMARK_V6.0.md)只作历史比较。

CPU V3.1 源仓的独立单时钟测试工程已完成 3 次性能加 1 次验证长跑（见 CPU 源交付包 `CPU/handoff/V3_1_VALIDATION.md` 和 `CPU/handoff/validation/v3_1/source-coremark/`）。每次 2600 迭代、49.5 MHz；三次性能各为 514,595,220 `mcycle`、10.395863030 目标秒、CRC `25b5`、5.052514868 CoreMark/MHz，验证例为 516,281,520 `mcycle`、10.429929697 目标秒、CRC `70a1`、5.036012135 CoreMark/MHz。它使用源仓 CPU `mcycle` 而非本 SoC 的 SYS `mtime`，因此这些数值只作独立对照，**不是 V6.1 或 V6.5 集成 SoC 成绩**。源仓 Verilator 主机 C++ 的 `-Os` 可能影响模型大小和仿真墙上时间，不会直接提高被测 CPU 的 CoreMark/MHz；被测 RISC-V 固件仍由 GCC 16.2.0 `-O2` 编译。本 SoC 的 Pilot 估值、主机模型优化参数与目标固件参数分别记录在原始 summary；今后的正式 RTL 仿真分数须另有完整 Long manifest，板测则使用独立串口测量证据。
