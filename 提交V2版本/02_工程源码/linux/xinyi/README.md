# 芯弈一号产品层（T2 软件候选，尚未板验）

2026-10-25：当前硬件目标为main P3 `6565ad37…`。新增真实CoreMark输出/翻页按钮、
独立十秒参考演示、低频局部进度刷新及完整64位ticks打印。参考演示使用main六个真实ROM样本，
标注“非本次实测”，保留实际Linux成绩且不伪造执行输出。
host/RV32软件验证和PN04候选详见[当前离线记录](../../docs/PictureNew_离线完成与main同步_20261025.md)。
下面V6.5参考值和首版模拟交互说明是历史记录；现役host预览也支持独立十秒参考演示。

这是构建在 integrated60 GUI1080 上的产品控制/显示扩展，不是另一套棋盘。
已有 `linux/xinyi_board/` 的真实板端 main/runtime、V321 候选协议及异步客户端、
voice_2/引擎/播报接线和 RV32 完整链接；当前证据仍为 host 合成功能验证、
RV32/QEMU 协议测试与编译，不能标作 T2 上板验收。真实物理 Space/Esc、
status5 几何失败恢复、完整新拍链路、音频听测及独占预览切换仍待上板。

## 固定入口

```sh
sh linux/xinyi/build_host.sh
python3 linux/xinyi/host_preview.py --duration 900
python3 linux/xinyi/test_preview.py --library build/xinyi-host-20261024/native/libxinyi.so --out build/xinyi-host-20261024/native
sh linux/xinyi/build_rv32.sh
```

host 命令在 WSL Ubuntu-22.04 执行。预览访问 `http://127.0.0.1:8765/`，
默认 15 分钟自动停止，Ctrl+C 可停；不记录请求日志。网页仅显示 C 渲染的
1920×1080 RGB565 转 PNG，按键/按钮调用同一个 native 控制层。
假照片/语音/荐着/耗时均为合成数据，CoreMark 按钮为模拟进度，绝不更新分卡。

## GUI 研读与复用

阅读来源固定为 `127ff9a5` 的 GUI_1080p_20261022、theme、config、renderer、
字体说明，并查看原 preview-light.png；根验证目录记录完整研读结论。

| 现有能力 | 产品扩展 |
|---|---|
| 已确认浅色、暖木纹、88px 格、48×48 AA 棋子 | 原样调用 `draw_board` / `draw_position`；不重写棋盘 |
| 选中高亮、A–I 坐标、AA UI 字体 | 保留；空目的格用原 `draw_ring` 补高亮 |
| 胜率条、引擎节点/用时、voice display | 语音模式复用原胜率/节点/时间绘制，缺数据显示 `--` |
| 局部重绘、uncached DDR 32 位写 | 复用原 `redraw_square` / fill/AA primitives；角标限制在脏格内 |
| 旧侧栏、重开、执黑应着状态 | 新产品入口改为首页、单激活双模式、两卡+实时条；旧代码保留回退 |
| 旧中文字模子集 | 额外独立产品子集；不改棋子或原 UI 字模 |

原 GUI 文档描述历史 1080p60 / CPU80；当前分支 `display.json` 是 1080p30。
产品只显示 1080p，硬件时序/位流身份由主程序核验。现有硬件各加速路径不能
因产品提示中的“共享”表述而被改写成一个阵列，首页写“单 FPGA 三项 AI”。
参考数值采用明确范围：历史 V6.5 63.64MHz CoreMark/MHz 5.262385；
分类器 B32 5.35×，不能代表检测器全图；NNUE 热态约21ms，冷态151→22ms约6.8×。
≥85% 为目标，r14 FP32 75/84 与 INT 68/84 为历史汇总，整数识别未过门槛。

## 接线边界

`xy_backend` 在主进程接入真实 capture/recommend/voice/coremark/cancel/speak。
`xy_app_init` 必须确认麦克风关闭；图像模式禁止开启语音输入，语音模式禁止
capture。只切换标签不构成关闭 microphone 后端。

每个异步作业携带 token。切模式/回首页先请求 cancel，主程序完成相机安全
DDR drain、引擎/ASR/benchmark 停止后，才可调用 `xy_cancel_complete`。
教练播报为 `XY_ANNOUNCE` 作业，荐着显示后仍占用资源；
`xy_announce_complete(token,okay)` 或播报安全取消确认后才恢复空闲。
失败保留荐着并显示播报失败，导航须等安全 ack；不能启动下一拍或抢开麦克风。
所有旧 token、取消中的完成回包均拒绝。调用 `xy_photo_elapsed` 传入真实
Space 到终态时间；不得用 FPGA busy 代替整拍延迟。

识别入口先完成现有 token/frame/CRC/backend/geometry 严格校验，再把完整
已排格候选交给 `xy_capture_complete_scored`。真实输入用 `xy_scored_detection`，
保留完整 float score 排序，uint16 confidence 千分位仅供显示；验证 finite、
.05..1 和 floor(score×1000) 一致。同一千分位不构成真实并列。
旧 `xy_detection`/`xy_capture_complete` 留给合成适配。最大300，超限明确拒绝、不截断。
独立 `coach_protocol` 不沿用旧 status6 零候选包；几何/身份严格校验后才能修复。
现有几何阈值、量化数学、权重均未更改。

自动修复顺序：同格稳定留最高置信 → 每类超上限稳定删最低置信。绝不添加、
移动或换类。removed_count 是删除候选数，corrected_cells 是不同格数（界面
“N处”）。输出每子都来自输入。非法盘显示但不发引擎；几何/数据整体失败
保留前盘。静态校验包括双将数量、可达格、将帅照面以及红方行棋语义的合法性；
不删除其它棋子来凑合法。引擎始终收到 `side=0`，回包再用现有合法走法检查。
语音盘与图像盘分别保存，语音应着不覆盖“上一拍”图像盘。

显示使用 `xy_fb_render(app, active_pixels)`。该 translation unit 包含原 renderer，
不要再次链接 `xiangqi_fb_gui_1080.o`。原 `xq_fb_gui_init` 的显示 ABI 检查和
主进程 present/摄像头切入切出仍须执行；产品 render 不读写 MMIO。
外部绘图/摄像头/换缓冲后调用 `xy_fb_invalidate`。只处理 Space/Esc 和产品按钮，
不接旧 R 页、手动四角、对局跟踪、自愈或 AI 执黑校验。
按钮命中由 `xy_pointer_action`/`xy_pointer_targets` 共享渲染布局；无手工复制坐标。

`platform` 已适配目标 DTS 完整 camera-preview 6MiB no-map reservation，
相机仍使用原 HOLD/复制/drain。目标 integrated60 视频 mux 的相机预览占满
HDMI 整个源，无法同时显示 GUI；捕获停止并排空后恢复 GUI 并重绘。
E8 的 0x1b800000/0x1ba00000 私有银行与 GUI 重叠，禁止冒充该能力。
语音页与实时相机画面同屏仍是明确硬件缺口，软件不能创造合成能力。

`coach_task` 只在新建0700、已验证 tmpfs 的 `/run/xinyi-coach.*` 写固定帧/请求/结果。
输入 RAM 必须 pin 至 writer join 的 `xy_coach_consumed`；结果完成及取消均等同身份
status9、IDLE、V321 BUSY=0 才可复用。强停需 TERM/KILL、waitpid 和 BUSY=0，
未知 BUSY/排空失败进入隔离，不确认取消。stdout/stderr 私有有界读取，不输出现场 IPC。

## 真正的 CoreMark 后端

`coremark/build.sh <out>` 将 `sw/coremark` 的五个原始算法单元原样编译，
`-include coremark/core_portme.h` 只替换 POSIX 端口，不修改裸机端口或旧成绩。
`coremark/benchmark.c` 对 performance/validation 两种种子分别用实际 iterate 循环标定，
不再用性能段估计验证段；有界重试后只报告实际执行的迭代数。
默认总目标45s，正式两段各至少10s，已知 seed/list/matrix/state CRC 两组都过
才输出 valid=1。计时为 `CLOCK_MONOTONIC_RAW` 纳秒；不是睡眠计分。
`coremark/test_calibration.py` 用明确模拟的计时/CRC检查校准控制流、重试耗尽和失败关闭，
不产生成绩；`test_host.sh` 还运行原算法CRC、各≥10秒及真实子进程取消检查。

```sh
sh linux/xinyi/coremark/build.sh build/xinyi-host-20261024/coremark-host
build/xinyi-host-20261024/coremark-host/xinyi-coremark --target-ms 45000 --cpu-hz 0 --identity 0000000000000000000000000000000000000000000000000000000000000000
```

真实板端 callback 建议持有 `xy_cm_process`：

1. 初始化 `xy_cm_process_init`；`backend.coremark` 调用 `xy_cm_process_start`，
   传入已绑定 SHA 的绝对可执行路径、token、45000、当前实测 CPU_HZ 与64位位流SHA。
2. 事件循环调 `xy_cm_process_poll` / `xy_cm_process_apply`；不阻塞 GUI。
   计分期间只局部重绘进度/取消/状态条，建议主循环以约200ms节拍呈现进度，
   不重复绘整页以免 GUI 抢占基准负载；实际并发开销仍属于本次实测环境。
3. `backend.cancel` 调 `xy_cm_process_cancel`。先 TERM，500ms未退出再KILL；
   waitpid 回收后才发取消确认。进程退出时 `xy_cm_process_dispose`，父死信号防孤儿。
4. 只有父/子都编译为 RV32、CRC/时长过关、CPU_HZ与位流身份匹配时才可更新
   本次实板卡。host真实算法校验、模拟进度、失败/取消均保留原卡。

这是 Linux 单线程短测，不能冒充裸机历史成绩、3+1 BoardRelease 或当前新硬件
已经获得验收。本目录构建入口输出产品 objects 和独立静态 CoreMark ELF，
完整产品 GUI 链接由 `linux/xinyi_board/` 集成入口负责。

## 验证与字模

`test_product.c` 覆盖55组**自行生成**第三辆车、200/300候选、并列置信、只删不造、
非法/几何失败、真实 float 同千分位排序、播报占用/失败/安全取消、旧回包、
取消drain与互斥、CoreMark模拟不能改分。没有读取
CAMERA_v2、game2 或现场图像/IPC。`test_fb.c` 覆盖原木棋盘/AA像素不变、
48轮局部/完整重绘逐像素相等、显存前后guard。`test_preview.py` 为交互API冒烟。

新中文字模保存在 fonts/ 与 xinyi_font.h，来源 Noto Sans SC 字重500，许可证
OFL。源SHA、静态子集SHA、Pillow/FreeType/fontTools与字模SHA有固定收据。
仅生成器使用隔离依赖，板端不解析字体。不改记录的 Python 或全局环境。

```powershell
& build/picture-tools/python3144/python.exe -X utf8 linux/xinyi/gen_font.py --deps build/xinyi-host-20261024/tools --check
```

首次从本机只读原字体生成可加 `--source C:/Windows/Fonts/NotoSansSC-VF.ttf`；
后续重建使用提交的重命名子集。动态中文记法覆盖14类棋子、一至九、前中后、
进退平及常见繁体/别名。未知字符占位且不改变棋盘数据。

当前产品 focused 验证产物在 `build/xinyi-host-20261024/scored-final-native/`、
`scored-final-preview/`，汇总与源码 SHA 见 `final-focused-validation.json`。
真实 Linux CoreMark 静态 RV32 ELF 在 `static-rv32/coremark/xinyi-coremark`；
平台回执 `build/xinyi-platform-20261024/r02/platform-validation.json`，
coach 客户端当前协议回执 `build/xinyi-coach-task-20261024/r10/coach-task-validation.json`，
含 wire5 保留旧结果并用同一 resident 成功再拍、wire6 致命拒绝、三组 host/RV32
配对测试，以及跨毫秒停止计时回归与旧表达式确定性负控。
所有上述测试都不构成模型准确率、当前位流性能或板测验收。
