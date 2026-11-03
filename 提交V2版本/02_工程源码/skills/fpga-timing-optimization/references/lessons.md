# PDS / DDR 时序的历史教训

来源：性能工程 `docs/NNUE_10ms_Optimization.md`、
`docs/YOLOv5n_Perf30_DMA_20261005.md`、`docs/YOLOv5n_Perf_LUT_20261006.md`、
`docs/YOLOv5n_Board_Timing_20261007.md`。数字为特定候选，不是推荐布局。

| 候选 | 慢 setup | 慢 hold | 快 setup | 快 hold | 结论 |
|---|---:|---:|---:|---:|---|
| 10-05，334 条 DDR 绑定 | +0.532 | +0.142 | +3.032 | +0.101 | 物理通过；10-09 基线部分板测通过，音频并发未通过 |
| 10-06，332 条绑定 | −0.003 | +0.111 | +2.700 | +0.077 | 拒绝；另有原生输入覆盖错误 |
| 10-07，333 条绑定 | −1.794 | −0.714 | +1.622 | −0.768 | 拒绝，未下载 |
| 10-09，配置＋递增地址，331 条绑定 | +0.862 | +0.137 | +3.081 | +0.100 | 物理通过；匹配候选板测以本轮报告为准 |

单位 ns。10-06 小幅负裕量仍是违规；生成位流不改变结论。

10-06 的单 endpoint 是 `ddrphy_sysclk → phy_dq_sysclk_0`：
`this_group_ca_dly/opit_0_inv/CLK` 到 `u_outbuft_wen/opit_1/TX_DATA[0]`，
第一段 net 2.082 ns。10-07 将起点从 CLMS_327_541 FF1 移至 CLMS_339_541 FF1，
保留原 332 条；最终 333 条位置都实际生效，17 个时钟周期也未变，但两组
DDR 时钟分布与跨组路径恶化。最差新 setup 是 `phy_wrdata_en_r[0]` 到另一组
TSERDES TS_CTRL[6]，路由占 92.358%，skew −2.703 ns，并出现双向 hold 违规。
“更靠近一个门”不保证整机 setup/hold 改善；需要共同检查两组时钟与数据路径。

## 原生流程的几个非显然问题

- `override_pcf FALSE` 并不足以防止重建项目覆盖外部 PCF。
- PDS 解析普通 Tcl 时可能早于 dev_map 创建 PCF。既要解析时文件存在，也要在
  当前完整流程的映射后重新追加。候选脚本用了预映射和完整冷流程两次调用。
- PDS 会导出 `impl.tcl`，即便设置不同 `project_name`。应保留该文件名给导出，
  以 `flow_input.tcl` 输入并检查哈希不变；不能靠假工具测试断言工具行为。
- 把映射 DB 独立送 PNR 的试验没有读到完整约束，失败；未经验证的热复用流程
  不能替代当前完整项目冷构建。
- 打包后两个旧单元名消失的候选被严格拒绝。不要通过放松名称检查掩盖该问题。
- 10-07 布通用了 943 轮，约 6,453 秒的 detailed routing；全部网络布通后仍
  时序失败。停止条件应是原生结束和完整验收，不能由迭代次数推断成功。

可用实现：性能工程 `scripts/build_mac_conv_stage2_soc_candidate.ps1`、
`scripts/ddr_reference_placement.py` 和 `scripts/test_mac_conv_candidate_build_flow.ps1`。
脚本具体参数随版本核对；被拒绝的 PCF 留作实验，不是生产范本。

## 2026-10-09：映射变化后的严格绑定

配置与 DMA 简化后，旧约束中的一条 `wrlvl_dqs_en/...L6QL5` 打包单元不存在，
第一次原生冷构建被严格拒绝，尚未进入布线。根据明确的缺失记录删除这一条，
保留其余 331 条，不推断替代名；第二次完整冷流程全部时序满足。最终从 PNR
数据库导出的 331 条实际位置与输入一致，17 个时钟的周期/波形保持不变。
本例详细布线 168 轮、531.48 秒，hold 修复后才检查最终全部 summary；不能
将较快布通本身解释为时序通过。当前位流 SHA 为
`2e5087a4336399002f51258cb8525be6dfc025fcef401e0df2de912bac071ead`。
精确物理、程序下载与模型验收范围见性能工程
`docs/YOLOv5n_LUT_Board_20261009.md`，不是其他映射版本可复用的位置模板。
## CPU 迁移时的块 RAM 预算（2026-10-09）

CPU V3.1 接入完整现有 SoC 后，128 KiB 启动 RAM 的原生映射占满 155 DRM，
实际布局在启动 RAM 单元失败。将启动 RAM 缩为 64 KiB 并重新链接 bootloader
后，综合器把释放的 RAM 分配给其他存储，原生 DRM 仍为 155。不能只根据 ROM
字节数推算最终器件资源或可布局性。

候选约束显式设定 `syn_allowed_resources blockrams=144` 后，原生映射为
52,797 LUT / 38,725 FF / 191 APM / 144 DRM；余下 RAM 为布局留出空间，但
仍须通过实际布局、布线和全角时序。该资源预算是本器件的一次实验，不是可迁移
默认值。减小启动 RAM 必须检查链接段、BSS、最大栈需求和运行时缓冲；本次
链接器保留 16 KiB 栈，代码/数据/BSS 41,648 B，额外 7,488 B，不修改生产 ROM。

同版完整候选的 seed 4 与 seed 2 均布局成功，估算 slack 为 +2.469 / +2.224 ns，
但详细布线分别停滞在约 10,000 和 7,900 条未布通网络。seed 2 超过 300 轮后
仍有大量未布通，且从约 5,900 条恶化；核对归属后停止本任务进程，两者都没有
最终时序或可上板位流。布局估算为正不表示可布通；只改 seed 连续停滞时，应
根据拥塞/资源证据改变实现条件，保存停止原因，不能无限复跑同一条件。

PDS 2022.2-SP6.4 本地 User Guide 的 Placement Decongestion Mode 说明为
0–9：面积扩展通常改善布线而可能恶化时序，主要资源超过 70% 时建议选择
0–4。这是本工具建议，不作为其他工具的参数规则，也不能保证本例收敛。

## 2026-10-14：V3.5 S/Sv32 候选的资源优先决策

远程 main 加入 V3.5 显式 S/Sv32 配置后，63.642857 MHz 的两个布局种子
均在详细布线高未布通数时提前停止；它们不是频率上限证明。按用户要求另建
59.4 MHz 功能候选，PLL、FDC、DTS、时钟声明与测试脚本一起更新；SYS/timebase
仍为 49.5 MHz。ADS LUT 从 49,701 变为 49,652，但资源变化不能推出布线结论。

降频重新映射还更改了 PMA 地址故障 LUT 的自动网名，写死名字的 CPU ADS
审计在 PnR 前失败。修复应绑定实际生产者、输入和真值表，并让故障变异测试
继续拒绝错连；不能只放宽网名正则。该次快照的 85,760 组前端、2,144 组
PMA、17,152 组提示和五种故障变异已通过，物理验收仍独立。

59.4 MHz 布局种子 5 在第 610 轮达到零未布线，但最终慢角 DDR PHY setup
为 -0.960 ns，CPU hold 慢/快角为 -0.019/-0.011 ns，CPU 同域 setup
为 +1.162 ns。保持布局种子和频率、只改 route seed 及 hold 修复目标的
同频重试在第 519 轮布通，CPU hold 转为 +0.049/+0.037 ns，DDR PHY
慢角 setup 却恶化至 -1.767 ns，反向读数据路径为 -0.060 ns。零未布线
与局部 hold 改善都不是全角时序通过证据。

第六次实验增加两个违规 DDR 网的路由优先级并启用四轮关键路径迭代；首次
布通后第二轮第 760 次迭代仍有 171 条未布线网，按用户要求先减资源而停止。
它没有最终 STA 或可上板位流。布局物理 CLMA 从 10,851/11,675 到
11,046/11,675，约 95%；同一旧布局的 CLMS 为 4,764/4,975（96%），
DRM 为 140/155，而工程 FDC 的 DRM 预算正好为 140。新 ADS 的主要 DRM
使用者是 CPU 49、MAC 37、本地存储 32、帧缓冲 DMA 12；MAC 的 1 Mi bit
权重暂存 bank 用 29 块。该最低 29 块只适用于保留现有 1024 条×128 B
通用单作业容量的条件；Pikafish Stage B 单作业仅用 64 条，resident model
在共享 DDR 而不在此 bank。不能把 DRM 总使用率直接当成局部连线拥塞证明。
若缩小 bank，必须同时检查通用描述符范围、分块 DMA 次数、每拍 1024 位
读口、数值、周期和整机资源，不能只按模型单作业字节数推算 DRM 节省。
失败搜索的新增 DDR 优先网和自动四轮重布线选项
已从当前候选撤回，保存在失败快照中。FP8 资源改写经独立完整 ADS 复核
减少 364 LUT；同次 CPU 同域综合 setup 估计为 +2.138 ns，综合报告仍有
DDR PHY hold 违规。这些不是布线后的时序；尚无新布局 CLMA 或完整
CPU/DDR 双角时序。重新 PnR 前
先比较整机资源、CPU 综合关键路径和正确性；完整验收仍要同一输入快照的
CPU/ICache/CDC 门槛、PnR、双角 STA 与匹配位流。
来源：性能工程 `docs/Pikafish_Main_Integration_Candidate.md`、
`docs/validation/v35-sv32-20261013/search-budget.json`。

## 2026-10-15：内部 hold 修复摘要与最终 STA 不一致

59.4 MHz、120/155 DRM 的候选仅增加 HID 按下计数 MMIO，综合为
44,473 LUT、36,944 FF；详细布线第 163 轮达到零未布线，hold
修复后的内部摘要显示 `All Constraints Met`，CPU setup 估计 +1.632 ns。
随后同一次 PDS 的正式 `report_timing` 却报告 CPU 慢/快角 setup
−13.995/−1.593 ns，7 个失败端点；最差路径从
`frontend/ftqAlloc[3]` 到 FTQ 目标 RAM 写地址，只有零级组合逻辑，
但 66 扇出的这条网络路由延迟为 30.486 ns。DDR PHY 同次正式
setup 通过。构建脚本正确拒绝了这份位流，没有上板。

因此不能把 PnR 内部 hold 修复摘要当作最终多角报告；保留两份原生
报告及哈希，按正式起终点和路由延迟定位。当前在不改变 CPU RTL、
时钟或例外的条件下，仅对上述已确认的实际 PnR 网名增加一条受
快照审计的优先布线约束，结果仍待新的完整构建确认。来源：性能工程
`pds/input-snapshots/fe88c5a6cfac428d8574b4969f3bfbe9/`、
`pds/ddr3_test.rcf`。

## 2026-10-15：轻微负时序候选的功能板测边界

上述 `ftqAlloc[3]` 优先布线在新冻结快照
`cb4bacadcd544bc4b9e4ed3416482f53` 中将 CPU 最终慢角 setup
恢复至 +1.613 ns，DDR PHY setup +2.203 ns；正式双角 STA 仅剩
MAC 权重移位到权重 bank 的 SYS 慢角 hold −0.012 ns，一条失败端点。
构建仍按正式时序门槛拒绝发布，生成的位流只在独立核对快照、
最终报告和 SHA-256 后另存为测试候选。按用户明确授权，JTAG 只写
PG2L100H 易失 CRAM 测功能；板上 Stage B 96 例、384 个 MAC 作业
通过，Linux 和官方 PFF1 GUI 达到最终 READY。实体鼠标走棋尚未验收。

后续若只有少量、幅度很小的负值，可逐条审查违例时钟域、端点、
幅度、其余双角路径及输入快照，再单独标识候选哈希做易失 CRAM
功能诊断。功能通过不能抵消 STA 失败，也不能将候选位流复制到
正式 artifacts、发布包或交付证据。修正 hold 目标后必须重新完成
PDS 和正式报告审查。来源：性能工程 `pds/input-snapshots/`
`cb4bacadcd544bc4b9e4ed3416482f53/`、
`build/pikafish-min-drm-board/board_hid_candidate_stageb_20261015.log`。

## 2026-10-15：通过 STA 但保持余量接近零

一次完整 PDS 构建使用新 boot ROM、相同 V3.5 CPU RTL 和 120/155 DRM，
最终 slow/fast 均为 `All Constraints Met`，CPU setup 约 +1.983 ns，
但 CPU 同域 hold 只显示 +0.000/+0.001 ns。原生 hold 路径由 CPU
store-data 寄存器到同一 CPU 内的 ROB 存储 RAM 输入；工具 200 ps
修复目标未完全达到，正余量仍可满足正式 STA 门槛。报告四舍五入为零时
不可把它称作宽裕的时序，也不能凭单次功能板测推断运行稳定性。
保留路径起终点、时钟偏斜、位流哈希与冷启动/重复启动结果；若要提高
余量，先分析该路径及布线拥塞，再更改一个有根据的因素重新做双角 STA。

## 2026-10-16: original and duplicated LUT inputs need equivalent audit proofs

An unrelated audio FIFO changed PDS packing of the unchanged supervisor LSU:
the N972 LUT6D Z5 consumer used original aGo where an earlier mapping used
aGo_cpy. Do not bypass the pre-PnR gate or require a duplicate to exist when
the actual input is original. Accept only the reviewed input sets, prove any
used duplicate's producer, and exhaustively check the load truth table for
both values of the packed, unrelated query input. Corrupt a cofactor and cut
the PMA connection to prove rejection still works. Audit-script changes are
frozen inputs and require a fresh build snapshot; a prior failed gate remains
a failure even after a standalone diagnostic passes. This lesson is about ADS
audit equivalence, not timing or physical CPU acceptance.

For the matching voice candidate, PDS reported `Hold violation fix failed`
when some paths missed the configured 200 ps optimization target. The final
multi-corner RTR nevertheless reported All Constraints Met, with CPU hold
+0.153/+0.109 ns and unchanged clocks/constraints. Distinguish the optimization
target from the formal STA requirement; retain both diagnostics and the final
report rather than treating either a successful route or a warning string as
the acceptance decision. This is PDS evidence only, not physical audio or board
stability acceptance.

## 2026-10-17: CPU clock candidates and arithmetic reconstruction

For an integer-divider PLL, select an actual supported CPU clock at or above
the requested target and keep unrelated accelerator/timer domains fixed. In
the PG2L100H case, 891 MHz / 13 is below 70 MHz; / 12 is 74.25 MHz. Derive
PLL, FDC, CDC bounds, MMIO frequency, test clocks and Linux DTB together.
Unchanged firmware may be reused only with exact binary/ROM hash checks and
proof that clock-dependent software reads the matching hardware registers.
Its original build metadata must retain its original identity.

A routed multiplier-partial-product to writeback/reservation-station path can
be dominated by routing rather than arithmetic. A carry-save reconstruction
with one final carry-propagating adder is a source-level candidate, not a
timing result. Preserve signed/unsigned high-product correction, truncation,
valid/done, bubbles and back-to-back throughput. Test the original first,
regenerate paired synthesis/simulation outputs, and inspect whole-SoC ADS
resources and routed paths before adopting it. Passing unit tests does not
establish unchanged CoreMark/MHz or physical clock acceptance.

Native routing can report zero remaining nets for intermediate global-routing
substeps and then start another routing stage. Report the stage name and wait
for the final detailed-route, hold repair and formal all-corner STA results.
Source: performance_soc_voice_hw/docs/CPU_70MHz_Optimization_20261017.md;
the campaign and arithmetic alternative remain candidates until acceptance.

The 74.25 MHz search1 report later identified an ALU0-to-MDU bypass path,
not the historical multiplier path: final setup -0.211 ns, one failing
endpoint, 88.466% routing. The internal post-hold summary had shown -0.095 ns;
retain this difference and use formal report_timing as the decision source.
An exact measured-net routing priority requires updating and testing the
fail-closed input, native-execution and actual-netlist allowlist together.
Missing/duplicate/failed priorities and altered net spelling must still fail.
Do not relax the gate to allow arbitrary new nets, or adopt an unrelated
arithmetic alternative because its unit tests happen to pass. The subsequent
priority experiment subsequently improved formal CPU setup to -0.111 ns,
still failed at 74.25 MHz, and moved the critical path to ALU1 comparison ->
branch-recovery arbitration -> redirect-PC clock enable. A changed critical
path is new evidence; do not keep prioritizing the old bypass or label the
estimated 73.6431 MHz as an accepted 74.25 MHz clock.

## 2026-10-17: move owner comparisons before late eligibility

When selecting the oldest eligible lane and then comparing its age with a
pending owner, a late ALU predicate can traverse an age mux, comparison and
wide register enable. For unsigned circular ages measured from the same
head, `min(eligible ages) < pendingAge` is exactly equivalent to the OR of
each lane's `eligible && age < pendingAge`. The empty set is false. The
no-pending-owner case and external block/flush/reset qualification must be
preserved, as must the oldest-lane payload choice and tie behavior.

Test the original implementation first, then the source rewrite. Exhaustive
five-bit age predicates (4,194,304 combinations) and an independent 8,192-cycle
RTL interface model checked reset, flush, block, wrap, ties, target alignment
and invalid payload stability. The integrated candidate retained all other
63 generated CPU modules byte-for-byte, passed 96 CPU unit tests and core/
console functional checks, and reduced whole-SoC ADS LUTs by 82 with unchanged
FF/DRM/APM. These facts do not establish a timing or CoreMark improvement;
that candidate's final STA and board performance must be assessed separately.

The subsequent formal STA rejected that candidate: CPU setup -1.113 ns,
58 failing endpoints, versus the prior -0.111 ns / one endpoint. Routing
took 760 iterations and 2168.91 seconds. The new critical cone was ALU0
shift/writeback -> ROB/dispatch forwarding -> MDU operand capture, with
86.236% route delay and a 3.392 ns dispatch net. Whole-SoC LUT -82 did not
predict physical improvement. The isolated recovery module itself mapped
to 78 LUTs versus 77 before; distinguish inclusive module counts from
global optimization changes. Retain the rejected report and roll back the
source hypothesis before choosing another measured cone.

## 2026-10-17: move link arithmetic across an existing capture boundary

If a shared ALU writeback cone carries link-address arithmetic after the
execute register, calculate PC+4 on the issue side and capture it with the
same reset, enable, bubble and flush behavior. This may remove a carry chain
from the result-to-forwarding path without adding an execution cycle; inspect
the new issue-to-capture path as well. For BEQ/BNE, a direct equality test must
use the actual subtraction operands, including PCADD/immediate selection and
otherwise legal multi-hot control words, rather than assuming only two source
registers are compared.

The PG2L100H ALU candidate used a frozen original module as a whole-interface
reference for 16,384 cycles, tested it before the rewrite, then passed 95 CPU
unit tests and the core/console functional fixtures at unchanged cycle counts.
Paired regeneration changed FuAlu and removed only an unused Alu equality
output; the other 62 modules stayed byte-identical. Whole-SoC ADS measured
43,348 LUT / 34,581 FF / 120.5 DRM / 177 APM, versus 43,369 / 34,520 in
the routing-only control. Two 32-bit declarations mapped to 31 named DFF cells
per ALU; use actual netlist/resource counts, not declared bits, for budgeting.
These are source, functional and ADS observations; routed timing and board
CoreMark/accelerator acceptance remain separate requirements.

## 2026-10-18: incomplete route databases and explicit clock selection

A route log ending at "Saving design to DB" is incomplete even if detailed
route finished with zero unrouted nets. The PG2L100H fourth candidate's
internal post-hold CPU setup was -0.039 ns, but its 30.5 MB ADF copy was
rejected by native read-only report_timing with FileSystem-0003. Record
formal WNS as null, preserve the original and failed recovery evidence, and
keep the PnR start consumed. Do not infer the cause of process termination
without an owner/timeout receipt. Use a detached, auditable bounded owner
for a long build when the interactive tool session can end independently.

When an integer output divider cannot realize the requested minimum clock,
an independent PLL can be an explicit frequency choice. This changes the
hardware and requires full synthesis/PnR, not just a longer FDC period.
For this campaign, shared 891 MHz gave 74.25 or 68.538 MHz; a separately
reviewed 27 MHz * 2 * 15.75 / 12 CPU PLL gives 70.875 MHz while SYS/video
stay unchanged. A predeclared final choice is not evidence of same-frequency
improvement and must not be used to disguise additional search attempts.
Validate fractional-feedback legality, actual primitive waveform, both PLL
locks/reset release, resource capacity, rational periods, CDC bounds, MMIO,
DTS/DTB and firmware time conversion. Host/RTL passes still require final
multi-corner STA and board performance acceptance for the exact image.

Changing a PLL source also requires changing the FDC clock object, not only
its period and the audit's expected source path. The first dedicated-PLL
attempt still declared cpu_clk on the unused video PLL output. Native STA
showed nineteen clocks, zero loads on declared cpu_clk, and an inferred clock
driving the actual CPU; CPU/SYS exceptions named cpu_clk were ineffective.
Reject that run, including internal summaries. Add source checks for the
exact FDC object and inspect native ADS CLKOUT3 SDC annotations before PnR:
the actual CPU PLL must carry declared cpu_clk, with no inferred substitute.
Freeze that checker and run it in the ordinary pre-PnR gate. Preserve all
clock-pair coverage and existing exception/CDC limits when fixing the object.

Native report_timing -input_db_file on a routed ADF copy retained the DB's
saved constraints despite a different FDC registered in the project. It is a
read-only diagnostic, not a way to retime an old implementation or validate
a changed FDC. Use fresh synthesis and the full mapped/routed flow after
fixing source binding, and verify actual clock names, loads and targets.

The corrected original-CPU control passed the actual native ADS clock gate,
but its detached owner later disappeared during placement without a final
receipt or placement checkpoint. Keep the ADS result separate from final
STA: formal WNS remains null, and the start stays consumed. A detached launch
is not a completion guarantee. Check the recorded owner and native processes,
preserve the incomplete transcript, and do not invent a crash/timeout cause.
This case used a historical campaign quota. That policy was removed by the
user on 2026-10-19: current launches need no count/deadline exception.
Still record a real restart as a full launch, never as read-only analysis.

The user then allowed one identical retry under that historical policy.
Preserve failed records, the original input map and the seventh launch record;
the old six-start policy is not a current constraint. Do not edit frozen build
scripts to manufacture identical-input evidence. The ordinary unchanged build
then completed with all 446 inputs identical, actual declared CPU clock loads
11,660, and final CPU setup +0.166 ns / slow-fast hold +0.069/+0.052 ns at
70.875 MHz. Scope covered 18 clocks/116 summary rows and 20 max-skew rows;
the existing external I/O gaps remained disclosed. This is FPGA gate acceptance,
not board CoreMark/MAC acceptance.

PDS ran a further post-route hold repair after its internal after_hold_fix
summary. That summary had DDR group1 hold -0.469 ns, whereas the final native
report had +0.493/+0.115 ns. Preserve both and the native repair transcript.
Warnings about missing the 200 ps optimization target can coexist with positive
formal hold margins; do not lower the target or reject/accept solely from that
warning. In the same run, internal CPU setup +0.288 ns became final +0.166 ns.
An attached monitored owner recorded a normal exit for this retry; this does
not prove why earlier owners disappeared.


## 2026-10-18: distinguish zero constrained violations from full timing coverage

Read final native XML check_timing and warning tables in addition to the RTR
All Constraints Met banner. Recheck report/bitstream hashes against both the
build receipt and the actual programming receipt. CPU70 run 4b7d86bb had zero
failing endpoints across 116 slow/fast setup, hold, recovery, removal and pulse
width summary rows, and passed 10 Gray-pointer skew groups in both corners.
Nevertheless it retained 187 Timing-4086/4087 external I/O messages and
no_input_delay=61/no_output_delay=128 direction counts. These are different
statistics; do not describe 187 as a physical port count or full I/O signoff.
A baseline whitelist establishes no newly introduced gaps, not complete board
timing coverage. Native virtual_clock=1 here means no virtual clock was found;
inspect the detail before labeling it a failing internal clock. Record SCCB
unateness assumptions and empty-clock notices instead of claiming zero warnings.

## 2026-10-19: simplify retirement implications before CSR control selection

Follow every segment of a routed failure, including trips into an asynchronous
frontend target RAM. CPU80 candidate p6 failed with CPU setup -0.937 ns and 27
endpoints; the worst path ran from ROB valid through FTQ target comparison and
dual retirement into CSR priority control. The source implications were useful:
slot-1 head retirement requires slot-0 invalid, and dual slot-1 retirement implies
slot-0 retirement. Expressing CSR validity as slot-0 retirement OR slot-1 head
retirement can remove a redundant dependence on the dual-retirement decision
without changing retirement cycles. Parallel lane-qualified privilege/exception
controls need whole-interface comparison, including inactive outputs and arbitrary
multi-hot words, rather than tests restricted to normal instruction sequences.

The local d9b9467 candidate passed 8,192 whole-interface cases before and after
the rewrite; paired generation changed only Commit. Native synthesis measured
42,773 LUT / 32,344 FF / 119.5 DRM, +65 LUT with unchanged FF/RAM/DSP versus
p6. The complete CPU entry subsequently passed 127 tests / 48 suites; SoC23,
eleven Windows functional groups, actual candidate PLL edges and native ADS
gates also passed before the new full native build. These are correctness and
synthesis observations, not a routed improvement or CPU80 board acceptance.
The eventual p7 final report failed: CPU setup -0.682 ns / 63 endpoints,
CPU slow/fast hold -0.028/-0.015 ns and RGMII setup -0.046 ns. WNS improved
versus p6, but endpoint count and TNS worsened; describe both. Diagnose the
complete endpoint set rather than promoting a narrower source rewrite.
The earlier weight-input hold pads and official
Pikafish Stage A/B/cache remain separate, retained contracts.

Global ADS optimization can replace or move a module's nominal output port.
A fan-in query returning only the requested absent name is not independence
proof. Shared LUT6D inputs also require Boolean cofactor support analysis; raw
pin reachability can include functionally unused signals. Resolve observed
hierarchical aliases before comparing cones, and retain inconclusive diagnostics
as such. Do not convert them into timing evidence.

## 2026-10-19: preserve register boundaries and audit new native primitives

For a binary-head ROB read, a one-hot head register at the existing state edge
can move decode before the read cone without changing retirement latency.
Keep the binary payload-RAM address and prove reset/flush/advance priority,
stall and wrap behavior against it. For rename operands, raw register-file
capture followed by the already-registered use flag can move a late decode
away from wide FF data/reset inputs; compare the complete interface through
capture, wakeup, stall and flush. These are hypotheses until final routed STA.
The 439077d candidate passed before/after 4096-cycle checks, 14 targeted
integration tests, and 65536 vendor identity/write-edge vectors for 32 ROB
virtual-address pad bits. Its native mapping retained 16 head FFs and all
64 physical pad-to-RAM DI pins, with 42685 LUT / 32353 FF. Complete CPU
entry subsequently passed 129 tests / 50 suites. The p8 final STA still failed
CPU setup -0.054 ns / 3 endpoints, while CPU slow/fast hold improved to
+0.140/+0.103 ns. These are distinct final outcomes, not CPU80 acceptance.

Changed global mapping may legitimately introduce GTP_LUT6CARRY in an
unchanged frontend. Reject unsupported cells; derive both Z and COUT from
the unmodified vendor model, including I5_TO_LUT/I5_TO_CARRY defaults,
constants and functional support. Test all binary inputs for all parameter
combinations, walking INIT bits and random tables against vendor simulation.
The new checker passed 102400 output comparisons and the actual complete
metadata-cone BDD equality. Preserve the rejected frozen run and regenerate
a distinct candidate with the checker frozen into its inputs. A standalone
diagnostic cannot retroactively turn the old failed audit into a passing run.

## 2026-10-19: remove invalid-lane guards and prove absorbed SD write controls

In the p8 final report, static ROB RAM data reached CSR mtval/mepc through
slot-0 alignment exception, slot-0 effect, slot-1 store blocking and slot-1
head retirement. Slot-1 head retirement already requires slot-0 invalid, so
slot-0 effect is false on that path. Use a dedicated head-store guard with
only SB-full blocking, retaining the full two-store guard for dual retirement.
The ebf11de candidate passed 12288 before/after whole-interface/head-isolation
cases, paired generation changed only Commit, and the full 130/50 entry
passed. Synthesis measured 42643 LUT / 32353 FF, with RAM/DSP unchanged;
new final STA and board acceptance remain pending at this review.

Unrelated CPU mapping can absorb an SD bank's named cpu_write port into its
module body. Retain the old rejected run and do not merely accept a renamed
generated identifier. The new native SD gate follows actual RAM WE cones
across hierarchy, stopping only at FF Q, recognized RAM data outputs and top
inputs. Exact SAT checks prove CPU write/normal/busy/TX-full guards, byte
strobes, RX coverage, nonvacuous CPU/RX paths and mutually exclusive bank
ownership; independently retain 4096-bit CPU/TX views, read muxes, data-bit
coverage and CMD24/CMD25 checks. This is not full native SD address/data or
protocol equivalence; keep the functional RTL tests separate.

ROBDD variable ordering exceeded the node bound on the 172-leaf integrated
cone. A Tseitin CNF and the installed pycosat 0.6.6 proved those invariants
without combinational boundary assumptions. Validate the CNF compiler with
1008 direct truth-table output cases and reject 11 deliberate ownership,
strobe, capacity and disconnected-source faults. Bind the frozen checker,
snapshot and actual netlist hashes, and run both ownership and structural
checks before PnR as well as at finalization. Missing solver support or any
unknown cell must fail closed. New r9 synthesis passed these native gates;
old p8 remains a failed run despite later diagnostics.

The p9 Commit-only simplification passed 12,288 differential cases and the
complete 130-test/50-suite CPU entry, reducing whole-SoC LUT by 42. Final
physical timing nevertheless regressed to CPU setup -0.754 ns/104 endpoints
and slow hold -0.010 ns. Expanded read-only STA identified all 104 endpoints;
the formal ADF/RTR/XML hashes stayed unchanged. Do not infer physical gain
from fewer logic terms or a synthesis-area improvement. The user's next
priority was resource reduction before another timing attempt: profile the
native whole-SoC hierarchy, prove functional/cycle contracts and measure
mapping gains before launching another PnR. Preserve p8's near-pass and p9's
failed databases independently; neither is a board-accepted 80 MHz image.

## 2026-10-20: full correctness before a resource-only timing experiment

The MAC PE-result reuse candidate passed native resource gates at 41826 LUT /
29313 FF, 817 LUT and 3040 FF below p9, with RAM/DSP unchanged. Its two bank
profiles matched 128 cases and 22 reset phases; each profile retained 24385
output words and 64020 job cycles. The full Windows entry passed against all
452 frozen inputs, and rebuilt ELF/BIN/ROM matched the frozen firmware bytes.
The CPU stayed ebf11de with its already-bound complete 130/50 unit result;
the new native physical run was still pending at this review.

A synthesis-only tree has no final artifacts for synthetic board-release
policy fixtures. Supply a complete, read-only, independently hashed corpus
only to those policy tests, keeping current checker imports and all current
RTL tests. Label the borrowed corpus synthetic; never substitute its timing
or bitstream for the candidate. Forward the selected Python into nested
policy entry calls and model the new index-refresh step explicitly in the
fixture. Preserve the missing-artifact and old-host-path failures separately.
Build the staged pds/bootrom.hex alias from the frozen artifacts/bootrom.hex
before source-bound simulation gates; its absence is preparation failure,
not an RTL or native STA result. Fix the shared staging helper for future runs.

The subsequent p10 native run did not close timing: CPU slow setup -0.572 ns
with 155 endpoints/TNS -36.368 ns, CPU hold -0.028/-0.014 ns, SYS setup
+3.088 ns and DDR hold +0.141/+0.102 ns. All 116 formal summary rows and the
failed build were archived; the bitstream was not programmed. A read-only
replay expanded all 155 endpoints without changing formal ADF/RTR/XML hashes:
142 RAT, 5 recovery, 4 ROB, 3 Rename and 1 MDU reservation-station endpoints.
The worst IB address -> RAM -> instruction writeback decode -> RAT allocation
path had 11 levels and 85.386% routing. Preserve area savings separately from
physical timing; positive placement estimates are not the final routed result.

When moving RF-write classification ahead of the instruction-buffer memory,
do not freeze dispatch-time CSR privilege, TVM or counter-access permission at
fetch. Cache static legality/classification and resolve current permissions at
dispatch. The ibwrite experiment first matched the unchanged decoder across
45056 encoding and 97088 dynamic CSR cases, then expanded the compact version
to 274432 encoding cases; its old-buffer 4096-cycle/reset/backpressure oracle
was kept independently. Full CPU, native mapping, STA and board remain gates.
For the predictor-target FF -> RAM short path, a shared 16-pair/32-bit identity
pad passed 32768 vendor and 32768 default vectors, plus synthetic retention,
bit-order, source-binding and both-way DI-bypass faults. This does not prove
native retention or a physical hold margin before the new candidate is built.

## 2026-10-20: inspect the mapped carry before rewriting the arithmetic

The ibwrite candidate passed full correctness and removed the previous RAT
endpoint failures, but final CPU setup still failed at -0.937 ns/65 endpoints.
The worst ALU-to-writeback/ROB-forwarding/issue path was 92.381% routing.
Read-only expansion retained the original formal ADF/RTR/XML hashes.
An A+B+Cin source expression did not imply two mapped adders: PDS had already
absorbed carry-in into one chain. Packing carry-in in a discarded low bit
passed whole-ALU and execution tests, yet each actual ALU still used 34 carry
cells with the same parsed carry depth. Whole area decreased by 36 LUT, which
did not establish the intended local structure improvement. Preserve that
synthesis-only run and label the deliberately stopped full regression as
interrupted, not failed RTL or passed correctness. Require native mapping
evidence before spending another physical run on the same hypothesis.

## 2026-10-20: grouped carry and issue-union candidates need physical confirmation

A four-bit local carry/eight-group Brent-Kung implementation passed 168448
whole-ALU vectors and FU cycle/link checks. Native mapping reduced the two
ALUs' parsed carry depth from 34 to 7/11. Whole resource use was 42106 LUT /
29312 FF, versus 42077/29313 before this CPU change. The extra -1 FF belonged
to DDR training mapping: all 248 non-CPU hardware inputs stayed identical,
and the MAC remained at 5453 FF with its existing 3040-FF saving. Attribute
whole-chip and subsystem deltas separately. The full Windows entry matched
all 455 frozen inputs and rebuilt firmware bytes; full CPU and physical STA
were still independent pending gates at this review.

For base/fast issue arbitration, base OR fast equals the union of the two
operand-eligible sets. A union candidate outside base necessarily consumes a
fast operand. Keep fast2Valid out of blocker reduction and retain the age
matrix and final selector. The auxiliary candidate passed all 4096 pairwise
eligibility/age vectors, frozen-whole-RS and older reference checks at depths
4/8. Actual local tag-to-grant depth improved from 10/11 to 10/10 with +117
whole-chip LUT and no FF/RAM increase. This is a measured local tradeoff,
not routed timing acceptance; retain the primary candidate independently.

Random RS stimulus must model Dispatch's same-cycle writeback forwarding:
matching new operands need ready and the prioritized forwarded data. The
first untouched-DUT baseline rejected invalid stimulus. Preserve that source
and failure, correct the driver, rerun the original baseline, and only then
change the DUT. Never disable the producer-contract assertions to make an
equivalence test pass. Copy fault tools for auxiliary experiments so future
fixture-shape changes cannot invalidate another candidate's frozen evidence.

## 2026-10-20: independent clock pairs after a CPU arithmetic change

The grouped-prefix candidate passed full135/53 and the complete Windows
entry, but final physical STA still failed CPU setup -0.291ns/32 endpoints.
It also failed DDR sysclk to bank1 PHY setup -0.807ns/7 endpoints, slow/fast
hold -0.081/-0.250ns, and RGMII RX setup -0.011ns. Positive DDR self-clock
hold +0.139/+0.101ns did not cover the failing cross-clock pair. DDR RTL
and constraints were unchanged: global placement/clock routing still changed.
Preserve every failing clock pair and corner, including clock skew and the
existing multicycle/uncertainty settings; do not relax them to accept CPU.

Read-only expansion identified all32 CPU endpoints and preserved formal
ADF/RTR/XML hashes. Nine crossed ALU sum-zero equality into recovery,
eleven started at MDU valid through writeback/issue, and twelve covered other
operand/LSU/CSR paths. A direct subtraction equality is algebraically sound,
but the standalone ALU also exposes sum-zero in non-subtraction modes.
Keep that full-interface behavior, including PCADD and mixed operation
masks, and inspect actual mapped consumer dependencies before claiming that
a source rewrite removes the arithmetic path. Focused equality tests alone
do not establish a physical cut or final all-corner closure.

## 2026-10-20: a dedicated equality chain is a different physical hypothesis

Keep the generic ALU's sum-zero interface intact when only the BEQ/BNE
consumer needs equality. A consumer rewrite can use the same selected
PCADD/source and immediate/register operands, retaining arbitrary mixed
operation masks and all public FU outputs/cycles. Freeze the prior whole FU,
run the untouched baseline, then compare the candidate over all256 branch
masks, four ALU masks, both operand modes, boundary values and reset/flush.
This example passed16384 directed cycles/four resets plus the existing whole
ALU/shift/link references before pairing the source and generated exports.

PDS mapped the direct equality into a separate dedicated comparator carry
chain. Conditional support fell132/130 to51/52 cells and whole area fell136
LUT with no FF/RAM/APM increase. Parsed depth nevertheless increased; counting
primitive types does not compare the different output timing arcs or routing.
Do not promise a carry-free comparator or routed improvement from `==`, and
do not equate more parsed levels with a measured delay regression. Preserve
both sides of the tradeoff and require the unchanged full physical STA gate.

Hierarchy names can misidentify the remaining dependency. A diagnostic first
rejected any Alu-local cell, but the only shared term was the final wbBrTaken
Z gate folded into that module. Under the fixed BEQ/BNE controls, its CIN/
ordered-compare input was absent from exact LUT cofactor support. Allow only
that actual root/output and proven input support, retaining rejection of
other arithmetic dependencies. Preserve the original diagnostic rejection,
tool/netlist hashes and corrected evidence; do not weaken timing exceptions
or the native build audit. Full CPU and board gates remain independent.

## CPU75-derived CSR experiments (2026-10-20, not physical acceptance)

Read the accepted baseline's actual routed paths before transferring a later
candidate's bottleneck. CPU75/942e2dd had D-cache to ALU shift input at +0.524
ns, followed by ROB head metadata to supervisor instret[63] CE at +0.531 ns
and 18 logic levels. Later CPU80 trap paths describe different implementations
and layouts. A new experiment should isolate one such verified dependency.

The CPU75-derived 47bd9d85 Commit/trap control experiment passed 16384
Commit and 16384 CSR full-output cycles and paired generation. At an identical
80 MHz SoC synthesis input set it used 41117 LUT/29273 FF versus the CPU75
control's 41199/29273. These are synthesis and local mapping observations,
not final STA or CoreMark results. A separate instret experiment tests all byte
and word carries, counts 0..7, inhibition and competing trap/return/CSR writes
against a frozen CPU75 reference and an independent state scoreboard.

Commit the paired implementation before staging source.json, then assert the
exact implementation SHA and clean worktree after import, before firmware
source manifests or FPGA input freeze. A staging race recorded the right RTL
under the old commit with dirty=true; its owned synthesis Job was stopped and
preserved, and a new directory was staged from the clean frozen commit.

Normalize line endings for module-text comparisons between git-show bytes and
text-mode file reads. Preserve exact file hashes separately. Native PDS may
remove or rename public module ports through cross-hierarchy sharing: a missing
target must report unavailable, not a one-leaf cone or absence of dependence.
Local surviving-port depths require an explicit scope limit and cannot prove
the complete ROB-to-CSR delay; actual final all-corner STA remains the gate.

The isolated CPU75-derived fefd9305 instret rewrite passed 121 CPU tests and
the complete SoC entry with all455 frozen inputs. Parallel old-state byte
carries reduced surviving retireCount-to-instret local mapped levels63 to10
and carry levels63 to8, with unchanged FF/storage/multiplier capacity. CSR
half-word writes suppress the increment and preserve the other old word;
trap/return priority and old-state inhibit semantics need explicit boundary
tests. This measurement is local logic depth, not delay or routed closure.

For CPU75, control-only and instret-only CPUs, the same two compact CoreMark
ROMs gave identical CRCs, workload ticks1186933/1192632 and total CPU
cycles1257711/1263689. Ten iterations are a cycle-regression fixture; the
official port rejects that duration as a valid score. Never promote it to
CoreMark board evidence. Full native STA and actual model/CoreMark board
measurements remain required, even with identical non-CPU hardware sources.

Synthesis can assign a few LUTs differently across unchanged accelerator
hierarchies because of cross-boundary optimization. Record every difference,
check exact source inputs and state/storage/arithmetic capacity, and retain
original diagnostic rejections. Inclusive hierarchy rows cannot be summed.
Identical sources/capacity do not prove equal physical model performance.

## 2026-10-20: distinguish an interrupted owner from stale RUNNING receipts

After a conversation/tool interruption, recheck owner PID, creation time,
argv and native engine descendants. A stale BUILD_RUNNING receipt with no
owner, a stopped partial routing log and no final RTR is an interruption,
not a setup failure or a pass. Preserve original receipts/logs/snapshot and
mark the execution history separately. Retry identical gated inputs in a
new native root/run; do not rewrite an old snapshot to finish a different run.

In this Windows host, ordinary child processes and a WMI-created worker were
still subject to an outer kill-on-close Job. A harmless native probe using
CREATE_BREAKAWAY_FROM_JOB succeeded but IsProcessInJob remained true: the
remaining host Job had flags0x1800 (breakaway/silent-breakaway, no kill-on-close),
versus ordinary-child0x2800 (kill-on-close/breakaway). Inspect actual limit
flags and verify a hidden worker's real PID/time/argv before launch; Job
membership alone cannot distinguish those cases. Keep the native build's
own bounded Windows Jobs and stage deadlines. Do not generalize these host
flags to another environment or silently remove process-ownership guards.

## 2026-10-22: convolution enable can evict CPU cache block RAM

CPU80 convolution enable synthesized to 140 DRM under the project's soft
mapping budget. The convolution subtree used 32 DRM/14 APM, including six
descriptor-guard APMs beyond the eight PE APMs. CPU cache storage silently
fell from 58 to 46.5 DRM, with an instruction-cache LUTRAM/FF replacement.
Inspect hierarchy mapping before assuming an unchanged CPU retains its
physical cache implementation or that a PE count equals total DSP usage.

Keeping both 32x1024 weight banks and their existing output registers, an
explicit LUTRAM mapping reduced the complete design to 121.5 DRM, 46726
LUT and 35396 FF in a new synthesis, restoring CPU cache block RAM. The
before/after public-interface differential covered 60000 cycles each at
depth4/27/32; enabled/disabled dense/gather matched seven exact cycle counts.
These are correctness/resource evidence, not final STA or board performance.
Do not remove register boundaries to obtain a smaller resource number.
Preserve failed preflight snapshots; fix a mistaken resource assumption in
the checker and require a fresh run rather than relabeling the rejected run.

An unavailable board permits an explicitly requested offline candidate,
with complete SD software and an independent unpack/rebuild receipt. It
does not permit inherited board performance, formal delivery completion or
remote hardware publication. Bind new SD candidate_run/bitstream fields
separately from the accepted software-baseline run; include prerequisite
loader sources and simulation bootrom bytes beyond the FPGA input list.

The CPU80 all-LUTRAM convolution trial 43e6b02b subsequently failed final
slow setup by0.117ns at one RsMem s1ValA_1[17] endpoint (14 levels,
1.810ns logic/10.301ns routing,85.055% routing; worst CPU hold+0.087ns).
Resource reduction and restored caches did not guarantee timing closure.
Preserve its original RTR/XML, database, generated bitstream and rejection;
do not publish that image as a usable candidate. The project's stricter
minus0.1ns resource-first rule applies. A mixed bank-memory trial may use
available block-RAM budget to reduce distributed storage, but requires
fresh synthesis, CPU cache mapping/read-register checks, correctness and
final all-corner STA; do not claim success from a predicted resource delta.

The hybrid bank trial0fad63eb failed pre-screening:47095LUT/36423FF/
4892LUTRAM/136.5DRM, increasing369LUT/1027FF versus the all-LUTRAM trial.
Its CPU ADS folded-RAS binding also rejected the actual mapping. Keep both
rejections; fewer LUTRAM cells did not mean fewer LUTs or preserved CPU map.
No PnR was started for that candidate.

For the16-output convolution frontend, only the low512weight bits feed
MACs; the high512bits feed a linear32-bit window checksum. A separate
candidate stores low512bits plus the upper-half folded contribution in a
544-bit bank, retaining32lines,128DDR bytes/line and one registered read
boundary. Default DMA raw1024-bit mode remains intact. Reconstructing the
upper checksum contribution as word31 and15zero words preserves the full
32word fold; no host ABI/quantization change follows from this representation.
Prove the actual consumers and module mode before applying this optimization
elsewhere: a consumer reading any raw upper weight would invalidate it.

Synthesis28471092 measured46120LUT/34916FF/4924LUTRAM/121.5DRM,
minus606LUT/480FF. Native checks retained512MAC output FF,32checksum FF,
read_valid and CPU cache DRM allocation. Exact affine truth-table checking
of128mapped LUTs proved all32fold outputs over512independent registered
bits; the preload cone had3LUT levels and maximum2data pin loads. These are
structural screening metrics, not routed timing or physical fanout. The new
four-state320x320 full-layer simulation independently matched CRCeb240272
and8897293cycles; full SoC passed. Final all-corner STA and board acceptance
remain separate gates; these synthesis/correctness facts alone are not a
usable-image or performance pass.

## CPU80 folded-store final native 8f05785e3ff0461caa69af2d35620f40

The frozen458-input SoC836090ec36bceab9e55085f89cfae97810918271 passed final116 timing rows and20skew rows at CPU80MHz/SYS49.5MHz. CPU setup0.03ns/hold0.069ns. Formal synthesis repeated the544-bit read/cache allocation and exact affine proof; three synthetic wrong-wiring/nonlinear-LUT/wrong-clock faults rejected. This is an offline candidate; independent ZIP unpack/rebuild is recorded separately, and real-card/board acceptance and remote publication remain pending.

## 2026-10-22 CPU80 SD ROM repair final native result

SoC3433872213649fde70106dda3f18bfd9fd7fcfce keeps CPUfefd9305 and changes the ROM's
zero-address SD loader. The new459-input run44aa982f752c4b7d91accea60292735f passed
final116timing rows and20max-skew rows at CPU80MHz/SYS49.5MHz. CPU minimum setup
is +0.030ns and minimum hold +0.069ns. Bitstream SHA256 is
30d8f0d5ccdefcf9225780965df3efd399b9b9f27eb390d849754fcd57d526f1.
Relocated full regression rebuilt all459inputs byte-identically. Both actual SYN
netlists separately passed544-bit read-boundary/cache and512-input/32-output affine
fold proofs; three synthetic faults were rejected. The new native content gate
also rejected six altered identity/proof fixtures without mutating native files.
These are offline gates. Direct SD boot, new-image board performance, physical
HDMI and final ZIP/media completion remain pending; old UART-bootstrap diagnosis
must not be promoted to production SD acceptance. Intermediate after-hold timing
numbers differed from the final report: only the final RTR/XML values above bind
this run. Existing external I/O coverage gaps61/128 remain disclosed.

## CPU80 convolution offline package fixture dependency recovery

The first offline ZIP cfa9b938 failed independent regression because the source inventory filtered historical policy fixture ELF files. Include the union of that fixture snapshot inputs and evidence outputs explicitly, beyond the main FPGA input set. Preserve the failed ZIP/logs, create a new ZIP and independently extract it to a new directory; never patch the old extraction and claim its original ZIP is reproducible. Revised ZIP fb8dcc89eb73d51366854ea3285acea3f4c9048d21a59c21a912615d52b04f00 passed the full independent SoC regression and relocated SD loader byte rebuild. Hardware inputs/bitstream stayed unchanged and board acceptance remains pending. This is post-seal maintenance; the packaged skills manifest remains immutable.
