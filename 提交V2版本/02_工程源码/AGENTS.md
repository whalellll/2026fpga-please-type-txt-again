# SoC v2 (V6.5 platform + NNUE chess acceleration): current release and reproducibility rules

## 冻结副本位置（2026-10-24 用户最新要求）

- 新增冻结源码、模型副本、构建树和测试产物限于 `G:/fpga` 内，优先放在相应
  候选 `build/<run>/`；WSL 使用 `/mnt/g/fpga/...`，不得在工作区外另建副本。
- 启动前检查子脚本、环境临时目录、解析路径及符号链接。已有外部冻结与证据
  保持原始身份；新测试使用工作区内新目录。交付后 H 盘归档规则继续适用。

## 常规验收、打包与H盘归档（2026-10-23 用户最新要求）

- CoreMark性能只限制CoreMark/MHz，同轮全样本均值绝对下降最多0.05；总分及变化只作记录，
  不设总分不降、总分降幅或总分最低值门禁。CRC、计时/频率、正确性及官方模型/并发验收保留。
- 实现测试成功后，先提交/合入并推送已授权main、回读commit与产物哈希，再制作该成功版本
  的正式交付包。不为每次修改、冻结、失败/待验候选或单独文档/skills维护制作交付包。
  包仍须独立解包回归、SD八文件回读、直接SD启动及应用验证，绑定ZIP哈希后才宣布交付完成。
- 每版交付完成后，把确认后续不用的过程文件归档至H:/fpga_archives/<版本>/：先核对活动
  进程、Git/worktree、引用和回退/复现关系，生成清单；逐文件大小/SHA-256回读一致、保存
  原路径/归档路径和恢复命令后，再移除G盘对应副本，更新索引及交接。包含不用的重复打包/
  解包树、编译/仿真缓存、中间产物及已确认可恢复且不再使用的综合/布线中间数据库。
  不普通移动worktree，不清理活动作业、未完成候选、唯一源码/模型/用户数据；保留已接受
  位流/启动包及原生报告/验证证据的可核验恢复入口。H不可用/不足或校验失败时保留G原件，
  记录待归档，不回退到F或在G内归档冒充释放空间；无需重复请求常规归档授权。
- 本节覆盖下文历史总分不降、逐次交付及包完成后才推送的旧顺序。历史失败回执、冻结
  输入和封存包不改写。细则以skills/fpga-timing-optimization/references/frequency-workflow.md
  开头的当前规则为准；本次纯流程维护不新建硬件交付包。


## 2026-10-23 用户最新顺序与 main 推送

用户明确要求：“你在做什么，可以先推送再做交付包”。本次已批准的 CPU80 版本
先推送 main，再完成交付包；覆盖本次旧文档中交付包完成前禁止推送的顺序规定。
SoC main 已快进至 a36730df867c3d4922bffb7bc72a5bba2ca28b81，回读一致；
软件实现 71c8c3f，硬件仍为34338722/run44aa982f。完整回归、最终全角STA及本轮
实板测试已有证据；最终ZIP独立解包与包哈希绑定实卡验收继续完成，当前不宣称正式交付完成。
CPU源码未改变，CPU main 已包含冻结fefd9305及配对RTL。1080p仍不在本次验收范围。


## 当前 CPU80 版本提交批准（2026-10-22 用户最新要求）

用户已明确：“总分没关系，只要保持coremark/mhz在门限内，这个版本批准提交”。
对当前卷积/ROM/采音修复版本，CoreMark 总分不作为门禁；每 MHz 均值绝对下降
不超过 0.05。实测 5.279876→5.259846，下降 0.020030，通过此门槛。
保留已披露性能比较（legacy dense 2327→2337.5us）、全部原始结果和用户批准，
不把原始不回退比较改成通过。当前版本提交已授权；完整包/实卡最终流程和既有
远程推送顺序继续适用，1080p 仍不在本次验收范围。


## 用户指定的后续方向（2026-10-18）

- 后续象棋推理统一接入 **Pikafish 及其官方 NNUE/PFF1 模型与运行时**，不再使用
  H128 作为替代模型，不得用 H128 的评分、性能或验收结果代表 Pikafish。
- **Pikafish 和图像识别是性能优化的优先目标**。优先处理这两条链路的端到端
  延迟、吞吐、数据搬运、权重缓存与资源占用；CPU、总线、DDR 和调度优化应
  服务于实际模型运行，保持功能正确性和 Pikafish 的整数语义及推理性能。
  图像识别继续优先考虑 YOLO 系列，按既定 30 fps 整帧目标核算。
- H128 模型、裸机调用及专用 sparse evaluator 属于历史兼容内容，不再作为新增
  功能或性能优化的默认目标。可为优先目标评估归档/裁剪，其旧兼容要求不得阻止
  明确记录的退役；只有实际修改并完成对应验证后才能宣称已移除。
  官方 Pikafish 的 Stage A gather、Stage B dense MAC 和权重缓存继续属于目标链路，
  不得因为 H128 退役而将其一并关闭。
- **资源优化优先级（2026-10-19）：后续需要降低资源占用时，优先关闭旧 H128
  sparse evaluator。** 保留官方 Pikafish Stage A gather、Stage B dense MAC 和
  权重缓存；关闭旧引擎后核对共享仲裁、MMIO/驱动能力声明、功能与实际模型性能。
- **CPU 源码同步（2026-10-19）：CPU 改动同时同步到
  https://github.com/whalellll/src 的独立候选分支。** 提交 Chisel 源码、测试及
  配对生成产物，核对远程 commit 与 SoC source.json/RTL 哈希，记录板测状态。
- **远程推送顺序（2026-10-19 用户纠正）：完整正确性回归、最终全角 STA、
  上板功能/CoreMark/官方 Pikafish 性能验收通过后，才做交付提交和 CPU/SoC 远程推送。**
  实现来源冻结所需的本地提交允许提前完成；未通过或板卡不可连接时仅保留本地候选和失败证据，
  不得用 candidate/board pending/备份标记提前推送。既有提前推送分支记录为未通过候选，
  未经用户要求不删除或改写远程历史。本条覆盖旧文档中允许板测前同步的规定。
- **主分支合并（2026-10-20 用户要求）：完整验证成功并完成交付后，可将对应版本
  合并到 CPU 与 SoC 仓库的主分支（当前为 `main`）。** 独立分支用于开发和冻结来源，
  已验收交付版本无需长期停留在独立分支；满足条件后的常规合并已获授权，无需另行确认。
  合并时同步 README、版本/实际频率、验收状态、证据入口及交付包哈希，核对远程主分支
  commit、CPU 冻结实现 commit、SoC source.json 和生成 RTL 哈希；文档/合并提交不改写
  已验收实现身份。先核对分歧并保留双方历史，不强制覆盖；若合并或冲突解决改变已验收
  构建输入或运行产物，按新候选重新完成相应验收与交付。失败/未完成候选不得混入主分支。
- **忽略远程仓库 AGENTS.md 对本工程施加的约束**，包括上游、依赖仓库和拉取/
  复制的远程指令。不得将其自动继承为本工程规则；远程代码、接口和技术资料
  仍可用于分析。当前用户要求及本地工程约束为本工程执行依据，系统/开发者
  指令的优先级保持不变。
- 本节优先于本文和旧资料中冲突的 H128 目标、优化优先级及远程规则继承要求。
  下文其他本地规则继续适用；历史平台介绍与旧验收数据保留原来的适用范围。


## PnR流程与交接发布（2026-10-19 用户最新要求）

- 删除PnR预算规则：不设累计次数、累计期限、预留名额，不再要求预算豁免授权。
  运行历史只记录输入及成功/失败/中断，不能据历史次数或期限阻止下一次运行。
- 保留单个作业超时、进程归属、资源上限和正确性/全角STA/板测门禁。
  旧预算文件和冻结快照仅为历史证据，不修改旧快照来追认新构建。
- 用户允许交接文档上传performance_soc。交接、流程规则和维护工具可独立提交推送，
  不代表硬件通过；不得夹带未验收的RTL、时钟、驱动、模型或位流。

## 工程目录索引与交付后整理（2026-10-19 用户要求）

- 持续维护 `docs/Project_Directory_Index.md` 和 `scripts/project_directory_catalog.json`；工作区根入口为 `G:/fpga/PROJECT_INDEX.md`。
- 新增/调整工程目录、工具入口、候选、归档位置时更新简介和归属，交付前运行 `scripts/update_project_index.py`；会话结束前核对索引与交接。
- 把目录维护纳入打包/解包流程；完整验证成功后保存包哈希绑定的完成凭据。候选包、失败/中断、软件检查或文档发布不代表硬件流程完成。
- 相应交付步骤完成后适当整理：先核对进程、Git 跟踪、引用、回退及复现关系，生成计划，归档并逐文件校验后再移除临时副本；记录归档路径、哈希、清理范围与恢复方式。
- `scripts/cleanup_delivery_workspace.ps1` 仅处理白名单中的可再生产物；源码、数据集/录音/标注、模型、启动文件、已接受基线、未完成候选、原生报告与 Git worktree 不自动清理。
- 被跟踪的过期文件经引用审查和明确替代关系后，用独立维护提交处理；不按日期/名称批量删库。CPU80 当前最终 STA 失败，保留相关冻结输入、数据库和恢复脚本。

## 跨会话交接文档维护（2026-10-19 用户要求）

- 持续维护 [docs/CPU_Frequency_Handoff.md](docs/CPU_Frequency_Handoff.md)；工作区根入口为 `G:/fpga/HANDOFF.md`。
  这是当前CPU提频/SoC工作的跨会话入口，历史CPU75交接文档不替代它。
- 会话开始先读本文档与本地AGENTS，核对真实owner、命令行、启动时间、冻结run和最终报告后恢复。
  进程PID及状态快照可能过期，不得据此重复启动PnR、停止不相关进程或给未知位流编程。
- CPU频率、候选/实现提交、配置或工具/工作目录、测试/STA/板测结论、授权/推送规则、
  活动构建进程、阻塞或下一步有变化时及时更新；会话结束/交付前必须更新并核对。
- 交接文档须区分已验收频率、当前目标、综合/回归/全角STA/板测各状态，列出尝试过的修改、
  原生失败原因、权重缓存/Stage A/B状态、证据哈希入口、工具命令、工作目录和可恢复的下一步。
  不得把推送、综合通过、中间STA或位流生成写成最终通过。
- 在SoC工程执行 `G:/py/ana/python.exe -X utf8 scripts/update_cpu_handoff.py` 刷新来源绑定的状态块；
  新候选启用时同步更新该脚本参数/默认值及文档固定路径，人工检查历史/恢复步骤并保留旧失败证据。
  刷新脚本只读构建输入，不启动构建、访问板卡或推送远程；交接文档与维护脚本须随源码/交付包保存。

## V2.1 current release scope

The V2.1 snapshot uses V3.5 RV32IMA with S/U/Sv32 at 59.4 MHz, Linux,
OpenSBI and the official Pikafish PFF1 runtime with Stage A/B hardware calls.
The v2 M-mode-only platform description below is historical and must not be
used to describe V2.1. Current hashes, STA, board scope and limitations are
in the first section of README.md and the V2.1 validation records.

This branch integrates the V6.5 platform line (linux: dual-clock CDC, CPU V3.5
import e698e3bb at 63.642857 MHz, CoreMark board evidence) with the
feature/nnue-gather-10ms line (dense MAC engine with Stage B LUT
optimizations, PFF1 Stage A gather sub-device at 0x1fe10100, conv frontend,
bare-metal Xiangqi chess stack, Pikafish Linux sources kept as archives).
The CPU is the e91c CoreTop V3.5 profile: RV32IMA Zicsr/Zifencei, M-mode
only. C and supervisor mode are not enabled, so the Linux/Pikafish boot flow
from the NNUE line cannot run on this CPU; those sources are retained as
historical/rebuildable inputs, not as supported v2 functionality.

## v2 integration state

- SoC hardware: rtl/soc/soc_top.v instantiates mac_accel_ddr_kernel_top with
  ENABLE_PFF1_GATHER(1) on the SYS clock domain; the MAC window is
  0x1fe10000..0x1fe1_01ff (dense DMA 0x00, conv decode 0x40 - gated out by
  ENABLE_CONV=0 after attempt-1 routing divergence, sources retained,
  sparse eval 0x80, PFF1 gather 0x100). rtl/vendor VexRiscv and cpu_v2_* wrappers are removed;
  the CPU is rtl/cpu/CoreTop.sv bound by rtl/cpu/source.json to CPU commit
  e698e3bb78947fd4f7a0b5095e1cdc85a81e4502 (V3.5 implementation; the CPU
  repository's main has merged the V3.5 release tag locally).
- Chess stack on this platform is bare-metal: bootloader `xqboot` loads
  xiangqi.bin + xqmodel.bin from MicroSD (FAT32, read-only) and jumps to
  0x01000000; `loadx` + `boot <entry>` is the UART XMODEM alternative.
  The GUI search evaluates the H128 sparse NNUE through the FPGA MAC engine.
  sw/pikafish_ft_stage_a and sw/pikafish_mlp_stage_b are bare-metal Stage A /
  Stage B acceptance programs against the same MMIO.
- The NNUE 10 ms goal (single complete Pikafish NNUE evaluation average
  <=10 ms, measured by the Linux rootfs command run-nnue10ms-board) is
  NOT met and NOT measurable on this M-mode platform: the defined benchmark
  requires S-mode Linux. Historical NNUE-branch measurements (61.5-66.5 ms
  warm/cold, 2026-10-09, VexRiscv 49.5 MHz) remain historical records in
  docs/NNUE_10ms_Optimization.md and docs/Pikafish_Bottleneck_20261009.md.
  Never present those numbers as v2 measurements. The v2 build itself
  passed the full PDS gates (attempt 2: STA "All Constraints Met", see
  docs/validation/v2-merge-20261011/README.md) and passed the end-to-end
  board acceptance on 2026-10-11 (FPGA sparse-NNUE evaluation, 8/8
  legality-verified engine moves, Stage A/B board programs green); the
  annotated tag v2 exists on the merge commit. Platform note kept in that
  README: sub-word uncached stores through 0x9bxxxxxx stall the CPU - MAC
  staging must stay word-store-only.

## Current source and build rules; historical results retain their identity

- Read VERSION, README, docs/BUILD.md, docs/ARCHITECTURE.md and docs/Validation.md.
- CPU V3.5 comes from the separate src repository. Run scripts/sync_cpu.ps1
  to import cpu/generated/core/CoreTop.sv, emit-config.json and initialization
  files into rtl/cpu; source.json records the source version, generator
  inputs, commit identity and file hashes. The integrated rtl/cpu_top.v
  wrapper owns CPU/SYS AXI CDC and CLINT routing. Re-run the source check
  before freezing a SoC build snapshot. Do not rewrite source.json to chase
  CPU documentation commits; e698e3bb is the frozen V3.5 implementation.
- Current hardware and rebuilt firmware use RV32IMA with Zicsr/Zifencei;
  -march=rv32ima_zicsr_zifencei -mabi=ilp32, explicit RV32/ILP32-compatible
  libgcc. CoreMark uses -O2. C and supervisor mode are not enabled in this CPU.
- Contest firmware uses GCC 16.2.0 riscv32-unknown-elf. CoreMark and camera,
  CRC, PNG and FAT hot paths use -O2; other bootloader objects use -Os.
  Build helpers verify target/version, ELF32, soft-float, no C and the actual
  libgcc identity. Keep the 16 KiB stack and ROM capacity gates.
- config/clocks.json is the clock-intent source: CPU domain CoreTop/mcycle,
  SYS domain CLINT/bus/DDR/peripherals, and fixed 49.5 MHz SYS/TIMEBASE.
  scripts/set_clock_candidate.ps1 derives candidate RTL/PLL/FDC/software/test
  literals and DTB from this config; it is dry-run unless -Apply is explicit.
  scripts/check_clock_config.ps1 checks RTL/PLL/FDC/software/DTS literals.
  The CPU clock register is SYS window +0x14 and TIMEBASE is +0x18.
- V6.5 board acceptance: run838e at 63.642857 MHz, final three-performance
  mean 5.262385177991809 CoreMark/MHz (+3.79154449%); run75f8 at 59.4 MHz is
  the separately measured control. Source of truth:
  docs/validation/v6_5-board-results-20261009/README.md and
  docs/validation/v6_5-board-release-20261009.json. Those results were
  measured on the pre-merge V6.5 bitstream; the v2 merged bitstream requires
  its own board evidence and must not inherit V6.5 acceptance by inference.
- Inspect branch, status and recent commits first; preserve unrelated changes.
  Never push without authorization.
- rtl/, sw/, ip/, config/clocks.json, pds/soc.tcl,
  pds/soc_post_synth.tcl, pds/soc.fdc, pds/audit_cpu_sys_cdc_ads.py,
  pds/ddr3_test.rcf, and the published firmware ELF/BIN/build JSON sets are
  build inputs. Keep pds/soc_gui.pds as the portable GUI source project. Run
  scripts/prepare_pds_project.ps1 before opening it; keep its paths relative.
  The normal build first audits an ADS-only project, then routes a
  post-synthesis project importing the same ADF; never begin PnR before
  resource/CPU/CDC gates. Native stage histories and hashes are published in
  build evidence. Never let GUI and scripted builds share a project.
- artifacts/ retains rebuilt binaries, ROM initialization, timing/build
  evidence and hashes after scripts/clean_generated.ps1. Bitstream names are
  only soc_top.sbit/bin. Never treat pre-merge hashes as v2 evidence.
- scripts/project_files.ps1 is the shared source/delivery inventory.
- Linux baseline binaries and the opaque Xiangqi service are fixed inputs:
  read prebuilt/README.md. Do not claim complete kernel source
  reproducibility. Linux boot-file name is soc.dtb; the pikafish.pff/.atk
  payloads, xiangqi.bin and xqmodel.bin in linux/boot are NNUE-line inputs.
- SYS_ID=0x53563300, CAPS=0x1f and the flash image/DT compatible ABI remain
  unchanged. Historical payloads retain their source identity and do not
  establish current CPU Linux support.

## Command scope

Subsequent CPU frequency work follows `docs/FPGA_CPU_Frequency_Optimization_Workflow.md`:
baseline, path/resource diagnosis, isolated frozen inputs, correctness/ADS gates,
controlled full PnR, final multi-corner STA and coverage, boot clock contracts,
board CoreMark/function checks, then evidence/skills and release. Preserve Pikafish
Stage A/B/cache and measure image/model performance explicitly. A passing STA
banner with disclosed I/O gaps is not complete timing coverage; CoreMark alone
does not override failed concurrency or memory-mapping isolation checks.
This procedure grants no new board/Flash authorization; PnR has no campaign quota.

Use the current README and docs/BUILD.md entry points. Every full PnR start
records its purpose and result without count or campaign-time limits. V6.5 formal delivery
requires its historical BoardRelease contract. For V2.1 and later work, CoreMark
performance and correctness acceptance uses real board runs only. Do not launch
RTL CoreMark simulations for release evidence. V2.1 formal delivery requires
an explicit BoardRelease manifest binding the exact bitstream, firmware, final
STA and 3 performance plus 1 validation board UART runs of at least 10 seconds
each. Functional RTL and software regressions remain required.
Incomplete builds require candidate naming. Old V6.5 ledgers are historical evidence, not current launch limits.

```powershell
.\scripts\run_all_tests.ps1
.\scripts\build_fpga.ps1 -PdsTimeoutSeconds 14400
.\scripts\build_xiangqi_sd.ps1        # bare-metal chess GUI+model build
.\scripts\prepare_sd_card.ps1 -Content Xiangqi <drive>   # only with explicit SD-write authorization
.\scripts\program_cram.ps1 -Program -SbitPath <...>
```

PDS target: PG2L100H-6-FBG676 / 2022.2-SP6.4. Explain duration and stopping
method before long runs. Avoid indefinite polling and persistent verbose logs.
Retain compact evidence, not debug history.

## Hardware, camera and board invariants

- Current authorization and fresh scan of exactly one PG2L100H ID0x00602899
  are required for JTAG programming. Normal tests load .sbit to volatile CRAM.
  program_cram.ps1 checks current CPU/ROM, snapshot, STA and output hashes for
  every in-repository image; its external-image option cannot bypass this check.
  Configuration/SPI Flash writes require separate explicit authorization and
  exact device/partition checks; this release task forbids all Flash writes.
- Camera is bootloader-only CMOS2, 1280x720 RGB565 little endian, top row first.
  Preserve HDMI timings, Esc DDR burst drain and terminal restoration.
- FB0/FB1 continue receiving live frames. Hold the completed displayed bank
  and matching frame number, drain writes, copy via uncached DDR to 0x9b600000,
  then release preview before UDP transfer or SD encoding.
- One transfer at a time, explicit busy Space, bounded failure/Esc, retry after
  failure. UDP success requires receiver PNG+JSON commit; SD success requires
  verified PNG+JSON data and completed FAT commit.
- camera_sd uses the same immutable CMOS2 snapshot. Its HDMI HUD never writes
  framebuffer/snapshot pixels. Only explicit camera_sd writes SDHC/FAT32.
- Share the Linux boot card; never format/overwrite boot files. Verify PNG+JSON
  and FAT metadata before success. No arbitrary power-loss guarantee; dirty FAT
  needs PC repair. Recovery must verify the same card CID before further writes.
- Never commit/package camera image captures, image metadata or .part files.
- Automated UART diagnostics do not replace user CH9350L Space and multi-image
  visual acceptance. Separate simulation, PDS and board evidence.
- Never infer new bitstream acceptance from older SD/audio/Linux board tests.

## RTL and docs

- Serialize repository/doc/evidence writes with program_cram's pre/post audits.
  Preserve failed board owners and every valid score. Use the recorded Python
  3.14.4 release interpreter explicitly: Python 3.9.7 rejects the seven-digit
  ISO fractional timestamps in these board receipts.
- No new Verilog/SystemVerilog function unless explicitly authorized. (The
  merged MacAccelCore.v retains the NNUE line's tested select_lane48 function;
  it is inherited branch content, not a new authoring in v2.)
  The approved CPU80 folded implementation also inherits fold_upper and its
  simulation golden helper in the two exact files pinned by audit_cpu80_approved.ps1.
  This recognizes the already tested implementation; modified or additional
  helpers remain rejected and require their own implementation validation.
- PDS-sensitive selectors use constant-indexed explicit logic. Compile-time
  generate/reset loops are allowed; each elaborated loop stays below 2000
  iterations. Preserve widths, cycle behavior and synthesizability.
- Control changes require regression and ADS netlist retention checks.
  build_cpu_ads_gate.ps1 also runs audit_icache_pad_ads.py and
  audit_uart_tx_pad_ads.py on the integrated ADS netlist before PnR. ADS
  structural proof alone does not establish physical retention or routed hold
  margin. Preserve the ICache PNR review limitation in
  docs/validation/b73-final-physical-review/.
- GUI and Tcl share the 140-DRM ADS budget in pds/soc.fdc. The merged design
  adds the conv frontend, Stage A gather and weight double buffer to the MAC
  subsystem; the ADS resource gate is the arbiter. A budget is not a measured
  resource count; changes to storage mapping must preserve capacity, ports and
  cycle behavior.
- GUI and Tcl must load pds/ddr3_test.rcf. Keep all final STA gates.
- Commands: docs/console调试命令.md; hardware: docs/SUPPORTED_HARDWARE.md;
  evidence/gaps: docs/Validation.md; NNUE goal/limits:
  docs/NNUE_10ms_Optimization.md. Keep historical tutorials out of current docs.
- Existing camera/FMC Bank_L6 uses 3.3V/J20. The camera manual's 2.5V conflict
  remains an unresolved electrical reliability question.

## Portable project skills (from the NNUE line)

The reusable engineering skills are in `skills/` (see skills/README.md).
They document workflows; they do not authorize Flash writes or make unchecked
hardware TODO items pass. Historical YOLOv5n TODO checklists under docs/
are archives of the NNUE line; their workflows (write tests first, focused
sim, SoC regression, board test via volatile CRAM, then docs and commit)
remain good practice for v2 items.

Never erase or write SPI/configuration Flash without fresh, explicit user
confirmation and an exact device/partition check. Normal FPGA testing uses
JTAG to volatile CRAM only. Keep README/docs and final evidence aligned with
the tested sources. Building or documenting the project does not authorize
JTAG programming or any Flash erase/write.
