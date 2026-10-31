# 芯弈一号图像识别软件

当前选用源码为R29：原模型加软件亮度初始化/自适应，几何失败后最多同图曝光重试一次。R35自动纠角已撤回。平台版本以根[VERSION](../../VERSION)为准（2.1）；V321、192/640/32输入尺寸和MMIO值是既有接口合同，不是待统一的发布版本号。

## 完整工程输入与入口

在WSL仓库根目录，用已有RV32 musl工具链执行：

```sh
sh linux/picture_new/build_r29.sh "$PWD" "$PWD/build/r29-local"
```

输出目录必须是不存在的新目录。入口不访问硬件，先复制并校验六个固定输入，再启用冻结R29构建选项，调用已有`build_native_coach.sh`。输出ELF位于`build/r29-local/worker/r29-worker.elf`。工具链仍使用现有约定`/opt/toolchain/bin/riscv32-linux-musl-*`；安装工具链不是删除缓存的一部分。

三份原生pack直接引用仓库已有`artifacts/main70_20261027/model-source/native_int8/`；其余固定工程输入、长度/SHA和原冻结包来源见[prebuilt/picture-r29-inputs](../../prebuilt/picture-r29-inputs/README.md)。没有复制原始照片、IPC、盘面或训练checkpoint，也没有重新训练/量化或修改模型字节。

原被ignore排除的几何C参考源现按原字节纳入Git；发布清单显式包含它、原生模型及所需工程C/H。

用户本轮明确不要求验证R29从提交重建，因此没有运行这个新增入口，也不宣布新的重建/板测验收。先前恢复源码得到`23498d99…`的字节一致回执保持原测量范围；当前板端尚未回退确认，最后交付完整SD仍为R21。

以下是早期移植和V321后端的历史说明，旧日期不代表当前运行身份。

2026-10-26：本地已接收并核验working-r14三份原生模型及三份FP32主权重；见[本地模型资产](local-model-assets.json)。原生三包SHA与下文冻结契约相同，模型输入只读，不代表重新量化或新精度验收。


2026-10-25：PN05 r04默认coach构建启用S16+指数载体、等价32位requant与分类器整数GAP；
`XQ_CLASSIFIER_S16=0`回退GAP，`XQ_INTEGER_GRAPH=0`回退旧图，legacy builder仍保留原入口。
分类器已按full裁定通过独立int64的8层四张量对拍；检测器整数化仍等r24b实测与节点类型裁定。
当前状态、仿真边界和PN05安装候选见
[整数图离线记录](../../docs/validation/picture-integer-graph-20261025/README.md)与
[r04执行记录](../../docs/validation/picture-integer-graph-20261025/full-classifier-integration.md)。

以下保留初次T1移植说明（当时目标`127ff9a5`）；当前硬件为main e7288be9 P3，
CPU60/SYS49.5/1080p30，位流6565ad37。本轮只改软件，不重新生成RTL/位流。
移植来源、冲突和验证入口：
[`docs/validation/xinyi-one-20261024/t1-software.md`](../../docs/validation/xinyi-one-20261024/t1-software.md)。

本目录没有上游携带的旧 adapter 副本。`vision32_layer.c` 复用当前
`artifacts/vision-model-20261020-adapter/runtime/xq_int8_layer.c`；
构建使用当前 graph/post/geometry 和 working-r14 三个原 pack。全部点积走 V321
raw-I32，CPU 处理原精确 bias/量化/LUT 及非 MAC 图操作，设备错误立即失败。

离线复验（Windows，在项目根执行）：

```powershell
& build/picture-tools/python3144/python.exe -X utf8 -B scripts/check_picture_r14_v321.py `
  --output build/<new-golden-directory>
& build/picture-tools/python3144/python.exe -X utf8 -B scripts/check_xinyi_v321_interface.py `
  --output build/<new-interface-directory>
```

上述工具使用真实 r14 pack、独立 ioctl 算术模拟以及 host/RV32 QEMU，不访问板卡。
默认模型与合成输入来自既有 `build/picture-merge-20261023/native-models/` 和
`build/picture-board-resume-20261023/synthetic-inputs-r01/`；允许显式传入同 SHA 的目录。
新检出必须先按现有 adapter 流程恢复冻结交付并无损导出模型/夹具，Git 清单不代替权重。
`r14-models.sha256` 对整组三 pack 关门校验，不能用其他版本的同名文件。

私有 worker（WSL，参数均为 Linux 绝对路径）：

```sh
sh linux/picture_new/build_native_v321.sh <repo> <repo>/build/<new-worker> <r14-model-directory> rv32
```

默认关闭高开销 observer；可用 `XQ_NATIVE_TIMING=1` 编译仅计数版本。
旧 `build_native.sh` 的 dense pin/DIRECT_PACK 仍是历史 CPU80 回退入口，本构建不调用它。
本 worker 保留现有 IPC 身份/帧/CRC/状态与严格几何约束；T2 新候选协议及产品调度另行接入，
不能把当前 worker 直接当成完整自动修复教练程序。

私有内核构建：`scripts/build_xinyi_kernel.py --output build/<new-kernel>`。
`platform/cpu60.dts` 是 CPU60/1080p30 模板，`contract.dtb` 只用于合同检查；
部署前必须绑定最终 rootfs 边界、软件哈希和实际位流身份，不能复制模板直接当完整启动包。
所有输出在 `build/`，无 `linux/boot` 覆盖、SD 写、JTAG 编程或 Flash 操作。
