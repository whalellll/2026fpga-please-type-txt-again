<!-- CPU125_CM60_SMALL_CANDIDATE_20261102 -->
# CPU125 compiler-only CoreMark candidate

The unchanged Zbc CPU reaches 6.031419 CoreMark/MHz in the performance-seed
100-iteration diagnostic and 6.011921 in validation at CPU125/SYS49.5 MHz.
All six CoreMark units use O2/no-if, unroll2, LTO and branch-cost1. No CPU
RTL, instruction, queue, cache or accelerator changes. These are short RTL
diagnostics. Fresh native synthesis/map confirms zero LUT/FF/LUTRAM/DRM/APM
increase, identical device control/configuration and all boot data bits checked.
Fresh routing, all-corner STA and actual physical readback now pass.
The new CPU125 sbit is committed on the independent candidate branch;
board connection remains deferred and board acceptance is pending.
[New sbit, timing and hashes](docs/CPU125_CM60_Sbit_20261102.md).

See [implementation and evidence](docs/CPU125_CoreMark60_Small_20261102.md).
<!-- /CPU125_CM60_SMALL_CANDIDATE_20261102 -->

<!-- CPU120_ZBC_FC1_ACCEPTED_20261101 -->
# CPU120 optional Zbc / official NNUE FC1 delivery completed

Implementation SoC `4253258cbd1fe23dc3cfd4d6ff029e85086a959c` / CPU `b1164e42737a081cc640a2113c76a53d0c91a97a` / native `75198114550743ada4e4015ad5cbf4e2`.
CPU120MHz and SYS49.5MHz; optional standard CLMUL/CLMULH/CLMULR. CoreMark all-sample mean5.281638583 ->5.910712298/MHz; no total-score gate. Earlier actual-board NNUE cold/warm14.862/13.959ms;10ms goal remains unmet.

Formal ZIP `CPU120_ZBC_FC1_20261101_r5.zip` SHA256 `ed740929a95ca1f9c48e6c92b9db29fc922edea51654ea9af259ce0a85922464`.
Independent unpack CPU134/49 suites, architecture9, SoC/CDC/console, vendor FC1 cases38 and all packaged-file integrity checks PASS. Previous final all-corner STA/native/physical checks and actual matched CoreMark/Zbc/official FC1/NNUE/image/voice/concurrent/new SD/GUI/mouse acceptance are retained.

The user explicitly requested “这一版不做实板复核”. Final ZIP-bound actual SD8/CID, repeated CRAM/direct SD boot and application rechecks were waived; they were not performed and are not claimed as fresh passes. Earlier actual SD8 readback hashes match all eight package files. No Flash write. H archival is pending actual archive-disk availability; G originals remain.

Source publication SoC `0d461b33ee233e2b3ca85ef2ae8d2a176e6ab536` / CPU `abd87bb1d3b3ccb3ae1e1c50b585a5ad05858a91`. Later completion metadata commits preserve these frozen source identities and the unchanged ZIP.

[ZIP-bound completion receipt](docs/validation/cpu120-zbc-fc1-20261101/final-delivery/delivery-completion.json).
<!-- /CPU120_ZBC_FC1_ACCEPTED_20261101 -->

<!-- CPU120_ACCEPTED_20261101 -->
# 120 MHz CPU / official Pikafish FC1 repair

The CPU120 implementation has passed final all-corner routed STA, native
PDS25 CPU/CDC qualification, board CoreMark3+1, direct SD Linux boot, official
NNUE, image/voice and concurrent audio tests. User confirmed GUI and mouse.
Implementation13ea2329 / CPU8c14579; native b4dc02253edf402ea26104f106505857.
The previous odd-FC1-bank mismatch is fixed with eight independent32-bit DRM
banks. Full NNUE cold/warm200 means14.852/13.937ms;10ms remains unmet.
CoreMark all-four mean5.281757871/MHz; the user waived comparison testing.

Formal ZIP completion and its independent regression/SD acceptance remain
pending until a ZIP-hash-bound completion receipt is present. See
[board results](docs/validation/cpu120-20261101/BOARD_RESULTS_20261101.md),
[source and evidence bindings](docs/validation/cpu120-20261101/source-export-index.json)
and [handoff](docs/CPU_Frequency_Handoff.md). Historical source notes below
retain their original version and acceptance identities.

[CPU120 deployment and reproduction guide](docs/CPU120_Delivery.md).
<!-- /CPU120_ACCEPTED_20261101 -->

> Current offline120MHz NNUE/CoreMark5.2 merge candidate: [scope](docs/PDS25_CPU120_NNUE_CM52_Merge.md). Fresh correctness and routed all-cornerSTA required; board performance and the prior NNUE2951/2392 mismatch remain pending. No formal delivery or push.

<!-- CPU80_BRAM_RESOURCE_CANDIDATE_20261029 -->
当前CPU80资源候选：图像权重缓存保持原周期改用块RAM；仅局部仿真/模块综合已通过，整机综合、原生证明、最终STA与板测待验。详见[候选范围和证据](docs/CPU80_Block_Ram_Weight_Cache_Candidate_20261029.md)。

# SoC V2.1：V3.5 CPU + NNUE 象棋加速

当前 CPU75 联合版已补齐语音对战鼠标选子与合法走棋入口，保留语音输入。
完整 SoC 回归、最终全角STA、CoreMark/MHz ABAB、固定WAV/图像/官方Pikafish及并发通过。
真实板端鼠标命令事务已完成选子、非法/合法走法、ASR排空、512节点应着及重新开始/返回检查；
实体鼠标传输、最终SD更新与ZIP独立验收另行记录，当前RAM试用版重启后仍恢复旧SD GUI。
[交付与启动流程](docs/Main75_Delivery_20261028.md)、[鼠标修复说明](docs/Voice_Mouse_Chess_20261028.md)、
[来源绑定状态](docs/validation/main75-release-20261028/current-state.json)。

<!-- MAIN75_JOINT_20261027_BEGIN -->
## 当前分支：75MHz图像/voice3联合候选

已合入图像三模式驱动与voice_3 r05。最终全角STA通过，CPU慢角setup由−0.050ns改善到+0.191ns。
2026-10-28完成75MHz直接SD启动、CoreMark交替、图像三轮、固定WAV数值与Pikafish自动并发，GUI已恢复。
图像模式2均值51.658秒；语音独跑755.557ms、与NNUE/搜索并发1624.857/1648.559ms。

[实测报告](docs/CPU75_Board_Performance_20261028.md) · [候选来源](docs/Main75_Joint_Candidate_20261027.md)。
研究语音模型未晋升准确率；NNUE10ms/图像30fps未达到，实体相机/HDMI/麦克风未在本轮验收；未推送main或正式交付。
下方CPU70历史发布记录保持原适用范围。
<!-- MAIN75_JOINT_20261027_END -->
<!-- MAIN70_DELIVERY_CURRENT_BEGIN -->
2026-10-27 当前工作：合并后的 main 正在完成 **CPU70 MHz** 交付验收。原生最终全角 STA、
完整回归、实板官方 CoreMark/MHz ABAB、模型/并发及现场图像/语音/重开/Esc均已通过。
当前发布并准备正式包，最终包独立解包/实卡回读/SD直启仍须完成。尚未宣布正式交付完成。
硬件冻结 c50bb158/run6d01c260，GUI 源码冻结8f4de1c7；CPU实际实现05c7ef96。
来源、实测值和限制见[本版验收记录](docs/Main70_Delivery_20261027.md)。
`voice_3` 未合入；图像 worker 复用用户授权的原 PN07，不宣称 PN08 已完整源码重建。
<!-- MAIN70_DELIVERY_CURRENT_END -->

## 历史状态记录

以下按日期保留原适用范围；当前工作与交付结论以上方 CPU70 入口为准。


<!-- LOCAL_OPTIMIZATIONS_MAIN_20261026_BEGIN -->
2026-10-26：按用户要求把本地连续复制、去输入快照、可选驻留、Pikafish特征更新和GUI精细绘制整合到图像主线。保留32位I/O及严格设备策略；驻留默认关闭，显式PIKAFISH_ACCUM_RESIDENT=1启用。新收到三份INT8与三份FP32权重，包内SHA全部通过，三INT8与r14契约一致。来源与验证见[本地优化合入记录](docs/Local_Optimizations_Merge_20261026.md)。这是源码整合，尚非联合板测或正式交付。
<!-- LOCAL_OPTIMIZATIONS_MAIN_20261026_END -->

<!-- PICTURE_MAIN_VOICE3_20261026_BEGIN -->
2026-10-26：按用户要求集成 `Picture_new@776f217c` 图像识别源码到本地main。PN08仍为未完成实板验收的软件候选，`production_ready=false`；图像权重包不在Git，本次没有下载完整模型或更新生产启动包。来源、离线检查和限制见[主线合并记录](docs/Picture_Main_Merge_20261026.md)。`voice_3@2cc38efb` 另目录拉取，本次未合入。
<!-- PICTURE_MAIN_VOICE3_20261026_END -->

2026-10-26：下一验收目标为**物理空格至正确显示整盘≤60秒**，荐着另计。
main 已包含，发布 e42 已合入候选；配套私有驱动、HWC 检测器、新内核及引擎
已完成离线构建/数值与取消回归。e42 已实际写入易失 CRAM 并回到 ROM 控制台，
新内核/图像链、整盘正确率和≤60秒均未通过。上游约57秒仅是检测图和F32头，
不能当作整盘时延。
训练侧 HWC 验收 kit (`build/hwc-acceptance-kit/README.md`, historical attachment absent from this checkout) 已生成，并已复制桌面 ZIP；
178帧由训练侧运行，r24b S16 的157/178不能转作本 HWC 路径验收。
当前工作和证据见[2026-10-26 集成记录](docs/validation/picture-e42-integration-20261026/README.md)。
下方旧段落保留各自的历史状态。

2026-10-25 当前集成：用户授权接入发布的 e42 硬件及 aa134da 软件快照。`main e7288be9`
已包含；e42 源码与原生证据正在合入，实际板卡仍为 P3。P3/PN05 r04 回退检查点为
`134d046a`，配套新内核与产品快路径仍需本机适配、重建及验证。

PN05 r04 本次实景已得到一拍完整基线：到显示1043.010秒、到荐着1075.092秒；
严格几何status5，产品估计32候选删10、显示22子。用户确认实物为初始32子，
因此识别与时延均失败；播报有声音但软件audio okay0。第二拍物理Esc恢复操作，
五BUSY=0、相机idle及第二帧CRC绑定release9通过。当前证据、材料边界和顺序见
[集成复核](docs/validation/picture-fastpath-review-20261025/README.md)。`production_ready=false`。
以下各阶段旧状态保留其历史适用范围。

2026-10-25 当前：已合并远端main `e7288be9`的P3 CPU60硬件，位流`6565ad37…`，
495冻结输入与发布证据核验通过。本次刷新远端后没有新提交，硬件目录仍与该main一致。
PN04已实卡启动过；PN05软件更新及离线回归已完成，**PN05尚未写入SD**。
COM5无输出，用户暂不能实体复位；上板安装与实测等待恢复操作条件。
当前软件、包和续接入口见[PN05检查点](docs/validation/xinyi-pn05-20261025/README.md)。

r19–r23已作归档级接收，训练线按第二轮QAT失败收官，game2判定窗口未用即关。
模型仍为working-r14；INT68/84未达73/84是保留的关闭差距，production_ready=false。
CAMERA_v2矩阵156/178是与FP32的一致率，不能称为棋盘识别准确率。
见[训练收官与main复核](docs/validation/picture-training-closeout-20261025/README.md)。
下方2026-10-24及更早的分期内容保留历史状态，以以上入口为当前答案。

`Picture_new` 当前是实验开发检查点，基于保留的 `Picture@86d1966`，平台 `VERSION=2.1`。
现状、证据和剩余任务见 [芯弈一号检查点（2026-10-24）](docs/validation/xinyi-one-20261024/README.md)。

当前按[芯弈一号总单](docs/PictureNew_芯弈一号_工程总提示词_20261024.md)推进：启动页、
独占双模式、无状态红方教练和只删不造的纠错。T0 已停止 CPU80/PN02 时延线；先研读
原浅色 GUI/voice_2，再提交 T1 软件移植，真实 r14 全部80层的 host/RV32 QEMU 黄金对齐通过。
T2 已有完整产品程序及合成进程集成验证，**物理空格到荐着、现场 status5 定界仍未验收**。

硬件目标固定 CPU60/1080p30/V321/PFN1；指定 `9ba02f10` 只作功能联试，其原始 STA
仍有 SYS hold 负裕量。原交付缺四份被哈希引用的原生审计文件；用户随后明确授权功能联试，
已通过独立精确镜像检查加载易失CRAM，并按新增授权经XMODEM安装PN03到SD、六CRC启动Linux及产品。
原始STA失败与原生记录缺口保留，默认正式加载检查及Flash禁令保持。
该硬件的摄像头独占 HDMI，不能同时显示预览和 GUI；连续预览并显仍是上游硬件缺口。
`production_ready=false`；整数68/84未达73/84，不把软件通过当作准确率或演示时延通过。

以下为 2026-10-23 及更早的归档状态；CPU80/PN02 和旧任务顺序不再是当前执行线。

2026-10-23：r13–r17 已完整接收，当前 PC 默认切到 **冻结640 + 标准 v3d-QAT
（d1476f80）+ 冻结 board192 + 方案 A + B80**，FP32/pc-fp32。
训练报告 FP32 正确75/84、候选84、冲突0；整数68/84未达73/84，状态为“待新局归因”，
仅供功能联调。`production_ready=false`。第二局继续隔离，只引用报告汇总。

已合并 origin/main 的 CPU80 卷积硬件身份，完成宿主常驻权重、直接数据准备、灰度分派、
目标构建及离线 PN02 候选。逐层/整图/回放验证见 [本次记录](docs/validation/picture-merge-20261023/README.md)。
板子当前不可用，本次没有上板或安装；旧 PN01 未变。当前卷积 ABI 与模型的精确语义和形状
不完全兼容，80层均未启用卷积分派，尚无实际加速成绩。用户已授予每拍≤10秒的演示豁免，
5秒/3秒保留为工程目标，CPU80 端到端均待实测。
正常完整隔离回归r7已通过；主线逐层、整图、回放及语音资产核验通过。
历史v1的PC回退本地缺原包，当前r14主线和PN02不受影响。

以下至正式发布章节前为 2026-10-22 及更早的历史检查点，默认组合和授权以本段为准。

r12 当时 PC 主线为 **E：冻结640 + v3c + 方案 A + 精修 B**，默认 FP32；
640/v2-band 保留显式 FP32/exact 回退。94项载荷及整包覆盖通过，truth_v2/正式报告已归档。
正式 FP32 正确且严格可用 **73/84（86.9%）**、候选83、冲突1；不把候选数当正确数。
v3c INT8 尚缺，E 未上板；第二局只归档正式材料和引用汇总，不读取照片或跑推理。
冻结 E8 实际 bank64，不能零 RTL 扩为128/256；时延豁免未授予。
证据与同口径预算见 [r12记录](docs/validation/picture-r12-engineering-20261022/README.md)。
一次空格持续重拍已通过宿主回归和RAM实板验证：一次NACK后自动恢复，新帧与模型请求
完整性一致，原生board模型执行1508个作业。新程序本次在RAM生效，SD未固化；
实体空格、完整识别和时延验收仍待完成。

r09 历史组合为 det416 + v2-band + 冻结 board + 方案 A + 精修 B；新域未达标，代码路径保留。
其历史 FP32 参考网格 133/135、严格 118/135；exact-int64 量化实跑
131/135、严格 116/135，不能把 FP32 数字移作量化结果。3.91 秒仅为模型忙周期预算。
接入、回放和口径差异见 [r09 无板记录](docs/validation/picture-r09-offline-20261021/README.md)。
此前 r08 exact 严格 120/135（88.9%）保留原组合身份，见 [r08](docs/validation/picture-r08-offline-20261021/README.md)。
板子和SD已回归，本次E8/原PN01启动核验通过；PN01尚未更新新模型或重拍程序。
现场缺黑将及 M0/生产状态没有翻转。

已完成三模型原生部署、FPGA 80 层数值核验，以及 PN01 独立 SD 文件与公共启动菜单。
在匹配 E8 易失位流下，`soc>` 输入 `xqboot` 后选择 `1 Picture_new` 即可从 SD 启动，
日常无需串口上传启动器；其他分支保留自己的文件和菜单项。见 [SD 启动约定](docs/PICTURE_SD_NAMESPACE.md)。

2026-10-20 原始标签历史复测为两原后端均 134/135、三个弱类 AP50 均 .995；
指定数字通过，整体 M0 尚未接受。实拍完成全部三模型，但最终盘面校验拒绝；
单次并行诊断耗时约 54 分 52 秒，正确识别、3/5 秒时延、三局及挪盘验收仍未通过。
用户已确认识别期间保留对弈页且提示可见；实体空格、字体偏好和听感仍待验。

训练侧问题及复现材料见 [训练 AI 交接](docs/TRAINING_AI_HANDOFF_20261020.md)。
历史 P19、模型接收及各次失败均保留在日期验证目录和 [CHANGELOG](CHANGELOG.md)，
不作为当前运行态。下文 V2.1 正式交付与更早版本保留各自发布身份；本检查点不新增 BoardRelease。

## 2026-10-15 V2.1 交付重建状态

工程已配置本地 Windows 原生 `riscv32-unknown-elf-gcc` 16.2.0；编译器
SHA-256 为 `e1ca0bb0ca138a597885e61b174f40744b3e8e08b4317c6ecb5f708623a746a6`。
它与历史固件所用的同版本编译器哈希不同，因此重新编译了 bootloader，
不能继续用旧位流和旧板测记录代表这组新固件。仅 bootloader 代码
使用 LTO，相机、CRC、PNG 计算单元及官方 CoreMark 保持 `-O2`，
相机 SD/FAT 控制代码用 `-Os`；镜像为 91,148 字节，链接器核对留给栈
17,752 字节，超过 16 KiB 下限 1,368 字节。完整 `run_all_tests.ps1`
回归已报告 `SOC_ALL_TESTS_PASS`。新 PDS 输入快照
`5f802f47f8ad4907925af156b227ad21` 生成位流 SHA-256
`a3f288b30991b111c3a840c03aae18694c748529ea57278c228b7d277c408b33`，
整机资源为 42,979 LUT、35,447 FF、4,436 LUTRAM、120/155 DRM、177 APM。
最终慢/快角 STA 均为 `All Constraints Met`；CPU 慢角 setup +1.983 ns，
同域 hold 报告为 +0.000/+0.001 ns，余量很薄；DDR PHY 最差 setup
+1.015 ns。输入快照、位流和新 bootloader 已通过工程审计及频率证据归档。

该新位流经 JTAG 仅写易失 CRAM 后，用原 microSD 的六个文件完成板端
CRC32、S 模式 Linux、官方 PFF1 加载和 `/dev/pango-mac0` 注册。两次
`h2e2` 自动走棋均返回 `b9c7`，首轮记录 Stage A gather 与 Stage B MAC
硬件作业。旧 rootfs 在该位流上的启动有两次到达 GUI READY，另两次在
`DIRECT CORE READY` 后分别超过 300/420 秒未就绪；同卡旧位流也有约
167 秒的就绪延迟。当前位流的板上 CoreMark
3+1 已通过，每次运行超过 12 秒，性能均值为 5.280148744 CoreMark/MHz，
详见[板测记录](docs/validation/v2_1-board-coremark-5f802-20261015/README.md)。
2026-10-15 按用户要求停止长 RTL CoreMark，今后 CoreMark 只以实板
3+1 计时及官方 CRC 复核验收；V2.1 的独立板测交付校验已通过。
功能 RTL 与软件回归仍执行。CPU hold 余量仍很薄。针对 GUI 状态查询会同步等待加载线程的问题，
当前源码已改为非阻塞查询、退出时回收线程；新的
`linux/boot/rootfs.cpio` 为 8,227,328 字节，SHA-256
`0470b510ad45b6b9dd394aea8f174825238158ff76dbd31a37d18ac22329a763`，
已通过 WSL 构建、UCI/GUI 主机回归和 rootfs 合约检查。2026-10-15
已将其作为 `brfs2.bin` 单独写入 microSD，回读 SHA-256、七文件大小与
CRC32 通过；原卡 `brfs.bin`、官方模型及攻击表均保留。相同位流和新
rootfs 连续三次从 SD 启动到 GUI/官方 Pikafish ready，均完成板端载荷
CRC32；用 FIFO 落子时黑方实际回应，Stage A gather 与 Stage B MAC
均有活跃日志。三轮从 SD 校验完毕到 GUI ready 仍耗时约 122–124 秒，
说明非阻塞查询没有消除固定启动延迟；三次成功也不足以关闭长期稳定性
问题。已启动 Linux 中单独重启同一 GUI 约 16 秒即 ready；附加冷启动
串口探针在延迟期间丢失命令字节，尚不能判定内核或 GUI 的具体阻塞点。
2026-10-15 现场操作者确认开发板保持供电、未重载位流，并在这组精确产物上看到
HDMI 棋盘、鼠标选中高亮与一次落子后的黑方回应；目视结果及身份边界见
[现场回执](docs/validation/v2_1-board-gui-nonblocking-20261015/board_nonblocking_visual_20261015.json)。
当前板测 `BoardRelease` 证据门槛已通过；正式包还须由
`create_delivery.ps1` 创建，并由 `verify_delivery.ps1` 在独立提取目录
报告 `SOC_CLEAN_DELIVERY_PASS`。实板启动使用随包的只读 SD 装载器，操作和限制见
[V2.1 上板指南](docs/V2_1_BOARD_BOOT.md)；原始证据见
[三轮实板记录](docs/validation/v2_1-board-gui-nonblocking-20261015/README.md)。
下文旧位流数据是历史记录。

历史偏置缓存优化位流为
`artifacts/soc_top.sbit`（SHA-256
`ec621b232854b70f931acb2895e805666758fd924131dc9ee950bb061a7c678e`，
输入快照 `b39d18697afd40ca98df381c9cf149ef`）。保持 V3.5 CPU、
59.4 MHz 与现有加速器作业周期；整机资源为 **42,981 LUT、35,447 FF、
4,436 LUTRAM、120/155 DRM、177 APM**，较上一正式版减少 1,517 LUT
及 1,497 FF。完整路由与慢/快角 STA 通过，CPU 慢角 setup/hold
+2.134/+0.038 ns、快角 hold +0.032 ns，DDR PHY 慢角 setup +1.811 ns。
该精确位流已通过易失性 CRAM 上板、SD 载荷 CRC、S 模式 Linux、官方
PFF1 加载和 Stage A/B 硬件走棋：注入 `h2e2` 后返回 `b9c7`、683 nodes。
本轮未复测实体鼠标与 HDMI 画面；详细证据及限制见
[接入记录](docs/Pikafish_Main_Integration_Candidate.md)。

以下是优化前的正式构建基线：

2026-10-15 正式构建：59.4 MHz CPU、120/155 DRM 的
`artifacts/soc_top.sbit`（SHA-256
`ee71c5c426f09d3453f2919a65e6e6542a2d281ebd0fbf646802b7ee9b73026b`）
来自输入快照 `e90ec0c4956a4659aeb8229b51faa2bf`。整机资源为
44,498 LUT、36,944 FF、4,436 LUTRAM、120/155 DRM、177 APM；最终双角
STA 全部通过，CPU 慢角 setup +1.280 ns、hold +0.124 ns，快角 hold
+0.086 ns，DDR PHY 最差 setup +0.768 ns。该精确位流已通过易失
CRAM、S 模式 Linux、官方 PFF1 模型、GUI 及 Stage A/B 硬件走棋测试。
同 RTL 的 `83c9561aa86d48858929a80f025cfc8b` 候选还由用户在
HDMI 棋盘上确认了实体鼠标选中高亮和黑方回应；正式位流的实体
鼠标交互结果单独记录。

V3.5 CPU 的 `TIME` 与 CLINT `mtime` 分别按 59.4/49.5 MHz 计数；
OpenSBI 将 SBI 定时器剩余时间换算为 CLINT ticks，设备树 timebase 为
59.4 MHz。新固件、rootfs 和设备树已加入 `linux/boot` 并通过主机校验。
修正 MAC CPU uncached alias 后，内核在板上注册 `/dev/pango-mac0`；
GUI 目前仍使用单进程 `mmio-shadow` 后端。注入红方 `h2e2` 后，
Stage A/B 均执行，官方 Pikafish 返回黑方 `b9c7`（683 nodes，约 6.7 秒）。
实板日志、时序范围及当前限制见[接入记录](docs/Pikafish_Main_Integration_Candidate.md)。

以下是新快照上板前的 HID 点击计数诊断记录。该功能候选另存于工作区
`board_test_candidates/soc_top_hid_cb4bacad_hold_minus_012ps.sbit`（SHA-256
`d332ba743dfeaea500b47c7d06ff269001a49c8373f0a39d54da6e32c3c8161b`）。
它的最终 STA 仅有一条 SYS 慢角 hold −0.012 ns，CPU 慢角 setup +1.613 ns、
DDR PHY setup +2.203 ns；综合为 44,473 LUT、36,944 FF、4,436 LUTRAM、
120/155 DRM、177 APM。用户授权将此位流写入易失 CRAM 测功能：板上
Linux 到 `/ #`，Stage B 16 桶、96 例、384 次 MAC 作业通过；官方 PFF1
加载、硬件 Stage B 初始化、GUI 最终 `XQ LINUX PIKAFISH READY` 均出现。
按键计数已由板上日志读到，实体鼠标选子和官方引擎实际回棋仍待验收。
这份时序未通过的位流仅用于诊断，不替换正式位流或交付包。

今后遇到少量、幅度很小的负时序路径，可以在核对最终双角 STA 的
违例类型、端点和输入快照后，单独保存候选哈希，用 JTAG **只写易失
CRAM** 测功能。测试记录必须标明时序未通过；功能通过不构成时序通过，
也不得将该位流提升到 `artifacts/soc_top.sbit`、发布包或交付结论。
交付仍需同一构建的完整布线、双角 STA 全部通过及相应板测。
后续复测与证据见[官方 Pikafish 硬件接入候选](docs/Pikafish_Main_Integration_Candidate.md)。

以下为该候选的早期构建追踪；当前结果以上述状态为准。远程 main 上的
[官方 Pikafish 硬件接入候选](docs/Pikafish_Main_Integration_Candidate.md)
已在 CPU V3.5 源码上以显式候选开关启用 M/S/U 和 Sv32，并增加可选卷积阵列连线与
RV32 MMIO 兼容后端。V3.5 默认 M 模式不变；S/Sv32 候选通过单元测试和 ADS 门槛，
63.642857 MHz 的两次布线搜索未收敛；59.4 MHz 的两次布局种子 5 构建均完成布线，
第二次 CPU hold 已转正，但 DDR PHY setup 仍未通过最终 STA。第 6 次约束迭代布线
按资源优先要求停止，未生成可验收位流。
官方引擎板上运行仍待验收。资源数字、WSL 编译方法和门槛见该文档。
已完成的 FP8 解码等价改写让整机 ADS LUT 从 49,652 降至 49,288（-364），
MAC 定向回归与 CPU ADS 控制/故障变异检查通过；完整布线和双角 STA 尚未完成。

**当前工程约束：先减资源，再做完整布线。** 在保持 CPU V3.5、既有外设和模型
数值语义的前提下，先从原生 PDS 的模块级 LUT/FF/LUTRAM/DRM/APM 与 CLMA 报告
定位占用，写正确性及周期基线，再做一项可回退的 RTL 优化。候选先过定向仿真、
整机 ADS 资源与 CPU/ICache/CDC 审计，并比较 CPU 时钟域的综合时序；只有资源或
关键路径有可核实改善、且性能退化在已记录口径内可接受时，才批准新的完整 PnR
搜索。换 seed、叠加 route 约束或单纯降频不能替代资源优化。物理性能、DDR/CPU
最终时序及上板功能仍须以同一输入快照的完整布线、双角 STA 和匹配位流验收。
多模型作业形状、权重 bank 缩容边界、DMA 与卷积阵列的取舍见[资源方案](docs/Multi_Model_Resource_Plan.md)。
从相机帧到整盘棋子状态、FEN 的模型选择与分次识别方案见[完整视觉系统审查](docs/Chess_Vision_System_Options.md)。

## NNUE/象棋加速整合说明（v2 合并新增）

本合并（v2）在 V6.5 平台（CPU V3.5 导入 e698e3bb，63.642857 MHz 双时钟 CDC，
M-mode RV32IMA）之上整合 feature/nnue-gather-10ms 分支的象棋加速能力：

- 硬件：MAC 窗口扩至 0x1fe10000..0x1fe1_01ff；`mac_accel_ddr_kernel_top` 以
  `ENABLE_PFF1_GATHER(1)` 实例化，新增 PFF1 Stage A gather（0x1fe10100）、
  卷积前端（0x1fe10040）与权重双缓冲；保留 V6.5 的 dense MAC、稀疏象棋评估
  （0x1fe10080）与 UART 偏置双输出 LUT 修复，同时保留 NNUE 线已测的 Stage B
  LUT 优化。
- 软件：bootloader 新增 `xqboot`（从 MicroSD FAT 只读加载 xiangqi.bin + xqmodel.bin
  并跳转 0x01000000）；保留 `loadx`+`boot` 串口 XMODEM 路径；sw/pikafish_ft_stage_a
  与 sw/pikafish_mlp_stage_b 为裸机 Stage A/B 验收程序。
- YOLO 卷积前端在 v2 位流中以 ENABLE_CONV=0 门控（第一次 PnR 布线发散后
  的平台决策；源码保留，棋力栈不依赖它）。
- 平台边界：本 CPU 不含 S-mode/C，NNUE 线的 Linux+Pikafish 流程在本平台不可运行；
  相关源码与 61.5-66.5 ms 历史测量仅作存档（见 docs/NNUE_10ms_Optimization.md）。
  10 ms 指标在本平台不可测量，也未达成。
- v2 构建完成全部 PDS 门禁（attempt 4：LUT 49,076、DRM 140.0、STA All
  Constraints Met，位流 soc_top.sbit sha256 6c079c42…），并于 2026-10-11
  通过端到端实板验收：稀疏 H128 NNUE 经 FPGA 评估（EVAL=SPARSE-HW16）、
  Stage A 78/78 与 Stage B 61/61 板上验收、8/8 步独立合法性校验通过的
  完整对局。板上根因修复（子字未缓存写挂死 CPU → 全字暂存拷贝）已入库。
  证据见 docs/validation/v2-merge-20261011/。


CPU V3.5 在 PG2L100H-6-FBG676 集成 SoC 上以 **63.642857 MHz** 完成完整布局布线、
slow/fast STA 和本轮板测。连续三次有效 performance 均值为 **334.913227361852 CoreMark /
5.262385177991809 CoreMark/MHz**，每 MHz 比 V6.1 受控基线提高 **3.79154449%**，
同时满足频率高于 59.4 MHz 与每 MHz 至少提高 1% 的要求。validation 单独通过。
[本轮板测、全部 ticks 与验收边界](docs/validation/v6_5-board-results-20261009/README.md)
和[显式发布清单](docs/validation/v6_5-board-release-20261009.json)是当前结果入口。

| 集成 SoC 板测 | CPU MHz | 三次 performance 均值 CoreMark | CoreMark/MHz | 相对基线每 MHz |
|---|---:|---:|---:|---:|
| V6.1 受控基线 | 59.4 | 301.16680611873926 | 5.070148251157226 | 基线 |
| 新 CPU 同频对照 run75f8 | 59.4 | 312.9670395559131 | 5.268805379729176 | +3.91817199% |
| V6.5 最终 run838e | 63.642857 | 334.9132273618522 | 5.262385177991809 | +3.79154449% |

最终成绩使用实际 6000 次迭代与完整 ticks；三次约 17.9 秒。SYS/TIMEBASE 均固定
49.5 MHz，GCC 16.2.0、`-O2 -march=rv32ima_zicsr_zifencei -mabi=ilp32` 不变。
63.642857 MHz 是本轮最高已完整验证频率，**不是已证明的物理极限**。PLL 为
891 MHz/14，固件配置整数值为 63,642,857 Hz；频率身份由 PLL、STA、固件和实际
CRAM 加载位流共同绑定，未用 MMIO 配置值单独证明时钟，也未作独立仪器测频。

## 当前实现与验证

CPU 实现为 `e698e3bb78947fd4f7a0b5095e1cdc85a81e4502`，
[source.json](rtl/cpu/source.json) 固定其 Scala、生成配置、RTL 和初始化文件身份。
主要改变是 ROB 结果写入与分配控制隔离、哈希索引的 64 组后备 BTB 和 4 项 ALU
保留站，没有新增流水级。SoC 同时修复 UART TX FIFO 写地址的 hold 路径：使用两颗
保留的双输出恒等 LUT，不增加状态或周期；ADS 合同检查四位地址到四个 LUTRAM 的映射。

最终 SoC 实现 `7ad9f204d5ad802b1eae8e5cb62890634a7bf275` 的 div14/seed5
run838e 完成第 5 次完整 PnR；对照实现 `4b4f4637` 的 run75f8 为 59.4 MHz。
两者分别保留冻结输入与实际 CRAM 身份，不互换位流或借用旧构建结果。
最终 CPU slow/fast setup 为 +1.336/+6.645 ns、hold 为 +0.022/+0.017 ns；
SYS hold 为 +0.173/+0.132 ns。同轮 ADS 资源为 49,332 LUT、37,933 FF、
4,530 LUTRAM、140 DRM、0 latch。18 个时钟、116 条双角摘要及 CDC 检查通过；
187 条历史外部 I/O 未约束信息仍保留。SYS 域值不是 UART 专属 slack，PNR 导出
不独立证明完整 pad 连接/INIT，详见[验证记录](docs/Validation.md)。

现有完整 RTL 回归通过（335.884 秒、338 source/194 test）；本轮 CoreMark RTL
仅使用原有短测，不把短测计为正式成绩。[终态身份复核](docs/validation/v6_5-development-20261008/run838e-identity-review-run02/result/review.json)
关联了 355 份冻结/Git 输入、7 份暂存输入、5 份固件合同、最终输出及短测模型/固件。
本轮两种频率的串口、DDR 装载和 MAC/DDR 自测通过；仅写易失 CRAM，没有 Flash/SD 写入。
Linux 启动与全面外设验收未作为新增目标，不能从 CoreMark 推断已经通过；
也没有独立 CPU 测试 SoC 的 V3.5 新正式分数。

[开发记录与预算](docs/validation/v6_5-development-20261008/README.md)保留全部尝试与失败：
完整 PnR 为 5/6，第 6 次未使用；两个板测编排失败发生在性能测试前，没有删除或排除
较低分的有效运行。早先的候选交付与旧 tag 均保留其历史身份。

## 复现与正式交付入口

源码、版本、固件和脚本须在硬件构建前冻结；后续文档/证据提交不改变实现身份。
不要让 source.json 追随文档提交。生成、回归与预算管理见 [BUILD](docs/BUILD.md)。
本轮使用 [BoardRelease](docs/BOARD_RELEASE.md)：短 RTL、真实板测 3+1、同频对照、
CRAM/固件/位流/STA 关联与按实际 iterations 的官方 CRC oracle 均已通过。
正式 ZIP、最终交付 commit/tag 及其哈希由最后的交付校验记录，不由文档标题代替。

```powershell
$python = 'D:\LJL\WORK\msys64\mingw64\bin\python3.exe' # 本轮 Python 3.14.4
.\scripts\create_delivery.ps1 -CoremarkEvidenceMode BoardRelease `
  -ReleaseManifest 'docs/validation/v6_5-board-release-20261009.json' -PythonPath $python
.\scripts\verify_delivery.ps1 -CoremarkEvidenceMode BoardRelease `
  -ReleaseManifest 'docs/validation/v6_5-board-release-20261009.json' -PythonPath $python
```

## V6.1 已核实基线（下面结果不属于 V6.5）

V6.1 在 PG2L100H-6-FBG676 上集成 CPU V3.1、DDR3、HDMI、MicroSD、以太网、音频、键鼠、相机和加速器。该版本 CPU 为 RV32IMA 机器态配置；随包 Linux 载荷来自历史平台，未验证在此 CPU 上启动。2026-10-08 已完成串口 CoreMark 三次性能加一次验证实板测试，性能均值 **5.070148251 CoreMark/MHz**；其他外设的整体验收仍未完成，见[板测记录](docs/validation/v6_1-board-coremark-20261008/README.md)。

`src` 仓库维护 Chisel CPU 和独立 CPU 测试 SoC。本仓库通过 [sync_cpu.ps1](scripts/sync_cpu.ps1) 导入 `src/cpu/generated/core/CoreTop.sv`、导出配置和三个初始化文件，生成 [source.json](rtl/cpu/source.json)；集成包装、AXI CPU/SYS CDC、CLINT 和板级外设由本仓库维护。当前验证结果与缺口见 [Validation](docs/Validation.md)，旧 V6.0 完整布线与短时 CoreMark 属于[历史记录](docs/Validation_V6.0.md)。

## V6.1 历史时钟与接口

V6.1 当时的时钟意图（历史记录见 [div15](docs/validation/frequency-search/divisor-15.md)）：27 MHz 输入、891 MHz PLL VCO、CPU `CLKOUT3 = 891 MHz / CPU_DIVISOR`，当时 divisor 15、CPU 59.4 MHz；SYS `CLKOUT1 = 49.5 MHz`，CLINT TIMEBASE 固定 49.5 MHz。V6.1 主树 div15 已完成全量 PDS 和最终双角 STA；更高的 div14（63.642857 MHz）候选最终 CPU setup 失败，因此 59.4 MHz 是 V6.1 已测试 18→14 范围内最高完整 STA PASS。板测 `info` 与 CoreMark 报告上述时钟值并完成运行；未用独立仪器测频，也未搜索实板最高频率。CPU CoreTop、缓存和 `mcycle` 用 CPU 时钟；CLINT、AXI 系统总线、BRAM 与外设用 SYS 时钟。MMIO 系统窗口 `0x1fe00300` 中的 `SYS_HZ` 位于 `+0x08`，`CPU_HZ` 位于 `+0x14`，`TIMEBASE_HZ` 位于 `+0x18`；原 `SYS_ID=0x53563300` 与 `CAPS=0x1f` 保持稳定。详见[架构与内存图](docs/ARCHITECTURE.md)。

## V6.1 历史构建入口（不用于 V6.5）

Windows PowerShell 下，从仓库根目录运行：

```powershell
.\scripts\sync_cpu.ps1 -SourceRepo '..\src' -Check
.\scripts\check_clock_config.ps1
.\scripts\run_all_tests.ps1
.\scripts\build_fpga.ps1 -PdsTimeoutSeconds 14400
.\scripts\create_delivery.ps1 -CoremarkEvidenceMode ShortPilot
.\scripts\verify_delivery.ps1 -CoremarkEvidenceMode ShortPilot
```

完整依赖、源码同步、DTS/DTB、构建快照和停止方式见 [BUILD](docs/BUILD.md)。`build_fpga.ps1` 须产生本轮 `soc_top.sbit/.bin` 和完整 slow/fast 最终 STA，旧位流改名不构成新结果。2026-10-08 [实板 3+1 测试](docs/validation/v6_1-board-coremark-20261008/README.md)各运行 4000 次、计时超过 13 秒且 CRC/PASS 检查通过，性能均值 **301.166806 CoreMark / 5.070148251 CoreMark/MHz**，验证种子单列。板上镜像身份的证据边界见板测记录；该次 V6.1 板测补录未改 RTL、固件或位流。

2026-10-05 的 [RTL 短测证据](docs/validation/v6_1-short-pilot/release_evidence.json)保留：性能/验证种子估值分别为 5.024741829/5.019605575 CoreMark/MHz，专用十次迭代 ROM 各仅约 0.0335 秒，均不是正式分数。上述交付命令的 `ShortPilot` 仍校验这份历史 RTL 证据；板测结果另行归档，不依赖完成 Long 仿真。计时和固件边界见 [COREMARK](docs/COREMARK.md)。

## 当前 Console 与介质边界；V6.1 历史交付

串口 115200-8-N-1。无有效 Flash 裸机自启镜像时进入 `soc>`；有效镜像可在三秒窗口按键取消。`info` 显示三个时钟及设备 ID，`coremark`/`coremark validate` 分别执行性能/验证种子。SD/TFTP/XMODEM 和 Linux 手动装载命令保留为调试入口，不代表 Linux 启动验收。[console 命令](docs/console调试命令.md)、[MicroSD](docs/MICROSD_BOOT.md)、[相机 SD PNG](docs/CAMERA_SD_PNG.md)、[相机 UDP](docs/OV5640_BOOTLOADER_CAMERA.md)记录操作和历史硬件边界。

原发布包 `SOC_linux_V6.1.zip` 对应已发布的 `v6.1` tag；含 2026-10-08 板测补录的交付包另存为 `SOC_linux_V6.1_board_20261008.zip`，包内根同为 `SOC/`，区别与复现命令见 [BUILD](docs/BUILD.md)。[CHANGELOG](CHANGELOG.md)记录本版变化。DOCX 由本仓库 Markdown 生成，生成输入哈希见交付记录。旧 tag、原发布包与历史验证文件按原身份保留。

## NNUE 分支 README 存档（feature/nnue-gather-10ms，VexRiscv 平台，2026-10-09 快照）

# SoC V4.3 原生 MicroSD DMA + Linux GUI + Pikafish + CH9350L
跨会话、跨工程可调用的技能库见 [skills/README.md](skills/README.md)，包含性能、
时序、模型兼容、软硬件协同与上板调试五类。维护源为工作区根目录 `skills/`，
本工程交付时自动同步同一库并验证 `SKILLS_DELIVERY.json`。

## 当前优化分支快照（2026-10-09）

开发分支为 [`feature/nnue-gather-10ms`](https://github.com/whalellll/performance_soc/tree/feature/nnue-gather-10ms)。
本次保存累计的 gather/resident 驱动与 NNUE runtime、DMA/卷积 LUT 优化、音频与语音
接口、定向测试、板测记录及分阶段剖析工具；后续性能优化继续在此分支进行。

| 当前证据 | 结果与范围 |
|---|---|
| 最新候选整机资源 | **34,206 LUT / 28,934 FF / 191 APM / 150 DRM**；比 10-05 基线少 3,269 LUT（8.72%） |
| 原生最终时序 | 慢角 setup/hold **+0.862/+0.137 ns**，快角 **+3.081/+0.100 ns**；331 条 DDR 位置、17 个时钟已核对 |
| 板端功能 | 易失 CRAM 加载及 SD Linux 启动、卷积、真实训练权重六个特征块、resident 双 fd、context 池和调度测试通过 |
| 完整 NNUE evaluation | 原程序冷缓存均值 **64.943/66.489 ms**，热缓存 **61.542/62.365 ms**；含完整 NNUE、不含 UCI 搜索；四组共 1,600 次测量整数一致 |
| 当前主要瓶颈 | gather/FC0 提交、CPU 特征索引、PSQT 和数据复制；诊断热评估中硬件作业合计约 **2.389 ms**，是提交时间的子集 |
| 尚待验收 | **10 ms、完整 YOLO 30 fps、真实语音识别及并发无丢样均未达成**；M3b/M3d 保持待办，外部完整 Pikafish 搜索明确跳过 |

匹配的候选位流、最终原生时序、资源报告、有效放置约束和输入哈希保存在
本地工作目录 `artifacts/candidates/lut_20261009/`（不随正式包分发）。
详细证据见 [LUT 与板测记录](docs/YOLOv5n_LUT_Board_20261009.md)、
[Pikafish 瓶颈报告](docs/Pikafish_Bottleneck_20261009.md)及各自 JSON。
这是待继续优化的开发快照；TODO 完成后再合并并验证完整 SoC 发布包。

复查入口：

```powershell
python -X utf8 scripts/test_pikafish_profile.py
python -X utf8 scripts/test_project_skills.py
python -X utf8 skills/manage.py verify
python -X utf8 skills/manage.py verify-delivery --package .
# 硬件与软件回归须指定同版候选启动文件；外部完整搜索仍须单独验收。
./scripts/run_all_tests.ps1 -SkipExternalPikafishSearch `
  -RootfsPath build/nnue10ms/image/rootfs.cpio `
  -DtsPath build/nnue10ms/image/cpu_v2.candidate.dts `
  -DtbPath build/nnue10ms/image/cpu_v2.dtb `
  -GuiPath build/nnue10ms/pikafish/xiangqi-pikafish-gui
```

仓库包含五个完整 portable skills 和与本快照文档/交付脚本关联的
`SKILLS_DELIVERY.json`。哈希覆盖文件保留原字节，避免 Git 换行转换破坏跨平台校验。

V4.3 在 V4.2 原生 4-bit SD 控制器上增加写 DDR 的 payload DMA，用它在 bootloader
阶段把独立 PFF1 模型直接预装入 Linux 保留内存。原有响应与数据重叠时序修复、CMD18
多块读取、自动 CMD12、双缓冲和一次重试继续保留。稳定 ABI 版本仍为
`SoC V3.0.0`。现有 Linux GUI/Pikafish、HDMI 文本终端修复与 V3 功能继续保留。V3 在 Linux V2 键盘/鼠标版本上合入
CH9350L HID、摄像头控制器、MicroSD 启动控制器）。本次 V4.3 交付保留稳定的
## V4.3 能力（保留 V3 ABI）
- `0x1fe13000` 100H 底板 J10 native 4-bit MicroSD 控制器（`SDN2`，ID
  `0x53444e32`，version `0x00040300`）：bootloader 只读 FAT16/FAT32，
  可从卡根目录加载 Linux，或加载象棋 GUI 与独立 H128 推理模型；使用 CMD18、自动
  CMD12 和两个 512 B ping-pong 缓冲，软件每批读取最多 32 个扇区。新增的 native SD
  DMA 以保守的 AXI single-beat 写事务将完整扇区直接写入物理 DDR；普通小文件仍可走
  CPU 缓冲读取路径。
除原有 `xiangqi_fb_demo.bin` 和 `xiangqi_service.bin` 外，当前仓库包含完整的板端
`sw/xiangqi` GUI/搜索源码。`scripts/build_xiangqi_sd_wsl.ps1` 生成可由 SD 启动的
`xiangqi.bin`，并从已校验的服务载体提取独立 `xqmodel.bin`。本地黑方 GO2 搜索实际
使用该 H128 XQ8 模型和 MAC/稀疏评估器；它不是完整 Pikafish 引擎或官方 51 MB NNUE。
推荐把 `linux/boot` 的 Linux 六文件及象棋两文件复制到 FAT16/FAT32 MicroSD 根目录；
其中 `pikafish.atk` 是板端直接绑定的预生成攻击表：
启动失败时才进入原有 TFTP 流程。终端命令 `sdinfo` 查看卡和文件，`sdbench` 测试只读
吞吐，`sdboot` 手工启动 Linux，`xqboot` 启动独立象棋程序；
构建独立 GUI 和 H128 推理模型、制卡并从 bootloader 启动：

```powershell
.\scripts\build_xiangqi_sd_wsl.ps1
.\scripts\prepare_sd_card.ps1 -Destination E:\ -Content Xiangqi
```

上电时按任意键停止默认 Linux 自动启动，在 `soc-v3>` 输入 `xqboot`。bootloader 将
`xqmodel.bin` 装入 `0x0f000000`，将 `xiangqi.bin` 装入 `0x01000000`，校验模型
尺寸、XQ8 头及 CRC32 后启动。也可用默认 `-Content All` 让 Linux 与象棋共存于同一卡。

## 完整 Pikafish CPU 移植与 SD 集成

当前已提供面向板卡 `RV32IMA/ilp32` Linux 的完整 Pikafish 构建，并把 NNUE Stage A
特征累加接入片上 MAC v2。构建固定使用
Pikafish 提交 `56be6f65c21c6a3c7f9b884a976fc85d31d03287` 和官方 51 MB NNUE
源模型（SHA-256 `3cd15292bf8c979884262f57fc723959fc0dea43b4d8d544f88db5ceb2479e24`）。
构建阶段将它转换为 68,122,688 字节的 PFF1 直读模型（SHA-256
`de0906fa1bea82248523eb39fc6b2956613b02ae675ccf67eef3f392de939260`）；
全部构建与测试在 WSL `pikafish-verify` 中完成，不使用 Docker；交叉工具链位于
`/opt/toolchain/bin`。

### 硬件加速与 DMA 接入 TODO

Stage B 的逐文件改动、调用链、风险、验证矩阵和完成定义见
[Pikafish Stage B 硬件加速接入方案](docs/StageB硬件加速接入方案.md)。正式实施必须遵守：

- Stage B 只替换官方 FC0，激活、FC1、FC2、skip 和缩放继续使用官方实现；
- FC0、positional、PSQT 和最终 NNUE 必须 bit-exact，不能使用误差容忍；
- PFSB 必须和当前 PFF1 的解码流指纹及 `MLPS` CRC 强绑定；
- Stage A/Stage B 必须共享一个 MAC 运行时、互斥、超时和硬件故障熔断；
- 任一 tile 失败必须丢弃全部硬件部分结果，由官方 CPU FC0 完整重算；
- `S95pikafish` 不得无条件预装 Stage B；阶段四上板对拍和性能验收通过后才允许默认开启；
- 第一版仅做软件接入并复用当前 sbit，性能不足时才评估 FC0 批处理 RTL。

已接入正式启动、GUI 或 Pikafish 搜索调用链：

- [x] native MicroSD payload DMA 装载 `fw_jump.bin`、`Image`、`rootfs.cpio`、
  `cpu_v2.dtb`、`pikafish.pff` 和 `pikafish.atk`；完整扇区走 DMA，异常时回退 CPU。
- [x] PFF1 由 bootloader DMA 预装到 `0x10000000`，Pikafish 通过只读、cacheable
  `/dev/mem` 映射直接使用，不再建立约 64.4 MiB 的模型私有副本。
- [x] PFA1 由 bootloader DMA 预装到 `0x15000000`，Pikafish 通过
  `Attacks::init_precomputed()` 绑定，不再在板端生成车炮攻击表。
- [x] NNUE Stage A 特征累加已接入官方 Pikafish accumulator 更新路径；不少于 8 个
  特征项的更新拆成 4 个 256 通道 MAC 任务，小更新和硬件错误走 CPU 精确回退。
- [x] MAC DDR DMA 已用于 Stage A 输入、权重、偏置读取和结果写回；实体板搜索后已观察到
  `DONE`、无 `BUSY/ERROR`，最后一次任务为 10 个输入项。
- [x] GUI 已提交完整六字段 FEN 并调用真实 Pikafish 搜索；实体鼠标连续两次红方落子均收到
  黑方自动回应。
- [x] DDR RGB565 framebuffer DMA 已接入 Linux GUI 到 HDMI 的显示链；GUI 当前只映射并
  原地更新 FB0，不再映射未使用的 2 MiB FB1。

Stage B 正式搜索接入状态：

- [x] 已生成 16 个 NNUE Stage B 层栈的 593,920 字节 MAC 原生预排布包。
- [x] 已提供 `pikafish-stageb-load` 手工加载器，并完成容器、版本、逐栈 CRC 和 DDR 回读校验。
- [x] 已完成 Stage B FC0 的 4 个 `256x32` MAC tile 计算和 CPU 参考对拍；FC1、FC2 与激活
  函数当前仍由参考 CPU 路径实现。
- [x] 已增加 Stage B 黄金验收程序：16 个 bucket、6 类确定性输入、96 组完整 propagate、
  3072 个 FC0 lane 已与固定版本官方标量实现 bit-exact，并校验 PFF1/PFSB 布局与 CRC。
- [x] 已完成同一组官方黄金向量的实体板验收：真实 PFSB 直接驱动 384 个 MAC tile，3,072 个
  FC0 lane 和 96 个完整 Stage B 分数全部 bit-exact，并检查 scratch canary 和权重区未被改写。
- [x] Stage B 权重装载已纳入引擎生命周期；`S95pikafish` 不预装 PFSB，模型或硬件失败不阻止 GUI READY。
- [x] 官方 Pikafish `Network::evaluate()` 已按 bucket 调用 Stage B FC0 后端；激活、FC1、FC2、skip
  和缩放仍走官方实现，`trace_evaluate()` 保持纯 CPU。
- [x] Stage A/Stage B 已共享同一 MAC MMIO、DDR 映射、互斥锁、有界超时和硬件故障熔断状态。
- [x] PFSB 已升级为 v2，并与 PFF1 解码流 SHA-256 及 `MLPS` 大小/CRC 强绑定。
- [x] 已补齐 16 bucket、红黑双方共 32 个合法局面的 transformed features、FC0、PSQT、
  positional 和最终 NNUE 对拍；实体板真实执行 128 个 MAC tile，全部 bit-exact。
- [x] 共享互斥、有界超时、完整 CPU 回退、真实搜索 shadow 对拍、8 线程宿主压力以及
  MAC BUSY/ERROR/timeout 实板故障注入均已完成。
- [x] 已实现 `0`、`verify`、`1` 三种运行模式，并通过正常、截断、坏 payload CRC、坏 bucket
  和模型指纹不匹配测试；阶段四实板固定节点搜索提升 17.9%，生产默认值已改为 `1`。
- [ ] 根据 FC0 实际搜索收益决定是否继续硬件化激活函数、FC1、FC2 和 skip/缩放尾部。
- [ ] 消除 Stage A 的 CPU 权重行整理：评估 MAC DMA 直接读取 PFF1 离散权重行或加入硬件
  gather；当前 MAC DMA 读取的是 CPU 已整理到 scratch 的连续权重。
- [ ] 完成整盘、多局面和长时间搜索上板回归；当前证据覆盖 GUI READY、两次实际落子回应和
  Stage A 完成寄存器状态，不等同于完整对局验收。

不属于当前 Pikafish 计算接入范围：相机写帧 DMA 仅供 bootloader CMOS2 模式使用；native
SD DMA 在跳转 Linux 前结束，当前没有 Linux MMC/块设备驱动；以太网/TFTP 使用 MMIO/FIFO，
不是 DDR DMA。上述独立路径不应计为 Stage A 或 Stage B 搜索加速。

```powershell
.\scripts\build_pikafish_rv32.ps1
.\scripts\build_pikafish_attack_tables.ps1
.\scripts\test_pikafish_rv32.ps1 -SkipBuild -Nodes 1000
```

产物为 `artifacts/pikafish-rv32` 和 `artifacts/xiangqi-pikafish-gui`。回归会检查静态
ELF32/RISC-V/soft-float 属性，执行
20 万组 portable 128 位运算对拍、x86_64/RV32 Stage A 布局对拍，并用 QEMU 运行完整
UCI 初始化、`eval` 和三组局面的
`go nodes 1000`，与同源码构建的 x86_64 参考引擎比较 `bestmove`、`ponder` 和 WDL。

完整 SD 启动文件将 Linux framebuffer/CH9350L GUI 和内嵌引擎放入 initramfs；68 MB 官方
NNUE 不再塞进 `rootfs.cpio`，而是作为卡根目录的 `pikafish.pff` 单独加载。车炮 magic
攻击表由构建机生成到卡根目录的 `pikafish.atk`。构建脚本会同步 DTS/DTB 的
`linux,initrd-end` 并生成外部模型：

```powershell
.\scripts\make_rootfs.ps1 -IncludePikafish -ExternalPff1 -Distro pikafish-verify
.\scripts\test_pikafish_rootfs.ps1
.\scripts\build_fpga.ps1
.\scripts\prepare_sd_card.ps1 -Destination E:\ -Content Linux
```

生产 rootfs 默认是 embedded-only：GUI 内已静态包含所需 Pikafish 核心，因此不再重复放入
启动流程未调用的 `/usr/bin/pikafish`。这样可为阶段二板级验收 ELF 留出空间，并保持
initramfs 小于 8 MiB。仅在明确需要板端命令行诊断时使用 `-EmbeddedOnly:$false` 构建
非生产镜像；rootfs 测试和主回归采用相同默认值，防止无用独立引擎再次进入生产卡。

当前阶段三上板 `rootfs.cpio` 为 8,185,344 字节，范围为 `0x03000000..0x037ce5ff`；外部 PFF1 为
68,122,688 字节，预生成攻击表为 34,603,072 字节。bootloader 用 SD DMA 把攻击表装到
`0x15000000`，Linux 校验并通过 `Attacks::init_precomputed()` 直接绑定，不再在板端生成
33 MiB 车炮表。成功标志为 `PFA1 DMA preload ready` 和
`XQ LINUX ENGINE INIT stage=attacks-ready`。
必须配套使用 V4.3 CRAM 位流，因为旧控制器没有 native SD DMA 寄存器。
Linux 进入 root shell 后执行 `xiangqi-pikafish` 启动完整引擎 GUI，走棋后显示 Pikafish
WDL 换算的红方胜率。此流程不需要、也不会写入 SPI/configuration Flash。
GUI 提交给 Pikafish 的每个局面均使用完整六字段 FEN；象棋没有王车易位和过路兵状态，
因此后三个状态字段使用规范占位与计数。搜索入口分别记录 FEN 生成、`set_position()`、
搜索启动和无 bestmove 错误，避免把解析失败误报成笼统的“搜索错误”。宿主测试固定校验
初始局面和落子后的六字段 FEN，并用同源码参考引擎执行真实搜索。

### PFF1 DMA 与最小 CPU 改动

本方案**不修改 CPU 内部实现**：`rtl/vendor/VexRiscv_Linux.v` 的 cache、MMU、异常和换页
逻辑均保持不变。SoC 原有 DDR 地址译码已经提供 `0x80000000..0xbfffffff` uncached alias，
因此这里只复用现有能力；不新增 cache flush 指令，也不依赖换页异常搬运模型。

| 用途 | 地址/大小 |
|---|---|
| PFF1 物理 DDR 起点 | `0x10000000` |
| Linux/CPU 只读缓存映射 | `/dev/mem` 物理 `0x10000000`，不使用 `O_SYNC` |
| 诊断/旧复制路径的 uncached alias | `0x90000000` |
| DTS `reserved-memory` | `0x10000000..0x14ffffff`，80 MiB，`no-map` |
| 当前 PFF1 有效数据 | 68,122,688 B，`0x10000000..0x140f783f` |

数据路径为：FAT 根目录 `pikafish.pff` -> native SD ping-pong buffer -> AXI 写 DMA ->
物理保留 DDR -> Linux `/dev/mem` 只读、cacheable 映射物理 `0x10000000` -> PFF1 头和
固定布局校验 -> 五个 feature-transformer 段直接视图，只有 MLP 小段复制进引擎。
DMA 只接受 512 B 扇区、4 字节对齐且低于
`0x1c000000` 的物理目标；FAT 连续区每个命令最多合并 32 个扇区。DTS 的 `no-map` 防止
Linux 页分配器复用模型区。DMA 在跳转 Linux 之前完成，运行期没有设备或 CPU 写者，
因此首次 cache fill 一定发生在 DMA 完成之后；运行时不能再通过 `0x90000000` 别名修改
同一模型区。`0x90000000` 仅保留给诊断和旧复制加载路径。这就是本版处理访存一致性的
边界，不需要扩大 PWA，也不需要侵入 CPU cache 控制。

PFF1 已在构建机完成 Zstd 解压、LEB128 展开和 MLP 运行时顺序预排布。板端不再执行
Zstd/LEB128 解压，也不再复制或重排 67,548,352 字节的五个 feature-transformer 段；
这些段由 `Pff1ArrayView` 直接引用 DDR；563,264 字节的 `MLPS` 段在原映射上校验 CRC，
再直接解析进运行时层数组，不再建立中间 `std::string`/`istringstream` 副本。
这样消除了约 64.4 MiB 的模型私有副本。板端 `pff1-view:` 路径复核头部、固定布局和
MLP 段的 CRC；五个直接引用段不再重复扫描 CRC，跨进程共享后端也不再对这 64.4 MiB
计算内容哈希。完整性边界由写卡前 SHA-256/回读、SD 块 CRC16 和不可变 `no-map` DDR
共同保证。文件/QEMU 路径仍完整校验五个大段及 MLP，保留离线损坏回归。成功时输出
`PIKAFISH_PFF1_VIEW_READY direct_bytes=67548352 mlp_direct_bytes=563264` 和
`PIKAFISH_PFF1_READY`；`PIKAFISH_PFF1_STAGE stage=... elapsed_ms=...` 以及
`PIKAFISH_INIT_STAGE ... delta_ms=...` 用于区分映射、头解析、MLP 和验证耗时。
GUI 会先完成首帧、鼠标输入和点击轮询，再在后台线程初始化引擎，因此慢加载期间界面仍可响应。
嵌入式入口把最终 PFF1 路径、单线程和 8 MiB Hash 一次性交给 `Engine` 构造器，避免先加载
默认 NNUE、创建默认线程/16 MiB 置换表，随后再重建线程、缩小置换表、重载 PFF1 并重复
`search_clear()`。PFF1 的 MLP 已按当前运行时布局连续存放，loader 从已映射段按层直接
复制，不再构造中间流，也不再对约 50 万个 `int8` 权重逐字节调用 `istream.read()`；
每个层栈输出 `PIKAFISH_PFF1_MLPS_STACK_READY`，便于定位板级访存停点。需要 SIMD 重排的
构建仍按索引写入目标布局；普通 UCI 构造保持原来的默认模型和 16 MiB Hash 行为。
直视图对象含进程本地 mmap 指针，嵌入式 GUI 会把已经解码好的 `unique_ptr<Network>`
直接移交给引擎持有，不再执行上游跨进程共享后端的约 68 MiB 内容哈希、共享映射创建和
第二次全量复制；普通 UCI 构建仍保留上游共享行为。Stage A 直接使用该唯一 PFF1 模型
的行权重；刷新和较大的增量更新被拆成
4 个 256 通道 MAC 任务；默认不少于 8 个特征项
时走硬件，更小更新留在 CPU，任何 `/dev/mem`、ABI 或任务错误都回退原始精确路径。
Stage A scratch 使用总线 `0x1b0a0000..0x1b0b23ff`（CPU uncached alias
`0x9b0a0000..0x9b0b23ff`）。串口先后出现 `PIKAFISH_STAGEA_ACCEL_READY` 和
`PIKAFISH_STAGEA_ACCEL_ACTIVE` 表示寄存器校验及首批四个 tile 均已成功。

嵌入式构造只在 `ThreadPool::set()` 末尾初始化一次 Worker 历史和 NNUE cache，不再在
cache 构造及 Worker 构造中提前重复写入；首次 8 MiB TT 直接使用 Linux 匿名映射的零页，
`ThreatOffsets` 也不再先清零再逐项覆盖。单线程嵌入式构建进一步把历史项编码为“物理零
= Pikafish 逻辑初值”，从而让 41,230,336 字节共享历史区直接使用 Linux 新匿名页，首次
启动不再执行数百万次 16 位 atomic 赋值。两轮优化合计避免约 95 MiB 启动写入。
运行期“新局/清 Hash”不会跳过清理：历史表使用分片 `memset` 恢复逻辑初值，TT 仍完整清表；
普通 UCI/多线程构建保持上游类型和行为。Stage A 打包改为逐槽写入有效值和 padding，
不再先清两块 scratch；单缓冲 GUI 也不再映射未使用的 2 MiB FB1 窗口。

rootfs 保留 16 个 Stage B 层栈的 593,920 字节 MAC 原生预排布包、官方黄金向量、实体板
验收程序和手工加载器。官方 Pikafish 搜索已在 FC0 调用 Stage B 后端；权重仍由引擎在
PFF1/PFSB 强绑定校验后装载，`S95pikafish` 不运行独立预装程序。主机侧执行
`scripts/serial_pikafish_stageb_board_accept.ps1` 会停止 GUI、校验板上文件哈希、完成
16 bucket × 6 输入的真实 MAC 对拍后再重启 GUI；通过 marker 为：

```text
PIKAFISH_STAGEB_BOARD_GOLDEN_PASS buckets=16 cases=96 jobs=384 fc0_lanes=3072 pfsb_crc32=0836b938
```

该 marker 只表示第一阶段独立硬件路径验收通过；正式搜索接入由阶段三/四 marker 单独验收。

.\scripts\build_pikafish_stageb_linux_wsl.ps1 -Distro pikafish-verify
.\scripts\make_rootfs.ps1 -IncludePikafish -ExternalPff1 -Distro pikafish-verify
.\scripts\build_pikafish_attack_tables.ps1
.\scripts\test_pikafish_rootfs.ps1
```

日常开发、调试和上板迭代只更新源码、`linux/boot` 运行文件及必要的
`artifacts` 产物，并执行与改动范围匹配的回归；不要求每个开发版本都生成或更新
`soc_linux.zip`。只有里程碑版本、正式发布，或用户明确要求交付包时，才执行：

```powershell
目标器件为 `PG2L100H-6-FBG676`，默认使用 PDS 2022.2-SP6.4。V4.3 native SD DMA 位流
- V4.3 干净交付验证摘要（docs/CLEAN_VALIDATION_SUMMARY.md，仅存于 feature/nnue-gather-10ms 历史分支）
2026-09-20 已把当前 V4.3 生产位流通过 JTAG 下载到易失 CRAM，并用实体 J10 MicroSD
完成 `sdinfo`、`sdbench`、118,735,179 字节六文件 DMA 装载、Linux root shell 和完整
Pikafish GUI 启动。共享历史区、TT、PFF1/PFA1、16 个 MLP 层栈均到达完成 marker，
当前修复版 `constructor-ready` 为 38,112 ms；旧版在 `shared-pawn-clear-start` 超过
900 秒无进展的问题已消失。物理鼠标连续两次红方落子均触发 Pikafish 并得到黑方自动
回应；第一步 `h9g7`、653 nodes、55,372 ms。Stage A MMIO 显示 DONE、10 个输入项以及
匹配专用 scratch 的输入/权重/输出地址，确认搜索已实际提交硬件任务。该结果只覆盖这张
FAT32 SDHC 卡和当前两步走棋；实体 HDMI 完整视觉、全盘走棋、Esc/热拔卡/TFTP 故障回退、
其他卡兼容性、双目摄像头组合回归，以及 Linux HDMI
`clear`/物理 CH9350L Backspace 仍需验收。没有擦除或写入配置 Flash/SPI Flash。

## Stage B 阶段二合法局面验收

阶段二新增的是独立验收程序，还不是正式搜索接入。它从固定版本 Pikafish 的官方 NNUE
入口生成 16 个 layer-stack bucket、每个 bucket 红黑各一例的 32 个合法局面黄金向量，
逐项锁定 1024 字节 transformed features、32 路 FC0、PSQT、positional 和最终缩放评估。
宿主机 direct-view 路径必须与官方压缩模型 bit-exact；实体板路径必须真实提交每局 4 个
`256x32` MAC tile，共 128 个硬件任务，任何 CPU 冒充硬件成功、CRC 不匹配或 scratch
越界都会失败。

```powershell
.\scripts\build_pikafish_rv32.ps1
.\scripts\test_pikafish_stageb_phase2.ps1 -Distro pikafish-verify
.\scripts\make_rootfs.ps1 -IncludePikafish -ExternalPff1 -Distro pikafish-verify
.\scripts\serial_pikafish_stageb_phase2_accept.ps1 -PortName COM17
```

成功标志分别为 `PIKAFISH_STAGEB_PHASE2_HOST_PASS` 和
`PIKAFISH_STAGEB_PHASE2_BOARD_PASS`。只有这两个标志都出现，才能勾选“合法局面数据通路
验收”；它不表示 `Network::evaluate()` 的搜索调用点已经改用 Stage B。正式搜索接入、
共享 MAC 互斥/熔断、三模式回退、固定节点对拍和性能门槛仍保留为后续 TODO。

2026-09-21 的实体板结果为
`PIKAFISH_STAGEB_PHASE2_BOARD_PASS buckets=16 cases=32 jobs=128 fc0_lanes=1024
pfsb_crc32=0836b938 cycles=984136`，16 个 bucket 均报告 `hardware=1`，测试后 GUI 已恢复。

阶段三、四仍不生成或验证交付包，也不重建 `soc_linux.zip`。阶段三保留当时“不做全量回归”
的历史结论；阶段四按更新后的约束必须执行完整源码/rootfs 回归。每阶段完成后更新本 README
与对应 Stage B 方案/TODO，并形成独立 Git commit。

## Stage B 阶段三正式搜索接入验收

阶段三只替换官方 `NetworkArchitecture::propagate()` 内的 FC0：
`Network::evaluate()` 把当前 bucket 传入后端，每次执行 4 个 `U8xS8 -> I32` MAC job；
激活、FC1、FC2、skip 和最终缩放继续使用官方代码。`verify` 模式同时运行硬件 FC0 与官方
CPU FC0，逐 lane bit-exact 后仍提交 CPU 结果；任一差异只禁用 Stage B，MAC 硬件错误则由
共享运行时同时熔断 Stage A/Stage B。

```powershell
.\scripts\test_pikafish_stageb_phase3.ps1 -Distro pikafish-verify
.\scripts\make_rootfs.ps1 -IncludePikafish -ExternalPff1 -Distro pikafish-verify
.\scripts\test_pikafish_rootfs.ps1 -Distro pikafish-verify
.\scripts\prepare_sd_card.ps1 -Destination E:\ -Content Linux
.\scripts\serial_pikafish_stageb_phase3_accept.ps1 -PortName COM17
```

2026-09-21 主机验收通过 PFSB v2 正常路径以及截断、坏 payload CRC、坏 bucket、坏模型指纹
四类负向测试。PFSB payload CRC 为 `7261d3e8`，文件 SHA-256 为
`9707836b14e84c74e05921f0872ff2c17391e879a06f569c542f485c09834197`；GUI SHA-256 为
`873d0dfb743516808e3c0d2951062f4c39a184b045ffe270f097bc61d34aad48`。新 rootfs 为
8,185,344 字节，写入 E: 后逐文件回读一致。

同日实体板在真实 GUI 落子后输出：

```text
PIKAFISH_STAGEB_ACCEL_READY version=00020000 stacks=16 mlps_crc32=8c4b6711 pfsb_crc32=7261d3e8 model=2f6c8ed9 mode=verify
PIKAFISH_STAGEB_ACCEL_ACTIVE bucket=11 jobs=4 mode=verify total_jobs=4 cycles=31821
XQ LINUX PIKAFISH DIRECT BESTMOVE=...
PIKAFISH_STAGEB_PHASE3_BOARD_PASS mode=verify search=official-network
```

`DIRECT BESTMOVE` 只会在非空合法着法已成功应用到棋盘后输出。串口未出现 Stage B mismatch、
CPU fallback 或共享 MAC fuse。第二次 GUI 启动的 `stageb-prepare` 累计时间为 63,528 ms，存在
明显启动耗时波动；本阶段只证明正式搜索接入正确，不宣称 NPS 或端到端性能提升。阶段四继续做
固定节点开关对照、长搜索、故障注入和启动/搜索性能收敛。本阶段按约束未构建、未验证交付包，
也未重建 `soc_linux.zip`。

## Stage B 阶段四性能、驻留与故障验收

阶段四先增加独立测试程序，再修改生产实现：`pikafish_stageb_phase4_test.cpp` 覆盖三模式、
16 bucket bit-exact、8 线程并发、常驻复用和三类故障；`pikafish_stageb_phase4_search.cpp`
通过正式 `Network::evaluate()` 对三个固定局面比较 bestmove、ponder、score、WDL 和 nodes。
生产后端以带 CRC 的 64 字节 PFR4 stamp 绑定 PFSB/PFF1；stamp 和 16 个 stack 头匹配时直接
复用 593,920 字节常驻权重，不再做每次启动的全量复制和 DDR 逐字节回读。

宿主测试：

```powershell
.\scripts\test_pikafish_stageb_phase4.ps1 -Distro pikafish-verify
.\scripts\test_pikafish_stageb_phase4_search.ps1 -Distro pikafish-verify -Nodes 128
```

实板没有改 SD 卡。脚本用 XMODEM 把临时 ELF 放入 PFF1 保留区未使用尾部，再用 mmap helper
复制到 `/tmp`；验收后删除补丁并恢复原 GUI。需要重跑时先在一个终端等待 bootloader，再在
另一个终端只下载易失 CRAM：

```powershell
.\scripts\serial_pikafish_stageb_phase4_patch_accept.ps1 -PortName COM17 -Nodes 256 -WaitForBootloaderStart
.\scripts\program_cram.ps1
```

2026-09-21 实板三个 256-node 局面在 `0`、`verify`、`1` 下的搜索签名完全一致：CPU 合计
52,496 ms，verify 53,428 ms，硬件开启 43,112 ms，硬件路径比 CPU 缩短 17.9%，超过 10%
默认开启门槛。硬件模式执行 355 次 FC0、1,420 个 MAC job，`mismatches=0`、`fallbacks=0`；
第二次 prepare 报告 `resident=reused copied_bytes=0`。busy、error、timeout 分别在真实搜索中
触发共享运行时熔断，随后三个局面均以 CPU 完整回退并保持相同结果。生产默认
`PIKAFISH_STAGEB_ACCEL=1`，仍可显式设为 `verify` 或 `0`。

阶段四全量回归入口为：

```powershell
.\scripts\run_all_tests.ps1 -Distro pikafish-verify
```

2026-09-21 全量 WSL 回归已通过 `CPU_V2_ALL_TESTS_PASS`、`SOC_V3_ALL_TESTS_PASS`、
`PIKAFISH_ROOTFS_REGRESSION_PASS bytes=8189952 initrd_end=0x037cf800` 和
`PIKAFISH_STAGEB_PHASE4_FULL_REGRESSION_PASS`。

同日把上述生产 rootfs 写入 `E:` 并逐文件回读，`rootfs.cpio` 为 8,189,952 B、SHA-256
`cf8eb2cd3de3697259ce20d2d686c8fa3e5595b8cbdfc9c59bbec2e711becdab`。实体板从该卡装载
118,714,187 B，耗时 13,503 ms（8,585 KiB/s），Linux 在 113.639724 s 进入 root shell。
生产默认配置验收使用：

```powershell
.\scripts\serial_pikafish_stageb_phase4_sd_accept.ps1 -PortName COM17
```

脚本核对板上 GUI/PFSB 哈希及 `S95pikafish` 的默认 `PIKAFISH_STAGEB_ACCEL=1`，不显式覆盖
环境变量重新启动 GUI。真实红方落子后得到：

```text
PIKAFISH_STAGEB_ACCEL_READY ... mode=1 resident=reused copied_bytes=0
PIKAFISH_STAGEB_ACCEL_ACTIVE bucket=11 jobs=4 mode=1 total_jobs=4 cycles=29763
XQ LINUX PIKAFISH DIRECT BESTMOVE=h7e7 NODES=706 RED_WIN_PERMILLE=39
PIKAFISH_STAGEB_PHASE4_SD_BOARD_PASS mode=1 source=microsd
```

黑方着法已应用到 GUI；日志未出现 mismatch、CPU fallback、MAC fuse 或搜索失败。这一步
证明生产 SD 镜像确实以默认硬件模式调用正式搜索，不再只是临时补丁测试。未重写 sbit，
也未擦除或写入 SPI/configuration Flash。

整盘、多局面长时间 soak 仍作为后续可靠性 TODO，不阻塞已经通过的固定节点性能门槛。

## Stage B 阶段五生命周期、重开和持续搜索验收

阶段五先增加测试程序，再实现生产改动。`pikafish_stageb_phase5_test.cpp` 覆盖
PFSB 常驻镜像检查点、计数不变量、多轮 soak 和镜像损坏后永久 CPU 回退；
`pikafish_stageb_phase5_search.cpp` 使用正式 `Network::evaluate()` 覆盖八个局面、多轮
固定节点搜索、4,096-node 长搜索、带着法历史的终局以及新局重置时间上限。

GUI 引擎接口现在把每次搜索视为完整的 `FEN + moves` 快照。点击“重新开始”时，
不再同步调用 `Engine::search_clear()` 去重写 41,230,336 B 共享历史及其他搜索缓存；
改为复核 Stage B 常驻镜像、resident stamp 和 `jobs == evaluations * 4` 后立即返回。
TT 和着法排序历史作为按局面键匹配的暖缓存保留，不参与合法性或 NNUE 正确性判定。
进程首次启动仍会执行一次必要的内存分配和初始化；本阶段消除的是每次重开的
重复大内存清理，不声称消除首次构造。

宿主及全量回归命令为：

```powershell
.\scripts\test_pikafish_stageb_phase5.ps1 -Distro pikafish-verify
.\scripts\test_pikafish_stageb_phase5_search.ps1 -Distro pikafish-verify -Nodes 128 -LongNodes 4096 -Rounds 4 -ResetBudgetMilliseconds 250
.\scripts\run_all_tests.ps1 -Distro pikafish-verify
```

CPU、`verify`、`1` 三种模式的搜索签名全部一致，每次宿主逻辑重置约 11–12 ms，
低于 250 ms 门槛；加速模式最终为 1,985 次评估、7,940 个 MAC job，13 次检查点零失败。
全量回归通过 `PIKAFISH_STAGEB_PHASE5_FULL_REGRESSION_PASS`，重建 rootfs 为
8,194,048 B，`linux,initrd-end=0x037d0800`。

2026-09-21 首次 SD 验收真实暴露了问题：重开后旧路径进入 `worker-clear`，GUI 长时间
不能选子。上述快照重置重构完成后，新 rootfs 通过 `H:` 的六文件 SHA-256 回读：
其 SHA-256 为 `6b9b2c1fc6ca98c108f17f82ea72da0b3c3969dffec4c2fe45268bd0467712f8`，
GUI SHA-256 为 `00ad4d297796ab0229aa0e83ce46b74378b36f5e03b5739924e115112bbf200c`。
实板第一步返回 `g6g5` / 725 nodes，重开随即输出：

```text
PIKAFISH_STAGEB_CHECKPOINT_PASS checks=1 evaluations=370 jobs=1480 pfsb_crc32=7261d3e8
XQ LINUX ENGINE NEW GAME READY reset=position-snapshot tt=retained histories=retained checkpoint=pass elapsed_us=3068000
```

重置 marker 返回后红子可重新选中，第二步正常返回 `b9c7` / 641 nodes。最终统计为
580 次评估、2,320 个 MAC job、`fallbacks=0`、`mismatches=0`、
`checkpoints=1 checkpoint_failures=0`，并通过
`PIKAFISH_STAGEB_PHASE5_SD_BOARD_PASS mode=1 source=microsd checkpoint=healthy`。该轮只更新 SD 卡软件，
没有重写 sbit，也没有写 SPI/configuration Flash。

阶段五当前约束和 TODO：

- [x] 正式搜索、常驻镜像检查点、损坏后 CPU 回退、逻辑重置和重开后二次搜索已验收；
- [x] 阶段五软件全量回归和生产 SD 实板验收已通过；
- [x] 已完成跨线程/跨进程 Linux 调度第一阶段源码：`/dev/pango-mac0` 为每个 fd 分配
  私有 1 MiB shadow，并在内核串行提交单个 MAC job；RV32 内核和并发验收程序已构建；
- [x] 候选内核已从 MicroSD 实板启动；修正 shadow 为 `vmalloc_user()` 后，3 进程、每进程
  2 线程共 384 个不同输入的硬件 job 通过 `PANGO_MAC_SCHEDULER_TEST_PASS`；当前生产
  `linux/boot/Image` 仍未替换，旧 `/dev/mem` 程序不得与驱动客户端同时运行；
- [ ] 第二阶段需增加驻留权重/上下文代际，降低每 job shadow 复制开销；RTL IRQ 尚未接入
  CPU 中断控制器，因此第一阶段驱动仍是有界轮询；
- [ ] 持续数小时的整盘/多局面 soak 和频繁重开仍是可靠性 TODO；
- [ ] 如果需要严格的每局搜索可重现性，应增加异步/分块缓存代际策略，而不应恢复 GUI
  线程上的同步全量 `search_clear()`。

## YOLOv5n Stage 2 board acceptance (2026-09-29)

T0-T6 of [the Stage 2 checklist](docs/YOLOv5n_Stage2_TODO.md) have passed.
The [board evidence](docs/YOLOv5n_Stage2_Board_Evidence.md) records exact
bitstream, Linux image, DTB, rootfs and vector hashes. On the board, deterministic
1x1, 3x3 and 6x6 convolution outputs match CPU oracles byte for byte; 8 private
Linux MAC contexts, 384 jobs from concurrent clients, and the legacy Pikafish
Stage B golden test pass. A later production-format candidate automatically
started the GUI and passed the same convolution, scheduler and Pikafish tests;
the GUI survived a 60-second idle/reconnect check with six additional MAC jobs.

The DTS now reserves the CLINT MMIO range inside the advertised DDR span, and
the candidate rootfs skips the stock sysctl pipeline when there are no sysctl
configuration files. The driver remains the single owner of the physical MAC
engine. These tests use fixed, untrained vectors and do not establish model
accuracy or 30 fps. Full model integration follows
[the model integration TODO](docs/YOLOv5n_Model_Integration_TODO.md).

M0 model/data audit tooling is documented in the local model worktree
`vision/README.md`, which is outside this hardware delivery archive.
The earlier ROI 320 checkpoint matches the 14-class Detect metadata, but its
85/10-image random split has no independent validation data. M0 remains open
until new capture groups and board/FEN golden answers are frozen.

An exploratory 200-epoch ROI 320 checkpoint was trained from the archived
LabelMe images on a chronological 65/12/12 split. Its 12-image PC test reached
mAP@0.5 `0.37996`; the data still share one camera date, so this is not the M0
independent-set result. The candidate weight hash and preparation steps are in
[the model TODO](docs/YOLOv5n_Model_Integration_TODO.md).

The exploratory checkpoint's trained first convolution has now passed a
physical SD-card board probe. The board compared all 1,024 output bytes
against the CPU integer oracle and reported CRC32 c49864b6 and 38,139
compute cycles for a 16x16 input tile. The
[board evidence](docs/YOLOv5n_Trained_Conv_SD_Board_Evidence.md) records the
vector, bitstream, card-image hashes and JTAG/serial logs. This confirms
the Stage2 convolution path for layer 0; complete-model quantization,
the remaining 59 layers and independent FEN accuracy remain open.

The Stage 2 production files in `artifacts/` and `linux/boot/` match the
source and image hashes in the board evidence. The complete PDS database
reports `Design Summary : All Constraints Met.` Software reboot remains
unqualified; board loading used JTAG to volatile CRAM and serial XMODEM.
## GUI software move-injection interface

The complete Pikafish GUI exposes the Linux control FIFO
`/run/xiangqi-pikafish.in`. `S95pikafish start` creates it and the GUI reads it
without blocking. An injected move uses the same legality check, framebuffer
update, and real black-side Pikafish search path as a mouse move.

```sh
printf 'XQ_STATUS\n' > /run/xiangqi-pikafish.in
printf 'XQ_MOVE h2e2\n' > /run/xiangqi-pikafish.in
printf 'XQ_NEWGAME\n' > /run/xiangqi-pikafish.in
```

`XQ_MOVE` accepts a legal four-character ICCS move on the red turn. The GUI
prints `XQ LINUX INJECT MOVE_PASS` or `MOVE_FAIL`; successful moves include
`nodes`, `search_ms`, and end-to-end `total_ms` for automated latency tests.
For host/debug use, set `XQ_GUI_INPUT=-` to use standard input; Esc still exits.

With Linux and the GUI running on the board, repeat a fixed software-injected
move and save the raw serial transcript plus JSON measurements:

```powershell
python .\scripts\serial_gui_injection_latency.py --port COM17 --move h2e2 --trials 3 --skip-board-hash --stageb-ready-verified
```

The two flags above apply when the running board GUI hash and Stage B `mode=1`
activation were verified separately. Omit them for a fresh verification run;
that run checks the GUI/model hashes and requires an acceleration marker in
the trial. `search_ms` and `total_ms` are measured by the GUI; `host_ms`
also includes paced UART command transfer and console output.

On 2026-10-01, a real PG2L100H board booted from MicroSD with the production
CRAM bitstream. Its card contained an older GUI, so the current GUI was
reconstructed from a verified delta and installed only in the RAM rootfs.
The board's rebuilt GUI SHA256 was
`0a1d11ec3b920349d16cd65f820231a75a515a7dc4470635d511e28be6915d2e`.
The first `XQ_MOVE h2e2` printed `PIKAFISH_STAGEB_ACCEL_ACTIVE ... mode=1`
and reported `search_ms=31580`, `total_ms=31744`. Three further FIFO trials
after `XQ_NEWGAME` reported search times of 19688, 20768, and 27644 ms
(median 20768 ms), with total times of 19848, 20924, and 27808 ms
(median 20924 ms). `NEWGAME` retains the search tables, so these repeated
trials are warm runs. Raw board logs and JSON are under `build/gui_latency_retry/`.

The [search bottleneck probe](docs/Pikafish_Search_Bottleneck.md) measured
Stage B FC0 calls at 9.09% of five board searches and MAC execution at 0.48%.
After restoring JTAG volatile CRAM access, a test-only WSL-built GUI probe
measured NNUE feature transform at 21.944 s of a 32.728 s fresh search
(67.1%). A 16-call timer probe reduced search time to 11.484 s; adding a
quiescence timer probe reduced it to 2.464 s, but changed the selected move.
Neither timer probe is in the production GUI.
Hoisting four Stage A weight-row pointers in the software packer kept the
same 683-node, `b9c7` board result while reducing feature-transform time
from 21.944 to 19.532 s and search time from 32.728 to 30.328 s in one fresh
paired run. The [probe record](docs/Pikafish_Search_Bottleneck.md) gives the
test GUI hash and limits of this single-position comparison.

On 2026-10-01, a source-matched banked 2x4 convolution PE tile was built and
tested on PG2L100H through volatile JTAG CRAM. PDS reported all timing
constraints met at 37,414 LUT / 195 APM. The full first-layer board test
matched CRC `eb240272` and took 10,092,320 compute cycles versus 15,466,918
for the production scalar core (34.75% fewer cycles). The same candidate booted
MicroSD Linux to `/ #` and reached `XQ LINUX PIKAFISH READY`. This is a
spatial PE tile, not a clocked wavefront systolic array; the production
bitstream is unchanged. See the [array probe](docs/MAC_Conv_Array_Probe.md)
for hashes, timing, resource results, and board logs.

The [PFF1 Stage A gather prototype](docs/PFF1_StageA_Gather_Prototype.md)
adds an isolated, bit-exact RTL experiment for direct NNUE feature-row reads.
Board profiling found 7.248 s in generic-MAC weight packing during a 32.552 s
fresh 683-node search; CPU-only Stage A took 41.312 s. The prototype's
integrated map used 38,248 LUT, above the 37,500 LUT budget. Its SoC wiring
was reverted; it is not in the production bitstream or Linux runtime.
An isolated 128-byte row-major-to-MAC permutation now passes simulation using
only fixed wiring. A trial DMA mode passed SoC simulation but mapped to 37,898
LUT, above the budget, so it was reverted. The matching row-major software
packer is tested but not selected by the running GUI.
The [Stage A transform trial](docs/StageA_Transform_Optimization.md) rechecked
the row-major mode after the LUT savings: it mapped at 37,408 LUT, but left
only 92 LUT headroom and its RV32/QEMU packer was slower. The active
interleaved packer now uses aligned halfword reads and word stores; its
2,000-call RV32/QEMU microbenchmark improved from about 5.1 to 3.7 us/call.
The fixed board search still needs to be repeated with this software change.

A [MAC resource optimization](docs/MAC_DMA_LUT_Optimization.md) removed the
duplicate 1,024-bit weight and 1,536-bit bias staging registers and merged
the FP8 sign selection with two's-complement negation. The seed-2 SoC
candidate maps to 36,952 LUT / 29,610 FF / 195 APM, saving 462 LUT and
2,494 FF against the verified convolution baseline. PDS reports all timing
constraints met with +0.915 ns slow-corner setup WNS, and the full WSL
regression passes. Its earlier JTAG scans found no device at that time; the
production bitstream is unchanged.

The subsequent [bounded-count LUT trim](docs/MAC_DMA_LUT_Optimization.md)
narrows MAC loop state to the accepted 16-pixel/256-channel limits, replaces
wide DMA ceiling arithmetic, and folds the convolution window's modulo-6 row
index into a five-bit sum. The integrated interleaved-DMA map uses 36,726 LUT
and 29,488 FF, saving another 226 LUT and 122 FF. Boundary simulations and
the full `pikafish-verify` WSL regression pass with unchanged MAC cycles.
The source-matched seed-3 image meets all timing constraints (global slow-corner
setup WNS +0.927 ns) and passes volatile-CRAM board tests: first-layer CRC
`eb240272` in 10,092,565 compute cycles and dense MAC self-test in 279 cycles.
The row-major DMA trial also fits the LUT ceiling at 37,216 LUT, but remains
unselected because its RV32 software packer benchmark was slower.
The selected interleaved candidate also booted MicroSD Linux on the board,
probed `/dev/pango-mac0`, and ran the current GUI after a SHA-verified update
inside the RAM rootfs. A software-injected `h2e2` move activated Stage A and
Stage B hardware (`mode=1`); three subsequent warm searches had median
`search_ms=20692`, close to the previous same-GUI median of 20768 ms. The
[resource and board evidence](docs/MAC_DMA_LUT_Optimization.md) records the
candidate bitstream hash, boot conditions, and raw logs. The production
bitstream and MicroSD files were not replaced.

The next [timeout-counter LUT trim](docs/MAC_DMA_LUT_Optimization.md) sizes
the input DMA, weight DMA, and compact-writer timeout counters to the configured
100,000-cycle bound (17 bits). The source-matched seed-3 candidate maps to
36,693 LUT / 29,444 FF, saving 33 LUT and 44 FF over the board-tested
interleaved candidate. All timing constraints pass with +0.479 ns slow-corner
setup WNS. Focused DMA/compute tests and the SoC regression pass with unchanged
cycle counts; new tests check the exact 30-cycle write-response timeout and
the full 320x320 input DMA boundary (102,400 pixels in 217,602 cycles).
The full WSL regression stops at an existing rootfs file-size mismatch for
`pikafish-stageb-position-accept`. A fresh JTAG scan found no device, so this
candidate has not been board-tested and the production bitstream is unchanged.
An additional 18-bit input-pixel-counter trial mapped at 36,605 LUT, but its
seed-2/3/4 routed images violated DDR PHY setup timing; that RTL trial was
reverted.

On 2026-10-03, a Stage A word-load packing candidate passed exact x86/RV32
layout checks and the full `pikafish-verify` WSL regression. Five paired RV32
QEMU runs at GUI optimization flags reduced median packing time from 4.529 to
3.317 us/tile; this is not a board inference measurement. The rebuilt RV32 GUI
candidate in `build/nnue_ft/gui_wordpack_candidate` has SHA-256
`856fee5a12d289c3d4f07f449563eb3312e9129c67836dca7cae08d565452afb`;
the board-tested GUI artifact remains unchanged.
Six planned repeat
board trials could not start: COM17 had no output and a fresh JTAG Server saw
the USB cable but no FPGA device. The [Stage A trial record](docs/StageA_Transform_Optimization.md)
contains the phase baseline, hashes, and retry log. Board acceptance and the
10 ms latency target remain open.

## NNUE 10 ms 硬件优化候选（2026-10-04）

本轮在独立 `feature/nnue-gather-10ms` 工作树中接入流式 PFF1 gather 和内核常驻
Stage B 权重，同时合入现有语音音频接口与 GUI IPC。Stage A 直接从预装模型读取
特征行，四路 int16 累加，无新增 APM；描述符和累加器共用一块 DRM。旧 dense MAC、
YOLOv5n 卷积与语音协议继续保留。候选综合为 37,475 LUT、29,959 FF、195 APM、
154 DRM；37,500 是此前的优化预算，器件实际 LUT 容量是 66,600。

256 项 gather 在带等待的仿真中为 276,355 周期，49.5 MHz 下约 5.58 ms，
这是单次 Stage A 硬件时间。10 ms 目标按单次完整 NNUE evaluation 的平均时间验收，
包含两视角特征变换、PSQT、FC0/FC1/FC2，排除模型加载和局面初始化。它不等同于
整步棋的搜索时间。

候选内核、GUI、语音程序和完整 NNUE 计时程序已构建；rootfs/DTB 地址契约及载荷
哈希检查通过。当前 JTAG 扫描无设备，Windows 报 USB Port Reset Failed，实板
平均延迟及 10 ms 达标状态尚未取得。seed 1/2/3 候选的 DDR PHY 时序验收失败，
DDR 区域约束与多角优化候选也失败；多角基线 setup WNS=−1.275 ns、hold WHS=−0.661 ns。
进一步核对布线后的 `_perm` 名称及单元类型后，已生成当前映射对应的严格位置
约束。大范围固定试验遇到共享位置冲突；22 点固定槽位方案将 setup 改善到
−0.482 ns，但 hold 未通过。随后 274 点仅固定逻辑块方案完成最终报告及
274/274 实际位置核验，setup=−0.489 ns、hold=−0.525 ns，分别改善
0.786 ns / 0.136 ns，仍有 DDR 读数据、写使能和写 mask 路径违规。
继续针对写使能、mask 组合逻辑及读数据位调整后，298 点方案已在原约束下收敛：
最终慢/快角 setup=+0.384/+2.900 ns、hold=+0.141/+0.100 ns，
`All Constraints Met`，298/298 实际位置核验通过，构建和审计退出码为 0。
同一 RTL、49.5/125 MHz 频率、计算周期及综合资源保持不变，新增 LUT 为 0。
收敛后整机回归实际退出码为 0，15 项位置测试通过；通过候选位流位于
`build/nnue10ms/ddr_targeted_seed1_hold100_fpga/generate_bitstream/soc_v2_top.sbit`，
SHA-256 为 `2e032dfab7633f7c60b61d6cf761b1484bdb158c1be94ce1238d4ef3eb4a66bc`。
JTAG USB 异常仍在，实板兼容性和平均推理时间验收尚未完成。
候选内核按 4 KiB 分块恢复模型与拷贝卷积/dense 数据，并在块间提供调度机会，
减少语音线程被长拷贝阻塞。
布局布线和最终回归状态、构建命令、兼容性边界
见 [NNUE 10 ms 优化记录](docs/NNUE_10ms_Optimization.md)。生产镜像和交付包未替换。

## YOLOv5n 新数据训练与密集 MAC 分块试验（2026-10-05）

已用 `G:/fpga/数据集` 的 1,042 对图片/LabelMe 标注训练新的棋子 YOLOv5n。
保持 14 类顺序、320×320 输入、SiLU、九组 anchor 和 stride 8/16/32；
按序列划分 720 train、141 val、141 test，边界排除 40 帧。GPU 训练 200 epoch，
固定 320×320 FP32 验证的 val/test mAP@0.5 为 0.83427/0.62950，
test mAP@0.5:0.95 为 0.40993。采集批次独立性尚未证明，黑炮/黑马等类别仍需改进。
权重 SHA-256 为 `463b20a814b07ac5aa7da3f20a07a0202368cc3c1716ca52efa0555927958c9a`，
保存在 `build/vision/train_20261005/training_fullframe/run/weights/best.pt`。
训练、静态三原始头 ONNX 导出和数值对照详见
[训练记录](docs/YOLOv5n_Dataset_Training_20261005.md)。

现有卷积 ABI3 支持 Cin≤4、Cout≤16、K≤128，60 个卷积中仅首层形状能直接
提交，占卷积乘加量 8.4577%。为复用现有硬件，已实现密集 MAC ABI1 的
S8S8→INT32 分块路径：每作业最多 16 个输出像素、256 个 K 元素和 256 个
输出通道；CPU 展开窗口并合并部分和，最后只加一次 bias、做一次量化。

| 本轮验证 | 结果 |
|---|---|
| 真实权重层级试验 | 6 组、19 个作业，覆盖 K=1152、Cin=512、Cout=256/57 |
| 当前 SoC RTL | 37,954 个 INT32 部分和逐元素通过；C 后端最终 15,170 个 INT32/S8 输出一致 |
| 仿真 MAC 周期 | 646,929；按候选 49.5 MHz 折算 13.0693 ms，仅覆盖六个小特征块的 MAC 作业 |
| AXI 数据量 | 读 720,544 B、写 151,816 B；最大单作业暂存 90,112 B |
| 回归 | 35 项相关测试、原 MAC SoC 回归、MAC 调度及音频驱动检查通过 |
| 硬件与兼容接口 | 未修改 RTL/UAPI/内核/语音/Pikafish 代码，没有新增 LUT |
| 实板状态 | JTAG USB Port Reset Failed、扫描无设备；COM17/115200 三秒探测收 0 字节，实板平均耗时未知 |

严格设备程序只通过 `/dev/pango-mac0` 提交作业，没有 CPU 或 `/dev/mem`
回退。RV32IMA 静态程序及候选板测包位于 `build/vision/dense_tiled_20261005`，
其中 `dense_tiled_probe.tar` 包含程序、向量、清单与 `RUN.sh`。
分块试验提交为 `6920303`，复现和板端运行步骤见
[分块试验报告](docs/YOLOv5n_Dense_Tiled_Probe_20261005.md)，接口限制见
[加速器兼容性记录](docs/YOLOv5n_Accelerator_Compatibility.md)。

当前 `.pt/FP32 ONNX` 保留为模型参考，`device_model_ready=false`。
完整 W8A8 校准、SiLU/非卷积算子、整图运行时，以及语音/Pikafish 争用下的
实板性能仍待完成，进度见[模型接入 TODO](docs/YOLOv5n_Model_Integration_TODO.md)。
本轮结果未覆盖完整模型推理耗时；生产启动文件和交付包保持原有版本。

## YOLOv5n 30 fps 优化进展（2026-10-05）

已优化 dense MAC DMA 输出流水线，并修复 S16 最大作业的输出 bank 地址回绕。
同一组六个真实训练特征块、19 个作业的周期从 646,929 降至 613,721，降低
**5.13%**；37,954 个 INT32 结果及 DDR 字节数全部匹配。定向测试覆盖输出停顿、
尾通道、32 字节边界、错误返回及最大 S16 作业。随后压缩 DMA 实例的 S16
输出槽位，输出 SRAM 从 8,192×32 降到 4,096×32；默认裸核心布局及 Linux
输出格式保持一致，4,147 个正负整数结果和周期对照通过。

**尚未达到 30 fps。** 新增整帧统计及 26 种分块尺寸的 SoC 仿真：320×320 模型
每帧 523,033,600 MAC、6,956 次作业，设备侧 DDR 读/写约 76.8 MB；优化后的
卷积 DMA 周期按尺寸汇总约 **1,086 ms**，未含 CPU 打包、SiLU、后处理或共享
引擎竞争。这是仿真作业汇总，不是完整推理或实板帧率。

最终版本映射 37,475 LUT / 29,955 FF / 195 APM / 150 DRM，相比原 NNUE
基线不增加 LUT/DSP，节省 4 DRM；历史资源门槛通过。297、302 条 DDR 绑定的
候选最终时序失败，进一步增加写路径位置约束后的 **334 条候选四角时序通过**：
慢/快角 setup 为 +0.532/+3.032 ns，hold 为 +0.142/+0.101 ns，
`All Constraints Met`，334/334 实际布局位置核对通过，17 组时钟周期与参考一致。
候选位流位于 `build/vision/perf30_20261005/fpga_ddr_writepath/generate_bitstream/soc_v2_top.sbit`。
Linux/Pikafish/语音接口保持本轮开始时的版本，相关仿真与软件回归通过；
JTAG USB 仍报 Port Reset Failed。完整证据、适用范围及后续权重驻留/硬件展开
路线见 [30 fps 优化记录](docs/YOLOv5n_Perf30_DMA_20261005.md)。

18:53 按要求重新启动 PDS JTAG Server，65420 端口正常监听；再次扫描的 cable
list 仍为空，报 `JtagServer-0306: No devices detected`。COM17/115200 四秒探测
收 0 字节；未能加载候选 CRAM。记录在 `build/vision/perf30_20261005/jtag_retry_20261005_185258`。

新增同模型的权重精度诊断：全部 141 张测试图上，FP32、W8/FP32、W4/FP32
的 mAP50 分别为 0.62936、0.62959、0.30001。全 W4 损伤精度，暂不采用；
该诊断保留 FP32 激活，不能当作 W8A8 设备模型或板端性能验收。

独立 W8 双乘法原语使用厂商 APM 仿真模型，957,504 个 S8 乘积精确通过，
每有效拍计算两个乘积；PDS 映射为 1 APM、38 LUT、12 FF、0 DRM。
该原语尚未接入阵列，也没有物理时序或板测证据，不能据此宣称整机吞吐翻倍。

## 加速器性能与 LUT 优化（2026-10-06，候选）

密集 MAC 将下一 lane 的后处理准备与当前输出重叠；卷积激活缓存改为四个
单写端口银行。原生整机映射 **34,308 LUT / 28,932 FF / 195 APM / 150 DRM**，
相比上一候选减少 **3,167 LUT（8.45%）和 1,023 FF**，DSP 和块 RAM 数不变。
增加 LUT 的 one-hot 选择器实验已拒绝。

原 MAC 各模式/激活/格式的 64 作业差分、激活银行独立参考、卷积路径和完整
回归通过；使用匹配的 NNUE/语音启动候选，外部完整 Pikafish 搜索明确跳过。
同一组真实权重块的 19 作业由 613,721 降至 **576,996 周期（−5.98%）**，
37,954 个 INT32 结果和 DDR 字节相同；49.5 MHz 折算 **11.6565 ms** 仅适用
这组六个小特征块。26 种尺寸的卷积 DMA 加权预算从约 1,086 降至 **1,008 ms**，
未执行完整模型，**30 fps 尚未达到**。

最终严格约束物理实现与板端验收状态见[本次记录](docs/YOLOv5n_Perf_LUT_20261006.md)。
重启 JTAG server 后仍为空 cable list/USB 错误码 43，未运行板端作业；
生产位流和交付包尚未替换，M3d 保持未勾选。

## 上板重试与时序修复（2026-10-07）

再次启动 JTAG server 并扫描仍报 `JtagServer-0306`，USB 端口复位失败
（代码 43）；没有下载 CRAM 或运行板端作业，平均推理时间仍未知。
17:06/17:11 曾恢复扫描并核对 PG2L100H ID `0x00602899`，但下载会话
再次掉线，17:23 当前连接检查又报 USB 43；没有执行到 CRAM 编程。
10-06 候选的最终 DDR 慢角 setup 为 **−0.003 ns**，明确拒绝时序验收。
新增起点绑定的 333 条约束冷构建已完成，但慢角 setup/hold 为
**−1.794/−0.714 ns**，快角 hold **−0.768 ns**，同样拒绝验收及下载。
17 个时钟周期和原 332 条位置保持一致，不能由单点位置绑定推断整机时序改善。

同一模型的分块流量拆分显示权重读取占 **49.3%**，首层占卷积作业周期预算
**16.3%**；后续优先减少权重重复读取及改善首层小通道利用率。
详细证据及最终修复状态见[10-07 记录](docs/YOLOv5n_Board_Timing_20261007.md)。

## 可迁移 skills 与交付维护（2026-10-08）

五个技能分别覆盖加速器性能、FPGA 时序、模型兼容、软硬件协同和上板调试，
均为标准 `SKILL.md`＋调用元数据＋自包含参考，可独立复制或安装到其他工程。
入口先识别新工程器件、工具和 ABI，案例中的 Pango 路径/参数不是运行依赖。

```powershell
python skills/manage.py install
python skills/manage.py install --destination D:/other-project/.agents/skills
# 在工作区维护源更新经验后，同步本工程
python skills/manage.py workspace-sync --project .
```

后续会话可直接调用 `$accelerator-performance`、`$fpga-timing-optimization`、
`$accelerator-model-compatibility`、`$soc-hardware-software-codesign` 或
`$fpga-soc-board-debug`。完整安装/迁移说明见 [skills/README.md](skills/README.md)。
每次交付对照本次变更更新技能并刷新审阅清单；交付脚本自动同步可用的上级维护源，
没有维护源的独立包使用本地副本。所有完整包含技能文件和 `SKILLS_DELIVERY.json`，
与本包 README、AGENTS 和交付脚本哈希绑定，验证拒绝陈旧或混用内容。
本次仅修改知识库和工具，无硬件影响；M3d 的时序/板测门槛及生产包发布条件不变。

## CRAM 与候选 SD 实板测试（2026-10-09）

本次 USB/JTAG 已恢复正常枚举。10-05 四角时序通过的基线下载到易失 CRAM 成功，
DONE=1、DDR=ready、49.5 MHz；10-06/10-07 LUT 候选仍因时序违例未下载。
经读卡器更新并回读校验 E: 的三个启动文件，六文件与 `build/nnue10ms/image`
匹配；用户返卡后候选 Linux 成功启动，MAC 和音频设备均初始化。

载荷哈希、常驻模型/跨 fd 恢复、卷积整数结果、8 context 池及 384 作业调度通过。
NNUE 整数结果通过、无 fallback；但初测 jiffies 时钟校准失败：
`sleep 5` 的 host 时间为 8.25 秒，CLINT 记录 1.436778 秒时 Linux 仅记录 1.004 秒。
44.460/41.600 ms、独立 MAC 3.960/1.440 ms 等系统读数及倍率已撤回。
此前未独立校准的 GUI/search/profile 系统时间也需重测。

通过只读 CLINT 重测，10 个局面、各阶段排除 10 次预热后 200 次：

| 模式 | 冷缓存平均/ms | 热缓存平均/ms |
|---|---:|---:|
| CPU | 706.939 | 593.275 |
| 硬件并另做 CPU 校验 | 124.315 | 120.385 |
| 严格 gather＋常驻 FC0，其余 CPU | **64.799** | **61.935** |

范围是完整 NNUE evaluation，不含模型装载/FEN/黄金比对/UCI 搜索。
严格模式相对 CPU 为 10.910×/9.579×，无 fallback/fused/mismatch，整数结果通过。
gather ioctl 平均 17.951/16.058 ms，FC0 host 12.681/12.665 ms，其余 host
34.167/33.212 ms；硬件周期合计只折算为 2.692/2.383 ms，是上面时间的子集。
下一步优先细分其余 host，并减少提交、拷贝及 gather→FC0 数据往返；10 ms 未达到。

独立 window 和音频接口采集通过，但 NNUE 并发采集 320,000 样本出现 716 次溢出。
SCHED_FIFO 对照触发 RT throttling，溢出增至 176,800，不采用该方案。
语音兼容性未通过；输入恒为 −1，且缺识别权重；完整 YOLO 与 30 fps 尚未验收。

保留原 O3/LTO 参数的 CLINT 计时候选通过 QEMU 整数向量、rootfs 12 项载荷与 DTB 校验，
位于 `build/vision/board_candidate_20261009_004155/clint_image`。
rootfs 12,488,704 B，DTB 同步装载范围；该诊断镜像尚未写卡。
Linux 下 XMODEM 两次控制传输失败后，改用 bootloader `loadx` 到预留 DDR 空闲区。
校准程序 1,747 块 CRC 无重试，Linux 只读 mmap 回读哈希通过，板端测量已完成。
工程回归通过，外部完整搜索按参数跳过；QEMU 正确性/无隐式回退检查及 skills 15 项测试通过。
无需再次移卡。测试使用临时 `/tmp` 程序，没有替换生产位流或完整交付包；GUI 已重新启动。
详见[本次实板记录](docs/Board_Acceptance_20261009.md)。

## 最新 LUT 候选继续优化（2026-10-09）

保持 10-06 的流水线与激活银行，缩减卷积内部配置计算，并将输入 DMA 的
像素索引乘法改为递增地址。原生整机映射为 **34,206 LUT、28,934 FF、191 APM、150 DRM**；
相对最新版减少 102 LUT 和 4 APM，相对已上板的 10-05 基线减少 3,269 LUT（8.72%）。
公开 ABI、合法作业范围、输出与周期保持；未新增块 RAM。

843,296 项配置、12 组地址/1,490 tap、最大 320×320 图像、reset/abort、DMA 并发和
整机回归通过。真实权重块 19 作业仍为 576,996 周期，37,954 个 INT32 结果与
720,544/151,816 B 读写相同。完整冷构建全部时序满足，慢角 setup/hold
+0.862/+0.137 ns、快角 +3.081/+0.100 ns；331 条 DDR 实际位置和 17 个时钟已核对。
新候选已下载到易失 CRAM，DDR 正常并从现有 SD 启动 Linux。窗口四形状、真实权重
六块各三次共 57 作业、常驻模型 400 并发作业、ABI3、8 context 和 384 调度作业通过。
CLINT NNUE 冷/热均值 **65.458/61.042 ms**（每阶段 200 次），整数通过且无回退，
10 ms 未达。硬件计数仅为其中 2.693/2.405 ms，后续重点是主机计算和数据提交。
确认 GUI 完全退出后，音频单独 16,000 样本无溢出；与 NNUE 并发仍溢出 2,736 次。
音频功能对照的原时钟耗时无效，真实语音权重缺失、声音输入恒为 −1。
GUI 已恢复；完整语音兼容性、完整 YOLO 图和 30 fps 未通过，M3d 保持未勾选。
本轮仅更新候选源码/证据与完整 portable skills，不替换生产位流、SD 或完整 SoC 发布包。
详见[本轮 LUT 与板测记录](docs/YOLOv5n_LUT_Board_20261009.md)。

## Pikafish 分阶段瓶颈实测（2026-10-09）

同一最新版位流重新上板，现有 SD 启动；停止 GUI 并等待进程退出后，以只读 CLINT
测 10 个局面的完整 NNUE，每组冷/热各 200 次。原程序前后复测冷均值
**64.943/66.489 ms**、热均值 **61.542/62.365 ms**；4 组共 1,600 次正式评估整数一致，
无 fallback/fused/mismatch，10 ms 未达到。

诊断开启时，热评估中 gather 完整调用 **18.589 ms**、FC0 提交 **10.409 ms**，
特征索引 **7.934 ms**、CPU PSQT **6.724 ms**、Stage A 用户态输入/输出复制 **5.864 ms**；
FC1 **3.470 ms**。硬件作业仅为其中 **2.389 ms**，不能再次相加。
诊断开启比关闭增加 4.089 ms，诊断关闭与原程序也有约 4.5% 差异；不将剖析值缩放为原程序耗时。

13 种小作业各 50 次整数微测试通过。dense 4×1 仅 12 B 复制，硬件约 0.004 ms，
submit 仍为 1.929 ms；应先区分提交路径的 MMIO、复制、校验和等待，再评估批量或硬件
sequencer，以及 PSQT/accumulator 中间状态驻留。内核未启用 ftrace，差值不能全归为 memcpy。
8 项剖析验收测试及 RV32 QEMU 整数/计时闭合通过；GUI 已恢复，实际 STATUS 为 ready。
完整搜索及其中的增量 accumulator 分布本轮未测；语音/完整 YOLO 的待验收项继续保留。
详见[完整瓶颈记录](docs/Pikafish_Bottleneck_20261009.md)及对应 JSON。
