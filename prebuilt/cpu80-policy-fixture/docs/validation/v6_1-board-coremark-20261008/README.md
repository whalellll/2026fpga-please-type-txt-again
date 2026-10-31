# SOC_linux V6.1 CoreMark 板测（2026-10-08）

状态：**BOARD_COREMARK_3_PLUS_1_PASS**。用户连接开发板并授权复测后，经 COM5、115200-8-N-1 的生产 `soc>` console 完成三次 `coremark` 和一次 `coremark validate`。四次均为 4000 迭代、超过 13 秒，全部已知 CRC、成功标记和同迭代性能 final CRC 一致性检查通过。串口已经关闭，板端返回 `soc>`。

三次性能的算术均值为 **301.16680611873926 CoreMark**，即 **5.070148251157226 CoreMark/MHz**；范围为 **5.0672892561207465–5.0716341546110471**，中位数 **5.071521342739886**。按测量前确定的均值/范围报告，不挑选最快一例；验证种子不计入性能均值。

## 实测数据

CPU_HZ=59,400,000，SYS_HZ=TIMEBASE_HZ=49,500,000；GCC 16.2.0，`-O2 -march=rv32ima_zicsr_zifencei -mabi=ilp32`。存储为 boot BRAM (static)，`TOTAL_DATA_SIZE=2000` B；官方输出的 `CoreMark Size : 666` 是每个算法分配的大小。

| 运行 | 种子模式 | 迭代 | `PORT_TICKS64` | 秒数 | CoreMark | CoreMark/MHz | seed/final CRC |
|---|---|---:|---:|---:|---:|---:|---|
| 1 | performance | 4000 | 657264972 | 13.278080242 | 301.248367759 | 5.071521343 | `e9f5/65c5` |
| 2 | performance | 4000 | 657250352 | 13.277784889 | 301.255068784 | 5.071634155 | `e9f5/65c5` |
| 3 | performance | 4000 | 657813905 | 13.289169798 | 300.996981814 | 5.067289256 | `e9f5/65c5` |
| 4 | validation | 4000 | 656848044 | 13.269657455 | 301.439582273 | 5.074740442 | `18f2/5249` |

性能种子为 `(0,0,0x66)`，list/matrix/state CRC 为 `e714/1fd7/8e3a`；验证种子为 `(0x3415,0x3415,0x66)`，对应 CRC 为 `e3c1/0747/8d84`。每例均输出 `Correct operation validated.`、`COREMARK_PASS`、`COREMARK_DONE`。

按完整 ticks 计算，避免从串口已舍入的小数继续计算：

```text
seconds = PORT_TICKS64 / TIMEBASE_HZ
CoreMark = iterations * TIMEBASE_HZ / PORT_TICKS64
CoreMark/MHz = iterations * TIMEBASE_HZ * 1,000,000 / (PORT_TICKS64 * CPU_HZ)
```

## 原始证据与复现

- [board-info.log.txt](board-info.log.txt)：测试前的 `info`，确认 CPU/SYS/TIMEBASE、SYS_ID、DDR ready 和外设 ID；读取 ID 不构成外设功能验收。
- [uart.log.txt](uart.log.txt)：本次四例串口原始字节；仅将脚本输出文件的扩展名改为可交付的 `.log.txt`，内容未改动。
- [result.json](result.json)：现有 `measure_coremark.ps1` 直接产生的 PASS 结果、完整数值、CRC 和提供给脚本的磁盘产物哈希。
- [board-evidence.json](board-evidence.json)：性能均值、来源、证据文件 SHA-256 与验证范围。
- [user-provided-uart.txt](user-provided-uart.txt)：用户在复测前提供的两次性能日志，保留接收时间标签。两例为 657194017 / 657322275 ticks，分别 5.072068897628649 / 5.071079225686264 CoreMark/MHz，均值 5.071574061657456；与本次独立 3+1 组分开报告。

从仓库根执行，使用现场串口和全新目录：

```powershell
.\scripts\measure_coremark.ps1 -Port COM5 -CpuHz 59400000 -Optimization O2 -CompilerVersion 16.2.0 -TimeoutSeconds 90 -OutputDirectory '<全新证据目录>'
```

本次捕获开始于 `2026-10-08T09:01:58.7964026Z`（北京时间 17:01:58）。四条命令每条限时 90 秒，另有 10 秒提示符等待；捕获大小上限 2 MiB。脚本 DTR/RTS=false，只操作 console，不编程 FPGA、不复位、不写 Flash/SD。Ctrl+C 会关闭主机串口捕获，板上已启动的计算自行结束。

## 镜像身份及结论边界

本次复测对应的已发布提交为 `3886dea334f99981e37b07305f0c218acdcf2a26`，注释 tag `v6.1` 对象为 `48e236c3abc364c343e7e64865f924a93f2aa355`。测试时提供给脚本的本地 `soc_top.sbit` SHA-256 为 `a5defe7bcf91921b38a17d1eec7cea40a69fe8ef3f42536605c2577ab0a3d934`，`bootloader.bin` 为 `f6617eac7af1296cb8fa5c26acfc23398b5a879f801492869cb077512bc86159`，均与 V6.1 发布证据一致。用户于 2026-10-08 明确确认板上加载的是本次 V6.1 发布文件；本次串口脚本没有编程记录或 FPGA 读回，**上述磁盘文件哈希本身不证明板上镜像的逐字节身份**。

59.4 MHz 是发布配置和板上 MMIO 报告值；本次没有独立频率计测量，也没有提高频率搜索实板极限。原 PDS 记录中 59.4 MHz 为已测试档位最高完整最终 STA PASS、63.642857 MHz 最终 STA FAIL 的结论保持不变。本次仅确认当前配置下 console/CoreMark 3+1 板测通过，不代替 Linux、相机、SD、音频、网络或其他外设验收。

本次补录只更新证据和文档，RTL、生产固件、ROM、位流保持发布字节。旧固件中的 `Candidate: board validation pending.` 横幅反映 2026-10-05 构建时状态，当前验收以本记录为准。原十次迭代 RTL Pilot 仍为短时估值；板测不会把旧 `COREMARK_FAIL` 改写为仿真 PASS，也不改写源 CPU 独立 49.5 MHz 的 5.052514868 仿真成绩。
