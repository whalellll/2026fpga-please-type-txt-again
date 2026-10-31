---
name: soc-hardware-software-codesign
description: 协同修改 FPGA/SoC 的 RTL、硬件 ABI、驱动、模型 runtime 和启动产物。用于引擎共享、常驻权重、调度响应与兼容性验证，不用于单独的 PC 模型训练。
---

# 软硬件协同

先画清当前 RTL→MMIO→硬件 ABI→驱动或 RTOS/裸机 owner→runtime→模型→启动文件
的调用链与所有权。先识别 Linux/RTOS/裸机环境、引擎数量和一致性机制；把 Linux
fd/mutex/调度点映射到新工程相应机制。多引擎工程按每个物理资源分别定义 owner。
按需读取 [系统边界经验](references/lessons.md)。以当前工程文档和源码为准，
不混用根 V2 的裸机地址布局和性能工程的 Linux 候选。

## 事务与所有权

- Linux 单引擎配置的 MAC/卷积/gather 由一个驱动管理。设备模式不得同时让旧
  `/dev/mem` 客户端写寄存器或 scratch。多进程并发是安全串行化，不是多引擎。
- 每次 open 独立 fd context、shadow、模型 snapshot 与输出。设备级 mutex 覆盖
  数据拷贝、寄存器、启动、完成/恢复、输出发布的完整事务；共享 fd 的线程另需
  应用锁。硬件拒绝/出错时不发布无效结果。
- 驻留权重用 owner/generation 标记。其他 fd、YOLO 或 legacy job 覆盖物理
  scratch 后必须恢复所属 fd 的不可变模型；输入不同仍须逐作业更新。
- 超时与 abort 要明确硬件 DMA 的生命周期。BUSY 或已接收 AXI burst 尚未排空时
  不能复位后立即放另一个事务进 scratch。确认设备空闲或进入明示隔离/恢复状态。
- 从用户参数到范围检查、copy、DMA publish/start、done/output 的内存屏障和
  地址单位逐项核对；整数尺寸/偏移溢出、重叠、未知 ABI、代次和 timeout 先拒绝。

## 语音与延迟

核对内核抢占配置。大块 copy/恢复可在安全事务锁内分块并提供调度点，避免
PREEMPT_NONE 下 CPU 语音/采集线程长时间失去调度。不能用解除引擎锁来替代
调度点，否则可能暴露部分恢复的权重。测音频 FIFO overflow、采集连续性、队列
等待、模型恢复和 NNUE/YOLO 延迟；单进程均值不能替代混合负载验收。

## 候选组合与验收

替换 CPU 时先固定现有总线、外设时钟、地址保留区和加速器接口，在隔离候选中执行
真实指令程序验证启动、异常返回、中断、缓存与 DMA 可见性。另设操作系统能力门槛：
核对生成配置及实际 CSR/特权转换/页表行为；模块名、ISA 字符串、旧 DTS 声明不能
证明 MMU 可用。裸机启动和 MAC 正确通过后，Linux 与模型运行仍须各自验收。
CPU 单独提频时分别核对 mcycle、time CSR 和系统定时器频率。

修改前固定 UAPI 布局和旧版本行为，写错误参数/并发/超时/模型切换及性能测试。
RTL 周期、驱动 ioctl 和 runtime 标记都应能证明同一模型由期望引擎执行。
普通运行的 fallback 与严格验收开关明确分开；严格模式任何 fallback 为失败。

Image、DTB、rootfs、bootloader、位流、UAPI、模型和向量一起记录哈希；确认 DTS
reserved-memory、物理 aperture 和装载地址不冲突。候选输出隔离于生产文件。
裸机固件编译器还要核对主机可执行格式、target、版本、ISA/ABI、libgcc ELF 属性和
编译器/库哈希。模型用户态 Linux 工具链不能代替裸机工具链。同版本但不同哈希的
新编译器先在隔离目录完成整镜像链接、BRAM/栈容量门槛和回归；不能仅凭小程序
或 ISA 测试通过就覆盖与旧固件哈希绑定的位流。若体积优化只留下极小栈裕量，
须继续评估栈和热路径性能，不将其作为已验收替代。
通过主机/仿真及原生时序后，启动同版 Linux 核对设备身份/能力，再跑旧 dense、
卷积、gather、resident、语音、GUI 和私有 fd 不同数据的混合测试。外部完整
Pikafish 搜索跳过时明确写 SKIPPED，不算通过。

交付文档说明 CPU/硬件边界、并发模型、启动文件及剩余限制；按本地 TODO 要求
完成板测、提交、合并和包验证，最后同步相关 skills。

采集连续性验收时，由 FIFO 容量/采样率求最大服务间隔，实测并发丢样与调度限流。
提高整个采集/识别进程实时优先级可能触发 RT throttling、丢更多样本；先做对照，
再评估独立采集缓冲与计算线程。无识别权重或输入恒定时，仅验收接口范围。
