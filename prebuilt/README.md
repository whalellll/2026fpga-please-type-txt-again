# 固定预编译输入

以下资源作为发布固定输入，由工程根目录 SHA256SUMS.txt 校验。
FPGA、bootloader、MAC/象棋示例从附带源码重建；rootfs 由基线与 overlay 精确重建。

| 资源 | 来源与复现边界 |
|---|---|
| `../linux/boot/Image` | LiteX VexRiscv linux_2022_03_23.zip 的 Linux5.14 预编译内核；未附完整内核源码/配置重建流程 |
| `../linux/images/prebuilt_2022_03_23/rootfs.cpio` | 同一上游 Buildroot2021.11-git /BusyBox1.33.1 基线；make_rootfs.ps1 使用附带 overlay 生成运行 rootfs |
| `../linux/boot/fw_jump.bin` | 本工程固定地址 OpenSBI1.3.1；附上游源码归档，独立重建尚未纳入发布回归 |
| `../linux/boot/soc.dtb` | 当前 DTS 经正式 dtc 重建的 DTB；可读结构见 linux/soc.dts；scripts/make_stable_dtb.ps1 仅为旧 bootargs 二进制修补工具，不是 DTS 编译器 |
| `xiangqi_service.bin` | 继承的串口象棋服务，原先位于 artifacts；服务端源码缺失；serial_xiangqi_service.py 默认从此处装载 |

这些边界不影响从干净交付目录构建 FPGA/bootloader。所附 Linux 介质作为固定输入保留；当前 CPU V3.1 为 M 模式 RV32IMA，尚未验证 Linux 启动，不能据此宣称可运行所附 Linux。
不将预编译服务冒充源码构建产物。来源与许可见 [第三方来源](../docs/第三方来源.md)。
artifacts/SONG.PCM 也是固定媒体输入，原始 MP3 不在仓库；使用 make_song_pcm.ps1 -ValidateOnly 检查，无需从用户桌面重建媒体。
