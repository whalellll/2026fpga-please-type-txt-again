# FPGA / SoC 工程 skills

维护源：工作区根目录的 `skills/`。`performance_soc_linux_nnue10ms/skills/`
是当前性能工程的交付副本；修改维护源后用该工程的
`python skills/manage.py workspace-sync --project .` 同步。
交付脚本在发现同一技能库的上级维护源时自动同步；独立解压的工程使用
包内副本，工具不依赖 `G:`、PDS 安装目录或个人 Codex 配置。

| Skill | 适用工作 |
|---|---|
| [accelerator-performance](accelerator-performance/SKILL.md) | 测量 NNUE/YOLO 延迟、DMA 瓶颈和资源；依据证据选择优化 |
| [fpga-timing-optimization](fpga-timing-optimization/SKILL.md) | 布局布线、DDR 跨域时序、约束生效和全部时序角验收 |
| [accelerator-model-compatibility](accelerator-model-compatibility/SKILL.md) | 模型算子映射、分块、整数语义、旧 ABI 和多模型兼容 |
| [soc-hardware-software-codesign](soc-hardware-software-codesign/SKILL.md) | RTL/驱动/runtime/启动文件协同、引擎所有权和系统调度 |
| [fpga-soc-board-debug](fpga-soc-board-debug/SKILL.md) | JTAG、UART、DDR、系统启动和实际后端的分层调试 |

各目录的 `SKILL.md` 是入口，`agents/openai.yaml` 提供调用元数据，
`references/lessons.md` 保存按需读取的具体经验和来源。每个 skill 独立自包含，
不依赖之前聊天、固定盘符或本工程脚本；案例中的工程路径用于追溯历史，缺少
原文时仍可执行通用工作流，但不得声称复现历史数据。

## 安装、跨会话调用与迁移

需要 Python 3，无第三方依赖。Windows 可用 `python`，Linux/macOS 用 `python3`。

```powershell
# 用户级安装，默认 ~/.agents/skills，适用于其他工程和后续会话
python skills/manage.py install
# 迁移到另一工程的仓库级发现目录
python skills/manage.py install --destination D:/another-project/.agents/skills
# 本机旧版 Codex 若使用 ~/.codex/skills，可显式选择该目录
python skills/manage.py install --destination C:/Users/your-user/.codex/skills
```

之后可输入 `$accelerator-performance` 或 `$fpga-timing-optimization` 等名称，
也可由任务描述匹配。需要时重启 Codex 以刷新发现；安装不修改 config.toml。
目录已存在且有不属于本库的技能或本地修改时，安装器拒绝覆盖。
按当前 [OpenAI Docs](https://learn.chatgpt.com/docs/build-skills)，用户级发现目录
是 `~/.agents/skills`，仓库级是 `.agents/skills`；本机旧目录需以实际版本核对。

迁移整套库可以复制 `skills/` 或生成独立包：

```powershell
python skills/manage.py pack --output artifacts/fpga_soc_skills.zip
```

解压后保留完整 skill 目录，运行包内 `skills/manage.py install`。单个 skill 也可
直接复制其目录到发现路径；每个入口的参数识别与验证流程都适用于新的工程。

## 每次交付时维护

1. 对照本次实际代码、测试、时序和板测更新相关 skill。记录成功的适用范围，
   也保留改变后续决策的失败原因；没有新经验时写明本次核对结论。
2. 在维护源工程运行：

   ```powershell
   python skills/manage.py review --note '本次核对或新增经验的具体说明'
   python skills/manage.py verify
   ```

3. 性能工程运行 `python skills/manage.py workspace-sync --project .`；首次同步可在
   维护源运行 `python skills/manage.py sync --destination performance_soc_linux_nnue10ms/skills`。
4. `create_delivery.ps1` 验证并复制全部技能，生成 `SKILLS_DELIVERY.json`，关联技能
   清单 SHA-256、审阅记录和本包 README/AGENTS/交付脚本。`verify_delivery.ps1`
   检查这些文件；缺技能、内容修改未刷新清单、旧技能快照或混用交付元数据均失败。

`manifest.json` 是经审阅的库版本与逐文件 SHA-256，不是性能验收文件。
技能更新不使未完成的 TODO 或硬件候选自动通过；生产包仍按所在工程 AGENTS.md
的回归、板测、合并及交付条件发布。

## 证据边界（2026-10-08 整理）

本库总结此前性能工程的工作；根工程的 V2/27 MHz 与性能工程的 V3/49.5 MHz
不是同一配置。每次应用先读取实际工程的 AGENTS.md、README、UAPI 和验收文件。
10 ms 是完整 NNUE evaluation 的候选目标，30 fps 是识别整帧目标；两者仍未由
此次候选板测证明。10-06/10-07 LUT 优化候选时序被拒绝，不能作为生产配置。
历史数据的原文路径放在各 skill 的经验引用中，交付包只携带摘要，不携带本地
PDS 实验数据库、探针位流、模型副本或调试日志。

2026-10-09 的增量经验：匹配 SD 部署与回读、系统时钟校准失败和只读计时对照、
音频并发溢出及实时调度对照失败。CRAM/驱动功能通过仅适用于 10-05 时序基线；
CLINT 热加载重测 NNUE 冷/热平均为 64.799/61.935 ms，10 ms 未达到；
完整语音兼容与 30 fps 仍未验收。保留 DDR 热加载的可用范围与回读校验也已整理。
