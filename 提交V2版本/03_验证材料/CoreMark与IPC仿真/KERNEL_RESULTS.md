# CPU125 CoreMark 计算内核 IPC 与低窗口 IPC 解释

固定版本：dfb849e6a6df77eb90d1a066c1b8bc3c493f1a08；CPU125MHz、SYS49.5MHz；发布CPU RTL与自动校准ROM未修改。

完整100次迭代计算内核平均IPC = 24,735,238 / 16,524,628 = **1.496871094**。

| 自动校准调用 | 完整迭代数 | CPU周期 | 有效提交数 | IPC |
|---|---:|---:|---:|---:|
| 1 | 10 | 1679730 | 2473417 | 1.472508677 |
| 2 | 100 | 16524628 | 24735238 | 1.496871094 |

100次迭代区间：零提交2049542周期，单提交4214934周期，双提交10260152周期；双提交占62.0901%，零提交占12.4030%；提交异常0。

## 为什么三个1024点窗口明显偏低

前一轮选择的是首次进入链表、矩阵内联路径、状态转换函数的短窗口，包含256个触发前周期。它们受到首次执行代码的取指缓存请求/回填影响，不是完整算法的稳态平均。补测加入内部Icache状态、指令缓冲是否为空、ROB是否为空、ROB头是否未完成等观察信号，并确认三组旧采样的全部原有字段逐行完全复现。

| 窗口 | 零提交周期 | 同时Icache请求/回填 | 同时Icache请求/回填且IB、ROB均空 | 最长连续零提交 |
|---|---:|---:|---:|---:|
| 链表 | 859 | 733 | 628 | 116 |
| 矩阵 | 556 | 360 | 325 | 61 |
| 状态转换 | 959 | 887 | 834 | 121 |

Icache等待定义为 CoreFrontend.cache.state 为2（读请求）或3（回填）。计数是观察信号重合关系，不把不同条件相加为互斥原因；取指缓存请求/回填且IB、ROB均空说明这些周期前端没有供给可提交的指令。不能把所有零提交都解释为一种阻塞。

## 测量口径与验证

- 从 iterate.isra.0 入口1C00E880首次有效提交周期，累计至同一次调用的返回1C00E970有效提交周期；两个边界周期均包含，两路valid均累计，包含所有被调用的链表、矩阵、状态转换及内核CRC操作。边界周期可能包含一条调用上下文指令，口径为整CPU周期IPC。
- 第一调用观察到20次core_bench_list入口，第二调用观察到200次；结合iterate反汇编每次迭代两次调用，分别确认10和100次完整迭代，均等到返回后才结束统计。
- CPU周期=零+单+双，提交数=单+2×双，两组均核验通过。第二次kernel正常返回后仿真正常finish，没有提交异常或原测试平台的计时断言失败。
-100次区间持续约0.132197024目标秒。这里是生产ROM自动校准过程中的完整100次迭代计算内核，不是整个大于等于10秒正式评分运行，也不包含上电、命令输入和串口成绩打印。未新完成全程CRC/正式评分验收。
- 本次没有改动CPU或ROM，仅增加仿真观察与计数；沿用上一轮记录的旧版仿真器启动force兼容处理，所有测量发生在原计时器release之后。

## 复现

编译：verilator --binary --timing -Wno-fatal -Wno-BLKANDNBLK --top-module tb_cpu_integration -j 2 -CFLAGS -Os --Mdir obj_profile rtl/cpu/CoreTop.sv rtl/clint.v rtl/cpu_top.v rtl/soc/axi_1x2.v rtl/soc/axi_boot_periph.v rtl/soc/axi_cpu_sys_cdc.v rtl/soc/uart_tx_fifo.v sim/tb_cpu_full_profile.sv

运行：obj_profile/Vtb_cpu_integration +production_coremark +coremark_mode=performance +cpu_hz=125000000 +max_cycles=100000000

统计校验：python analyze_kernel.py；工具Verilator5.020，命令均在本目录通过WSL执行，编译600秒/运行600秒上限，无全程波形输出。

原始数据：kernel_profile.csv、kernel_simulation.log、profile_list.csv、profile_matrix.csv、profile_state.csv。