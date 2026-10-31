# 芯弈一号板端软件候选

2026-10-27 当前 CPU70 实现通过完整回归、实板模型/CoreMark与用户现场功能复测。GUI冻结8f4de1c7；正式包与实卡最终完成状态见 [本版记录](../../docs/Main70_Delivery_20261027.md)。以下为原历史范围。


2026-10-25：当前目标main P3 `e7288be9`/sbit`6565ad37…`，新产品候选PN04。
五路BUSY/身份检查、严格batch引擎、CoreMark真实输出与独立十秒参考演示已离线验证。
详见[本轮完成记录](../../docs/PictureNew_离线完成与main同步_20261025.md)。
以下为原T2说明及历史验证范围，PN03/9ba02f10不适用于P3。

`main.c` 是 CPU60/1080p30/V321/PFN1 的完整产品入口，连接 `linux/xinyi/` 的原生
GUI1080 扩展、相机、working-r14 教练 worker、专用 NNUE 引擎、原 voice_2 自动会话、
真实 PCM 播放和 Linux CoreMark。当前为 T2 软件候选；实板识别、听感、时延和取消未验收。

## 构建和启动

在 WSL Ubuntu-22.04 中执行，输出必须是尚不存在的仓库 `build/` 子目录：

```sh
sh linux/xinyi_board/build.sh "$PWD/build/xinyi-one-20261024/product-rv32-final"
```

默认工具链为 `/opt/toolchain/bin/riscv32-linux-musl-gcc`，静态 RV32IMA/ILP32、
strict-align、无 C/硬浮点；renderer 只包含一次原 `xiangqi_fb_gui_1080.c`。
构建前后检查源码哈希。`engine_service.cpp` 通过 `build_engine_service.sh` 在 T1 已核验的
私有 prepared 官方引擎源树中重链接；保留原 StageA/StageB/pipeline hook，不接 CPU 回退。
`scripts/verify_xinyi_elf.py` 检查三份 ELF，核对 strip 前后所有 SHF_ALLOC 节字节和地址。

`scripts/prepare_xinyi_cpu60_kit.py` 从原始 prebuilt rootfs 生成私有 RAM 材料，校验模型、
37 PCM、7 个基础语音资产和静态 ELF，并只重绑最终 DT 的 initrd-end。具体参数见脚本
`--help`。材料生成不会写卡、不会选择公共启动项，也不会生成安装或上板成功回执。
材料构建强制要求 `--coach-proof`，把当前源稳定证明与实际 rootfs worker 绑定，拒绝旧 ELF。
`scripts/build_xinyi_cpu60_loader.py` / `.ps1` 另外生成匹配原 CPU60 ROM 的独立 PN03 只读 loader；
七文件候选及验证见 `docs/validation/xinyi-one-20261024/t2-pn03-candidate.md`。
当前仍缺四份原生门件。用户后续明确要求先实板测试，独立 CPU60FunctionalTrial 检查及真实
CRAM加载/串口CPU60身份已通过；PN03 loader 已传RAM，Linux启动及产品功能仍待板验。
此功能授权与原生完整预检、正式STA通过分开记录，见验证目录的 `t2-board-functional-r01.md`。

主程序只接受经过材料包 launcher 核验后的绝对路径：
`XINYI_COACH_WORKER/MODELS/ENGINE/SPEECH_WORKER/PCM/COREMARK`。
语音沿用 `XQVOICE_RUNTIME/MODEL/BACKEND` 合同；CNN 固定 balanced24，NNUE 采用固定
PFF1 物理视图和匹配 StageB pack。默认引擎搜索512节点；180秒是诊断 watchdog，
不是时延验收。coach 的7200秒请求期限同样只服务功能带起。

`XINYI_CURRENT_CRAM_SHA256` 只能从本次成功的 CRAM 赋值回执注入；材料包中的目标 SHA
不能代表当前已配置器件。缺回执时 CoreMark 不更新现场分卡。MMIO 另核对 CPU60、
SYS49.5、显示 ABI、PFN1/V321/StageA/NNUE 身份和 no-map 预留。

## 异步资源与数据

主线程只处理事件和绘制；相机、帧写入、引擎、播报和基准均有独立异步执行边界。
CoreMark 期间每200ms呈现进度，按键轮询继续。语音会话的原 pause 最多会等待约1.6秒；
真实播报仍使用原 SCHED_FIFO 策略，单核 GUI/Esc 响应需板测，不能凭进程隔离宣称通过。

相机成功后把 immutable RAM frame pin 到 coach writer 消费结束。IPC 只使用经 tmpfs
核验的 `/run/xinyi-coach.*`，固定文件、私有权限、无 SD 落盘；worker 日志为私有有界管道。
协议严格校验 token/frame/raw CRC/backend/结果体 CRC。status0 只说明几何/排格通过，
所有最多300候选仍须按原始 float score 纠错、再做红方局面合法性和回着合法性验证。
无上一拍几何、人工角点或对局修复状态。几何失败保留前盘；非法修复盘显示但不荐着。

模式切换和回首页先取消，再等明确回执：相机 HOLD/drain、writer join、教练原 identity
的 release9/IDLE、引擎 waitpid 与四路 BUSY 全空、音频清理完成。仅删请求或杀进程都不足
以释放所有者。超时/未知排空保持隔离，阻止下一拍和麦克风。教练播报占 `XY_ANNOUNCE`，
完成前也不能抢跑新拍。退出执行有界清理，失败以非零退出并要求人工恢复，不重启循环。

`accelerator_idle.c` 只读固定寄存器，无 abort/reset/control 写。其四个 BUSY 位按该试验
实际 RTL 核对；该只读探针只服务进程退出后的资源确认，不代替驱动序列化或硬件验收。

UART 每拍最多记录三个阶段结果/耗时，不输出棋盘、FEN、语音原文、帧号、CRC、角点或照片。
界面的本拍延迟为 Space 到荐着结果可见；播报结束另有 phase 标记。未经真实场景重现，
不把 status5 写成某个已确定根因。

## 当前硬件缺口

目标镜像摄像头占用整个 HDMI 源，没有 GUI 合成。当前入口保证采集后安全恢复产品页；
语音模式连续预览与产品页并显仍未满足，交给 main worker 的硬件收敛线，不在这里新增 RTL。
具体板侧加载缺件、软件验证和后续依赖见 `docs/validation/xinyi-one-20261024/t2-software.md`。

## 实板只读/小向量检查

`v321_board_probe.c` 默认只通过真实 `/dev/pango-mac0` 执行四个 raw-I32 作业，比较37个
预先确定的输出，覆盖尾通道、卷积边界、K1152及超过24位的累加值；错误直接失败，无CPU回退。
`--self-check` 仅检查向量布局，不访问设备，输出明确标为非板测。

`gui_readback.c` 要求匹配CPU60/1080p30寄存器及相机空闲，只用32位读取GUI专用bank，
以640×360 RGB565/RLE输出到stdout；不读相机bank、不改显示或写SD。`--fixture` 为纯色合成夹具。
`scripts/decode_xinyi_gui_readback.py` 将该流解码成PNG，真实回读须提供板上文件SHA256；
截图保存在私有build中，不能把现场盘面截图当成可提交的合成UI预览。
离线ELF、strip前后已分配段一致性及夹具检查见验证目录的 `t2-linux-board-helpers-r02.json`；
实际设备向量及HDMI/GUI结果仍须单独记录。
