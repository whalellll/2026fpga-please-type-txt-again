# JTAG / 启动调试经验

## 2026-10-15：引擎核心就绪后的 GUI 停顿要对照线程等待

同卡六个载荷 CRC、S 模式 Linux、官方模型及加速器初始化通过后，
GUI 仍可能在引擎 `DIRECT CORE READY` 后超过 420 秒不就绪，
串口 shell 也无响应。旧位流在相同位置也曾延迟约 167 秒，
因此不能只凭新位流接近零的 CPU hold 余量判定硬件为根因。
该 GUI 的异步引擎状态查询原先在输入轮询里调用线程 `join()`；
状态读取必须保持非阻塞，完整发布 Engine 后用 acquire 读取 READY，
并在退出时回收线程。主机和 RV32 回归只能验证构建与 ABI，
更新 rootfs 后仍须同卡板测确认启动稳定性和硬件走棋。
Linux LiteUART 上直接用大块 raw/base64 串口写文件会丢字节；
应先用小文件做回读 SHA-256，失败时改用经逐项回读校验的 microSD，
绝不运行部分传输的二进制。来源：性能工程
`docs/Pikafish_Main_Integration_Candidate.md`。

## 2026-10-15：下载线复扫与板上 CoreMark 的证据边界

Windows 仅按友好名称过滤 PnP 设备时，可能只看到 CP210x COM17，
却漏掉 D2XX 驱动管理的 PANGO 下载线。本轮 PDS 原生单会话扫描确实发现
`USB Cable II`、唯一 PG2L100H `0x00602899`、DONE=1；随后同一位流
重新写入易失 CRAM，并以 `cfg_program` 成功与 DONE=1 核验。
诊断应以当前原生扫描和器件 ID 为准，不因友好名称过滤结果就判定线缆缺失。

长 RTL CoreMark 仿真若根据短仿真吞吐预计超过设定时间上限，可另用
同一位流与固件在板上直接运行三次 performance 加一次 validation；
保留完整 UART、编程回执、位流和固件哈希，由脚本检查每轮超过 10 秒、
官方 CRC 与成功标记。本轮板上 59.4 MHz 运行四次均通过，三轮均值
5.280148744 CoreMark/MHz。此板测不能代替正式交付要求的 Git 实现证明、
控制组或长 RTL 仿真，不把单项性能 PASS 写成整机正式发布 PASS。
来源：性能工程 `docs/validation/v2_1-board-coremark-5f802-20261015/`。

## 2026-10-15：S 模式定时器必须核对两个计数器的实际频率

PG2L100H V3.5 的 `TIME` CSR 映射 CPU `cycle`，在本候选按
59.4 MHz 计数；CLINT `mtime` 实际按 49.5 MHz SYS 时钟计数。
OpenSBI 若直接把 S 模式提供的 `stime` 绝对截止值写入
`mtimecmp`，SBI 调用虽返回成功，Linux 的 `sleep` 和搜索定时仍会
失效。先分别用 M 模式探针确认 CLINT MTIP，再用 S 模式探针记录
SSTATUS/SIE/SIP、SBI 错误码和物理 `mtimecmp`，可把 CPU 时钟域问题
与 CLINT 硬件故障分开。本候选采用 OpenSBI 按剩余 CPU ticks
乘 5/6 转成 `mtime` ticks，并把设备树 timebase 设为 59.4 MHz；
板上 S 模式 2 秒中断、Linux 两次 `sleep 5` 和 GUI 搜索均通过。
比例只适用于当前已核对的频率，变更 PLL 后须重算并重新板测。
来源：性能工程 `docs/Pikafish_Main_Integration_Candidate.md` 和
`linux/opensbi/0001-pg2l-time-cycle-bridge.patch`。

同一候选上，内核 `pango-mac` probe 返回 -22 时应先核对设备树是否
声明驱动所需的 CPU uncached DDR alias；本例补入 `0x9b000000` 后，
板上出现 `/dev/pango-mac0`，官方 PFF1 GUI 达到 `PIKAFISH READY`，
注入红方走法后 Stage A 和 Stage B 都执行并返回黑方走法。
驱动节点出现不等于 GUI 已使用字符设备：本次 GUI 启动环境仍指定
`mmio-shadow`。记录初始化后端、内核注册与实际 MAC 作业三项证据，
分别描述，不据此宣称多进程共享已经验收。
正式输入快照 `e90ec0c4956a4659aeb8229b51faa2bf` 的位流通过
slow/fast STA 与 CRAM DONE 校验，同一套 SD 载荷再次通过 Linux、
驱动注册、官方模型、Stage A/B 走棋；板测结论须绑定该位流哈希，
不可只沿用先前同 RTL 候选的日志。

来源：性能工程 `docs/YOLOv5n_Board_Timing_20261007.md`、
`docs/NNUE_10ms_Optimization.md`、`docs/Linux启动与集成说明.md`、
`scripts/program_cram.ps1`、`scripts/pds_program_cram.tcl`。

## 2026-10-07 的真实失败

新 server 可连接 65420，但 cable list 为空，scan 报 JtagServer-0306；CLI
退出零仍判失败。Windows 下载器为 Port Reset Failed / code 43，CP210x COM17
正常，4 秒只读为 0 字节。不能由正常串口推断供电或 JTAG 下载可用。

17:06/17:11 重启后曾读到 USB Cable II、PG2L100H 0x00602899、DONE=0，随后下载
会话再次为空列表。独立目录、单一会话、显式 Tcl、关闭 UART、延长等待及只读
控制扫描都失败；两种 D2XX DLL 枚举设备数均为零。可排除部分参数猜测，但没有
证明故障一定在 USB 线，也不能由早先成功扫描证明现在能编程。
当日 21:29 新 server 的重试也报空列表/0306，未执行到 cfg_program。
10-04 对已核对身份的 USB 设备重启曾返回 Access is denied，pnputil 退出码却为
零；权限/错误输出仍需检查。以上尝试未写 CRAM/Flash、未运行新模型、无板测均值。

## 会话细节

该配置工具会随 cfg_close 结束 server；“留着 server 再连”不是可靠前提。
`cdt_cfg_shell -work_dir` 影响相对 `-file`；使用绝对 Tcl 路径。fresh server
10 秒等待是历史对照条件，不是所有板子都要固定等 10 秒。
在有 USB code 43、D2XX 零设备时，继续更改卷积参数或下载 Tcl 不能修复模型。

## 启动与加速器确认

bootloader 是项目自研 `soc-v3>` 等提示，命令按版本核对；不要发 U-Boot 命令。
TFTP 使用 bundled server，支持 offset resume/hexcrc，100 Mbps Full Duplex
是既有验证配置。SD/网络文件名相同不能证明卡中模型与候选哈希相同。
CRAM DONE 和 Linux shell 不代表驱动能力一致；要核对设备 ID/version/features。
`run_nnue10ms_board.sh`、`serial_mac_conv_stage2_accept.ps1` 和分块探针 `RUN.sh`
用于不同范围，执行前检查源码与严格硬件完成标记，注意 GUI 停止/恢复。
六个特征块的 `DENSE_TILED_CONV_BOARD_PASS` 不等同于完整 YOLO 图或 30 fps。

## 2026-10-09 恢复连接与候选卡部署

当次 Windows FTDI 与 CP210x 均正常，独立扫描读到目标 ID 后，10-05 时序通过
基线成功 CRAM 编程，DONE=1、DDR=ready。此结果没有确定此前 USB 43 的根因；
说明下一会话仍应重新查询当前枚举和工具输出。时序失败的 10-06/10-07 候选未下载。

旧卡能启动 root shell 和 Pikafish GUI，但缺少音频设备，8,445,440 B rootfs
与 10,643,968 B NNUE/语音候选不同。E: 经核对为 USB 读卡器的 FAT32 卡；
Image/rootfs/DTB 先备份再更新，已有匹配的 OpenSBI/PFF1/PFA1 保留。
六文件回读哈希、文件/卷缓存刷新通过，返卡后新 MAC/音频驱动均初始化。
因此“能启动 SD”与“已启动待测驱动/模型组合”应分别验收。
证据来源：性能工程 `docs/Board_Acceptance_20261009.md` 与本次 SD 更新记录。

随后 Linux XMODEM mini receiver 在 QEMU PTY 通过坏 CRC/重复包/部分尾包，
实际 UART 两次控制传输仍失败，根因未确定。16 B UART FIFO 和内核轮询接收
是应核对的条件，不能直接宣称为已证实根因。改用读卡器准备诊断镜像，
再次确认媒体及返卡；原启动成功不代表新的计时版本已部署。

随后使用已有 bootloader `loadx`：实际 PFF1 文件位于预留区的前部，
`0x14200000` 到 `0x15000000` 的空闲尾部允许该 1.79 MB 临时程序，
不与攻击表、MAC scratch 或 Linux 分配区重叠。1,747 个 CRC 块无重试；
原 SD 启动后临时 payload 保留。普通 dd 对 no-map 区返回 Bad address，
现有只读 mmap 复制器成功取到 /tmp；控制文件和完整程序 SHA-256 通过才执行。
这证明 bootloader 路径可用，没有确定 Linux XMODEM 失败的根因；未改 SD/Flash。
其他工程不能直接沿用此地址或假定保留区跨启动不被清零。

同日新 LUT 候选严格物理验收后，JTAG ID/DONE/DDR 再次通过。四份临时载荷
按各自真实大小规划互不重叠的 DDR 范围，CRC 传输全部无重试；SD 启动后
分别回读原始长度与 SHA-256，不将 XMODEM 的填充字节纳入可执行文件。
Linux 文本上传复制器时，GUI 正在加载 NNUE，768 字符块/每两字节 2 ms 的
传输在第六块报 `base64: truncated input`。保留失败，等待串口持有进程结束，
停止 GUI 并改为 256 字符块/每两字节 5 ms；150 块和整个复制器哈希通过。
这组调整同时改变了多个条件，只证明组合恢复了传输，不能归因为某一个因素。
串口子进程仍在运行时，新的打开曾被拒绝；先确认旧进程实际退出，再启动依赖
步骤。停止 GUI 后的测试须在结束时恢复服务并核对实际进程。新候选与全部载荷
的精确身份、测试范围见 `docs/YOLOv5n_LUT_Board_20261009.md`。

音频对照发现服务打印 `STOPPED` 后进程仍延迟退出；本轮等待约 74 秒才确认
`/proc/<pid>/stat` 消失。立即开始的两轮采集可能混入退出线程负载。CLINT 探针还
在 CLEAR 后首次 mmap/初始化计时，存在额外启动干扰；应将预热移到采集开始前。
保留这些 raw 溢出结果，不单独据此宣布 RTL 引入回归。确认 GUI 完全退出后，
显式 `NNUE_CLOCKSOURCE=linux` 的原时钟功能对照收满 16,000 样本，硬件溢出为 0；
其 648 ms 是未校准的 jiffies 读数，不能作为采样速率或绝对耗时。
模型推理继续使用已校准 CLINT，与音频功能计数的有效性分开记录。
无 GUI 的原时钟音频功能对照与严格 CLINT NNUE 并发时，320,000 样本有
2,736 次硬件溢出，计数闭合；语音兼容性仍未通过。两类计时不能混用。
结束恢复 GUI PID=505，实际进程存在且状态查询 engine=ready；识别权重缺失、声音恒 −1 和物理 HDMI
均仍有验收缺口。原时钟输出 12,716 ms 不作为该 320,000 样本的绝对耗时。
一次 Windows 原生命令参数丢失内层引号，FIFO 收到无效的 `XQ_STATUSn`，被
前端拒绝；通过 JSON 命令文件传送字面引号和换行后，正确 STATUS 返回 ready。
复杂 UART 命令应使用结构化文件，先确认实际回显，避免将宿主 shell 转义当作
板端协议错误。该控制对照没有执行棋步或更改模型。

## 新 CPU 的实板功能测试边界

已有 Linux 启动镜像不能证明新 CPU 具备原 CPU 的特权与 MMU 功能。测试顺序为
真实 CPU 仿真→同版候选资源/最终时序→新镜像 CRAM→bootloader/DDR/裸机
加速器→操作系统启动。记录每层结果；缺少 S/U/Sv32 时，前几层通过仍不能宣布
Linux、Pikafish 或语音可用。需要回到原环境时，使用已验收镜像及原启动文件恢复，
并重新核对实际进程/服务状态；镜像只在磁盘上存在不代表板卡已恢复。

探测缺失的能力 CSR 时，按当前 ISA 安装异常处理或单独的异常测试，记录访问是否
成功、异常原因与返回值。CPU V3.1 的独立 SATP 指令先超时，加入处理后捕获
mcause=2；同源 C 探针捕获 4 次异常并正常完成。此时打印的零只是初始化值，
不能当作有效读回。内部空壳模块接线、探针程序完成和实际能力支持分别判断。

完整系统无法布通时，可用隔离的精简硬件环境定位 CPU/DDR 等问题，明确列出
保留和排除的模块，并让未使用输出保持适当闲置状态。仍需该环境自己的资源、
原生最终时序、镜像哈希和板测证据。仅删除被裁掉逻辑的约束，核对保留时钟及
DDR 合同；精简环境通过不能替代原系统或被排除模块的兼容性验收。诊断文件
按当前工程规则隔离，不把它们自动提升为生产交付。

## 2026-10-14：Linux 启动后的模型与 GUI 分层定位

PG2L100H 的 59.4 MHz 最小 DRM 候选通过易失 CRAM 下载、裸机
DDR/MicroSD/MAC 自测，以及 microSD 临时加载器对六个启动载荷的
CRC32；Linux 到达 `/ #`。但首次 Stage B 黄金向量在 Linux 报
`pfsb-contract`，GUI 到“drawing initial framebuffer”后没有继续输出。
因此启动文件的 CRC 与 root shell 只是传输/启动层证据，不能替代
用户态文件哈希、PFSB 合同、官方 UCI `readyok`、硬件整数向量和
GUI 帧计数验收。诊断 rootfs 按此顺序输出标记，主机/QEMU 的同一
Stage B 文件通过只用于缩小故障范围。后续板端诊断见下节。

本工程既有备注已在板上确认 DDR uncached alias 的子字写会使 CPU
停住。Linux GUI 映射该 alias 后直接以 16 位 RGB565 写像素，
与绘制停顿吻合；修复为 32 位成对像素写及边界读改写，并给首帧
等待设置有限超时。共享绘制源属于已冻结的 FPGA 输入，即使
`#ifdef` 分支只给 Linux 用，改字节也会使已有位流快照审计失败；
此轮把修复隔离进 Linux 专用源文件，恢复共享源原字节，并重新
通过 `program_cram.ps1 -DryRun`。主机画面回归通过，后续板上
已确认 HDMI 棋盘；引擎最终就绪和搜索仍是独立门槛。
来源：性能工程 `sw/video/video_fb.h`、`linux/pikafish/xiangqi_fb_gui_linux.c`、
`docs/Pikafish_Main_Integration_Candidate.md`。

随后从旧 rootfs 的 shell 手工执行 Stage B 黄金向量，通过 96 例、
384 个 MAC 作业；这不等于官方 UCI 或 GUI 已通过。新诊断 rootfs
在相同位流、内核、PFF1 与攻击表下，两次都在 `/init` 前的
`kernfs_add_one+0x38` 出现同一空指针异常，六个 SD 文件的板上
CRC32 均匹配。新 rootfs 仅更换 GUI、Stage B 验收程序并增加两段
启动脚本，总长度增加 5 KiB，initrd 尾地址跨越一个 4 KiB 页边界。
因此这次内核异常不能归因于尚未运行的脚本或模型；须用相同位流
依次对照旧包、仅 GUI 修复包、无脚本包，以及旧内容补零到新长度的包，
区分内容、解包分配布局和硬件运行问题。对照结果见下节，不能
把此分析写成已证实的根因。来源：性能工程
`artifacts/board_linux_diag_20261014.log`、
`artifacts/board_linux_diag_retry_20261014.log`。

## 2026-10-15：同卡 initramfs A/B 与 GUI 就绪边界

同一位流、内核、官方 PFF1 和攻击表下，旧 rootfs、仅替换 GUI 的
rootfs、旧内容补零到较大总长度的 rootfs 均启动到 `/ #`；仅 GUI
修复版还打印 `GUI READY`，HDMI 实际显示棋盘，官方 PFF1 加载和
引擎核心初始化完成。含新版 Stage B 验收程序的无脚本 rootfs 在
`kernfs_add_one+0x38` 异常；把 `initramfs_async=0` 注入该版 DTB
后，解包和 initrd 释放完成，但后续在 `down_write+0x4` 异常。
所以启动脚本、initrd 总长度和异步解包竞争均不足以单独解释现象；
CPIO 条目移动 4 KiB 与异常相关，具体根因仍未证明。保持已能启动
的 CPIO 布局并只等长替换 GUI，可作为下一轮严格对照，不能由
等长推断板测必过。证据见性能工程 `artifacts/board_ab_*_full_20261014.log`
及 `artifacts/board_ab_*_full_20261015.log`。

GUI 首帧绘制、HDMI 棋盘、官方模型 `PFF1_READY` 和引擎内部
`ENGINE DIRECT CORE READY` 是不同门槛，均不等于 GUI 最终
`PIKAFISH READY`、实际搜索或 Stage B 硬件加速。逐帧等待函数
每帧重新绑定 UNIX socket 会泄漏描述符；若视频帧计数停住，
无限等待还会使引擎就绪轮询停止。GUI 应只建立一次 IPC socket，
每轮等待帧事件设时间上限，板测仍须看到最终就绪和实际走棋。
PFSB 回退时应记录板上读取的模型绑定、头部和载荷 CRC，而不是
仅依赖主机文件哈希或笼统 `pfsb-v2-binding`。来源：性能工程
`linux/pikafish/xiangqi_pikafish_gui.c`、
`linux/pikafish/pikafish_stageb_accel.cpp`、
`docs/Pikafish_Main_Integration_Candidate.md`。

同卡的后续对照中，较大的 initramfs 在 Linux 内部出现 Stage B pack
尾部和相邻黄金向量文件损坏，但 SD 加载器对整份 rootfs 的 CRC32
仍正确。只移除两个未被 GUI 启动脚本使用的大型可执行文件后，
板上逐文件 SHA-256、16 个模型槽位和尾部块均与主机一致，GUI 也
打印最终 `PIKAFISH READY`；这只界定了故障发生在 Linux 阶段，
不能把具体内核根因归于长度或文件布局。独立 Stage B 验收程序随后
在直接以字节访问 DDR uncached alias 时异常；与既有全字访问合同
一致的 shadow 加全字搬运版仍须板端黄金向量验证。

HDMI 棋盘显示且指针能移动、GUI 最终就绪时，点击仍可能完全没有
选中高亮。若串口也没有按键事件，逐层检查 CH9350L 解析出的
按键上升沿计数是否被接入 SoC MMIO，以及 GUI 读取的 HID 版本
和寄存器偏移是否与当前位流一致；只观察移动坐标不能证明按键路径。
性能工程当前候选新增左/右按下计数寄存器并完成仿真和 ADS 资源
检查，实板点击与走棋仍待同版位流验证。

## 2026-10-15：可移动卡盘符变化与重复启动证据

microSD 从开发板移回 Windows 时，原先使用的 `E:` 已是固定 NTFS
磁盘；同一测试卡实际挂载为 USB 读卡器上的 `H:` FAT32。写卡前
按总线、容量、分区文件系统与旧载荷哈希识别对象，只向已识别卡
新增等长候选 `brfs2.bin`，回读 SHA-256，再逐文件检查原载荷与
新增载荷 CRC32；历史盘符不能作为当前身份。用户返卡后用临时
DDR 装载器选取新文件，原文件保留以供同卡 A/B。

精确位流和新 rootfs 三次均通过 PG2L100H 易失 CRAM `DONE=1`、
六载荷板端 CRC、S 模式 Linux、官方 PFF1、GUI 最终 READY 与
Stage A/B 硬件走棋；但从 SD 完成到 GUI READY 仍固定约 122–124 秒。
因此三次功能通过只关闭这组短程功能门槛，不能证明非阻塞状态查询
就是旧启动超时的根因，也不能证明长期稳定或 1 秒搜索性能。
采集脚本必须读完整 `MOVE_PASS` 行，再判定标记；在标记前截断
曾造成一次脚本假失败。来源：性能工程
`docs/validation/v2_1-board-gui-nonblocking-20261015/README.md`。

同一候选在 Linux 已运行时单独重启 GUI 约 16 秒到 ready，而冷启动
仍约 189 秒。冷启动间隙用串口发送的 shell 查询丢字节，未形成完整
命令；没有回显不能证明 Linux 整体停顿。只有确认完整命令已提交、
串口 RX 保真并取得对应响应后，才能把 shell 计时用于层级归因。

同一位流持续供电且未重载时，操作者随后在 HDMI 棋盘上确认鼠标
选中高亮、红方落子和黑方回应。目视回执必须记录操作者、位流与
rootfs 哈希、供电连续性和观察范围；一次互动不能替代整盘稳定性。
板上 CoreMark 的原始 UART 与 JTAG 日志各仅数 KiB，发布时以
字节相同的 `.txt` 副本随包保存，并用 SHA-256、官方 CRC 源码与
四轮原始计时独立复核。V2.1 用户于 2026-10-15 指定 CoreMark 今后
只以上板实测验收，并停止当次长 RTL CoreMark；相应正式交付校验改为
精确位流、固件、STA 和 3+1 板测绑定，功能 RTL/软件回归仍执行。
不同版本的历史长 RTL 要求不能自动延续为当前项目门槛。来源：
性能工程 `docs/validation/v2_1-board-coremark-5f802-20261015/` 与
`docs/validation/v2_1-board-gui-nonblocking-20261015/`。

正式包的独立提取检查必须使用与上板镜像相同的 rootfs 构建选项。
默认 `make_rootfs.ps1` 只生成精简基线，不能拿它重建含 GUI 的 Pikafish
镜像；把确切 GUI/Stage B 二进制作为随包输入，并用
`-IncludePikafish -ExternalPff1` 重建到字节相同的 SHA-256。
若构建入口不同，先修正入口，再标记正式交付通过。

## 2026-10-16：PCM 连续性与真实声学输入分别验收

AUD1 v2 的 512×24 位采集 FIFO、Linux 字符设备与内存优先 WAV 工具，
在精确候选位流 `78487ddb…aa4d1b5` 上通过 2/4/6/12 秒、16 kHz 采集且
overrun=0；6/12 秒与官方 Pikafish 硬件搜索并发。WAV 串口导出须核对
完整字节数及板端 SHA-256，不能只凭采样计数通过认定声学质量。
一次用户说话窗口的去直流 RMS 18.99 与静音 19.65 相近，虽然样本变化、
无削顶，仍不构成人声响应证明。保留失败窗口，安排足够长且同步的说话/
轻敲对照，再查实际供电、共地、L/R 及引脚；不要靠增益或降低 VAD 阈值
把背景噪声变成识别通过。GUI 收到程序化 CANCEL ACK 仅证明 IPC 可用。
来源：语音候选 `docs/Voice_Hardware_Link_20261016.md`、
`docs/validation/voice-hw-20261016/board-capture-20261016.json`。

本轮移卡后 FTDI 消失而串口仍在，首轮扫描空链、未执行 assign/program。
操作者重新连接后才由新扫描确认精确器件并编程成功。已有同组 CRAM/新增
SD 文件授权继续有效；连接恢复不需要重复索要编程权限，也不扩大 Flash 权限。

后续 10 秒受控说话/轻敲窗口达到 160,000 样本且零丢样，去直流 RMS
142.95、范围 -1219..1992，明显高于静音 RMS 19.65；仍需区分人声与
敲击、确认可懂度。使用原识别源码和精确 XQT1 权重做离线 PCM 回放时，
10 ms 块 mean-absolute 最大 449，而默认 VAD 要连续三块≥600，因此
根本不启动分类。诊断调低 VAD 后的输出均为低分错误词，被原置信门槛
拒绝；不能标记为识别成功。幅度变化、VAD 触发、正确词和完整命令是
四个不同阶段。离线替换设备 ioctl/GUI 发送的 shim 必须明确标记，不能
把主机回放写成板上实时 ASR 或新的 FIFO/时序通过。
来源：语音候选 `docs/validation/voice-hw-20261016/recognition-replay-20261016.json`。

## 2026-10-16：Linux 运行时的低带宽 RAM 更新

当前 LiteUART 是 16 字节 RX FIFO 加 Linux 轮询，不能照搬 bootloader
XMODEM 的发送速度。控制命令逐字符限速；关闭回显要先作为独立命令执行，
再提交 here-document，因为 shell 会先读完整 here-doc 再执行同一行的
stty。完整载荷可用带 CRC/序号 ACK 的有界分包，按实测节奏发送；校验
小接收程序、旧基线、整包和最终重建文件 SHA-256 后才执行 RAM 候选。
本轮用差分缩小载荷，原 /usr/bin、SD 和 Flash 保持不变；传输/重建辅助
程序与原始日志只留 build，不作为生产启动能力发布。

BusyBox 功能以实际 --help 为准：本镜像 tar 没有 -z，可用 gzip -dc 管道。
串口脚本同时匹配根目录和子目录提示符，UTF-8 解码必须保留中文，而不能
把旧 ASCII 解码日志中的问号当模型输出。普通 /dev/mem read 与 mmap
支持不同，失败的 DDR 导出不能用作截图或 HDMI 视觉验收。
来源：语音候选 docs/Voice_GUI_Display_20261016.md；当前 FPGA 未重编程。

## 2026-10-16：GUI 重启要重新识别实际运行层次

重启请求先读提示符：`soc>` 是 bootloader，不能发送 Linux kill/exec。
RAM 部署的 GUI 在系统重启后失效，旧 rootfs 自启动棋盘不含新预览区。
硬件鼠标光标活动不能单独证明 GUI 活跃；棋子选中框等软件绘制反馈能
进一步区分状态。UART 没有命令回应时，不直接宣布 CPU 或 GUI 死锁。
本次 bootloader 收发正常、Linux 启动 TX 正常，但后续 RX 无回应；跳过
旧 GUI 自启动仍复现，尚不能将它归因为旧 GUI。之后由校验后的 RAM
覆盖层自动启动新版 GUI，UART shell 和状态查询均恢复；根因没有隔离，
只能报告该启动路径恢复交互，不能宣称修复了 UART 驱动。

若用 bootloader 临时预载软件覆盖层，先核对所有 DDR 装载范围，在进入
Linux 前完成复制；校验原 SD 载荷 CRC、覆盖层源和目标 CRC、原 DTB
字段，再更新准确的 initrd end。CPIO 覆盖层必须在原 trailer 处续接；
新程序的旧基线、重建文件和模型都通过 SHA-256 后才运行。整个动作只
改变 RAM，不代表持久化启动或新内核已经验收。传输助手留在 build。

## 2026-10-16：板上采音与 PC 引导标注

现有 16 kHz mono S16_LE PCM 为 32,000 B/s，115200 8N1 UART 的理论
字节载荷仅 11,520 B/s，不能未经验证地承诺串口连续实时原始音频。
本例先用既有录音程序在 RAM 缓冲完整 2 秒，再 gzip/base64 回传，核对
解压后的 WAV SHA-256、格式、32,000 样本及 FIFO overflows=0。
gzip 是否节约带宽由实际样本决定；回传成功不证明发音可懂或标签正确。

音频设备只允许一个读者。PC 工具先核对识别进程的真实可执行路径和
NUL 分隔参数，再暂停它；异常路径也尝试恢复原模型和参数，核对存活。
不停止棋盘 GUI，不把同名或已复用 PID 当作身份。等板端开始标记抵达
才显示视觉录音提示，避免 PC 蜂鸣被板上麦克风录入。

原 WAV、人工截取片段、SHA、采集统计与接受/拒绝记录分开保存。放大
仅用于试听，不改变训练原始 PCM。pilot、背景、未确认和拒绝片段不进入
当前单词模型清单。同轮固定 split，原训练器的 32,240 样本上限也必须
在采集入口检查。无人标注的通路检查保留为 unlabelled，不冒充静音或
真人词正确率通过。数据不进入源代码/工具交付包。

## 2026-10-16：从少量试录扩展词表

补录任务先按人工 accepted 记录盘点类别，原始、拒绝与待确认录音不计数。
本例已有 5 类 13 段，剩余 19 类；新 train 采集轮保持独立身份，旧 pilot
不自动改组。逐词目标只统计当前窗口人工确认的片段，保存后轮换未达目标
的词，丢弃不推进，不自动触发录音。小批次每词 3 段只是采集目标，不能
当作准确率门槛；同轮补齐原来 5 类后，验证/测试仍须另开采集轮。

升级 PC 引导程序时先正常关闭已识别的旧窗口，等待当前录音与识别恢复；
不强杀进程。未确认的原 WAV 留在旧目录，不静默接受。重新启动前只读
核对板端采音程序和识别进程路径、模型参数；打开提示窗口不等于已采到
新真人样本。交付只包含工具、说明、技能和紧凑准备记录，不包含个人音频。

## 2026-10-16：小型语音模型独立 RAM 替换

先正常关闭 PC 录音窗口，等当前采音与识别恢复完成，再独占串口进行模型
切换。保存旧识别进程的真实可执行路径、NUL 参数和模型哈希，旧模型保留。
经限速 UART 将候选写入唯一 .part，核对解压后 SHA 再落到独立 RAM 路径；
停止旧进程前再次核对身份并确认退出，启动时只换模型参数。以新日志边界内
READY、实际 argv、板端最终 SHA 与 GUI 的 executed=0 记录确认链路恢复。

大 GUI 二进制的 SHA 计算可超过短控制命令超时；超时不表示 shell 死亡或
模型已替换。先记录执行到哪一步并收回提示符，再缩小只读核对范围或采用
适合该工作量的有界等待，不盲目重发整套切换。本次检查 ASR 文件 SHA 与
GUI 可执行路径；前后 GUI PID/FEN 相同，framebuffer03/underflows0。
24词6020B的C loader/进程启动通过不等于新增C逐项数值或真人准确率验收；
重启后 RAM 文件失效，封存训练包中的未部署字段保留其训练阶段身份。
来源：语音工程 docs/Voice_All24_Deployment_20261016.md。

## 2026-10-16：采集软件入口与数据路径

给用户可双击的采集补充包时，入口应按自身目录定位源码，数据根目录
则由明确配置绑定，不依赖软件包的解压层级。保持24词/新train轮和每词
目标的默认值可见，validation/test另开轮；每次只运行一个设备读者。
本例沿用既有采集代码，启动前检查Tk/pyserial，优先本机已知pythonw，
说明包内不含Python运行环境。窗口启动不等于采音质量验收；不替用户
录入、接纳数据或调整当前板上模型。源码/说明/完整技能一同封装，
个人WAV与临时传输日志仍排除在软件包外。

## 2026-10-16：批量采音前先盘点Linux传输能力

物理网口/SD及bootloader TFTP/FAT能力不代表Linux已有netdev/block驱动。
用/proc/net/dev、/sys/class/net、/proc/partitions、挂载和设备树确认当前
可用路径。本例只有lo/sit0且无块设备，UART分频固定430；只改PC波特率
不能提速。16kHz/S16单声道需32000B/s，115200/8N1裸载荷仅11520B/s，
base64增加约三分之一，gzip效果由内容决定。批量一次回传可摊薄控制、
暂停恢复开销，不宣称提升链路带宽；新增网络或SD须另做驱动/设备树链路。

已有capture工具支持1～30秒；PC长录音入口可显式放宽原WAV解析长度，
但最终单词片段仍须满足原2.015秒模型上限。原始长WAV和人工短片段分存，
原FIFO/样本数/SHA检查保留；窗口启动不是长时采音或切分质量验收。
来源：语音工程 docs/Voice_Batch_Recording_20261016.md。

## 2026-10-16：SD存卡与控制链路的计时边界

音频留卡只回状态可消除大WAV串口下载，但逐字符10ms控制命令仍会让
整批等待很长。分开记录采音、板端写卡/回读/提交、完整控制流程，不能
把本例7.3秒存卡时间写成10秒录音的整批耗时。已验证的4字节/8ms分块
节奏可用于此板SD控制路径，仍保留唯一完成标记、工具SHA、CID/分区/卷
检查及请求JSON回读SHA；不能据此推广到不同UART FIFO/内核轮询系统。

复用UART ACK接收器时READY可能紧跟未消耗的shell提示符，不强制要求
行首；接收器O_EXCL会拒绝上次失败残留，重试使用新的临时载荷名，最终
解压二进制SHA通过后才执行。失败恢复按实际是否进入接收器发送END并
收回shell，不把仅出现提示符当作载荷成功。传输助手只留build。
SD实板先只读CID/分区/七启动文件CRC，再以unlabelled录音检查，避免
将通路样本写成训练真值。原始卡CID串可能采用寄存器顺序，应原样绑定。
来源：语音工程 docs/Voice_SD_Recording_20261016.md。

## 2026-10-16：先确认可移动介质当前归属，再查询板端目录

用户可能已把共享启动/录音卡移到PC。串口查询前先枚举PC可移动卷和
容量/卷序列号/VOICE目录，不沿用历史E盘或假定仍在开发板。只检查旧盘符
会漏掉新H盘，让本可直接读取的文件走一次不必要的板端工具上传。
本例SD_ERR_NO_CARD=-1与空卡检测寄存器对应真实无卡；PC读卡器中能
校验原WAV/JSON，不能误判为SD硬件或录音写入失效。

PC界面按已绑定卷序列号刷新介质状态，卡在PC时阻止板上存卡录音，
提供离线导入；板端缺卡映射为清楚的操作提示，其他错误不吞掉。
预检查必须在暂停ASR或开始录音之前，失败不影响正在运行的识别进程。
手工标定导入保留原SHA、split和speaker，建议片段不自动成为接受样本。
来源：语音工程docs/Voice_SD_Recording_20261016.md缺卡/手工标定修复。

## 2026-10-17：复用ACK通路进行小模型RAM切换

已有经SHA核对的UART ACK接收器可用于6KB XQT1小模型更新，不重复上传
传输助手。逐包CRC/序号、唯一临时文件、压缩与解压SHA均核对后再停止旧ASR，
传输期间保留原识别服务。停止前重新确认原PID/exe/完整argv，切换只改模型参数。
新日志READY需用切换前行号划界，排除旧进程历史READY；运行时display-only身份、
GUI PID、旧模型SHA及棋盘状态另外核对。候选显示和低差值不是有标签准确率验收。
原程序与阈值不变也不能仅凭模型SHA推断实时识别改善；RAM切换不等于持久更新。
本次156段版40b7b1d1…替换71段版f31b38e2…，GUI PID94不变，旧权重保留，
没有GUI/RTL/内核/SD/Flash变更。训练和部署跨日，模型名保留训练日期，部署记录
使用实际客户端日期；旧封存包的board_deployed=false仍描述原训练阶段。
来源：语音工程docs/Voice_All24_Retrain_Deployment_20261017.md。

## 2026-10-18：用陷阱和指令定位 RAM 启动校验失败

同一 CPU70 位流的 CoreMark 与基础 MAC 通过，RAM loader 却在六个 SD 文件
CRC 正确后回到 ROM。小型只读 CSR 探针保留 mcause=5、mepc=0x01003144、
mtval=0x9a000988；原 ELF 对应 lbu，定位到未缓存 DTB 尾部三个字节。
原 copy_to_uncached 已按字读取并移位处理尾字节，复用它保持原 CRC 期望值后
进入 Linux。不要跳过 CRC、把返回控制台都叫复位，或以 STA/CoreMark 通过排除
软件访问规则问题。原失败、CSR、反汇编和修正软件须分别绑定，冻结 FPGA 不变。

随后 3 进程×2 线程 MAC 调度出现 got=0/expected=16，shell 打印退出码后 UART
不再响应，回车/Ctrl+C 均无字节。保存失败、停止依赖测试，重载同一位流恢复；
不能把恢复后的单任务通过改写为并发已通过。来源：语音工程
docs/CPU_70MHz_Board_Test_20261018.md；当前不构成全功能或正式发布通过。

同候选重新启动后，8 上下文池在 slot0 回收重用时另报 live contexts are not isolated，
随后 UART 无后续响应。该测试没有 RUN，只做页映射和哨兵，不能归因于 MAC 运算。
将 pool 复用与跨进程调度分开定位；避免反复运行已知会破坏会话的压力测试。
