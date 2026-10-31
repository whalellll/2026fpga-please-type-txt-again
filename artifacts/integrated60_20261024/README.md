# CPU60 集成候选

本目录用于保存新 voice_2、Picture_new 接口和 Pikafish 专用加速器的匹配候选文件。CPU 60MHz、SYS 49.5MHz、显示1080p30；没有板测或SD/Flash写入，不属于正式交付包。

- `soc_top.sbit`：本轮原生位流。来源run、大小、SHA-256、最终STA及验收边界以 `manifest.json` 为准。
- `runtime-inputs/`：已回读的11个匹配内核/启动固件/运行程序/语音模型文件，详细入口及SHA-256见该目录README和manifest。它不是完整可启动SD包；旧SD77和旧卷积程序不兼容当前硬件ABI。
- `../../docs/validation/integrated60-physical-20261024/`：最终STA、原生构建回执、快照及报告压缩副本。所有解压字节均与原生报告核对。

balanced24语音模型已包含。Picture_new采用board192、detector640、classifier32原始图接口；训练权重按用户要求暂缓，未声明实拍精度、完整FEN服务或新语音GUI已通过。应用时延、加速比与板端并发尚未测量。

完整范围、构建恢复命令和旧失败证据见 `../../docs/Integrated60_20261024.md`。不要把本候选直接替换为生产位流或以旧板测结果代替新版本验收。
