# 系统协同的具体边界

来源：性能工程 `docs/NNUE_10ms_Optimization.md`、
`linux/mac_accel/kernel/pango_mac.c`、`linux/mac_accel/pango_mac_uapi.h`、
`linux/pikafish/run_nnue10ms_board.sh` 与模型集成 TODO。

## 历史 Linux 候选

- `/dev/pango-mac0` 为唯一 owner；MMIO 从 0x1fe10000，gather 从 0x1fe10100。
  scratch 为 0x1b000000 的 1 MiB；PFF1 68,122,688 B 从 0x10000000 装载。
  这些是特定 DTS/UAPI 合同，不是所有版本固定地址。
- Stage A 1–256 描述符，先校验所有描述符再读模型/写结果，1024 个 little-endian
  S16 以模 65536 更新。Stage B fd 模型快照 593,920 B；scratch owner 切换后恢复。
  两种机制与 dense/conv ABI 保持共存，不能因声称 resident 而跳过实际恢复。
- PREEMPT_NONE 内核把 copy 分为 4 KiB 块，块间 `cond_resched()`；完整模型对应
  145 次 copy、144 个调度点，mutex 不释放。实际音频调度间隔和 overflow 未板测。
- FC0 四个 job 的输入是不同 256 项块，不能为降低 copy 时间误用相同输入。
- gather 超时仍有 BUSY 时拒绝新 scratch job，不能复位尚在传输的 AXI 再复用。

## 语音不是已有 MAC 使用者

当时语音为 INMP441/MAX98357A、512 样本 FIFO、`/dev/pango-audio0`、CPU int8
TDNN/CTC 和 Unix datagram GUI IPC；不调用 MAC。要保证的是 CPU 调度、音频 FIFO
和 DDR/GUI 系统资源共存，而非虚构已有“语音 MAC job”。日后硬件化需新能力验证。
同步 RAM FIFO 必须保留空队列转发、满队列同时 push/pop、overflow/清零行为。

## 匹配产物与严格验证

候选文件集中在 `build/nnue10ms/image`：Image、fw_jump.bin、rootfs.cpio、候选 DTS
和 DTB，以及匹配 GUI。生产 `linux/boot` 不因候选回归通过被覆盖。
10-06 完整回归使用这些匹配文件，但 `-SkipExternalPikafishSearch` 明确跳过完整
外部搜索；这只证明相应回归范围，不证明搜索或语音在板上兼容。

板端入口如 `run_nnue10ms_board.sh` 的严格 HW 开关、卷积/pool/scheduler 驗收程序，
都应从当前源码核对。默认 GUI 停止/恢复行为和模型哈希必须留证。独立 fd 的模型、
shadow 和输出正确性与物理执行锁串行化，需在不同数据的混合负载中共同检验。

## 2026-10-09 的部署与 owner 验证

旧 SD 能启动 GUI，但 `/dev/pango-audio0` 不存在。按候选目录一起更新
Image/rootfs/DTB，保留哈希已匹配的 OpenSBI/PFF1/PFA1，返卡后两种驱动才同时就绪。
生产目录固定的准备脚本不能用于部署另一候选。启动成功仍需检查 payload/UAPI。

本次常驻模型两个 fd、400 并发作业的不可变快照及覆盖后恢复通过，8 context 池与
3 进程×2 线程、384 作业调度通过。完整 NNUE 整数比对通过，10 ms 目标未达。
语音可执行文件已校验，但候选缺少 `/opt/xqvoice/xqvoice.xqv` 权重；采集驱动存在
与真实语音识别、GUI IPC、混合负载采样无丢失须分别提供证据。
这些记录不使当前时序失败的 LUT RTL 获得整机组合验收。

独立采集 16,000 样本零溢出；与严格 NNUE 并发采集 320,000 样本有 716 次溢出。
对探针加 SCHED_FIFO 优先级 1 反而触发 RT throttling，溢出 176,800；拒绝该方案。
512 样本/16 kHz FIFO 仅提供约 32 ms 服务预算，仍需排查唤醒、驱动服务和计算干扰。
这些仅是驱动并发探针；无识别权重、输入恒为 −1，不能作为真实语音兼容性通过。

## Git 快照与可迁移哈希

保存待验收候选分支时，README 分别列出已测范围与未完成目标；提交本身不使 TODO
通过。把匹配的候选位流、原生最终时序、有效约束和输入清单放在独立候选目录。
源码中的逐文件 SHA 与 Git 的自动换行转换可能冲突：技能库及其清单保留原字节，
关联的文档/脚本使用固定换行，再从 Git index 或实际检出副本验证包关联。硬件原始
构建输入 SHA 保留；若只因 CRLF/LF 不同，应另记换行归一后的 SHA，不能伪造字节一致。
源仓库快照与完整发布包的验收门槛分别按当前工程要求处理。

## CPU 替换的分层验收（2026-10-09）

导入远端 CPU 应固定提交和原始生成文件哈希，选择性接入 CPU/wrapper/中断控制，
保持当前卷积、gather、音频、驱动 UAPI 和内存保留区。先同频验证，再独立改变
CPU 时钟；不能用整个上游 SoC 覆盖现有已扩展的加速器。

本工程从 linux@80ca5eb 导出的 CPU V3.1 配置 supervisor=false。RTL 中虽有 Sv32
及 SupervisorCsr 模块，实际 MISA 无 S/U，地址直接透传。内部 CSR 读回接线为零
不能证明该 CSR 指令可访问；独立 SATP 程序先超时，安装异常处理后确认三次
访问均触发非法指令异常，mcause=2。旧 CPU 在同一程序中保留写入值。真实
指令测试确认现有 bootloader 和 CPU→MMIO→MAC→共享 DDR 可以工作，Linux 的
最小 S/U/SATP 门槛失败。DTS 中历史性的 Sv32 声明不能修复这些缺失。

比较 MAC 周期与整段测试程序周期时分别记录。16 个全 1 输入输出通道的测试可
证明该整数作业正确，不能代替 NNUE、卷积整图或语音的运行验收；模拟器墙钟也
不能当作板端推理时间。不同 CPU 的缓存写回/失效机制须分别验证，不能把一种
CPU 的 fence.i 缓存刷新假设直接当作另一种 CPU 的验收标准。

生成的 SystemVerilog 需要显式开启目标综合器的 SystemVerilog 模式。仿真器存在
语言处理缺陷时可在临时副本中做等价适配，记录原始与适配文件哈希、具体差异及
验收范围；FPGA 使用原始源文件，不能将适配模型的通过冒充最终硬件通过。

## 2026-10-14：跨时间片图推理的所有权

多作业图像推理需把冻结的输入帧、每层 DDR 张量、INT32 部分和及最终 FEN
都关联同一帧 ID/模型代次；作业可释放单物理 MAC 锁，张量生存期却要
跨作业保存，下一租户不得覆盖。新帧到达时明确丢弃、排队或取消，并
记录帧到结果的延迟与丢帧。共享 1 MiB MAC scratch 只保证单作业容量。
bootloader 摄像头 snapshot 不等于 Linux 帧所有权；当前 Linux 设备树尚未
声明该相机外设。按棋局变化触发完整帧可减少运行次数，不能把部分图
或跨帧像素拼接结果称为单帧黄金通过。来源：性能工程
`docs/Multi_Model_Resource_Plan.md` 与 `docs/OV5640_BOOTLOADER_CAMERA.md`；
这里只是接入方案，仍需真实相机、完整图和并发上板验证。

完整棋盘系统还须维护标定版本、整盘置信度、对局状态与执棋方，
区分“同一帧完整视觉结果”和“由上一状态与局部新证据更新的局面”。
遮挡、移机、照明跳变、非法跳变或置信度不足时转全盘复核/用户确认；
合法着法用于约束和拒绝，不能凭先前局面填补当前看不清的图像。
替代 YOLO 的逐格分类器需要新的空格/遮挡与整盘 FEN 黄金数据和
单独的设备验收清单。来源：性能工程
`docs/Chess_Vision_System_Options.md`；此处没有新的板端结果。

## 2026-10-14：Linux 用户态映射的访问宽度也是硬件 ABI

当 `/dev/mem` 直接映射 DDR uncached alias 给用户态 GUI 或模型
运行时，必须把实板已验证的访问宽度写入接口合同。本板该 alias
的子字写可令 CPU 停住；RGB565 像素应按两个半字合成 32 位写，
奇数边界用 32 位读改写保留邻像素，并对帧计数等待设上限。
主机 GUI 回归只能验证像素结果和超时行为，不能证明板端总线事务。
临时 rootfs 中的诊断程序应在同一 Linux 启动中分别记录官方模型
UCI、Stage B 文件哈希/合同和硬件黄金向量，避免 GUI 停顿遮蔽
加速器问题。来源：性能工程 `sw/video/video_fb.h`、
`linux/pikafish/xiangqi_fb_gui_linux.c` 与
`docs/Pikafish_Main_Integration_Candidate.md`；板上复测未完成。
## 2026-10-15: boot BRAM capacity and compiler portability

On the V3.5/Sv32 SoC, a newly built native RV32 GCC 16.2.0 produced a bootloader
that failed the 128 KiB BRAM linker's 16 KiB stack reserve by about 3.6 KiB.
Keep the official CoreMark units at `-O2` and preserve its printed floating
score. Bootloader-only LTO plus `-Os` for camera SD orchestration and FAT code
reduced the linked image to about 91 KiB while retaining `-O2` for camera,
CRC and PNG compute units. Check the final `__bss_end` and `__stack_top`, not
just the binary size; LTO may inline public command symbols that existing
map-based tests require, so retain such entry points explicitly and rerun
the full console/IO tests. A compiler of the same version with different
binary or libgcc hashes still needs a fresh firmware/PDS/board evidence chain.

MSYS2 MinGW GCC 16 can fail to link Verilator C++ compiled with `-Os` because
of a constructor symbol issue. The host-only `-fno-declone-ctor-dtor` flag
allows the model to build without changing RV32 firmware flags. Icarus 13
requires declarations before their first use in several Verilog modules;
moving declarations is a parser compatibility change, not a functional pass.

## 2026-10-15: reuse an unchanged SD card across a firmware/bitstream rebuild

When the changed payload is the SoC boot ROM inside an FPGA bitstream, keep the
existing SD card if its Linux, OpenSBI, DTB, model and auxiliary files have not
changed. Bind the rebuilt bootloader hash to a new frozen PDS snapshot and
bitstream, load only volatile CRAM, then verify every SD payload's board-side
CRC before testing the OS and accelerator. The card's presence or matching
file sizes alone do not prove its contents. A model constructor ready marker
precedes the GUI's final ready marker; collect the latter and an actual model
operation before claiming an end-to-end pass. A repeated boot with the old
known-good bitstream and the same card can distinguish a new build regression
from common runtime or board conditions, while one successful retry does not
erase a prior unexplained timeout.

## 2026-10-16: preserve Pikafish while adding camera segmentation

Keep the deployed PFF1 model and auxiliary table unchanged. Preserve Stage A
modulo-65536 accumulator semantics and Stage B U8S8 results, existing MMIO/UAPI,
weight capacity and model layout. Select YOLO S8S8/SiLU behavior explicitly;
never replace the shared engine's numerical rules globally. A model switch
must invalidate and restore all overwritten weights, bias, LUT, scratch and
mode state. Resolve direct-MMIO versus Linux-driver ownership before mixing
clients, and provide safe tile-boundary scheduling with measured NNUE wait.
Require official golden vectors, both model-switch directions, timeout/abort
recovery and actual legal moves on each matching candidate bitstream. Separate
exclusive vision throughput from simultaneous vision/search acceptance.
Source: main performance project's
`docs/YOLOv5n_Seg15_320_Implementation_Plan.md`; design review only.

## 2026-10-16: audit audio capture contracts before integrating recognition

Trace the actual RTL version and register behavior through DTS, kernel probe,
UAPI and userspace. An existing driver can require a FIFO that the integrated
RTL does not implement: AUD1 v1 retained only the newest sample, while its
Linux driver required v2 peek/POP/status/overrun registers and a 512-sample
FIFO. Check that the kernel builder copies the driver and header, enables its
config and compiles the current DTS; stale filenames can hide integration gaps.

Use synchronous-read RAM with explicit first-head and one-item push/pop
forwarding; test serial sample order, nondestructive peek, full/drop policy,
clear priority and recovery. Preserve unrelated I2S playback and model hardware.
Capture to memory before writing diagnostic WAV files, bind the ABI and reject
overrun. A 512-sample FIFO at 16 kHz covers 32 ms, not arbitrary Linux latency;
measure concurrent search, feature extraction and IPC stalls on the board.

Read model magic and runtime code rather than trusting historical filenames.
Current XQT1 pooled isolated-token classification (40 inputs) differs from an
older XQV1 TDNN/CTC path (220 inputs). Synthetic TTS weights and host IPC tests
do not establish real microphone accuracy or compatibility with a frozen GUI.
Preserve production payloads in a candidate rootfs, update initrd bounds and
loader size/CRC together, and require separate authorization for board writes.
Source: voice-hardware branch `docs/Voice_Hardware_Link_20261016.md`;
simulation/build evidence only, physical capture and ASR remain unaccepted.

## 2026-10-16: Recognition preview must be separate from game execution

A display-only integration needs both ends constrained: the recognizer emits
typed DISPLAY events for partial/complete/low-score/error states, and the GUI
maps legacy MOVE/RESTART/CANCEL/EXIT messages to preview acknowledgements too.
Do not rely on a producer flag while the GUI still dispatches chess actions.
Keep the preview handler free of board/mouse/engine parameters and check the
FEN, turn, node count and process lifetime before/after legacy message injection.
Low-score words remain labelled as candidates; the existing quantized-logit
margin is not a calibrated probability. Preserve their warning colour while a
new capture is in progress; clear old demo text when a fresh listener starts.

Use nonblocking best-effort preview send/reply and bounded stale-ACK draining;
waiting for GUI acknowledgement must not consume the 32 ms capture FIFO budget.
An unchanged physical engine and official model need no new FPGA build for a
Linux-only HUD change, but bind exact GUI/recognizer binaries and actual board
logs. RAM deployment and GUI socket/renderer evidence do not prove persistent
boot packaging, physical HDMI eye acceptance or real-speech accuracy.
Source: voice candidate docs/Voice_GUI_Display_20261016.md; board preview and
live low-score forwarding passed, independent recognition accuracy unaccepted.
# 软件构建入口与冻结硬件配方的边界

新增 Linux GUI 构建脚本若放进 `scripts/build_*`，可能被现有 FPGA
输入枚举器纳入冻结硬件配方，导致库存差异。先比较精确新增/修改项。
本例只有软件构建入口新增，已冻结 RTL、固件、约束和配方逐项哈希
相同；将脚本原样放到 `linux/pikafish/` 后完整工程审计恢复通过。
不通过改写冻结快照、缩减审计条件或伪造 PDS 重建记录消除该差异。

## 2026-10-16：专用Linux用户态SD录音候选

已有SDN2硬件但Linux无块驱动时，可在当前无内核owner的系统中复用原
native SD与FAT事务，作为专用用户态存卡候选，不宣称已提供通用mmcblk。
限定/dev/mem映射到一页SD MMIO，检查ID/版本/空闲，持有独占flock；
发现mmcblk拒绝，不能与将来的SD驱动并用。SD定时改用Linux monotonic
微秒，不把裸机mtime常量直接搬到用户态。未取得owner时退出不能abort
已有硬件作业。原bootloader源不改，VOICE命名空间单独派生并绑定来源SHA。

先采完整音频到RAM、检查零丢样，再写VOICE/WAV+JSON；数据多块写、元数据
回读、双文件CRC/簇链验证及最终发布保持原事务语义。CID/分区/卷标识与
四个原启动文件先核对，保存前后另读七启动文件CRC。成功后清理本次RAM
临时文件，错误时保留。共享启动卡仅新增VOICE文件，FAT新增分配元数据
正常变化；不保证写中拔卡/断电原子性，repair状态不继续写。

实板10秒/160000样本零丢样，首建目录存卡回读提交7296ms；不含采音、
UART控制及人工时间。原模型和GUI恢复分别确认，不能从无标签录音推导
识别准确率。专用工具RAM部署不代表持久启动或全MMC驱动验收。
来源：语音工程 docs/Voice_SD_Recording_20261016.md。

## 2026-10-17：CPU 单独提频要同步检查 SBI 定时换算

CPU TIME CSR 与 SYS CLINT MTIME 属于不同频率时，DTB 中的 timebase
只能解释 TIME，不能自动修正 SBI 写入 MTIMECMP 的截止值。PG2L V3.5
旧 OpenSBI 桥接写死 SYS/CPU=5/6，适用于 59.4/49.5 MHz；CPU74.25 MHz
而 SYS49.5 MHz 时必须改成 2/3。从冻结 PLL 分频推导精确有理数，避免
用舍入后的 MHz 做比例；保持全一禁用值、已过期事件和 64 位溢出处理。

先用旧算法复现新频率下的误差，再把实际 C helper 对独立整数参考做边界/
随机验证。候选 OpenSBI、DTB、临时引导器与位流分别绑定时钟和 SHA；
M 模式 CoreMark 保留原编译器/固件，不用 Linux 工具链替代。只读 SD
装载器可在 RAM 发布新 SBI/DTB，并核对实际频率和发布后 CRC，从而保留
启动卡文件；同时维护项目要求的缓存别名和内存屏障。主机数学、交叉编译
和 ELF 检查通过仍不代表 Linux 定时、MAC/音频或 GUI 已通过实板验收。
来源：performance_soc_voice_hw/linux/opensbi/README.md 和
docs/CPU_70MHz_Optimization_20261017.md；当前属于独立构建候选。


## 2026-10-16：批量采音时长必须贯通所有边界

提高长录音上限时，同时检查板端采音参数/缓冲、WAV写入器字节限制、
PC录音参数、导入解析器、GUI与启动参数，以及传输后的编码长度。
16kHz mono S16的60秒WAV是1,920,044字节，base64加换行可超过2.6MB；
旧2MB串口接收保护会截断合法录音，本例改为4MB有界接收。
单词分类器约2.015秒输入限制保持，长批录音需人工切成短词。
编译出60秒工具后必须实际调用该工具；根文件系统里的旧30秒程序
不能因PC放宽参数就视为支持60秒。RAM部署以独立路径和SHA绑定，
在暂停ASR或开始录音之前验证实际工具版本及哈希。
文件变长后还需调整板端哈希等待预算；采音零丢样不代表后续保存已完成。
本例60秒采音先通过，但长WAV哈希超出旧20秒等待；单独延长校验等待，
不要把控制超时误报为音频FIFO失败，也不要清理未成功存卡的RAM原文件。
来源：语音工程 docs/Voice_SD_Recording_20261016.md。
# 2026-10-18: separate CPU PLL and exact timer ratio

For a CPU with TIME=mcycle and a fixed SYS-domain CLINT, derive the timer
ratio from the actual CPU PLL VCO and integer output divisor. A dedicated
850.5 MHz / 12 = 70.875 MHz CPU with SYS=49.5 MHz needs 44/63; the shared
891 MHz divisor/18 shortcut no longer applies. Preserve legacy clock
profiles explicitly, bind hardware clock-source selection to configuration,
and rebuild OpenSBI/DTB/RAM-loader together. The actual C helper passed
33,872 integer-reference cases including sentinel, past deadline and
saturation; this is arithmetic evidence, not Linux scheduling acceptance.
Do not reuse a prior 74.25 MHz 2/3 boot loader with the new clock circuit.

## 2026-10-18：用户指定模型和优化方向时同步本地约束

本例用户明确后续象棋推理统一使用官方 Pikafish NNUE/PFF1，性能优先优化
Pikafish 和图像识别，不再将 H128 作为替代模型；远程仓库 AGENTS.md 不作为
本工程约束来源。将决定写入工作区和活动工程的本地 AGENTS.md，并明确与旧
H128 目标冲突时以新规则为准。此为本项目用户决定，不是其他工程的默认规则。

H128 sparse evaluator 与官方 Stage A gather、Stage B MAC/权重缓存分别列明：
历史引擎可以评估退役，不能因此误关目标模型所需硬件。仅写入约束不等于完成
硬件裁剪、模型更换、时序或板测。技术资料可供分析，不能把远程指令自动导入。
来源：performance_soc_voice_hw/AGENTS.md 的 2026-10-18 用户指定方向。

## 2026-10-18：可选硬件存在不代表驱动已接入

本例 gather MMIO 能读到正确 ID/version，旧 DTB 却只公开 0x100 寄存器和一个
scratch phandle。驱动明确要求至少 0x200 和第二个保留 PFF1 模型区引用，才
开放 RUN_STAGEA。修正 RAM DTB 后 GET_INFO features=0x67，独立黄金比对
1/3/256 terms 的全部 1024 lanes 及非法描述符无输出写入检查通过。
检查硬件 ID、DT 资源/保留区、feature、runtime 绑定和真实作业这五层，不只看日志。

PIKAFISH_MAC_BACKEND=mmio-shadow 会强制走旧 MMIO；REQUIRE_DRIVER 不会
自动消除此显式选择。严格驱动验证须取消该变量，确认 backend=driver 及
kernel resident 标记。gather 日志曾硬编码 backend=driver，不能单独作为证明。
同一系统 resident 两 fd 400 作业通过，而 3×2 调度失败，应分别记结果。
来源：语音工程 docs/CPU_70MHz_Board_Test_20261018.md；无新 RTL/PnR/SD 写入。

同次全新会话的 pool 8 上下文测试在 slot0 复用后发现存活映射哨兵不一致。
此路径完全不提交 MAC，先检查 shadow 页管理与 MMU/TLB/缓存可见性，再将调度
输出错误归给乘法阵列。双 fd resident 通过不足以证明所有 mmap/fork/回收组合。

## 2026-10-18：RAM 范围内的 MMIO 必须排除页分配

后续对照定位到 CLINT `0x02000000..0x0200ffff` 被 CPU 硬件解码为 MMIO，
却仍在 Linux `memory@0` 中且没有 reserved-memory。大块 shadow 分配可能落入
该窗口，出现首字哨兵为零、末字正确，即使完全没有提交 MAC RUN。
把所有 CPU/MMIO decode 范围与 DTS RAM 求交，在页分配器启用前排除交集；
本例新增 64 KiB no-map。核对原生 DTB、板上设备树及 `/proc/iomem` 的 Reserved。

固定 59.4 MHz 位流/内核/overlay，只改变 DTB，诊断从六处不匹配变为零；
原规模 8 上下文池、3×2×64 调度、双 fd 400 驻留作业及 gather 均通过。
同一修正也在 70.875 MHz 原位流通过这些测试。不能用缩小并发规模规避问题，
也不能据此删除原失败日志或声称新频率候选已验收。来源：语音工程
`docs/CPU_75MHz_Optimization_20261018.md` 和 `validation/cpu75-20261018/`。

## 2026-10-18：生成来源按字节绑定时保留真实换行

CPU 生成清单会绑定生成源和 RTL 的原始字节。Windows 工作区的 CRLF 文件经
`git archive` 提取可能变为 LF，因此提交相同也不能直接证明归档满足清单。
先要求 CPU 工作区干净且 `verify_generated.py check` 通过，记录提交和逐文件哈希，
按已验证的实际工作区字节打包；独立解包后重新检查生成绑定。比较模块时可明确
归一化换行，但不能用比较后的文本替换真实生成产物或补写清单哈希。
本例 CPU75 `0ef404e` 源码包已这样验证；源码包验证不代替板上或时序验收。

# 编译器身份与完整产物复现

CPU75 案例找到的本地 GCC 16.2 可执行文件哈希与冻结 manifest 不同；不能只凭
版本号宣称相同，也不能仅凭哈希不同断言产物无法复现。隔离目录按原优化/ISA/
libgcc/链接脚本完成整镜像构建后，ELF、BIN、ROM 实际逐字节一致，libgcc 相同，
17,752 字节栈通过 16 KiB 门槛。保留新旧编译器身份与比较证据，不重写冻结
manifest 来冒充原编译器；位流内固件仍按实际冻结字节验收。

## 2026-10-22：open清零也是实时服务路径

CPU80/PREEMPT_NONE、HZ250、512样本/16kHz的轮询采音只有32ms硬件FIFO余量。
MAC事务已有分块拷贝和cond_resched，不代表open路径安全：私有上下文1MiB整块
memset仍可能阻断服务。把清零也经4096字节块和调度点执行，保持pool_lock、in_use
及清零完成后才发布private_data；调度点不等于释放所有权锁。
主机测试提取实际open/clear回调，覆盖保护字、其他七上下文不变、忙池拒绝、0/1/
4095/4096/4097/1MiB及slot0/7。旧驱动失败、新驱动12用例通过。主机字节间隔上限
不是实测调度时延；必须在同位流、同内核配置、完整SD启动后验证。
同30d8f0d5位流，新内核3ed55853与相应CRC引导器替换，其他六启动文件不变。
两轮普通优先级卷积+官方StageB1024作业+resident400作业+6秒PCM均96,000样本、
零overflow；此前旧内核正常优先级1058/nice-10为435 overflow的失败日志保留。
这证明该混合测试范围，不代表声学/识别精度、任意实时负载或完整交付通过。
来源：performance_soc_voice_hw/build/cpu80-conv-sdboot-fix-20261022/board-repair/
audiofix-mixed-binding.json及audio-software/kernel-01/build.json；未新增PnR。

### 2026-10-25：短期参数驻留和评分输入回拷

CPU shadow→scratch参数复用必须显式能力协商/opt-in，按fd、不可变代次、参数布局匹配。
输入不得覆盖参数区；其他加锁入口、运行错误/超时、close和代次耗尽必须安全失效，代次不得回绕。
旧客户端frame_id继续回显，命中标记只用于opt-in请求；112/144字节UAPI保持。
Pikafish仅评分临时补入的恒等输入可省略回拷，真正排队的零更新仍发布快照，覆盖别名/指针复用/flush/新旧驱动。
跳过CPU回拷仍核对全硬件export计数；RTL不变时硬件DDR导出量不减。
detector参数区CPU复制少8923840B（61.6%）不代表整图流量或端到端倍率；两份评分恒等输入少8192B逻辑回拷。
验证配对内核、原模型和SD18/八文件；硬件源完全相同时复用位流/STA，明确未新跑PnR、FPGA资源增量0。
