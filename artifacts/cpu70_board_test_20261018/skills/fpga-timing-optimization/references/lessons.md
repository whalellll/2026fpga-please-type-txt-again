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
If the fixed campaign budget is exhausted, request an explicit exception
before another full launch; do not relabel a restart as a read-only analysis.

The user explicitly allowed one identical retry. Preserve the six-start policy
and failed records, bind the separate exception to the original full input map,
and account for the seventh launch before starting. Do not edit frozen build
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
