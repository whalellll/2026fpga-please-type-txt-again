# CPU 70.875 MHz 实板测试（2026-10-18）

## 范围与身份

用户要求进行 CoreMark 和功能上板测试。FTDI JTAG 和 CP210x COM17 已枚举，
PDS 扫描恰好一颗 PG2L100H，ID `0x00602899`，易失 CRAM 编程成功、DONE=1。
各次重载均使用同一位流，编程前后均通过冻结工程 CPU/ROM/STA/输入输出审计。

- 位流 SHA-256：`0460ab2cf857c406f9018822ff8dc90b7ee8ab620ec03d49ac98aec5f754d84a`。
- FPGA 构建运行号：`4b7d86bb5f2a4e638b43359196ea52b3`。
- CPU 原提交 `45d24b9...`，RTL SHA-256 `80d88b8edab534e04d1e3f1488e72832c8d12194d711db7b060a11c75bee5464`。
- 实板读取 CPU=70,875,000 Hz，SYS/MAC/TIMEBASE=49,500,000 Hz，DDR ready。
- CoreMark 固件来自冻结审阅目录 `G:/fpga/b70r1`，GCC 16.2.0、O2、RV32IMA/ILP32，
  实际固件及日志哈希记录在 [CoreMark 结果](validation/cpu70-board-20261018/attempt01/coremark70/result.json)。
- Linux 使用原语音内核、官方 PFF1/PFA1、原 GUI 程序和 SD77 语音权重。
  本次没有修改 FPGA RTL、重新 PnR、写入 SD 或配置/SPI Flash。

## CoreMark

使用生产 bootloader 的 `coremark` 三次及 `coremark validate` 一次，均为实板执行，
每次 6000 iterations。官方 CRC 与最终 CRC 检查通过，CLINT 64 bit 计时与低 32 bit ticks 一致。

| 运行 | 有效秒数 | CoreMark | CoreMark/MHz |
|---|---:|---:|---:|
| performance 1 | 16.037158 | 374.131119 | 5.278746 |
| performance 2 | 16.032922 | 374.229971 | 5.280141 |
| performance 3 | 16.032155 | 374.247871 | 5.280393 |
| validation | 16.110600 | 正确性通过 | 不计入性能均值 |
| 性能均值 | — | **374.202987** | **5.279760** |

三次性能加一次正确性均超过 10 秒。没有运行 RTL CoreMark。
本次未对原 59.4 MHz 位流做同会话 A/B，不能把历史不同候选的成绩作为严格不回退证明。

## 已完成的初轮功能检查

- bootloader 系统 ID、CPU/SYS 频率、DDR、SD、MAC/音频 MMIO ID 正确。
- 基础 MAC DDR 测试通过，`MAC_CYCLES=255`，输出全部正确。
- 六个 SD 载荷均完成读取及 CRC32 校验，包括 68,122,688 B 官方 PFF1 和
  34,603,072 B 攻击表；原启动文件保持不变。
- 修正 RAM 装载器后进入 Linux 5.14 root shell，设备报告 RV32IMA、Sv32，
  `/dev/pango-mac0` 和 `/dev/pango-audio0` 注册成功。
- 官方 Pikafish Stage B verify 模式完成 `h2e2 → a6a5`，硬件与 CPU FC0 一致。
- 首轮 driver 权重常驻测试通过：两 fd、400 个并发作业、快照不可变、覆盖后恢复正确。
- 初轮空闲录音 32,000 samples / 2000 ms、overflow=0；峰值 322，非零样本 31,967。
- 初轮 gather 路径走棋与录音并发：96,000 samples / 6002 ms、overflow=0，峰值 1414，
  `h2e2 → a6a5` 合法，Stage A gather 与 Stage B verify 均有硬件作业，重新开始检查点通过。
- 用户明确确认 HDMI 显示棋盘。语音保持 display-only，没有通过语音走子。

上述初轮包含分别执行的 driver 与 mmio-shadow 模式；不能将其混称为统一 driver 路径。
最终 driver-only 复测见后续结果小节。

## 本次发现并修正的启动软件问题

### 1. 未缓存 DDR 的 CRC 尾字节访问

旧 RAM 装载器成功读取所有 SD 文件后返回 ROM 控制台。保留原始失败日志并读取陷阱寄存器：
`mcause=5`、`mepc=0x01003144`、`mtval=0x9a000988`、`mtvec=0x1c000000`。
原 ELF 反汇编证明该指令为 `lbu a5,0(a1)`，发生在 DTB 尾部不足四字节的 CRC 处理。

`publish_clock_payload` 后的直接 `crc32_fast(uncached, full_length)` 改为复用已有
`copy_to_uncached`：完整部分按字读取，最后一个字读取后通过移位处理有效字节。
CRC 期望值保持不变，不通过跳过校验绕开异常。
源码入口为 `linux/opensbi/build_clock_candidate.py`，两项回归先失败再通过。
旧加载器保持原哈希，新 CRC 修正版单独生成，未覆盖冻结包。

### 2. driver Stage A gather 的设备树绑定缺失

首次严格 driver 走棋显示 Stage A 使用 dense 备用路径。
MMIO 能读到 gather ID `0x50464741`、版本 `0x00020000`，但原 DTB MAC `reg`
长度只有 `0x100`，`memory-region` 只有 scratch。驱动要求长度至少 `0x200`，
并以第二个 phandle 确认已保留的 PFF1 物理模型区，才公开 gather feature。

修改候选 DTB 为 `reg=<0x1fe10000 0x200>`，第二个 memory-region 引用
`pikafish-pff1@10000000`；保持已有模型物理地址、保留范围和接口整数规则。
同步维护 `linux/soc.dts` 及 RAM clock-boot 生成器，三项绑定检查通过。
新 RAM overlay 的 GUI 启动取消强制 `mmio-shadow`，设置 REQUIRE_DRIVER，
附带 gather/resident/scheduler/pool 实板工具，再次启动验证。

### 各次软件候选的身份

| 软件组合 | loader SHA-256 | 说明 |
|---|---|---|
| 原冻结 GUI restore | `f83e058395c5a8321a5cf2c4e5b126457df8d88b097ab43ca7548a0d30413b32` | 已记录 DTB CRC 尾字节访问异常 |
| word CRC 修正 | `7be99efe7526261d5b0647e888669c9556075bc23533136a141a045836d02fa9` | 初轮 Linux、走棋、采音通过 |
| driver gather 修正 | `44875e42fb1ed29270b0205195c47f45df9d5e90bad5c2092a36db9864a7376e` | 最终 driver-only 复测组合 |

最后一组 overlay 为 317,440 B，CRC32 `3276ae7f`，initrd end `0x0385b6b8`。
OpenSBI 保持 CPU/SYS 换算 44/63，FPGA 位流和模型权重未改变。

## 最终 driver-only 结果

| 检查 | 实板结果 |
|---|---|
| GET_INFO | ID `4d41434b`、version `00020100`、features `00000067`，含 gather/resident |
| driver gather 黄金比对 | 1/3/256 terms，各 1024 lanes，全部相等；cycles 4235/5870/222332 |
| gather 非法描述符 | EINVAL，输出哨兵不变，通过 |
| driver resident | 两 fd、400 个并发作业、快照不可变、恢复正确，再次通过 |
| 三进程×两线程调度 | **未通过**，value=4、loop=0、lane=0，got=0、expected=16 |
| 8 上下文池隔离 | **未通过**，释放/重开 slot0 后仍存活映射的首尾哨兵错误 |

resident 自报 100 次平均：普通 RUN 5508 us、RUN_RESIDENT 1664 us；这是当前
内核/模型下的局部 ioctl 结果，非完整 NNUE、非与旧位流 A/B，不能作为整模型倍率。

调度测试失败后仍打印 shell 命令结束码 1，随后新会话对回车和 Ctrl+C 均无响应，
6 秒观察未收到 UART 字节。没有重复假称成功，保留首次失败日志及后续空捕获，
通过重新加载同一位流恢复系统。失败原因尚未确定，不能断言是 MAC、驱动、
CPU 缓存/MMU 或时序中的某一项；此候选**不满足全功能验收**。

恢复到全新 Linux 会话后，pool 测试另报 `live contexts are not isolated`。
该程序只做 open/mmap、首尾哨兵及 slot0 复用，**没有提交 MAC 作业**。
这提供了独立于乘法阵列的错误证据；优先检查驱动私有 shadow 页的映射/复用，
以及 CPU MMU/TLB/缓存可见性。不能只因首次错在 S16 就断言 MAC 算术错误。
pool 失败后 UART 同样未给出后续命令结果，停止进一步压力测试并再次重载恢复 GUI。
官方全 bucket 工具及后续重跑未取得执行/通过证据，不计通过。

### 最终恢复状态

再次加载同一位流和 driver-gather RAM 启动组合，Linux root shell 正常返回。
最后一次只读状态检查确认 GUI PID94、语音 PID100 存活，官方 Pikafish engine=ready、
初始 FEN、nodes=0；`backend=driver`，`PIKAFISH_STAGEB_KERNEL_RESIDENT bytes=593920`，
Stage B `mode=1`，语音仍为 SD77/display-only，未通过语音走子。
证据为 `linux-boot-final-restore.log` 和 `final-status.log`。
恢复没有重跑已知失败的压力测试，也没有消除/覆盖其失败结论。

后续排查还应做单进程 S16、S16/INT8 模式切换、同进程多 fd、单线程多进程对照，
分别核对输入/权重/输出与 owner，定位后再改 RTL 或驱动。禁止用降低并发规模
替换原 3×2×64 验收条件。恢复后的其余独立测试与 GUI 状态继续记录在本目录。

## 证据和限制

原始编程、失败及修正后的启动、CoreMark、MAC、采音和走棋日志位于
`docs/validation/cpu70-board-20261018/attempt01/`；构建清单绑定每个 RAM 软件产物。

本次不是正式 BoardRelease：完整 Windows 发布回归、匹配旧候选 A/B、
完整 NNUE 延迟基准、图像识别整图及 30 fps 尚未验收。
语音采集/IPC 通路通过不表示识别准确率通过；旧 SD77 数据的缺类限制仍在。
既有 187 项外部 I/O 时序约束缺口保留，不能用此次板测删除。
本次配置是易失 CRAM 与 RAM 装载，断电不保留；SD 启动文件没有改成新频率组合。
