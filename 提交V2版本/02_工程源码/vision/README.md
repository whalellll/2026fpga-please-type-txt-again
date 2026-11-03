# YOLOv5n 中国象棋盘面训练工作区

这里是 SoC 工程内独立的模型训练工作区。已完成探索性归档训练和 2026-10-05
新数据训练；最新权重、评估及兼容性证据见文末。

## 环境

- Windows x64，项目内 Conda 环境：`vision/.conda`，Python 3.10。
- GPU：NVIDIA GeForce RTX 4060 Laptop，8 GB 显存。
- CUDA 训练：PyTorch 2.5.1 + CUDA 12.4、torchvision 0.20.1。当前 NVIDIA 驱动可运行该 CUDA runtime，无需另装系统 CUDA Toolkit。
- 训练代码：PyPI `yolov5==7.0.14`，其 wheel 包含上游 YOLOv5 提交 `5deff1471dede726f6399be43e7073ee7ed3a7d4` 的训练代码。该 PyPI wheel 由第三方打包，安装时按 PyPI 发布的 SHA-256 校验；训练代码采用 AGPL-3.0。
- 默认输入 320，目标任务为中国象棋棋子检测；红黑双方各七类，类别顺序见 `dataset/classes.txt`。
- 原始图片、标签、训练结果和权重默认不纳入 Git。

## 阶段 2 结构契约与候选滑动窗口

训练前可运行 `vision/.conda/python.exe vision/export_layer_contract.py`，从当前安装的
`yolov5==7.0.14` 构造 **未训练** 的 14 类 YOLOv5n，以 1×3×320×320 虚拟张量导出
`build/vision/yolov5n_14_320_contract.json` 和逐算子 CSV。清单含配置、类别和模型代码
SHA-256，183 个实际执行的叶算子形状，以及三个 Detect 原始输出形状；它不包含训练权重、
量化比例或准确率。`python sim/bench_yolo_stage2_traffic.py` 另导出 60 个卷积算子的
逻辑字节预算，表中的 DDR 字节数不是板端测量值。

输入契约采用 BGR 源图转 RGB，等比例 letterbox 到 320×320，填充值 114；`auto=False`、
`scaleFill=False`、`scaleup=False`、stride 32。CPU 浮点参考为 NCHW、`uint8/255`；
候选设备字节布局为 NHWC4，尾通道填零。窗口坐标按 `(输出 y, 输出 x, 通道块,
卷积核 y, 卷积核 x)`，卷积输出按 `(输出 y, 输出 x, 输出通道)`；Detect 原始张量按
`(batch, anchor, grid_y, grid_x, prediction)`。实际相机图像转换尚未接入该契约。

`rtl/mac_accel/mac_conv_window.v` 是一次处理一个 4 通道块的独立候选模块：1×1 直通，
3×3/6×6 使用六行缓存，支持 stride、padding、ready/valid 背压和 flush。
运行 `bash scripts/test_mac_conv_window.sh` 可复现 Icarus 定向仿真和周期/停顿计数；
`sim/gen_yolo_window_vectors.py` 还会校验固定种子的双通道块 Python 黄金向量，
并让 RTL 逐 tap 对照。
PDS 独立布局布线以默认 320 宽、10 ns 时钟得到 2 DRM、501 LUT、
慢角 WNS +0.870 ns；顶层 IO 没有整机约束。这不是整机时序或板端结果。
复现命令为 `powershell -ExecutionPolicy Bypass -File scripts/check_mac_conv_window_pds.ps1`。
这段独立模块结果保留为 T2 基线；整机 DMA 接入见下文。多通道块的整层输出
顺序仍需后续 MAC 接入落实。

独立窗口板测已通过：`scripts/test_mac_conv_window.sh` 覆盖 1×1、3×3、6×6、
通道尾块、边缘补零、背压、flush、连续配置，以及故意篡改预期 tap 的
FAIL 标记。使用 `scripts/build_mac_conv_window_board_candidate.ps1` 生成
PG2L100H-6-FBG676 临时位流，仅经 JTAG 写入易失 CRAM；D18/C22/C24
分别用于 27 MHz 时钟、复位和 115200 串口发送。实测 COM17 输出：
`WINDOW_BOARD_PASS C0=0010/0004 C1=0060/0012 C2=0060/0012 C3=01E7/006C`。
位流 SHA-256 为 `a9504c073407fdf779f1a3fdd7b79d9473dbdc49587601ed1cc941a6fa31e25e`，
PDS WNS +28.060 ns；源/预期向量哈希和原始日志路径见
`docs/YOLOv5n_Stage2_TODO.md`。本测试顶层独立于 SoC，尚无 DDR/DMA/MAC 测量。

## 阶段 2 卷积 DMA 与权重双缓冲候选

T3 在旧密集 MAC 和 Pikafish MMIO 不变的前提下，新增 `0x40–0x7f` 卷积窗口寄存器组。
`0x58` 为卷积输入 DDR 源地址，DMA 的目的端固定为滑动窗口；`0x5c` 为权重源地址，
`0x60` 为将来紧凑输出预留的 DDR 目的地址。旧 `OUTPUT_DST(0x24)` 仍是旧密集 MAC
的 DDR 输出地址。Linux 仍使用单一 `/dev/pango-mac0` 驱动和设备锁；独立 ABI2
`PANGO_MAC_IOC_RUN_CONV` 的 `WINDOW_ONLY` 模式只返回 tap 校验和与流量/周期计数，
不产生卷积结果，也不写输出 DDR。这个模式不能证明 T4 的整数 MAC、紧凑输出或帧率。

`bash scripts/test_mac_conv_stage2_dma.sh` 覆盖尺寸和地址拒绝、4 KiB 突发边界、
错误/超时恢复、尾通道脏数据清零、双 bank 叠加读写及模型代次隔离；完整 SoC
回归运行 `scripts/run_all_tests_wsl.ps1`。Linux 5.14 候选内核可用
`scripts/build_mac_conv_stage2_kernel_candidate.ps1` 编译；板端静态程序与诊断
根文件系统分别由 `scripts/build_mac_conv_stage2_baremetal_test.ps1` 和
`scripts/build_mac_conv_stage2_rootfs_candidate.ps1` 生成。它们均留在 `build/vision`。

完整 SoC 候选位流由 `scripts/build_mac_conv_stage2_soc_candidate.ps1` 独立构建。
PDS 2022.2-SP6.4 实测 WNS +4.912 ns，185 APM、32,767 LUT、28,635 FF、
152.5/155 DRM；位流 SHA-256 为
`0fb855047b6e50aac2d342a13b8ad8dcf9bd07d1ebe2298b24f0e06997d17f03`。
仅经 JTAG 写入易失 CRAM，器件 ID `0x00602899`、done bit 1。COM17 板测
`MAC_CONV_STAGE2_BOARD_PASS` 覆盖 1×1、3×3 尾通道块、6×6 和首层 320×320；
首层记录 921,600 tap、输入 DDR 读取 409,600 B、权重读取 3,456 B、
权重复用 25,600 个输出窗口、1,342,255 周期、tap 校验和 `0008c8c8`。
旧密集 MAC 的同一候选位流复测 `MAC_DDR_SOC_TEST_PASS`，279 周期。
原始日志与测试镜像哈希见 `docs/YOLOv5n_Stage2_TODO.md`。Linux ABI2 尚待
T5 板端回归；这些窗口计数不包含乘加、量化、SiLU 或输出写回。位流构建时
工作树还包含独立的音频候选改动；T3 提交只收录卷积相关文件，最终合并基线
将在 T5 重新构建与板测。

## 阶段 2 整数计算与紧凑输出候选

T4 把窗口 tap 接入有符号 W8A8 乘加，单个输出像素的结果在 INT32 中累加，
加每通道 INT32 bias 后按每通道 0–30 位右移，采用远离零的半值舍入，最后饱和到
S8。输出按 NHWC 连续字节写入 DDR；末尾不足 4 B 的写入使用 byte strobe。
SiLU 仍由 CPU 在卷积输出之后执行，硬件不以 ReLU 代替。

当前可运行的硬件 tile 为输入通道不超过 4、输出通道不超过 16、
扁平化 K 不超过 128，且只支持 1×1、3×3、6×6 的单通道块。
大于 256 的 K 在 CPU 黄金参考中按最多 256 个标量一段保存 INT32 部分和，
所有段相加后才做一次 requant；当前硬件不接收这种深层作业。
`vision/stage2_traffic_report.py` 将 60 个 Conv2d 的逻辑流量与实际计数分列，
当前只识别首层为可直接运行的 tile，其他 59 层保留未测状态。
可复核的表格为 `vision/evidence/yolov5n_stage2_traffic_20260924.csv`；
首层实测行引用 `vision/stage2_compute_board_measurements.json`，其计数与
`vision/evidence/stage2_compute_board_20260924.log` 的串口标记逐字段核对。
其余层只有逻辑预算，实测 DDR 字节、停顿和周期列为空。当前同形状旧路径
基线为每个输出 INT32 的 4 B 逻辑写量；旧路径没有完整首层硬件周期实测。

`bash scripts/test_mac_conv_stage2_compute.sh` 覆盖固定 W8A8 黄金向量、
1×1 尾通道、3×3 边界、6×6×3 首层核、跨像素字节打包、写回错误/中止恢复
以及计算时改写下一层描述符。SoC AXI RAM 的 1×1×4→16 同形状样本
中，旧路径读输入 8 B、权重 128 B、写输出 64 B、161 周期；
最初四输出通道并行候选为 4 B、128 B、16 B、55 周期。这只是小样本
仿真基线，不是整层帧率。当前计算核每周期更新一个输出通道，使用四个
S8 乘法器，并只暂存 16 通道所需的 512 位权重。
`bash scripts/test_mac_conv_full_layer.sh` 对完整
320×320×3、6×6、stride 2、padding 2 首层进行 SoC AXI RAM 仿真：
读取输入 409,600 B、权重 3,456 B，写回 S8 输出 409,600 B，
输出 CRC32 `eb240272` 与独立 CPU 参考一致，当前实现作业
14,405,407 周期，低于测试先定的 16,000,000 周期上限；最初四输出通道
并行候选为 6,162,199 周期。资源目标测试先在旧候选的 203 APM、
38,284 LUT 上按预期失败，当前映射为 191 APM、37,358 LUT，通过
195 APM、37,500 LUT 门槛。最初四输出通道并行候选的探索性 CRAM
板测也得到同一 CRC、7,147,707 周期，但其 DDR PHY setup WNS 为
−0.171 ns，且不代表当前 RTL；该板测不计作时序合格候选的最终验收。

当前串行计算核的完整 SoC PDS 报告为 `All Constraints Met`，全局 slow corner
setup WNS +0.558 ns，191 APM、37,358 LUT、32,103 FF、152.5/155 DRM；
位流 SHA-256 为
`56ac5655b1923980df87120e84df4f4ce318caab6ef4b1ae1da1eb0a85706a92`。
该位流只经 JTAG 写入易失 CRAM，器件 ID `0x00602899`、done bit 1。
COM17 裸机板测 `MAC_CONV_COMPUTE_SUITE_BOARD_PASS` 覆盖 1×1、3×3、6×6、
尾通道和完整首层；首层实测输入 409,600 B、权重 3,456 B、输出 409,600 B、
921,600 tap、25,600 个窗口，CRC32 `eb240272`、15,466,918 周期，
停顿 14,119,561 周期。同位流旧密集 MAC 自测返回
`MAC_DDR_SOC_TEST_PASS`、279 周期。原始日志保存在本地
`build/vision/mac-conv-compute-clean/`，Linux ABI 板测结果另行记录。

## 创建环境

在工程根目录运行：

```powershell
.\vision\setup_env.ps1
```

脚本在 `vision/.conda` 建立独立环境，下载并校验 PyTorch 官方 CUDA wheel 和 PyPI YOLOv5 wheel 的 SHA-256，然后安装依赖。已有锁文件时优先按 `vision/requirements-win-cu124.lock.txt` 和 `vision/conda-win-64.lock.txt` 重建；没有锁文件时使用 `environment.yml` 和 `requirements-win-cu124.txt`。官方 CUDA wheel 使用并行分段下载，缓存放在被 Git 忽略的 `vision/.wheels/`。脚本会实际运行 CUDA 矩阵乘法及 torchvision NMS，并生成当前工作区绝对路径对应的 `vision/config/chess14.yaml`。

PyTorch/torchvision/CUDA 组合参照[官方历史版本安装矩阵](https://pytorch.org/get-started/previous-versions/)。YOLOv5 训练入口和自定义数据格式参照[上游训练代码](https://github.com/ultralytics/yolov5/blob/5deff1471dede726f6399be43e7073ee7ed3a7d4/train.py)及[自定义数据说明](https://github.com/ultralytics/yolov5/wiki/Train-Custom-Data)。

## 数据目录与标注

```text
vision/dataset/
├── images/{train,val,test}/
├── labels/{train,val,test}/
├── classes.txt
└── chess14.yaml.template
```

每张图片对应同名 YOLO 标签 `.txt`。每行格式为 `class_id x_center y_center width height`，坐标相对图片宽高归一化到 `[0,1]`。训练集和验证集都至少需要一张图片；测试集可以暂时为空。类别 ID 按 `classes.txt` 顺序标注为 0–13。

从棋盘视频采集数据时，按棋盘、拍摄批次或视频划分 train/val，避免同一连续视频的相邻帧跨集合造成验证结果虚高。图片先保持原始分辨率，训练时统一 letterbox 到 320，不要预先拉伸棋盘比例。

## 棋子检测结果映射到棋盘

YOLOv5n 一次前向就会给每个棋子输出类别、置信度和边界框。后处理取棋子框中心，把图像坐标映射到象棋棋盘的 9 列 × 10 行交叉点，再生成 Pikafish 所需的盘面数组；这里不需要再运行一个棋盘检测网络。棋子框中心与交叉点的映射可用固定机位下的一次性标定得到，最多约 32 个检测框的坐标换算开销很小。

相机和棋盘固定时，不需要给每张训练图额外标注棋盘角点。若实际使用时棋盘或相机位置会变化，再重新标定；有明显透视时，用一次四角标定求单应变换后复用即可。象棋棋子落在交叉点上，不是格子中心。

放入数据后先检查，再训练：

```powershell
.\vision\check_dataset.ps1
.\vision\train.ps1
```

训练默认从 COCO 预训练 `yolov5n.pt` 微调：320 输入、200 epochs、batch 16、GPU 0。首次运行会下载预训练权重；也可以把已有权重放到 `vision/weights/yolov5n.pt`。结果写入 `vision/runs/train/`，其中 `weights/best.pt` 是候选模型。没有图片和标注前不要启动训练。

8 GB 显存若出现 CUDA out-of-memory，可将 `train.ps1` 的 `BatchSize` 降到 8 或 4。训练使用 FP16 自动混合精度；设备端 W8A8/W4A8 量化属于训练后的单独校准和导出工作，不等同于训练 AMP。

## M0 candidate audit

`probe_model_m0.py` reads a trusted local YOLOv5 checkpoint and exports its
SHA-256, 14-class order, 320 input, Detect anchors, strides and raw shapes.
Use the Python environment containing the pinned YOLOv5 package. It loads a
PyTorch pickle, so only pass a checkpoint produced or verified locally.

```powershell
python -m unittest discover -s vision -p test_model_m0_audit.py -v
python vision/probe_model_m0.py --model <best.pt> --output build/vision/m0/metadata.json
python vision/model_m0_audit.py --model <best.pt> `
  --metadata build/vision/m0/metadata.json --dataset-root <dataset-root> `
  --data-config <chess14.yaml> --class-file <classes.txt> `
  --capture-groups <groups.json> --golden-boards <boards.json> `
  --report build/vision/m0/audit.json
```

`groups.json` maps every `images/{train,val,test}/name.png` to its real game,
video or acquisition-batch ID. The same ID may not cross splits; matching image
bytes are also rejected. `boards.json` is a nonempty list of test-image answers:

```json
[{"image":"images/test/game17.png","roi_xyxy":[500,40,1240,690],
  "corners_xy":[[520,60],[1220,60],[1220,670],[520,670]],
  "fen":"4k4/9/9/9/9/9/9/9/9/4K4 w - - 0 1"}]
```

The FEN above only illustrates the file schema. A production answer must come
from the pictured board and a separately known side to move. The current local
ROI candidate has 85 train and 10 test images whose filenames share one camera
date, with no per-game capture groups, no separate val images, and a config that
aliases val to test. The strict
audit therefore fails; these images do not establish the M0 acceptance set.

## Archived LabelMe exploratory training

The archived `archive/2026-09-28/imported_misc_20260926/1` folder has 95
annotated PNG/JSON pairs already used by the older random-split model, plus 97
PNG files without labels. `m0_exploratory_import.py` makes a new candidate under
`build/vision/m0/` without changing the archive. It orders annotations by
capture filename, uses 65/12/12 train/val/test images, excludes two three-image
gaps, crops `[500,40,1240,690]`, and removes exact duplicate boxes while
recording their number. Give each rerun a new empty output directory.

```powershell
python -m unittest discover -s vision -p '*m0*.py' -v
python vision/m0_exploratory_import.py `
  --source G:/fpga/archive/2026-09-28/imported_misc_20260926/1 `
  --output build/vision/m0/temporal_trial_dataset_clean `
  --crop 500 40 1240 690 --train-count 65 --val-count 12 `
  --test-count 12 --gap-count 3
```

The 200-epoch, 320-input, batch-8 run starts from the local COCO `yolov5n.pt`,
not the older Xiangqi checkpoint: the latter has already seen images in this
trial's validation/test sets. The new local best checkpoint is
`build/vision/m0/runs/temporal_roi320_e200/weights/best.pt` (SHA-256
`8ff15d34885fe98e2de4e794dc679f93ff04155d4047f19029b1257f87d10932`).
The clean candidate contains 65/12/12 images and 1,799/376/276 boxes. The
12-image test yielded mAP@0.5 `0.37996` and mAP@0.5:0.95 `0.27895` on PC/GPU.
The input and training parameters, data hashes, metrics and limitations are
recorded in [the model TODO](../docs/YOLOv5n_Model_Integration_TODO.md).

The training command, run from `G:/fpga/performance_soc_linux/vision` with the
existing pinned environment, was:

```powershell
& .\.conda\python.exe -m yolov5.train `
  --data G:/fpga/performance_soc_linux_stage2_integration/build/vision/m0/temporal_trial_dataset/chess14_trial.yaml `
  --weights G:/fpga/performance_soc_linux/vision/yolov5n.pt `
  --img 320 --batch-size 8 --epochs 200 --workers 4 --device 0 `
  --project G:/fpga/performance_soc_linux_stage2_integration/build/vision/m0/runs `
  --name temporal_roi320_e200
```

The two exact duplicate labels were found during the separate test evaluation.
The corrected dataset is `temporal_trial_dataset_clean`; its train/val files
are byte-identical to those used for training, and only two test labels changed.
The clean test was rerun with the same checkpoint and 276 distinct boxes.

All files have the same camera/date prefix and lack per-game provenance. The
strict M0 audit rejects the cross-split capture group. This checkpoint is an
exploratory candidate and has no independent-board/FEN acceptance.

## Exploratory trained first-layer MAC probe

The trained_conv_tile.py tool fuses Conv+BN from the exploratory checkpoint,
converts one real test image through 320 letterbox and RGB/S8 packing, and
exports a 16x16 first-layer tile. The output is an exact integer CPU oracle for
ABI3: 3 input channels, 16 output channels, 6x6 kernel, stride 2, padding 2.
The fixed right shift of 10 is only for the hardware connectivity test. M2
calibration and end-to-end accuracy are still open.
The three correctness/performance unit tests first failed as expected because
the exporter did not exist, then passed after implementation. Export took
5,280.07 ms on this PC, including trusted checkpoint load and CPU oracle.

Run the unit test, exporter, SoC simulation, and bare-metal build in this order:

1. Use the pinned model environment to run vision/test_trained_conv_tile.py.
2. Run vision/trained_conv_tile.py with the exploratory best.pt, the first
   sorted image in build/vision/m0/temporal_trial_dataset_clean/images/test,
   and output directory build/vision/trained-conv-tile.
3. In chiplab_sim WSL, run scripts/test_trained_conv_tile.sh from the repo root.
4. Run scripts/build_trained_conv_tile_baremetal.ps1 with PowerShell execution
   policy Bypass.

The generated manifest.json records the model/image/vector hashes and byte
counts. The probe source image SHA-256 is
9b85a032ddb7121b4f06ea464f49f2f02b0113681a5f9f864646965e6f03aaed;
the output is 1,024 B, SHA-256
82df885c65209a72ca9f36768d782d32e677e428f01ace5f86409122ba9496a4,
CRC32 c49864b6. SoC simulation compared all output words and measured 35,621
job cycles. The bare-metal image is
build/vision/trained-conv-tile/mac_conv_trained_tile_test.bin (SHA-256
b9be42f594e528dc392dcf8877f81f0c5eb32fe52b717f14d9048a51969a34fa).
The matching Stage2 CRAM bitstream is SHA-256
56ac5655b1923980df87120e84df4f4ce318caab6ef4b1ae1da1eb0a85706a92.
The exact vector files are tracked at sim/vectors/trained_conv_tile, so focused
simulation and the bare-metal build also run in a clean checkout without
the local exploratory checkpoint. Regeneration from the local checkpoint
matched all tracked vector files byte for byte.

For SD board acceptance, copy linux/boot/xqmodel.bin and the generated
mac_conv_trained_tile_test.bin to the root of a verified FAT32 SDHC card as
xqmodel.bin and xiangqi.bin. The bootloader xqboot command loads the model
for its existing validation contract and starts xiangqi.bin at 0x01000000.
The board program compares every output byte and checks DMA/tap/cycle
counters before printing PASS. Use scripts/serial_trained_conv_tile_sd_accept.ps1
to interrupt auto boot, issue xqboot, and record the log. This uses the SD
read path and serial console; it does not send the test image through XMODEM.
The prepared card was inserted in J10, the matching Stage2 bitstream was
programmed to volatile CRAM, and the final board run passed with output CRC32
c49864b6 and 38,139 compute cycles. See the
[SD board evidence](../docs/YOLOv5n_Trained_Conv_SD_Board_Evidence.md).

## Tracked Stage 2 structural contract

The untrained, pinned 14-class 320x320 operator manifest is tracked as
ision/yolov5n_14_320_contract.json (SHA-256
48da19517558191a022dc7f67f2bcb5218b89c0b507c2a29dd936ed545821b16).
The traffic report and benchmark use this file by default, so clean
checkouts and delivery archives run without a local model export. It contains
no trained weights or accuracy claim. export_layer_contract.py can regenerate
a copy under uild/vision in the pinned model environment.

## 2026-10-05 新数据 YOLOv5n 训练

`G:/fpga/数据集` 的 1,042 对 PNG/LabelMe JSON 已完成只读导入。
按序列分成 720 train、141 val、141 test，边界排除 40 帧，去除 2 个重复框。
固定 14 类顺序、320 输入、原 anchor/stride、SiLU 和 60 个卷积，GPU 训练 200 轮，
实际耗时 778.667 s。初始化采用未见过棋子数据的本地 COCO 权重。

固定 320×320、batch 1、FP32 评估：val mAP@0.5=0.83427、mAP@0.5:0.95=0.66864；
test mAP@0.5=0.62950、mAP@0.5:0.95=0.40993。黑炮/黑马等类别仍有明显精度短板。
这是未知同采集组的留出结果，独立批次与 FEN 验收尚未通过。

最新权重：`build/vision/train_20261005/training_fullframe/run/weights/best.pt`，SHA-256
`463b20a814b07ac5aa7da3f20a07a0202368cc3c1716ca52efa0555927958c9a`。
静态三检测头 ONNX 在 `build/vision/train_20261005/evaluation_final`，opset 12、无 NMS，
五图与 PyTorch 对照最大误差 `3.6239624e-5`。真实模型 183 个叶算子与当前结构契约一致。
新权重首层整数 tile 的 SoC 仿真逐字节通过，21,797 周期、CRC32 `28dae903`。

预处理使用**完整画面** letterbox 320，旧训练 ROI 不适用于这批盘外标注。
模型仍需完整 W8A8 校准和深层硬件运行时接入。PC/GPU 推理时间不是板端时间。
20 项相关测试通过；训练/导出/首层仿真进程均退出 0，没有硬件源或生产镜像变更。
复现命令、每类结果与哈希见
[训练记录](../docs/YOLOv5n_Dataset_Training_20261005.md)。

## 当前加速器的实际模型覆盖

当前卷积 ABI3 为 Cin≤4、Cout≤16、K≤128，已训练 YOLOv5n 的 60 个卷积
只有首层形状能直接运行，占卷积乘加量 8.4577%。其他 59 层、完整 W8A8 校准
和模型运行时尚未接入，`.pt/FP32 ONNX` 不是硬件可直接执行的设备模型。
新训练/导出工具显式报告 `device_model_ready=false`。

保持低 LUT 的优先适配方案是复用旧密集 MAC 的 S8S8/INT32 路径：
CPU 展开输入，按实际驱动每作业 16 像素、256 通道分块，汇总 INT32 部分和后
只做一次 bias 和 requant；SiLU 及其他非卷积算子继续实现受验证的 CPU 路径。
当前分块规划为 6,956 作业/帧、最大作业 90,112 B，完整图后端尚未实现，不能据此推断性能。
详细能力、拒绝规则和并发/ABI 要求见
[加速器兼容性记录](../docs/YOLOv5n_Accelerator_Compatibility.md)。

## 现有密集 MAC 分块试验（2026-10-05）

已实现 `dense_tiled_conv.py` 的打包/整数参考及
`linux/mac_accel/pango_mac_tiled_conv_test.c` 的严格设备后端。
从新训练权重提取 6 组层级探针，覆盖 K=1152、Cin=512、Cout=256/57、
跨像素及 K 块；19 个作业在当前 SoC RTL 逐元素通过，C 宿主重复 3 次也全部通过。
35 项相关测试、原密集 MAC SoC 回归、MAC 调度及音频驱动检查通过。

六个小特征块合计 646,929 周期，按候选 49.5 MHz 折算 13.0693 ms，
只表示仿真 MAC 作业时间。完整量化/SiLU/图运行时尚未完成；板卡 JTAG 无设备，
串口无响应，实板平均时间未知。硬件、驱动及原 ABI 无修改，无新增 LUT。
复现命令、每层测量和板端运行方式见
[分块卷积试验](../docs/YOLOv5n_Dense_Tiled_Probe_20261005.md)。
