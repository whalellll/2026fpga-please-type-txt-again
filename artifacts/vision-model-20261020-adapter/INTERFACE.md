# Picture_new 工程适配接口（2026-10-25）

r19–r23仅作归档级接收，训练线在第二轮QAT失败后收官，没有第三轮；当前模型和数值基线不变。
INT68/84未达73/84是关闭但未达标的差距，game2单次判定窗口未用即关；未来候选须重新授权。
当前注册见[归档与归因资产登记](evaluation/training_closeout_r19_r23.json)，
核验、模型不变及最新main复核见[收官记录](../../docs/validation/picture-training-closeout-20261025/README.md)。
CAMERA_v2矩阵的156/178是与FP32的FEN一致率，不是独立真值准确率；真值仅登记来源和哈希。
工程硬件为main e7288be9/P3 CPU60/1080p30。PN05实现产品侧部分结果/粗定位整理后合法荐着；
它使用独立协议，不改变PC默认FP32或原严格RESULT消费者，尚未实卡安装。
现行软件与板测边界见[PN05](../../docs/validation/xinyi-pn05-20261025/README.md)。

下面2026-10-23及更早的接口分期内容保留原身份；其“待新局归因”状态已由以上收官结论取代。

当前默认 `working-r14`：冻结640 + 标准 v3d-QAT d1476f80 + 冻结board192，
FP32/pc-fp32、A及B80。`rollback-v3d` 为r13 v3d，`working-r12`保留v3c；
r13补齐了v3c整数图，旧“缺图直接拒绝”只描述r12历史阶段。
r14显式 `--backend quantized-mac` 使用40d820c4图和exact-int64，只供功能联调，
结果附 `quantized_gate=false`，状态“待新局归因”，未达73/84。
候选84/84不是正确84/84，报告正确为75/84。协议/schema和盘面严格保护不变。

原生运行时使用共享驱动的一MiB私有shadow和不可变注册快照，board/classifier整模型，
detector逐层；物理权重区切换仍须恢复。1×1层直接准备输入；dense仍是默认主线。
`XQ_NATIVE_CONV=gray` 才允许能力检测后的精确子集分派，默认关闭，当前80层无符合者；
卷积错误不回退CPU。详见 [接口笔记](../../docs/CPU80_PICTURE_INTERFACE_NOTES_20261023.md)。
本次只构建CPU80 PN02候选，无板部署、SD写入或新性能验收。

下列r12及更早内容为历史接口状态，默认与交付可用性以本段和注册表为准。

本页修订接收侧措辞；冻结交付的 `../vision-model-20261020/INTERFACE.md` 保持原样。
识别结果 schema_version 不变，不新增 `require_both_generals` 开关。

2026-10-22 r12当前：默认E=冻结640/v3c，方案A和B80保持，默认backend为FP32。
`recognize_working.py --input ... --output build/...`消费`working_combination.json`的当前组合；
`recognize_peer.py`默认使用明确的`pc-fp32`身份。GUI源码加入该backend白名单，其余
token/frame/CRC/backend/status/FEN及盘面规则检查、协议版本均不变；新r12 GUI未部署。
v3c INT8参数/图缺失，任何量化E请求在加载前拒绝。`--profile rollback-v2-band`
为640/v2-band，默认FP32，可显式`--backend quantized-mac`使用SHA匹配的r08 exact包。
`--profile working-r09`与`frozen640-v1`保留原身份；显式det416/416mix路径仍可调用，
登记新域不适配。正式FP32正确/严格73/84、候选83、冲突1，详见
[r12](../../docs/validation/picture-r12-engineering-20261022/README.md)。
第二局仅允许归档正式真值/报告、引用汇总，不读取照片、推理、训练、调参或失败分析。

以下r11/r09描述保留历史身份，默认选择以本页r12和组合注册表为准。
2026-10-22 r11历史：v3c / det416mix 当时均待正式验收，默认为 v2-band / det416-r09。
`recognize_working.py --backend fp32 --classifier v3c --detector
det416-r09|det416mix-r11|frozen640` 可显式比较候选；r11 未交付 INT8 参数和图，
量化 v3c 请求直接报错。第二局材料封存；不引用临时独立验收评分。
清单38项 SHA通过但存在未列清单附录，整包覆盖未通过，待训练重发。

对弈采集改用 `xqc_capture_until_ready`：一次空格对可恢复 START/HOLD/CHANGED 错误
持续重试，Esc/TERM取消；每次安全排空后复位，并等待两次新的帧发布。
只有原 HOLD/bank/frame 验证成功的 RAM 帧才交给模型并绑定 token/frame/CRC。
身份、DDR、模式、无法排空等故障仍退出；盘面和模型协议保护保持不变。
新代码通过宿主回归及 RV32 编译，上板状态见
[r11 验证目录](../../docs/validation/picture-r11-offline-20261022/README.md)，不从编译推断部署。

方向规则：**双将帅缺失或证据冲突 → orientation_unknown；单一将帅在有效九宫内可定向**。
离九宫、多个同方将帅或方向证据不足仍拒绝。可定向只代表方向证据成立；
候选盘面仍须通过完整棋子数量、双将帅、FEN、合法局面及对弈状态检查。
缺黑将的现场帧仍不可对弈，不能用候选 `candidate_board` 状态代替盘面验收。

现有方向推断与上层双将帅保护已经分别实现上述职责。当前增加开关只会重复上层规则，
并引入结果语义分支；暂不采纳。未来若增加开关，需要升级 schema_version 并重新验证。

PC 的量化参考统一由 `pc_exact.load_integer_runtime` 加载，先运行平台探针，再安装
r08 原样复制的 `exact_mm_int64_reference.py`。跨平台完整探针：
`probe_mm_char.py --out <新的回执路径>`。`_int_mm` 只用于刻画偏差，永不作为黄金。
设备整数核及共享驱动不变；非 MAC 图算子仍为宿主浮点，production_ready=false。

r09 历史组合由 `working_combination.json` 的显式`working-r09`引用：det416 best@39 +
r08 v2-band + 冻结 board，当时待 P0-4 独立验收。该显式profile默认使用
exact量化参考，可显式`--backend fp32`；当前CLI/peer默认已切E。
`--profile frozen640-v1` 可回退原冻结参考；`recognize_exact.py` 保留原冻结 CLI 身份。
原始 r08/r09 ZIP 恢复并校验后，由 `prepare_r09.py` 在 build/ 重建缺失的 release；
模型及精修 B 的原始函数均来自验证过的交付。缺交付文件直接报错，不静默退回旧模型。

宿主原生精修默认 B：RANSAC 80 次，积分图仅覆盖粗四角 bbox 加半径和 20/21 像素余量；
保持五轮迭代及全部阈值契约。`xnp_refine_full` 仅供离线对照（240 次全图）；
C 档 48 次/两轮禁止使用。45 向量对拍与 416 回放见 r09 验证目录。

416 `.xqm` 使用软件图文件版本 2：原 48 字节头及 `XQGRPH1` magic 保留，
CRC 覆盖的 body 前加 16 字节小端 uint32 `[channels,height,width,0]`，其后是节点表及 blob。
仅接受 board192、detector416/640、classifier32；版本 1 仍按原尺寸解释。
worker 的编译尺寸与模型描述必须一致；宿主 letterbox 增加 416。
这不改变模型结果 schema、识别 ABI、FPGA 核、共享驱动或硬件地址。
预算与回归数值的适用范围见 [r09](../../docs/validation/picture-r09-offline-20261021/README.md)。

方案 A 在检测器 NMS、原图坐标映射后、分类裁剪前稳定移除检测分数 <0.05 的候选。
保留恰好 0.05 的候选及原始顺序；输出阈值、两级 NMS、冲突和拒绝规则不变。
四边形内过滤没有无损保证，本次不启用。

宿主原生几何 sidecar 保留 double 四角和来源：board_model / piece_fit / manual。
每个新 token 先试当前帧 board 模型及精修，失败一、二拍要求重拍，第三拍起调用原版
`geom_piece_fit`；只有当前帧有效的粗四角可作种子，历史缓存不自动补位。
模型粗定位失败时，第三拍允许全图检测提供圆心。少子或拟合失败请求手动四角。
缓存的 token/frame/CRC 保留原身份，只供诊断，不能推进新拍或对弈。

手动入口只消费当前冻结图。GUI 收到身份正确、count=0 的拒绝状态 8 后允许点选四角；
第 4 次点击重用相同像素和 frame、分配新 token，写入独立的
`manual-corners.txt`，再启动正常严格识别：

```text
XQ_MANUAL_CORNERS_V1 <token> <frame> <crc32-hex>
<TL-x> <TL-y>
<TR-x> <TR-y>
<BR-x> <BR-y>
<BL-x> <BL-y>
```

该独立 sidecar 的版本为 1，不更改识别 ABI 1 或模型结果 schema。拒绝身份错误、非有限数、
退化/越界四边形和尾随字段；worker 仍执行方向、归格、冲突与双将帅检查，GUI 仍执行
原 token/frame/CRC/backend/status/FEN 和盘面/状态校验。手动几何不能修改棋子类别。
宿主回放及 GUI mock 通过也不构成上板、移动棋盘、独立准确率或性能验收。
