# CPU 70 MHz 优化工作记录（候选）

## 目标与边界

目标是 CPU 至少 70 MHz，保持 RV32IMA、S/U/Sv32、缓存与保留站容量，
不增加乘法或加速器流水延迟，不降低 CoreMark 分数及加速器性能。
SYS、MAC、CLINT 保持 49.5 MHz。当前共享 PLL VCO 为 891 MHz，
相邻整数分频是 div13=68.538462 MHz、div12=74.25 MHz；前四轮采用 div12。
2026-10-18 最终频点选择新增 CPU 独立 PLL：850.5 MHz VCO / 12 =
70.875 MHz，原 SYS/视频 PLL 不变。此变更是实际时钟电路变更，不能把
原 74.25 MHz 结果改写为通过，也不表示同频性能提升。

工程内 `fpga-timing-optimization` 与 `accelerator-performance` skills 用于
资源筛选、冻结输入、门禁、全角 STA 与性能边界。六次 PnR/24 小时共享预算
从北京时间 2026-10-17 19:04:20 开始，为同频对照及最终构建预留次数。

## 基线身份

- 活动工程：`performance_soc_voice_hw`，分支 `feature/voice-hardware-20261016`。
- 当前板用语音候选：CPU 59.4 MHz，位流 SHA-256
  `78487ddbd5cfe0cf88fab2d952a2d8f82c81565e870d859518b7ed5c2aa4d1b5`。
- 该版最终慢角 CPU setup +2.171 ns，估算 Fmax 68.1942 MHz；
  CPU hold 慢/快角 +0.153/+0.109 ns。不能直接据此宣称 70 MHz 通过。
- CPU 来源提交 `45d24b9e09c44abc10f8b4fb5b69f69ecff48b70`，
  原始生成 RTL SHA-256
  `80d88b8edab534e04d1e3f1488e72832c8d12194d711db7b060a11c75bee5464`。
- 原语音整机 ADS：43,128 LUT、35,509 FF、120.5 DRM、177 APM。
- 当前板的语音模型及 GUI 未由本轮构建替换。

## 已实施与筛选中的改动

### 资源与加速器

沿用 [MAC 优化候选](Accelerator_Optimization_20261017.md) 的 64 行按字权重
写入和 AXI 读请求直发。另把输出 bank 的首次同步读与写命令接受重叠，
保留输出数据、尾字、背压及错误处理。DMA 单元测试的 512 次首字检查通过；
集成 AXI 写地址阶段遮住了这一拍，因此本次没有新增整机周期收益。

64/1024 行配置、最大 4096 字输出、整数输出与 DDR 流量对照及四项音频
仿真通过。相对上一轮候选，集成周期均未增加；256→32 作业仍为 4,779 周期
（优化前 5,051），4096 字输出仍为 13,720 周期。它们是 RTL 仿真数据，
不能换算为实板 CoreMark、Pikafish 整图或语音识别速度。

### CPU 乘积重构备选

原语音位流正式报告最差 CPU 路径从乘法器部分积寄存器出发，经乘积重构、写回
旁路进入访存保留站；19 级逻辑，路由占 77.065%。另建独立 CPU 源码分支
`feature/cpu70-20261017`，只修改 Chisel `exec/Mul.scala`：在已有输入寄存
级中计算负符号修正，把五个重构项压缩后做一次进位传播相加。
寄存器级数、valid/done 时序和发射吞吐保持原设计。

先为原实现添加并运行 5,120 组乘法器数值及拍序测试，再运行改写版；
新旧均通过。改写版 MDU/访存写回关联 9 项测试也通过，随后全部 33 个
单元测试套件的 95 项用例通过（不含 RTL CoreMark）。两份 RTL 已按原
配置重新生成并记录源文件绑定；生成 RTL SHA-256 为
`9dac3dc7f9534bda9364492fa71b98e87612e7f520f541f1352e13303332bd85`。
尚未把这一备选写入当前活动工程，是否采用由整机资源及最终路径结果决定。

## 完整构建记录

| 候选 | CPU | 输入快照 | ADS 资源 | 当前状态 |
|---|---|---|---|---|
| search1：MAC 资源优化，CPU RTL 不变 | 74.25 MHz | `db112c2dfb9a4e6da4be9111b13ba9f9` | 43,369 LUT / 34,520 FF / 120.5 DRM / 177 APM | 正式 STA 失败：CPU 慢角 setup −0.211 ns，1 个端点；不发布该位流 |
| search2-route：针对实测 ALU0 旁路网络的布线优先级 | 74.25 MHz | `bee0466cb1314fa4aba3a0c05ae03809` | 43,369 LUT / 34,520 FF / 120.5 DRM / 177 APM | 正式 STA 失败：CPU 慢角 setup −0.111 ns，1 个端点；不发布该位流 |
| search3-recovery-v2：并行分支恢复所有者比较 | 74.25 MHz | `80e2d82830a541aead7f75224c97a87f` | 43,287 LUT / 34,520 FF / 120.5 DRM / 177 APM | 正式 STA 失败：CPU 慢角 setup −1.113 ns，58 个端点；不采用该改写 |
| search4-alu-v2：链接地址捕获、直接分支相等判断 | 74.25 MHz | `6bb2b822f84c41e1bfead2e65ccc2f31` | 43,348 LUT / 34,581 FF / 120.5 DRM / 177 APM | 保存 DB 时中断，副本无法加载；无正式 STA，未接受位流 |
| final70-dedicated：ALU 改写与独立 CPU PLL | 70.875 MHz | `f45761f6744a494799a5407647155fd9` | 43,195 LUT / 34,581 FF / 120.5 DRM / 177 APM / 4 GPLL | CPU 约束误绑旧输出，实际 CPU 为推导时钟；正式 STA 失败，不接受 |
| control70-original-v3：原 CPU、独立 PLL、修正约束绑定 | 70.875 MHz | `a9bd7543c6074bcd85f5248c2ea39979` | 43,337 LUT / 34,521 FF / 120.5 DRM / 177 APM / 4 GPLL | ADS 原生时钟及资源/CPU/CDC 门禁通过；布局期间 owner 消失，无布局检查点或最终 STA，未接受位流 |
| 用户授权的同候选单次重跑 | 70.875 MHz | `4b7d86bb5f2a4e638b43359196ea52b3` | 43,337 LUT / 34,521 FF / 120.5 DRM / 177 APM / 4 GPLL | 正常完整构建通过；正式 STA All Constraints Met，CPU setup +0.166 ns，hold 慢/快 +0.069/+0.052 ns；未上板 |

隔离目录为 `build/cpu70-20261017/search1`，普通 `build_fpga.ps1` 冻结输入后
执行 ADS 审计，再将同一 ADF 导入 PnR。未降低时钟、不新增 false path；
CDC max-delay/max-skew 按更快 CPU 周期收紧到 12.668 ns。
复用原已验证 ELF/BIN/ROM 字节，CoreMark 从 SYS MMIO 读取真实 CPU 与
CLINT 频率；`CPU_CLOCK_HZ` 在现有 C 文件中没有调用者。DTS/DTB、PLL、
FDC、默认测试频率及脚本频率通过统一时钟生成器同步更新。

本机缺少历史 Windows GCC16.2/Icarus/MSYS 路径。外围仿真使用 WSL
Icarus 11；整核功能夹具采用现有 GCC9.4 汇编，不作为 release 工具链或
CoreMark 成绩。新增可重现的 `scripts/test_cpu_clock_candidate.py`，
整核沿用 `tb_cpu_integration`，不运行 RTL CoreMark。

WSL Icarus 的 21 个外围/CDC 功能用例已通过。原 CPU 与乘法重构备选均
通过 Verilator 5.048 的 74.25 MHz 整核汇编集成及生产控制台用例；
控制台分别为 165,588 SYS 周期。5.006 曾在 59.4 / 74.25 MHz 控制台用例
同时超时，失败记录保留；同一 RTL 换 5.048 后通过，没有修改硬件适配旧工具。

search1 正式最终报告与内部 hold 修复摘要不同：CPU 慢角 setup 最终
−0.211 ns（内部曾为 −0.095 ns），估算 Fmax 73.1048 MHz；CPU hold
慢/快角 +0.063/+0.049 ns，SYS setup +3.204 ns，DDR PHY +2.074 ns。
唯一失败端点为 ALU0 `exAluOp[9]` → MDU `s1Val_1[14]`，10 级逻辑，
逻辑 1.523 ns、路由 11.681 ns（88.466%）。其中 ALU0 写回 bit14
有 43 个负载，单段路由 2.165 ns。下一轮仅将该实际网络加入 RCF 优先布线，
其余 seed、CPU RTL、频率、hold 参数及例外均不变。先前乘法器备选不针对
本轮最差路径，因此暂不采用；不能用更换算术模块代替当前路径分析。

原门禁仅允许七条已审查优先网络，因此在 PnR 前拒绝新增网络，未消耗新的
PnR 次数。只在 search2-route 副本中把精确白名单扩为八条，并保留原生执行
成功记录及实际 PnR 网名逐条核对。先扩测试验证旧规则拒绝，再更新规则；
测试继续拒绝每条网络的缺失、重复、执行失败及空格/名称不匹配。
完整测试还发现旧 CPU 审计测试替身缺少 `return_cases=10240`，现补齐
测试数据，真实门禁未改。首轮完整正式 STA 已归档；只停止其后续网表/位流
生成，不发布时序失败候选，首次 PnR 仍计入共享预算。

新增八网名规则及其辅助脚本共 136 项合约检查通过（纯合成夹具，无 PDS/
实板操作），包括匹配、缺失、重复、实际执行失败、错误网名及辅助脚本超时。

search2-route 详细布线 218 轮、764.91 秒，无未布通连接；正式 STA 估算 CPU
上限 73.6431 MHz，仍不能作为 74.25 MHz 通过。CPU 慢/快 hold 为 +0.138/+0.100 ns，
SYS setup +3.143 ns、DDR PHY +2.077 ns。唯一失败路径已变为 ALU1 `exSrc0[6]`
→ 分支恢复 `redirectPcR[31]` 的 CE：28 级逻辑、logic 3.623 ns、route 9.364 ns，
skew −0.216 ns。原生正式报告保留，确认进程归属后仅停止后续网表生成，第二次 PnR
仍计入预算；无接受位流、无板测。

### 分支恢复候选

另建 `feature/cpu70-recovery-20261017`，从原 CPU 提交出发，不混入乘法器备选。
原实现先根据两路 eligible 选择年龄，再与 pending 年龄比较，ALU 比较结果要
经过这段串行逻辑才能更新重定向寄存器。候选提前分别比较两路年龄，accept
改为两路“eligible 且可替换”的 OR；最老 lane 的选择保持原样。若任意 eligible
比 pending 更老，则最老 eligible 一定比 pending 更老，等价关系包含环绕和相等年龄。
去掉 5 位 selected-age 选择器；是否节省整机 LUT、是否改善物理时序以 ADS/STA 为准。

先在原实现运行新参考测试与 LoadOrder 共 11 项，通过后才修改 Chisel。
其中纯整数谓词穷举 4,194,304 组，RTL 接口连续 8,192 拍比较所有可观察输出，
覆盖 reset/flush/block、环绕、相等年龄、未对齐目标及 invalid 时 payload 保持。
改写后全部 33 套件、96 项 CPU 单元测试通过（416 秒），配套 synthesis/simulation
RTL 已重新生成并通过来源绑定。生成 RTL SHA-256 为
`465f1be3ee26daf42c85086c1fca16e9d8e6ebc3e08896b2bec709b2e10a5db2`，
仅 `EarlyBranchRecovery` 一个模块变化，其余 63 个模块字节一致。
生成配置和缓存/容量参数与原 CPU 一致，源 worktree dirty=true 显式保留，不冒充已提交实现。
21 项外围/CDC 与 74.25 MHz 整核、生产控制台夹具再次通过。
第三轮 `search3-recovery-v2` 快照 `80e2d82830a541aead7f75224c97a87f` 完成了 ADS 与 PnR，
相对第二轮冻结硬件输入仅 CPU RTL 及来源清单变化；不混入乘法器备选。

整机 ADS 相对第二轮减少 82 LUT，FF/DRM/APM 不变，0 锁存器。相对原语音整机
减少 989 FF、增加 159 LUT，不能称为 LUT 整体下降。前端 85,760、返回路径 10,240、
PMA 2,144、hints 17,152 项检查及 ICache 64 对/128 位/2 路审计通过，UART/CDC
门禁通过。冻结 ADF SHA-256 为
`3e26fdc39adf96f132e8f751ad8fe7c21d042bf934d817b912267bac1b6af0f0`。
共享预算已使用 3/6 次，仍保留同频对照与最终构建次数。

当前整机 LUT 占 43,287/66,600（65.00%），DRM 占 120.5/155（77.74%），
APM 占 177/240（73.75%）。CPU 包含 20,660 LUT、12,072 FF、58 DRM；
MAC 子系统包含 9,422 LUT、10,845 FF、8 DRM、173 APM。模块值含子模块，
不能与子模块重复相加。单独分支恢复模块 LUT 为 78，上一轮为 77；整机减少
82 LUT 是整机映射结果，不能把这 82 个都归因于该模块内部直接减少。
原始资源报告 SHA 及逐模块对照在 `validation/cpu70-20261017/resource-comparison.json`。

MAC/音频仿真收据的 35 个候选输入及 3 个优化前参考输入已逐项核对 SHA，
与第三轮来源一致，因此引用同一份 15 项仿真证据，不把只改 CPU 的构建称为新的板上 MAC 测量。
另补充真实厂商 UART 原语的八组功能仿真和 BoardRelease 主机策略测试通过。
完整 `run_all_tests.ps1` 仍因本机缺少原 Windows 工具链路径而未跑通，原工具链固件未重编。

## Linux 时钟兼容与只读 SD 引导候选

检查发现现用 OpenSBI 桥接固定以 5/6 把 CPU TIME 剩余周期换算为 CLINT
周期；这只适用于 59.4/49.5 MHz。74.25 MHz 时应为 2/3，单改 DTB
不足以保持 Linux 定时、调度和超时正确。工程 `soc-hardware-software-codesign`
skill 用于核对这个跨软硬件边界。

新增 `linux/opensbi/pg2l_timer_bridge.h`、上游 1.3.1 补丁和
`build_clock_candidate.py`。从冻结 `clocks.json` 的精确 PLL 分频生成比例，
保留禁用定时器语义、至少一个物理 tick 和防溢出处理。先确认旧 5/6 算法
在 74.25 MHz 测试失败，再用真实 C helper 对独立整数参考验证 29,638 例，
覆盖 div12..18、64 位边界、已过期时间、禁用值和饱和；全部通过。

隔离输出 `build/cpu70-20261017/boot-v2/` 已构建：

| 文件 | 大小 | SHA-256 |
|---|---:|---|
| `fw_jump.bin` | 266,448 B | `5f783cebf2c60c5f5592b90472a7d8779e6185624bb8637cab3bf326caa3a0ab` |
| `soc.dtb` | 2,443 B | `5abf234388d42e6ba2260357d3c075b6fe48258de217f4affea47ff91ba8b888` |
| `loader-cpu-clock.bin` | 284,000 B | `23ec94ed5bc2200e87ee5030efb690b80c41ad9f8a7eb1e68944024d6103a7ee` |

OpenSBI 用 WSL GCC11.4，临时 DDR 引导器用既有 GCC9.4；两者均为 ELF32、
RV32IMA、无 C/硬浮点 ABI。它们不替代或重编 CoreMark 的 GCC16.2 固件。
引导器先只读核对现有 SD 六文件，再在 RAM 中发布时钟匹配 OpenSBI/DTB，
同时维护 cached/uncached 别名，以 CRC32 回读核对；启动前还检查实际 CPU/
TIMEBASE MMIO 频率。没有改写 SD/Flash，也没有改现用内核、rootfs 或模型。
本项目前是构建和主机数学通过，Linux 实板定时、采音、MAC/GUI 尚待新候选验收。

另准备了恢复当前 GUI 语音预览及 SD77 模型的 RAM overlay，沿用已验证的
GUI/识别器二进制和只显示文字的启动参数。overlay 为 91,136 B，SHA-256
`7b774ea1ad4deebc22b5bb3ef0d89fd5d7fe2880036a730ffbad46b3547507cc`；
相应 74.25 MHz 临时引导器 SHA-256 为
`dcae825643c260ad3821bfbed1f610a67ca88fe668f2fb3ad9c365619891d9c3`。
先只读校验原 SD 启动文件，再于 RAM 中安装新时钟桥、DTB 和 initramfs overlay，
不更换 SD 文件。已检查 newc 条目、模型哈希、CRC、地址范围、ELF ABI，
并从候选审查目录中的独立输入重新构建，overlay 与引导器字节一致。
这只是恢复文件的构建通过，尚无新时钟下的 Linux/GUI 实板验收。

候选审查目录 `artifacts/cpu70_candidate_20261017/gui-restore/` 包含源代码、
原 overlay、SD77 模型及固定 rootfs 输入。WSL 中从审查目录重建的命令为：

```sh
python3 artifacts/cpu70_candidate_20261017/gui-restore/prepare_cpu70_gui_restore.py \
  --project-root "$PWD" --output build/gui-restore-reproduced \
  --previous-overlay artifacts/cpu70_candidate_20261017/gui-restore/inputs/gui-overlay.cpio \
  --clock-boot artifacts/cpu70_candidate_20261017/boot \
  --model artifacts/cpu70_candidate_20261017/gui-restore/inputs/sd77-candidate.xqt \
  --base-rootfs artifacts/cpu70_candidate_20261017/gui-restore/inputs/vafs.bin
```

该命令只在 PC 构建，需既有 WSL RV32 工具链，输出目录必须不存在。
另外，交付模式 32 例、JTAG 证据策略 19 例、UART 映射合约 24 例通过；
它们是隔离的主机策略测试，不连接板卡，也不替代完整回归或上板验收。

## 第三轮失败分析与第四轮准备

第三轮详细布线 760 轮、2,168.91 秒，hold 修复 6 轮、69.34 秒。
正式多角 STA 的 CPU 慢角 setup −1.113 ns、TNS −20.103 ns，58 个端点失败；
估算上限 68.5824 MHz。CPU hold 慢/快角 +0.118/+0.077 ns，SYS setup +3.735 ns，
DDR PHY +1.586 ns。完整原生 RTR/XML 已保留；只在确认正式报告完成及进程归属后
停止后续功耗报告，未接受该位流。资源略减不能替代物理路径复核。

最差路径为 ALU0 `exSrc0[15]` → MDU `s1Val_1[28]` D，12 级逻辑，
logic 1.958 ns、route 12.268 ns（86.236%）、skew −0.054 ns。路径穿过移位结果、
写回选择后进位链、ROB 旁路和分发操作数；分发数据 fanout=12 的一段路由为 3.392 ns。
并行分支恢复改写不采用，后续从原 CPU 另建 `feature/cpu70-alu-20261017`。

第四轮准备仅修改 `FuAlu.scala`：在已有发射到执行捕获边界预计算 PC+4，
新增两组 32 位链接地址寄存器，让 ALU 结果的写回选择不再与链接加法串行；
BEQ/BNE 用实际减法操作数的直接相等比较，保持 PCADD/立即数选路及多热控制字语义。
发射、写回和 flush/reset 拍序不变；新增 64 FF 是否值得由整机 ADS/STA 判断。
先用原实现对新增 16,384 拍全接口差分测试，全部输出逐位一致后才修改源码，
随后完整 CPU 单元回归 33 套件、95 项通过（432 秒），最终源码再跑一次对照测试通过。
按 capture→双份 Emit→record 生成并验证来源绑定，完整导出 143 个源码/测试/RTL 文件。
第一次导出被来源清单门禁拒绝，保留失败目录；重新完整生成后的
`artifacts/cpu70_candidate_20261017/cpu-source-alu-v2/` 已通过两种来源验证。

生成 RTL SHA-256 为 `2e1aa75917fd6a962200f3b304c6ab27732b600f536bd5d161c48d1ecf22f8bd`，
生成器输入 SHA-256 为 `88e33a4bc6b131e4e146e9f5ddd4362ce49efb9a51f8b9493eaadc1f241d0155`。
Chisel 生产源码仅 `FuAlu.scala` 变化。生成模块 `FuAlu` 变化，`Alu` 只因输出
不再被使用而删除 `cmpEq` 端口及对应归约；已逐字检查剩余 `Alu` 逻辑不变，
其余 62 个模块字节一致。配置摘要仍为 `edaa35a8d7d6caec473709095f7335415e8b73e3c8b72eb0cbd0d4eff7c0e3ca`。

第一次从导出目录导入的准备构建缺少 Git 身份字段，已在 ADS 阶段、PnR 前停止；
未修改其冻结输入，也未消费 PnR 次数。最终准备目录为 `search4-alu-v2`，
从实际 Git worktree 导入，保留 `45d24b9…` 与 dirty=true 的真实身份。
相对第二轮冻结输入仍只有 CPU RTL 与 `source.json` 两项改变，35 个 MAC/音频
候选输入及 3 个原参考输入哈希一致。重新运行 21 项外围/CDC、整核及生产控制台
检查通过，整核 4,161 SYS 周期、控制台 165,588 SYS 周期，均与原 CPU 相同。
它们不是 CoreMark 成绩。

第四轮快照 `6bb2b822f84c41e1bfead2e65ccc2f31` 已冻结 444 项输入，ADS 及
资源、CPU/ICache/UART/CDC 门禁全部通过。CPU 前端 85,760、返回 10,240、
PMA 2,144、hints 17,152，ICache 64 对/128 位/2 路；0 锁存器。
整机资源 43,348 LUT、34,581 FF、120.5 DRM、177 APM；相对第二轮 −21 LUT、
+61 FF，相对原语音整机 +220 LUT、−928 FF。CPU 子系统含 20,701 LUT、
12,132 FF、58 DRM；MAC 含 9,449 LUT、10,845 FF、8 DRM、173 APM。
新增链接地址寄存器在 ADS 网表中保留，两路各映射 31 个以 exLinkPc 命名的 DFF；
逻辑声明 64 位与实际整机 FF 增量不同，采用真实映射报告作资源判断。
导入 PnR 的同一 ADF SHA-256 为
`fd531e67734ea95179dd9be2b27dc9ebddff1282fe4f320c4ba2d9a98c218f05`。
共享预算已使用 4/6 次搜索，余下两次保留同频对照及最终构建，不能重标用途继续搜索。
第四轮详细布线 310 轮、1,693.89 秒，hold 修复 6 轮、78.62 秒；内部
摘要 CPU setup −0.039 ns、2 个端点，但不是正式 WNS。原生日志停在
“Saving design to DB”，约 30.5 MB 的 routed ADF 副本经只读 report_timing
被 PDS 拒绝（FileSystem-0003）。进程终止的确切原因没有证据确认；本次
计数保留，formal_cpu_wns_ns=null，不生成或宣传通过位流。

## 2026-10-18 最终频点：独立 CPU PLL 70.875 MHz

原共享 891 MHz PLL 保持像素 74.25 MHz、SYS/MAC/CLINT 49.5 MHz、
I2C 配置时钟不变。新增 `pll_cpu.v` 使用 27 MHz 输入、IDIV=1、MDIV=2、
FDIV=15.75、ODIV3=12，实际 CPU 70.875 MHz。预计 GPLL 从 3/6 增至
4/6；以实际 ADS/PnR 报告为准。CPU 采用第四轮已通过完整单测的 ALU 改写。

`soc_top.v` 用静态 generate 选择 CPU 时钟源，默认仍兼容原共享 PLL；
CPU 与 SYS 异步复位均受两个实际 PLL lock 互锁，各自在本域经过三拍同步
释放。没有在 LUT 上切换运行中的时钟。新增原厂 `GTP_GPLL` 模型测试通过，
实测 CPU/SYS/像素/I2C 周期；实际顶层复位逻辑提取测试覆盖锁定先后、两种
lock 丢失、板复位及恢复，并检查共享 PLL 模式仍可工作。仿真不能验证模拟抖动。

时钟配置新增 `cpu_clock_source` 与 `cpu_pll_vco_hz`，旧缺省配置仍对应
`video891`。统一生成器同步 RTL、MMIO、FDC、DTB 与测试/脚本默认值；
CPU 约束 14.109347 ns，29 条 CDC 边界取保守值 13.309 ns，没有新增 false path。
17 项频率策略检查、24 项生成器与硬件绑定检查通过，覆盖原分频和非法修改。
OpenSBI 计时比例改为精确 44/63；实际 C 算术与独立整数参考的 33,872 例通过。
新 OpenSBI/DTB、只读 SD 的 RAM loader 和 GUI/SD77 恢复文件已另建，
不得复用先前 74.25 MHz 的 2/3 启动文件。

最终隔离目录 `build/cpu70-20261017/final70-dedicated` 的 21 个外围/CDC
用例、整核集成及生产控制台共 23 项通过；没有运行 RTL CoreMark。
2026-10-18 01:01 启动普通完整构建（用途 final，4 小时超时），由 ADS
及门禁通过后才消费第五次 PnR；采用独立隐藏 owner 保持有界进程归属。
正式 STA、资源与位流结果将在本节补充。用户当前无法连接板卡，板测保持待办。

后续审计发现时序范围清单及 FDC 的 CPU 约束对象均仍指向旧 PLL 输出；
新电路实际为 `g_dedicated_cpu.u_cpu_pll/.../CLKOUT3`。第五轮正式报告确认：
共有 19 个时钟，名为 `cpu_clk` 的旧目标有 0 个 clock loads，而实际 CPU
使用 `free_clk|g_dedicated_cpu.u_cpu_pll/u_gpll/CLKOUT3_Inferred`。因此既有
CPU/SYS 命名约束未绑定实际时钟。原生报告中实际 CPU 同域 setup −4.097 ns，
SYS→推导 CPU setup −15.947 ns，RGMII RX setup −0.261 ns，hold 也有违例。
这不是合格 CPU WNS；`formal_named_cpu_wns_ns=null`，不接受该位流。
保留完整 RTR/XML；核对 owner 后停止后续网表生成，计数仍为第五次。

统一生成器已同时更新 FDC 的 `get_nets` 对象和范围清单中的 CPU 目标，
26 项检查通过，覆盖旧 FDC 目标与旧范围目标的拒绝。其余 17 个时钟、
时序例外、I/O 缺口及全部 clock-pair 清单不变。CPU 周期仍为 14.109347 ns，
29 条 CDC 边界仍为 13.309 ns。新增原生 ADS 门禁检查 `pll_cpu` 的 CLKOUT3
SDC 注释必须声明 `cpu_clk`，拒绝 Inferred；检查器 8 项正反例通过。
该检查器加入冻结输入和正常 `build_cpu_ads_gate.ps1`，在 PnR 登记前执行。

另外，用新 FDC 对第五轮 routed ADF 副本执行只读 report_timing，仍得到旧
19 个时钟：此入口使用 ADF 内保存的约束，不能用项目旁的新 FDC 事后改写旧
PnR 的含义。此诊断不消耗 PnR，也不是时序通过。必须重新综合并走完整实现。

第六次保留给同频对照：在同样 70.875 MHz CPU/49.5 MHz SYS、相同 RCF 七条
原始优先网络、seed=3、hold=200 ps 及例外下，恢复原提交 `45d24b9...` 的
CPU RTL `80d88b8e...`，与 ALU 改写对照。其 FDC 和范围目标由修正生成器生成。
该对照在第五轮正式 STA 产生前定义；不是更换 seed 或新增优化搜索。
第五轮有效约束绑定错误，其布线数据不作为同条件性能基线。两版在 70.875 MHz
的整核夹具均为 4,247 SYS 周期，生产控制台均为 166,193 SYS 周期。
最终目录为 `build/cpu70-20261017/control70-original-v3`，完整功能回归 23 项
再次通过；01:45 启动正常综合，01:52 原生时钟及其余 ADS 门禁通过后登记
第六次 same_frequency PnR。原生 ADS 确认 CLKOUT3 声明为 `cpu_clk`，
综合 43,337 LUT / 34,521 FF / 120.5 DRM / 177 APM / 4 GPLL、0 latch。
相对原语音整机 FF 减少 988、LUT 增加 209；DRM/APM 不变，新增一个 GPLL。
时钟配置 26 项与 CRAM 证据 19 项检查在最终脚本上再次通过。
最终只选择通过完整门禁的候选，六次预算不增加。

### 第六轮中断及当时的源码交付

原生日志最后更新于 2026-10-18 01:57:12，停在第三次全局布局。
随后核查 owner PID 48328 和全部 PDS 进程均已不存在，原 owner receipt
仍为 RUNNING，未记录正常完成或异常退出。当前只留有 compile、ADS 及
device-map ADF，没有布局/布线 ADF，不能从布局检查点继续，也不能做最终 STA。
未找到能证明退出原因的应用错误事件；不能断言是工具崩溃、内存或超时。
该次仍计入第六次完整 PnR，正式 WNS 记为 null，未接受任何本轮可编程位流。

已完成的修正是 FDC CPU 源对象、范围目标及原生 ADS 预检；其配置和映射
证据通过不等于物理收敛。六次预算已经用完，已向用户提出“同一冻结硬件
输入额外重跑一次”的规则例外请求；收到答复前不启动第七次。当前候选
仅交付修正源码、完整 CPU 来源、匹配 70.875 MHz 的引导产物和诊断证据，
不附未通过完整 STA 的 FPGA 位流。证据见
`docs/validation/cpu70-20261017/control70-original-v3/`。

2026-10-18 用户随后明确回复“允许同一候选额外重跑一次”。03:10 在隔离目录
`G:/fpga/c70retry` 启动第七次正常完整构建，运行号 `4b7d86bb...52b3`；
新快照与第六轮全部 446 个输入的名称及 SHA-256 完全相同，seed、hold、
RTL、固件、FDC/RCF 和构建脚本均相同。原六次记录及默认六次门禁不变，
私有启动器在启动综合前已将单次用户例外计入原共享 ledger，失败/中断仍消费。
本次保留可监控的构建会话、owner 退出记录及每 30 秒的观察记录，
授权仅覆盖这一次同输入重跑，不覆盖新参数搜索或任何板卡动作。

### 第七轮最终结果与交付

03:10:39 至 03:59:32 的正常完整构建通过，约 49 分钟。详细布线 353 轮、
1,135.23 秒；路由器 hold 修复 6 轮、68.70 秒，随后还有一次 104.36 秒的
后续 hold 修复。完整数据库、正式 RTR/XML、位流及构建门禁均生成成功。
构建 owner 正常退出并记录 exit=0；不是中断后的只读恢复。

| 项目 | 最终值 |
|---|---|
| CPU 实际配置 | 70,875,000 Hz，独立 850.5 MHz PLL / 12 |
| SYS/MAC/CLINT | 49,500,000 Hz |
| 正式总摘要 | All Constraints Met |
| CPU setup WNS，慢角 | +0.166 ns |
| CPU hold，慢/快角 | +0.069 / +0.052 ns |
| CPU 估算 Fmax | 71.7206 MHz，仅 STA 估算 |
| DDR group1 hold，慢/快角 | +0.493 / +0.115 ns |
| CPU 时钟 | Declared，11,660 个 clock loads，源为实际 CPU PLL CLKOUT3 |
| 时序范围 / Max Skew | 18 个时钟、116 行摘要 / 10 组、20 行，均通过 |
| 外部 I/O 约束缺口 | 既有 187 项，范围清单核对无新增；不等于接口板测通过 |

内部 `after_hold_fix` 摘要的 CPU setup 为 +0.288 ns、DDR group1 hold 为
−0.469 ns。日志确认该摘要之后工具继续进行 hold 修复，正式报告才是最终状态。
工具的“hold violation fix failed”还包含未达到 200 ps 优化目标的正裕量路径；
CPU +52 ps、DDR +115 ps 等满足正式 STA 下限，但没有达到全部优化目标。
未调低 200 ps 参数、未改变时钟周期、例外或 CDC 限值。

当前最差 CPU setup 路径是前端 `pdInsts_2[15]` → `pdPcNextLineHi[26]` CE，
20 级逻辑、170 扇出，数据延迟 13.374 ns，其中路由 10.160 ns（76%）。
不再把历史 74.25 MHz 或错误推导时钟的路径当作本候选时序结果。

位流 SHA-256：
`0460ab2cf857c406f9018822ff8dc90b7ee8ab620ec03d49ac98aec5f754d84a`；
输入快照 SHA-256：
`a8ebe787519577a7d4018cc1df44c6314a4d22bbbddffee7efae8c5eb6c274db`。
证据目录 `docs/validation/cpu70-20261017/control70-retry-authorized/` 保存原始
正式报告、内部摘要、授权与同输入核对、正常构建及门禁记录。

通过门禁的构建目录为 `G:/fpga/c70retry`，候选审阅目录为 `G:/fpga/b70r1`；
源码与当前位流严格按同一快照核对。完整 CPU 来源为原版 135 文件导出，
匹配 OpenSBI 44/63 及 GUI 恢复产物随候选提供。开发目录保留原默认频率，
没有将未上板候选提升为生产镜像。CoreMark、MAC/Stage A/B、DDR、音频、
Linux/GUI 的新位流板测，以及完整 Windows 发布回归仍待完成。

## 收敛与验收要求

最终慢/快角 setup、hold、recovery、removal、脉宽、CDC 和既有时序范围
门禁全部通过后，才标为物理通过。布局估算、内部 hold 修复摘要或生成位流
均不能替代正式最终 STA。失败候选保留原报告和实际违规起终点，再针对路径
或资源改写，不靠连续换 seed 搜索。

CoreMark 不降分需同一工具链、相同种子/工作量的实板控制与候选 3 次性能
加 1 次正确性运行，每次至少 10 秒；同时复核 MAC/Stage A/B、DDR 和音频。
当前没有本轮新位流板测，不宣称 CoreMark 不回退已获验收。JTAG 编程按
本地 AGENTS 的要求另有当前授权及唯一器件核对；本轮没有 Flash 操作。
