# 版本记录

## Picture_new R29本地发布收尾 — 2026-11-01（平台2.1，不新增硬件版本）

- 保留用户指定R29，R35仅留撤回后的历史证据；完整SD仍为R21，板端未重连。
- 补齐原冻结R29直接需要的HWC布局、细化随机表和参数头；三份原生模型引用已有受控文件，避免重复存放。新增独立构建入口，输入逐文件身份与原冻结包一致；按用户要求不执行R29重建验证。
- 按完整清单获得确认后清理2035个缓存/普通编译中间文件及未完成SD草稿，约43.9MiB；已校验归档保留。原模型、ABI、旧包、私有证据、worktree与stash保持。
- 平台VERSION、CPU版本及运行时校验标记不改；本轮不刷写、不上板、不重跑硬件或模型检查。

## Picture_new 无板工程合并 — 2026-10-23（平台 V2.1，未发布）

- 完整接收r13–r17；默认标准v3d-QAT FP32，r14整数仅功能联调、待新局归因，负结果隔离。
- 合并main CPU80卷积身份，软件支持一MiB常驻快照、直接输入准备及精确子集灰度分派。
  当前80层不符合卷积ABI，仍走dense；不宣称加速或端到端达标。
- 离线逐层、整图、回放和宿主恢复验证及CPU80 PN02候选构建；本次未上板或安装。
  正常完整回归r7 PASS，696份执行源一致，MAC128例/22个复位相位通过。
  演示≤10秒豁免已授予，5秒/3秒仍是工程目标。详见
  [本次验证记录](docs/validation/picture-merge-20261023/README.md)。

## Picture_new 实验检查点 — 2026-10-20（平台 V2.1，未发布）

- 原生三模型、设备 80 层数值核验、离线回放与 GUI 严格拒绝链已接入。
  用户确认拍摄识别期间保留对弈页；完整回退、M5 和现场视听仍有待验项。
- 用户撤回第 3 局 77 条分类修正后，两原后端原始标签复测均 134/135，
  弱类 AP50 均 .995；整体 M0 未接受，旧评分与训练原件保持原样。
- 新实拍完成三模型但盘面校验拒绝，单次并行诊断 3292.131 秒；
  真实正确识别、3/5 秒时延、三局和挪盘验收尚未通过。
- 经授权通过 UART 安装 PN01 独立 SD 文件和常驻公共选择器，
  xqboot 后选 Picture_new 从 SD 启动；旧入口备份、其他分支载荷保留。
- 完整隔离回归 r06 通过（435 源、403 测试、52 Linux 输入），
  VERSION 仍 2.1；E8 只在易失 CRAM，未写 Flash，不新增 BoardRelease。
- 当前续接入口：[2026-10-20 检查点](docs/PICTURE_NEW_CHECKPOINT_20261020.md)。

## Picture 开发版本固化 — 2026-10-18（平台 V2.1，等待训练包）

- 固化当前 Picture 分支的源码、37 个 PCM 词片及验证证据，保持 VERSION=2.1；
  这是本地开发检查点，不是完整视觉模型发布。恢复入口见
  [续接说明](docs/PICTURE_CHECKPOINT_20261018.md)。
- P19 手动 SD 启动和完整 FIFO 桩回环通过；四次语音均成功，正文欠载
  0/1/0/0，默认 100% 音量经用户确认合适。全量回归 r17 绑定输入一致。
- P19 四次桩同步最大 4.999 秒，3 秒目标和真实推理后的最终性能仍待验收。
  相机在手动 xqboot 后、Linux 前预初始化作为当前启动设计，不再列为缺口。

## Picture 软件开发过程 — 2026-10-17（历史候选）

- 补齐 DTB 的 CLINT 64 KiB no-map，实板恢复 GUI 和串口；修复首帧 HOLD
  竞争、暗帧预热及复制循环误休眠。真实相机与官方引擎的桩回环通过，已保存
  20 对 PNG/JSON；真实模型验收仍待训练返包。
- 增加明确授权的 SD 新文件安装器，串口一次接收后核对 CID、尺寸和 CRC，
  两文件同扇区提交并读回；保留原启动文件，无 Flash 写入。部署状态见实板证据。
- P19 语音更新已持久写入 SD，默认音量按用户指定改为 100%；修复 musl 调度
  ENOSYS 空实现和 RT 限流，正文欠载容许值为每段 2 个样本，保留原计数与降级。
  P18 入口另备份为 P19XOLD，原装裸机的 P18XOLD 保留。
- P18 软件此前已持久写入 SD；备份旧 `xiangqi.bin` 后校验替换首簇装载器，复用
  固定 ROM `xqboot` 手动进入 Linux/GUI，启动阶段串口文件传输为零。
  零地址 `sdboot` 试验失败后已恢复原 `Image.mmode`，不改 ROM/位流。
- 相机单次整字读取同时写快照和普通 RAM，GUI 保留 RAM 画布并整字回写脏行。
  桩回环通过；四次 PC FIFO 同步为 5.056–5.141 秒，5 秒上限仍未通过。
- 补齐首拍/四角标定开发适配、R/C/Esc、冻结帧诊断与已知参照统计、退出
  提示帧、中文着法及 37 个 PCM 词片；9 组 C 主机检查通过，板端验收待完成。
- 增加 CMOS2 Linux 整字快照、快照区候选 DTB、RAM SD 装载器预初始化入口及
  PNG/JSON 调试工具；当前冻结位流与历史发布二进制未覆盖。
- 冻结识别 ABI，增加显式文件桩、受限 HID 空格输入、GUI 全重画、黑方摆子
  提示和 L1/L2/L3；主机模拟覆盖通过，不代表真实模型/板测或延迟通过。
- 增加训练包只读拒绝门禁、候选构建/组装工具和 Linux 跨机器源码交接包。
  本机 WSL 已完成 RV32 Linux GUI/采集程序编译；恢复 Python 3.14.4，
  补建原生 GCC 16.2.0 LTO 并实际验证跨文件优化；仿真辅助脚本适配 ucrt64
  安装并保留路径/选项/哈希门禁，隔离完整回归取得 SOC_ALL_TESTS_PASS。
  详见[候选说明](docs/PICTURE_INPUT.md)。

## V2.1 — 2026-10-13，添加 sdboot/coremark MHz/Esc 退出，Linux 启动失败
- `sdboot` 从 SD 卡加载 `Image.mmode` + `mmode.dtb` 到 0x0/0x1a000000，
  直接跳转 NOMMU M-mode 内核（不经 OpenSBI）；实板验证加载正确，但内核
  启动后静默——CPU V3.5（M-mode only，无 S-mode/Sv32）与 Linux NOMMU
  内核存在兼容性问题，非软件可修。
- `coremark` 命令新增 CoreMark/MHz 打印（实测 5.278 @ 63.642857 MHz），
  通过 port 层 printf 拦截迭代数，不修改官方 CoreMark 源码。
- 象棋程序（`xqboot` 启动后）支持 UART Esc 键退出，返回 bootloader。
- 修复 CoreMark/MHz uint64 溢出（两步除法）和 seed4_volatile 为 0 的问题。
- 版本标记字符串从启动横幅移至 `help` 命令；VERSION 更新为 2.1。
- 位流 SHA-256 `e2e484c52cdb2c71...`；LUT 49,076 / DRM 140.0 / STA PASS。

## V2.0 — 2026-10-11，整合 NNUE 象棋加速并完成实板验收

- 整合 `feature/nnue-gather-10ms`（ee4afcd）到 V6.5 平台线：MAC 窗口扩至
  0x1fe10000..0x1fe1_01ff，PFF1 Stage A gather（0x1fe10100）启用，
  YOLO conv 前端 ENABLE_CONV=0 门控（首次布线发散后的平台决策）。
- VexRiscv/cpu_v2 包装移除，CPU 保持 CoreTop V3.5 导入（e698e3bb）。
- bootloader 新增 `xqboot`（从 MicroSD FAT 只读加载 xiangqi.bin + xqmodel.bin）。
- 新增原生构建脚本（xiangqi_sd、pf_ft_stage_a、pf_mlp_stage_b）。
- 板上发现并修复平台限制：单字节/半字未缓存写（0x9B00xxxx）挂死 CPU，
  软件改为全字暂存拷贝。
- PnR attempt 4（run e5133861）全门禁 PASS：LUT 49,076 / FF 35,517 /
  LUTRAM 4,434 / DRM 140.0，routed STA "All Constraints Met"。
- 实板验收：FPGA 稀疏 NNUE 评估（EVAL=SPARSE-HW16），Stage A 78/78、
  Stage B 61/61 板上 PASS，20 步完整对局全部独立合法性校验通过。
- CoreMark/MHz 实测 5.242592（3+1 组，63.642857 MHz）。
- NNUE 10 ms 目标未达标；定义的 Linux 基准在本 M-mode CPU 上不可执行。
- Linux 启动尝试失败（OpenSBI 静默挂死，M-mode CPU 无 S-mode）。
- 位流 soc_top.sbit sha256 6c079c42...；SD 卡 xiangqi.bin 已更新为 v2 版。

## V6.5 — 2026-10-09，本轮集成板测验收通过

- 导入 CPU C1 实现 `e698e3bb78947fd4f7a0b5095e1cdc85a81e4502`：ROB 写入控制隔离、
  哈希后备 BTB64、ALU 保留站4项，保持原流水级数；CPU整核与初轮SoC短测通过。
- 为CPU微架构候选建立24小时/6次完整PnR预算，包括59.4 MHz同频和最终冻结构建。
- 时钟生成/校验扩展至合法div12..18；高频候选收紧CDC约束，新增完整STA范围比对。
- 发布增加显式BoardRelease清单：本轮短RTL、板测3+1、同频对照、CRAM/固件/位流/
  源码/快照/STA绑定及动态iterations CRC校验；保留旧证据与原验收模式。
- 串口采集保存三次performance的均值、中位数和范围；CRAM记录自动绑定本轮输入。
- run738（SoC 0b771）以63.642857 MHz完成完整PnR和双角STA：CPU slow/fast setup
  +1.426/+6.716 ns、hold +0.020/+0.014 ns，49,247 LUT/37,933 FF/4,530 LUTRAM/140 DRM；
  187条外部I/O基线缺口仍披露。仅为物理PASS、板测待验，不验收后续修改。
- run906的59.4 MHz控制因UART SYS hold三端点−0.027/−0.026 ns失败。e97aa4bb
  在TX FIFO四位写地址加入两颗双输出恒等LUT，不改变周期/数据/吞吐；增加绑定同轮
  VM、RTL和检查器的ADS合同与普通/厂商模型对照回归。04:55北京时间的历史检查点
  为控制实现0618c866完整RTL PASS（496.400秒、338 source/193 test、355项Git输入证明），
  当时预算2/6；后续run8ad在ADS检查器解析处失败，未启动PnR，原记录保留。
- 1720e40b修正实际ADS指针Q网别名解析，保持四FF、两LUT、四LUTRAM及逐位连接门槛。
  div13实现603d7ae7与seed5控制实现4b4f4637均完成新全RTL回归（338 source/194 test）。
  runaefd在第3次PnR路由超时；第4次run75f8以59.4 MHz完成物理PASS：CPU slow/fast
  setup +1.784/+7.577 ns、hold +0.030/+0.019 ns，SYS域hold +0.212/+0.150 ns；
  LUT49,284/FF37,933/LUTRAM4,530/DRM140。187条既有外部I/O缺口仍披露；该构建后续同频板测通过，见下文。
- 最终候选实现7ad9f204的div14/seed5完成第5次PnR，run838e完整物理PASS：CPU
  63.642857 MHz，slow/fast setup +1.336/+6.645 ns、hold +0.022/+0.017 ns，SYS hold
  +0.173/+0.132 ns；同轮ADS资源49,332 LUT/37,933 FF/4,530 LUTRAM/140 DRM。
  18时钟/116双角摘要与CDC门禁通过，187条既有外部I/O范围缺口保留。新十次短测及
  完整RTL回归PASS（335.884秒、338 source/194 test），355项冻结/Git输入与最终产物匹配。
  [终态证据与账本](docs/validation/v6_5-development-20261008/README.md)记录5/6，第6次未使用。
- 连接恢复后重新核实 COM5/CP210x 与唯一 PG2L100H（ID 0x00602899），实际加载易失
  CRAM。59.4 MHz 对照三次均值312.9670395559131 CoreMark / 5.268805379729176
  CoreMark/MHz（+3.91817199%）；最终63.642857 MHz三次均值334.9132273618522 /
  5.262385177991809（+3.79154449%），validation独立通过。两种频率的DDR/MAC自测与
  串口均通过，无Flash/SD写入；[全部原始数据及边界](docs/validation/v6_5-board-results-20261009/README.md)。
- 最终每次6000迭代、约17.9秒；官方CRC oracle按实际模式/迭代数验证，BoardRelease
  已通过。保留性能测试前两次编排失败和一次主机Python兼容性失败，没有排除有效分数。
  63.642857 MHz是本轮最高完整验证频率，不是物理极限；Linux/全外设未新增验收。
- CPU实现仍为e698e3b，文档交付提交不改变导入身份；没有独立CPU平台V3.5新正式成绩。
  正式包/最终commit/tag由后续交付校验记录，保留先前候选包与旧发布历史。

## V6.1 — CPU V3.1 双时钟集成

- 当前源路径统一为 `src/cpu` → `rtl/cpu`；顶层、CLINT、PDS 工程、DTS/DTB、脚本和交付包使用 `soc_top`、`cpu_top`、`soc.dtb` 与 `SOC_linux_V6.1.zip`。`SYS_ID`、`CAPS`、地址和外设命令保持稳定。旧 V6.0 tag、报告和短时分数保留原身份。
- CPU CoreTop/缓存/mcycle 在 CPU 时钟域；AXI 五通道经异步 FIFO 进入固定 49.5 MHz SYS 域，CLINT mtime、BRAM 与外设留在 SYS 域，中断电平同步回 CPU。SYS 窗口新增 `CPU_HZ +0x14` 与 `TIMEBASE_HZ +0x18`；配置与 RTL/PLL/FDC/固件/DTS 由 `config/clocks.json` 核对。
- bootloader、rootfs 与 DTS/DTB 已按当前源码重建。GCC 16.2.0 的完整编译/链接 argv、输入 SHA、libgcc 身份及严格 16 KiB 栈门禁记录在 `artifacts/bootloader.build.json`；CPU 生成 RTL 绑定真实实现提交 `dea0200205a1191964e50723e6dc3951617cf5bf`。主树 div15 以 CPU 59.4 MHz、SYS/TIMEBASE 49.5 MHz 完成同轮全量 PDS 和双角最终 STA；更高的 div14（63.642857 MHz）候选最终 CPU slow setup 失败。59.4 MHz 是本次已测试 18→14 范围内最高完整 STA PASS。
- 2026-10-08 补充[实板 CoreMark 3+1 证据](docs/validation/v6_1-board-coremark-20261008/README.md)：CPU/SYS/TIMEBASE 报告为 59.4/49.5/49.5 MHz，三次性能加一次验证均为 4000 迭代、超过 13 秒且 CRC/PASS 检查通过；性能均值 301.166806 CoreMark、**5.070148251 CoreMark/MHz**。记录串口原始输出、计算及镜像身份边界；未修改 RTL、固件或位流，也未搜索实板最高频率。
- 2026-10-05 按用户选择交付的 RTL 十次迭代短测保留为历史：[原始证据](docs/validation/v6_1-short-pilot/release_evidence.json)中性能种子 0.033504242 秒、估值 5.024741828764838 CoreMark/MHz；验证种子 0.033538525 秒、估值 5.019605575456619 CoreMark/MHz。短测固件与 ROM 单独编译，和位流中生产 bootloader/ROM 不同，成绩不满足十秒门槛。正式 3+1 Long 仿真当时已按用户要求停止，未产生四例正式 RTL 结果；后续板测独立记录。
- 当前 Markdown 是权威说明，`scripts/export_release_docx.py` 再生成同名 DOCX 和源文件 SHA 记录。板测范围为串口 CoreMark；Linux 启动和新组合其他外设实板验收未进行。

## V6.0 离线发布 — 集成 CPU V3

- CPU 改为 src 仓库维护的 Chisel CPU V3；统一 RV32IMA，完整编译参数为
  `-march=rv32ima_zicsr_zifencei -mabi=ilp32`，CoreMark 使用 `-O2`。
- 选择真实 `riscv32-unknown-elf` GCC 16.2.0；按完整镜像容量、CRC 和归一性能比较，
  优于已测试的 GCC 14.2/O2。当前 b73 CPU 的生产 console RTL 十次短测为
  1,988,892 ticks / 0.040180 CPU 秒，折算 5.027925 CoreMark/MHz；官方端口因不足十秒
  正确拒绝其正式成绩。早期 CPU 的 5.079685/MHz 是独立历史短测，不作为 V6.0 分数。
- 同步脚本核对 CPU RTL 与初始化文件；保留兼容顶层、AXI 接口、CLINT 和稳定 MMIO ABI。
- 保留可按键取消的 Flash 裸机自动启动；无有效自动启动镜像时进入 console。
  保留 debug/外设命令及手工 Linux 启动命令，Linux 启动未测试。
- 当前 CPU/AXI/系统时钟为 49.5 MHz；同一 b73 CPU/ROM/固件输入快照已完成全量布线，
  最终 slow/fast 双角 STA 全部通过，匹配的位流和构建证据随版本交付。
  55.6875 MHz 整机最终 STA 因独立 125 MHz DDR PHY setup 最差 −0.456 ns 失败；
  56.571428571 MHz 尝试依用户要求中止，未取得最终 STA。最高频率尚未测明。
  本轮无法接板；生产 bootloader console、真实 CPU RTL、逐周期 CLINT 的三次性能
  加一次验证种子各 ≥10 秒仿真尚未完成，因此不报告正式 CoreMark 成绩。
  不宣称外设上板通过或 Linux 启动。
- `.pds`、固件源码、编译参数和复现说明保留在 Git；生成数据库不作为工程输入。
- MAC bias 使用 LUT RAM；当前以 768 个双输出恒等 LUT 缓冲全部 1536 位写数据，
  保持容量、周期、复位及 CPU/ROM/时钟不变。实际独立 bank 为 1542 LUT、1536 FF、768 LUT RAM，
  比上一轮每位单 LUT 的方案少 768 LUT。新 ADS 逐位连接、原 512 周期已知输入二态功能、
  普通 MAC RTL 集成 `161/1211` 均通过，见 [当前分项证据](docs/validation/mac-bias-dual-bank/README.md)。
  [两位物理试验](docs/validation/mac-bias-pad-probe-v3/README.md)通过。[整机 PDS 构建](docs/validation/full_pds_gcc16_mac_dual/result.json)
  完成全部布线，但最终 DDR setup 最差 −1.000 ns、CPU I-cache hold 最差 −0.028/−0.016 ns，
  该旧 CPU 轮因时序失败未推广位流；失败记录保持原状。
  旧 Icarus 超时及 Verilator 验证记录独立保留，不宣称四态等价。
- 上一轮每位单 LUT 的[完整 PDS 构建](docs/validation/full_pds_gcc16_mac_pad/result.json)
  报 `Route-0008: Design cannot be routed`，最后 8 条连线未布通；未进入正式 STA，非超时。
  综合与逻辑检查通过不作为时序通过证明；该轮未推广位流，当时的 V5.4 产物不能用于 CPU V3 验收。
- GUI/Tcl 统一 DRM 预算；布局前检查实际资源及 CPU 控制逻辑，
  完整构建继续检查最终时序与输入/产物绑定。
- GUI/Tcl 采用 performance 模式与正 100 ps 的普通 hold 修复目标；保留原 FDC 时钟、
  多周期和不确定度约束，实际时序结果见 Validation，不以设置本身判定通过。
- 补齐 DDR IP 官方两条优先布线约束，纳入 GUI/Tcl、源码交付与实际注册证据门禁。
  该阶段 CPU、固件与时序约束保持不变；旧 CPU 双输出方案的正式 STA 仍有 DDR 路径违例。
- 据双输出方案的正式 STA，对三条单负载 DDR 数据网追加候选优先布线约束，
  同时要求 PDS 逐条报告五条约束执行成功；原 FDC、时钟和多周期条件不变。
  与 src 规范源码中的 ICache 低 128 位共享写缓冲一同进入 b73 完整构建；不能把改善单独归因于 RCF。
- 此前 49.5 MHz [b73 正常完整构建](docs/validation/full_pds_b73_normal_pass/result.json)退出 0，
  305 次详细布线、1538.95 秒工具计时，最终 slow/fast STA 及主机证据门禁通过，
  20 项匹配的候选产物已推广并通过工程审计。此前 [b73 主机证据失败](docs/validation/full_pds_b73_sta_host_gate_fail/result.json)
  保留 `BUILD_OR_GATE_FAIL`，不追认旧轮成功。
  同轮 MAC 768 对物理实例/端口声明及全局 STA 复核通过；ICache 仍为 `INCOMPLETE_UNSUPPORTED_EXPORT`，
  物理 INIT、逐位连接及无旁路尚不能从工具文本证明，见 [Validation](docs/Validation.md)。
  该次推广的 49.5 MHz 产物现为 V6.0 离线交付物；未上板、未测最高频率，
  也没有十秒 CoreMark 正式成绩。

## V5.4 — CMOS2 PNG 保存到共用 SD 卡

- 新增 `debug camera_sd`，Space 复用完整帧锁定/独立快照，取景继续。
- 原生 SDHC 4-bit CMD25 多块数据写入、ACMD23、双块发布/归还、CMD12/CMD13 确认；元数据仍用 CMD24 回读验证。
- 合并 RGB 展开与 Adler 计算、字访问及 CRC 热点优化，保留原始 PNG 像素与完整回读校验。
- 独立 FAT32 相机事务，临时文件、完整回读 CRC、同名 JSON、编号不覆盖旧文件。
- HDMI 左上角独立 HUD 显示保存进度/成功/错误，原始像素无文字。
- 有界 Esc 清理、故障后重拍、卡 CID 检查；新增只读 `sdverify` 与 Windows 图片校验脚本。
- 保留 UDP camera、speaker、键鼠与 Linux 启动；不开发麦克风新功能。
- Git 与交付包保留相对路径的真实 `.pds` GUI 工程，补齐准备/隔离打开校验；移除自动生成的 CPU 测试 HEX。
- 共享启动卡不保证任意突然断电/拔卡安全，可能需要 FAT 修复；证据见 Validation。
- 本次 CMD25 位流经实板易失 CRAM 验证，实体 SD 连拍、忙提示、Esc 取消及重拍通过；同位流三张完整保存均值 SD 5.822 秒、电脑 UDP 8.013 秒。六张 SD PNG/JSON 已只读导出并逐像素校验；共用卡 Linux 启动与用户人工视觉验收状态见 Validation。

## V5.3 — 清理与 CMOS2 空格拍照

- `debug camera` 支持物理串口与 CH9350L 空格拍摄当前 HDMI 显示的完整 CMOS2 帧。
- 硬件锁定双缓冲中的完整帧，bootloader 复制到独立 DDR 快照区后恢复取景。
- 独立 UDP 分块、CRC32、有限重传和保存确认；Windows 保存原尺寸 PNG 与基础 JSON。
- 合并重复文档，删除旧架构说明、原始调试日志和生成数据库；构建与交付清单从源码生成。
- 发布与运行标识更新为 V5.3，系统 ABI、Linux 启动文件和已有外设命令保持兼容。

## 历史基线

- V5.0：统一 `debug` 外设命令，音频监控与扬声器播放。
- V4.7：CoreMark；V4.6：HDMI 控制台方向键与行清除；V4.5：I2S 音频。
- V4.2：原生 4-bit MicroSD 只读启动；V3：Linux、键鼠、显示和加速器集成。

详细历史源码、日志摘要与旧位流哈希可通过 Git 历史查阅。当前证据只在
[Validation.md](docs/Validation.md) 维护，不以历史验收代替当前版本验收。
