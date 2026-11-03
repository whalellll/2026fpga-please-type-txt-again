# 芯弈一号 V321 软件候选

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
