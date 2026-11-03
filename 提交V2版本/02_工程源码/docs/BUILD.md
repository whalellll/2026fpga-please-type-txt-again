# SoC V2.1 构建与交付

2026-10-25产品续作已合并main P3 CPU60，旧CPU80/9ba02f10命令保留历史身份。
当前离线构建、GCC9/GCC16 CoreMark对比及PN04启动包见
[本轮完整说明](PictureNew_离线完成与main同步_20261025.md)。硬件495冻结输入保持main字节，
产品内核/worker/rootfs独立重建；不覆盖main发布boot文件或已安装PN03。
PN04构建使用`build_xinyi_cpu60_loader.py --target-profile MainP3`，原PN03默认profile仍独立保留。

`Picture_new` 的现役部署、构建输入和待验门槛见 [续接检查点](PICTURE_NEW_CHECKPOINT_20261020.md)。
模型接入是用户授权的实验，不代表整体 M0、时延或整局验收通过。

2026-10-23 已合并CPU80/卷积34338722硬件，构建和接口见
[本次说明](CPU80_PICTURE_INTERFACE_NOTES_20261023.md)及[离线记录](validation/picture-merge-20261023/README.md)。
本次使用GCC16.2的LTO可用工具链，Linux用RV32IMA musl9.4；旧disable-lto阻断属于历史环境。
CPU80候选使用99/160 SBI时基、匹配内核和DTB、≤16MiB raw rootfs及私有PN02六载荷。
仅在部署副本移除符号表，逐一核验可加载段和入口不变；原始ELF保留。
本次不运行新PDS/PnR、不接板、不写介质；PN01和已发布镜像保持原身份。
下面E8构建/启动说明只适用于旧硬件，不能用于CPU80候选。

当前使用 [PN01 独立 SD 名称和公共选择器](PICTURE_SD_NAMESPACE.md)：`xqboot` 后选 Picture_new，
不再逐次串口传启动器。更新时生成新的 PNxx 整套载荷及 CRC 合同，保留公共选择器、注册表其他项和旧文件。
原生 worker/模型打包、rootfs 和候选构建入口在 `artifacts/vision-model-20261020-adapter/`；
命令及数值门禁见 [P21 记录](validation/picture-p21-runtime-20261020/README.md)。
原始 initrd 不超过 16 MiB，模型启动时展开到 `/run/xq-native`；MAC 走严格共享驱动。

追加 rootfs helper 时须在 AdditionalPayloads 显式保留 Picture 的 `usr/bin/xiangqi-pikafish`，
并核验包装、实际 backend 和三模型 SHA，避免通用 overlay 覆盖 Picture 包装。
训练 venv 与 picture-tools Python 3.14.4 分离，训练树只读；全量回归在隔离目录运行，
避免普通 `run_all_tests.ps1` 重建主树冻结固件。当前 r06 绑定及证据见续接检查点。

后台相机 E8 的构建授权与门禁见 [后台捕获证据](validation/picture-background-capture-20261018/STATUS.md)。
已有位流、频率和发布身份固定；当前收尾不重新启动 RTL/PDS/PnR 或写 Flash。
较早的 UART RAM、N20 和 P19 入口只用于相应历史版本，不能替代现役 SD 契约。
以下为已发布 V2.1 及历史版本的交付流程，不是 Picture_new 的发布批准。

## V2.1 当前正式交付路径

V2.1 的冻结位流为 PDS 快照 `5f802f47f8ad4907925af156b227ad21`，
CPU 59.4 MHz、SYS/TIMEBASE 49.5 MHz；完整双角 STA 已通过。下面的
V6.5 BoardRelease 频率提升与同频控制组要求属于历史版本。按 2026-10-15
用户要求，V2.1 及后续版本的 CoreMark 性能和正确性验收只用实板，不再跑
RTL CoreMark。V2.1 独立 `BoardRelease` 校验器要求当前快照绑定的易失
CRAM 编程回执、原始 UART 三次性能加一次验证、每次至少 10 秒、官方 CRC
复核、双角 STA、三次 GUI 启动和现场 HDMI 鼠标确认。原有功能 RTL、软件
回归仍须通过。当前显式清单为
`docs/validation/v2_1-board-release-20261015.json`。实际命令为：

```powershell
.\scripts\create_delivery.ps1 -CoremarkEvidenceMode BoardRelease `
  -ReleaseManifest 'docs/validation/v2_1-board-release-20261015.json'
.\scripts\verify_delivery.ps1 -CoremarkEvidenceMode BoardRelease `
  -ReleaseManifest 'docs/validation/v2_1-board-release-20261015.json'
```

板上 CoreMark、Linux、官方 Pikafish、硬件加速及 HDMI 鼠标结果分别记录
在 V2.1 验证目录。板端 S 模式启动使用随包的临时只读 SD 装载器及
[操作步骤](V2_1_BOARD_BOOT.md)；生产 bootloader 尚未自动执行该路径。
GUI rootfs 重建所需的七个二进制输入随包放在
`linux/boot/v2_1_sd/rootfs_payloads/`，提取验证会以实际 Pikafish 参数
重建并比对完整 rootfs SHA-256；模型使用包内 `linux/boot/pikafish.pff`。
冷启动延迟、CPU hold 余量和模型范围随包披露。以下 V6.5 流程与数值
保持历史身份。

本轮按 2026-10-08 用户要求完成物理与板测 BoardRelease 验收。历史 V6.1 构建命令和已测数值
保留在下文；不要求重跑 Long，不把旧 evidence 改名为当前 evidence。

当前冻结顺序：CPU 源码/版本定稿 → 双份 Emit/配置/初始化 → CPU 实现身份同步到
SoC → SoC 版本/固件头/验收脚本定稿 → 生产固件及 FPGA 输入冻结 → ADS 检查 →
同一 ADF 完整 PnR 与双角 STA → 加载该位流到 CRAM → 本轮板测 → 文档、ZIP、最终提交/tag。
文档与验收产物交付提交可以晚于硬件实现提交，但所有冻结输入字节必须不变。禁止为追随交付提交
反复改 CPU source.json。

完整实现启动传 `build_fpga.ps1 -CampaignBudget <search-budget.json绝对路径>
-AttemptPurpose search|same_frequency|final -PdsTimeoutSeconds <有界秒数>`。预算登记在
ADS 门禁通过、后综合实现启动前完成，失败/取消/换seed仍占次。最多6次且24小时，
为同频与最终构建预留次数。本轮不要求依次重跑历史全部档位；候选选择须服从该共同预算。
SYS固定49.5 MHz，时钟配置只通过 set_clock_candidate 修改。
最终实现 `7ad9f204d5ad802b1eae8e5cb62890634a7bf275` 已按正常 ADS/同一 ADF
流程完成 run838e，第5次PnR，div14/seed5、CPU63.642857 MHz完整双角STA PASS。
59.4 MHz seed5 对照4b4f4637/run75f8也已物理PASS；run738/run906/run8ad/runaefd按
原身份保留，其中runaefd路由超时不能算最终通过。当前5/6，第6次未使用，统一截止
2026-10-09T12:55:41Z；不因交付再启动PDS。div13/12没有本轮修复的完整物理PASS。
后续状态及次数以[当前检查点和账本](validation/v6_5-development-20261008/README.md)为准。
连接恢复后，两份实际位流均经唯一目标扫描与易失CRAM加载完成板测3+1及DDR/MAC自测。
最终63.642857 MHz均值5.262385177991809 CoreMark/MHz，比基线提高3.79154449%；
[本轮板测](validation/v6_5-board-results-20261009/README.md)记录加载身份、失败和验收范围。

正式交付使用 `create_delivery.ps1 -CoremarkEvidenceMode BoardRelease
-ReleaseManifest 'docs/validation/v6_5-board-release-20261009.json'`，再以同参数 verify_delivery。
这两个步骤显式传 `-PythonPath 'D:\LJL\WORK\msys64\mingw64\bin\python3.exe'`（本轮3.14.4）；
Anaconda 3.9.7不能解析本轮七位小数的ISO时间，已有失败记录保留，不能当成硬件失败。
清单按版本选择
当前短 RTL、完整 RTL 回归、59.4 MHz 对照、最终板测3+1及CRAM/STA/哈希关联，允许
保留历史 evidence。未达到两个性能门槛或验收未全，不生成正式发布 tag。

## V6.5 UART修复输入与回归模型

UART RTL修复始于 `e97aa4bb2103cb8628d5862706b61fa4049b228e`；主树后续
`1720e40b5fc316a147bd83c349941bf14a1bb138` 更新ADS指针别名解析及冻结验收配方。
CPU导入继续绑定e698e3b；CPU文档交付检查点e4b1035不是新的CPU实现提交。
两个工作树采用同一UART修复，但各自时钟、固件、实现提交和冻结快照须独立记录。
最终主树实现为 `7ad9f204d5ad802b1eae8e5cb62890634a7bf275`（div14/seed5），控制实现为
`4b4f4637024c506c7532e3389c1a6a3a04328c3b`（div15/seed5）；各自355项冻结输入、固件、
完整RTL与PDS输出独立绑定。最终主树回归338 source/194 test、短测8份模型/27份固件源码
与run838e快照匹配。三份seed配方从4改5时其余352项输入未变；不据此借用旧物理结果。
终态复核进一步核对全部355当前/冻结/Git输入、7份暂存项和5份生产固件合同。
docs、DOCX、候选清单及最终位流/报告等验收产物可在交付提交补充，但不得改变这些输入字节；
SoC硬件实现仍为7ad9，source.json仍绑定CPU实现e698。

未取得正式板测时使用独立 `create_candidate_delivery.ps1 -OutputZip <明确candidate名称>
-Incomplete <实际缺口>` 路径与其候选验证器。SourceOnly包和另附的原生构建归档应分别标明
实现提交、位流/快照哈希和未验收状态；保留历史证据。不得使用正式 `SOC_linux_V6.5.zip`
或创建v6.5/V3.5发布tag。CPU候选VerifyPackage核对短固件元数据与哈希，不重新编译或运行RTL。
以上候选路径用于未通过验收的构建；本轮已通过BoardRelease，早先候选包仍保留。
正式包路径、哈希与最终交付提交由最终校验记录，文档更新本身不宣称ZIP已完成。

正常ADS在CPU检查报告中加入 `uart_tx_pad_contract`。新快照冻结
`scripts/audit_uart_tx_pad_ads.py`，布局前、最终快照及便携BoardRelease校验其
run/snapshot/VM/checker/parser/UART RTL哈希、四地址位/四LUTRAM连接合同；
缺少合同或错身份必须拒绝。旧快照未含该checker时保留其原审查范围。
软件正反例通过不等于新ADS映射、最终hold或板测通过。

完整回归包含UART原版逐周期对照与厂商 `GTP_LUT6D` 模型测试。可指定：

```powershell
.\scripts\run_release_regression.ps1 -ToolchainBin 'C:\tools\riscv32-gcc16\bin' `
  -EvidenceDirectory 'docs/validation/<new-regression-directory>' -TimeoutSeconds 1800 `
  -VendorModels 'C:\tools\PDS\arch\vendor\pango\verilog\simulation'
```

`run_all_tests.ps1`同样接受`-VendorModels`或`-PdsRoot`；显式模型路径优先，
其次显式PDS根目录，否则使用`PDS_ROOT`及既有本机位置。只读取五份已安装、
有许可的厂商Verilog模型，不启动PDS，也不把模型文件重新分发进交付包。

## V6.1 历史构建与已验证输入

以下各节保留 V6.1 当时的复现流程与命令；当前 V6.5 使用页首的预算与 BoardRelease 流程。V6.0 的具体构建、时序和失败记录原样保留在 [BUILD_V6.0](BUILD_V6.0.md) 与 [Validation_V6.0](Validation_V6.0.md)。当前验收状态以 [Validation](Validation.md) 为准。

V6.1 主树 div15（CPU 59.4 MHz、SYS/TIMEBASE 49.5 MHz）已用新冻结快照完成全量 PDS、位流及映射后门级定向测试；[同轮原始证据](validation/frequency-search/divisor-15.md)已归档。更高的 div14（CPU 63.642857 MHz）候选[原生最终 STA 失败](validation/frequency-search/divisor-14.md)，因此 div15 是 V6.1 已测试范围内最高完整 STA PASS。2026-10-08 已完成[实板 CoreMark 3+1 测试](validation/v6_1-board-coremark-20261008/README.md)，性能均值 5.070148251 CoreMark/MHz；该次 V6.1 板测补录仅增加验证与说明，RTL、固件和位流未改。2026-10-05 的 RTL 短测及当时停止的 Long 仿真按原身份保留。以下是 V6.1 重建命令记录，当时主树分频为 15；不描述当前 V6.5 配置。

## V6.1 历史工具与输入（共同接口仍适用）

- CPU：`src/main` 的 `src/cpu/generated/core/CoreTop.sv`、`emit-config.json` 和 `src/cpu/scripts/meminit/zero_{1024,2048,4096}.hex`。运行 `scripts/sync_cpu.ps1 -SourceRepo '..\src'`，再运行 `-Check`；SoC 导入目录是 `rtl/cpu/`，来源和 SHA-256 在 `rtl/cpu/source.json`。`rtl/cpu_top.v` 是本仓库双时钟集成包装。
- 固件：`riscv32-unknown-elf-gcc` GCC 16.2.0，`rv32ima_zicsr_zifencei`、`ilp32`。`scripts/riscv_toolchain.ps1` 核对工具链、libgcc、ELF32/soft-float、链接代码 ISA。CoreMark 六份官方核心文件依 [sw/coremark/upstream.json](../sw/coremark/upstream.json) 校验；CoreMark 与五份摄像头/CRC/PNG/FAT 热点 `-O2`，其余 bootloader 对象 `-Os`。链接后完整映像须留下严格超过 16 KiB 栈空间。`artifacts/bootloader.build.json` 记录全部编译/链接 argv、源文件哈希、运行库身份、ELF/BIN 和栈布局。
- FPGA：PDS 2022.2-SP6.4，器件 PG2L100H-6-FBG676。规范源码是 `pds/soc.tcl`、`pds/soc_post_synth.tcl`、`pds/soc.fdc`、`pds/ddr3_test.rcf`、`pds/soc_gui.pds` 和 `pds/audit_cpu_sys_cdc_ads.py`。GUI 工程路径相对 `pds/`；运行 `scripts/prepare_pds_project.ps1` 生成所需 ROM。PDS 数据库和 `work/` 是可重建缓存，不作为发布输入。
- Linux 载荷：原 `Image`、`fw_jump.bin` 和 rootfs 基线属于历史平台；来源与 ISA 限制见 [prebuilt](../prebuilt/README.md)。`linux/soc.dts` 是可读设备树源，使用正式 `dtc` 生成 `linux/boot/soc.dtb`。`make_stable_dtb.ps1` 只能调整旧 bootargs，不是 DTS 编译器。overlay 改动后运行 `scripts/make_rootfs.ps1`，核对 DTS `initrd-end`，再重新编译 DTB。

## V6.1 历史复现顺序（不用于本轮搜索与发布）

V6.1 当时的流程是先完成 18→17→16→15→14 各正式候选的独立物理验证和归档，选出已测试档位中最高的完整 PASS 档；在主工作树应用同一实现与分频，重新构建固件、DTB 和 PDS，不能复制候选位流。非 18 档还须保留与主树冻结输入一致的 `divisor-XX.inputs.json`，否则 PASS 归档会拒绝。下列命令从主工作树根目录执行；十次迭代 Pilot 从生产源码另编专用固件和 ROM，用于短时估值，不与本轮位流的生产 ROM 混同。若以后补测正式 RTL 3+1，须重新执行完整 Long 流程和十秒门禁；独立实板成绩不要求先完成该仿真。

```powershell
.\scripts\sync_cpu.ps1 -SourceRepo '..\src' -Check
.\scripts\check_clock_config.ps1
.\scripts\build_bootloader.ps1 -ToolchainRoot 'C:\tools\riscv32-gcc16'
.\scripts\make_rootfs.ps1
& 'C:\tools\dtc\dtc.exe' -I dts -O dtb -o .\linux\boot\soc.dtb .\linux\soc.dts
.\scripts\run_all_tests.ps1 -IcarusBin 'C:\tools\iverilog\bin' -MsysRoot 'C:\tools\msys64' -ToolchainBin 'C:\tools\riscv32-gcc16\bin' -PythonPath 'C:\tools\python\python.exe' -HostGccPath 'C:\tools\msys64\mingw64\bin\gcc.exe'
.\scripts\prepare_pds_project.ps1 -ValidateOnly
.\scripts\build_fpga.ps1 -PythonPath 'C:\tools\python\python.exe' -PdsTimeoutSeconds 14400

$repo = (Get-Location).Path
$clock = Get-Content .\config\clocks.json -Raw | ConvertFrom-Json
$runId = (Get-Content .\artifacts\build_snapshot.json -Raw | ConvertFrom-Json).run_id
.\scripts\archive_frequency_run.ps1 -ProjectRoot $repo -Divisor $clock.cpu_divisor -RunId $runId -Status PASS
$archive = Join-Path (Split-Path -Parent $repo) ("soc_freq_evidence/div{0}-PASS-{1}" -f $clock.cpu_divisor,$runId)
.\scripts\verify_frequency_archive.ps1 -ArchiveDirectory $archive
.\scripts\publish_frequency_archive.ps1 -ArchiveDirectory $archive -ProjectRoot $repo
.\scripts\verify_frequency_portable.ps1 -PortableDirectory (Join-Path $repo ("docs/validation/frequency-search/div{0}-PASS-{1}" -f $clock.cpu_divisor,$runId))

& 'C:\tools\python\python.exe' .\scripts\export_release_docx.py
.\scripts\run_coremark_production_sim.ps1 -Kind Pilot -PilotModes both -CpuHz $clock.cpu_hz -ToolchainRoot 'C:\tools\riscv32-gcc16' -MsysRoot 'C:\tools\msys64'

# V6.1 历史示例：使用 Pilot 命令实际输出的目录；下方是该版已核对的主树运行目录。
$pilotDir = '.\artifacts\selftest\production_coremark_pilot_f5b3bcc4bca848cf80497bb7ef9e2af4'
.\scripts\promote_coremark_short_pilot.ps1 -PilotDirectory $pilotDir -Destination .\docs\validation\v6_1-short-pilot
.\scripts\verify_delivery_evidence.ps1 -CoremarkEvidenceMode ShortPilot

# 写入短时估值及固件身份后重生成并核对 DOCX。
& 'C:\tools\python\python.exe' .\scripts\export_release_docx.py
& 'C:\tools\python\python.exe' .\scripts\export_release_docx.py --check
.\scripts\create_delivery.ps1 -CoremarkEvidenceMode ShortPilot
.\scripts\verify_delivery.ps1 -CoremarkEvidenceMode ShortPilot
```

路径仅示例，实际工具安装不包含在 ZIP 内；带空格路径可通过参数指定。`run_all_tests.ps1` 包含三组比率/种子的 AXI CDC、CLINT/IRQ、CPU/SoC 与外设回归。`build_fpga.ps1` 首先将 `soc.tcl` 解析为综合工程，只跑到 ADS，并以 SNR、VM、ADF、CCR 的原生哈希运行资源、CPU、ICache 和 CDC 门禁；通过后才将同一 ADF 导入 `soc_post_synth.tcl` 的 Post-Synthesize Project 进行 Device Map、PnR、最终 STA 和位流。后段不得重新编译或综合，解析后及布线后均核对 ADF/VM/SNR 字节。后段使用 `report_timing -report_max_skew`，要求最终报告列出 Gray 指针的偏斜检查；PDS 默认关闭此报告选项。发布证据含两段工程、原生命令历史和日志、约束检查记录、ADF 哈希及最终 bitstream 哈希。PDS 一轮可能持续数小时：脚本打印 owner PowerShell PID，`-PdsTimeoutSeconds` 对 Windows Job 及全部子进程设硬界；提前停止可终止该 owner 进程。不要并行运行 GUI 与 CLI 构建。候选分频的唯一改动集、18→17→16→15→14 计算表和逐轮归档字段见 [频率搜索步骤](validation/frequency-search/README.md)；基线 PDS 归档前不应用新分频。

## V6.1 历史交付校验（保留原包与证据身份）

原 `SOC_linux_V6.1.zip`（SHA-256 `3e15a4355d430bdb19244e21dfa19ea61963462c6a3de854602202649e14acfc`）与已发布 `v6.1` tag 的 `3886dea` 提交作为 2026-10-05 档案保留。2026-10-08 板测补录包名为 `SOC_linux_V6.1_board_20261008.zip`，包含当时的 Markdown、DOCX 和 [板测原始证据](validation/v6_1-board-coremark-20261008/README.md)，采用下列命令另存：

```powershell
.\scripts\create_delivery.ps1 -OutputZip '..\SOC_linux_V6.1_board_20261008.zip' -CoremarkEvidenceMode ShortPilot
```

补录包仍为 V6.1 同一 RTL、固件与位流；新增内容是文档和实测证据。该次 V6.1 补录执行当时的工程/构建证据门禁，随后按发布清单逐项核对 ZIP 条目、SHA-256、板测原始日志及计算结果，并将校验结果和 ZIP 哈希另存为同名前缀的 `.verify.json` 与 `.zip.sha256.txt`。该次 V6.1 补录不重跑 PDS、RTL 回归或软件重建，既有通过结果仅复用于逐字节未变的构建输入与产物。原发布 tag 的历史说明与本地补录提交的发布状态应分别报告。

Device Map 完成后，`build_fpga.ps1` 要求本轮原生 `device_map/soc_top.dmr` 的修改时间不早于输入快照，并逐字核对 FDC 中的两个 CPU/SYS 时钟与 48 条定向 CDC 指令各出现一次（Gray 指针 30 条、FIFO payload 10 条、第一级同步器入口 8 条）。该报告冻结在 `pds/input-snapshots/<run_id>/post.soc_top.dmr`，同时复制为交付文件 `artifacts/pds_post_map_constraints.txt`；三处 SHA-256 在 `build_evidence.json` 中绑定。综合期 CCR 的 1171 项约束、0 错误检查与后映射 DMR 是两项独立证据，最终仍须通过布线 STA。最终 ADS VM 还可按 [映射后 CDC/CLINT 门级测试](../sim/MAPPED_GATE_TESTS.md)运行有界用例，结果必须绑定同轮快照和 VM 哈希。

`scripts/project_files.ps1` 定义唯一清单；五份正式固件各交付 `.elf`、`.bin` 与 `.build.json`，对象文件和临时 ELF 不交付。`create_delivery.ps1` 在主树同轮 PASS 频率归档、原生 MaxSkew XML 及明确标为 `short_pilot` 的原始仿真证据通过相应校验后生成 `SOC_linux_V6.1.zip`，根目录 `SOC/`，并写入每个文件的 `SHA256SUMS.txt`。短测证据须分别列出专用 BIN/ROM 和位流所绑生产 BIN/ROM 的哈希，不能把二者伪装成同一运行。输入快照、PDS 输出证据及软件 metadata 都绑定生产 ELF/BIN 哈希。`verify_delivery.ps1` 解包到临时目录，复核这些发布证据，重建 rootfs、固件与例程并比较哈希；完整模式也跑回归。`-SoftwareOnly` 只验证软件，结果不能写成硬件通过。不要以旧 `soc_v2_top.sbit/.bin` 别名替代本轮原生 `soc_top.sbit/.bin`。

V6.1 Pilot 的两例各 10 次迭代，目标计时仅约 0.0335 秒；具体 ticks、CRC、估值、ROM 差异和公式见 [COREMARK](COREMARK.md)。`ShortPilot` 交付模式继续核验该历史 RTL 证据；2026-10-08 的[板测结果及原始输出](validation/v6_1-board-coremark-20261008/README.md)另行归档。历史可选 Long 流程不属于本轮 V6.5；未来若另行要求补测正式 RTL 成绩，`run_coremark_production_sim.ps1 -Kind Long` 仍要求当前 CPU、生产 ROM、快照、最终 STA 和位流哈希匹配，三次性能加一次验证均不少于 10 秒；先用 Pilot 测主机速度，再按有界 timeout/MaxCycles 执行。Ctrl+C 可停止 owner 进程，子进程由 Job 超时收束。
