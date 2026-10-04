# 各 Agent 运行时绑定

本流程法是 agent 无关的：**规格、门禁、库契约全在文档与脚本里**；
各运行时只需要绑定"脑"的落点。共同原则：脑只在决策点（档案整理、失败诊断、报告/提炼写作），
手=scripts/，闸=exit code。

## ZCode

- `SKILL.md` 已是技能格式：放入 `skills/` 或直接让会话读它；
  斜杠 `/benchpilot` 触发，参数=机器行+模型清单。
- 编排用**动态 workflow**：TS 脚本写阶段循环与重试边界（护栏代码化，比 prompt 更硬），
  子智能体做档案整理与报告；产物卡片自动可见（实时直播）。
- 无人值守：`CronCreate` 定时唤起。
- **Windows 执行注意（迭代实测）**：workflow 的 `world.run` 里裸 `"bash"` 解析到
  **WSL2**（不认 `D:/`、`$HOME` 无密钥）——bash 命令一律用字面量
  `C:/Program Files/Git/bin/bash.exe` + MSYS 路径 `/d/...`；shell 内建命令（mkdir 等）
  走 `bash.exe -c`（Windows 无独立 exe，直接 spawn 报 ENOENT）。子智能体自身的
  Bash/Write 工具是会话侧 Git Bash，`D:/` 路径正常——两套环境不要混淆。

## Claude Code

- 把 `SKILL.md` 内容并入 `CLAUDE.md`（或 `.claude/skills/benchpilot/SKILL.md`）。
- 编排：Claude 原生计划模式 + Bash 工具顺序执行 scripts/；
  重试边界写在 CLAUDE.md 的规则里，并靠 hooks 校验（PostToolUse 检查退出码非零即停）。
- 长任务：分段提交（每阶段一确认），或 headless 模式 + 外层 cron。

## Codex

- `AGENTS.md` 引用 `SKILL.md`（Codex 读仓库级 AGENTS.md）。
- 编排：Codex 的 plan/exec 循环；shell 工具执行 scripts/；
  注意为 Codex 显式列出不变式（它对"exit code 即门禁"遵守良好）。

## OpenCode

- `AGENTS.md` 同样是 OpenCode 的仓库级入口（读写同一份即可）。
- 编排：OpenCode 的 subagent/agent 机制做脑任务（档案整理、报告章节、经验提炼），
  Bash 工具串行跑 scripts/；后台任务用其 task/后台执行机制挂长电池。
- 密钥与路径注意与通用绑定一致（bash + python 可用即达标）。

## 并行加速：按宿主 IDE 选编排形态（强烈建议用满）

单场景电池（serve→闸→三 benchmark）受物理约束**天然串行**：一个 vLLM 进程一次
只能加载一组服务参数（TP/EP/MTP/parser 变了就得重启），GPU 也只有一个服务实例。
所以"并行"要加在**没有资源冲突**的环节上，映射如下：

| 可并行的环节 | 为什么安全 | ZCode 形态 | Claude Code | Codex | OpenCode |
|---|---|---|---|---|---|
| 多模型 M0 档案分析 | 纯读盘+CPU | workflow 里 `agent()` fan-out | 多个 Task subagent 并发 | 多个 cloud task | 多个 subagent |
| 数据集准备/校验 | 纯本地 IO | fan-out 子任务 | 后台 Bash | 并行 exec | 后台 task |
| 电池执行 | **GPU 互斥，禁并行**（多集群/多端口除外） | workflow 顺序 `world.run` | 顺序 Bash | 顺序 exec | 顺序 |
| 电池后处理（build_doc/渲染/index/经验提炼） | 只读 raw、写不同文件 | fan-out 4 个子智能体 | 多 Task 并发 | 多 cloud task | 多 subagent |
| 报告分章节写作（Part A/B/C） | 各章输入独立 | fan-out 后主控拼装 | 多 Task 并发 | 多 cloud task | 多 subagent |
| 多场景电池（不同集群或错峰） | 不同 GPU | workflow 循环+并行分支 | 后台 Bash 各自跑 | 并行 exec | 后台 task |

纪律（并行不改变门禁语义）：

0. **A4 归因回跳的两种控制器形态**（同一个循环，谁在方向盘后的区别）：
   - **会话内 Agent 控制**（交互场景默认）：cell 脚本失败即停（门禁交回大脑），
     Agent 收到非零退出 → 归因（日志/经验库/指纹复核）→ 定位回跳阶段 → 修复 → 幂等重入；
   - **workflow 代码控制**（无人值守/多模型接力必用）：同样的归因循环写进 workflow
     脚本控制流（症状→阶段映射 gate + 派子智能体诊断 + ≤2 轮上限 + 断点续跑），
     控制器是代码因为没人在方向盘前。诊断本身永远是 Agent 脑任务，两种形态只换壳不换脑。
   - **电池监工**（IDE 无关的标准形态）：长电池(2h+)运行期间，派一个**独立监工 workflow**，
     内含一个"监工"子智能体按 15min 周期跑 `scripts/foreman.sh`（分级退出码 0/3/4：
     健康双采样/观察容忍窗/异常），异常时子智能体只诊断上报、严禁动手——电池的归因回跳
     归电池工作流，双控制器不打架；监工见 DONE 自动撤岗。禁止用宿主 IDE 私有定时器
     （ZCode Cron/Claude hooks 等）实现该职责——流程资产必须 agent 无关。
1. 子智能体的产出仍是**脚本 exit code + 证据文件路径**，主控只做汇总，
   任何子智能体不得用自然语言"宣称成功"；
2. 并行任务**不得写同一个 raw 目录**（tasks/<task>/raw/<tag>/ 归属唯一）；
3. 失败归因（A4）在主控做——子智能体只带回证据，不自行重试越过 2 轮上限；
4. 物理串行段的进度监控归主控（progress.log），子智能体不重复轮询。

ZCode 参考实现：`scripts/overnight.sh` + 动态 workflow（阶段循环、归因重试 ≤2 轮、
build/渲染/沉淀 fan-out）即按本表执行；其它 IDE 把同一拓扑翻译成自家原语即可。

## 通用绑定检查清单（任何新 agent 接入先过这四条）

1. 能读 `SKILL.md` 并按阶段序执行，不跳门禁；
2. 能运行 `scripts/`（bash/powershell/python 可用，或让 agent 现场按文档规格重写等价脚本——
   **门禁语义不得弱化**）；
3. 能按 `docs/LIBRARIES.md` 的格式读写三库；
4. 密码处理合规（SKILL.md 不变式 #1）。

## 能力差异备忘

| 能力 | ZCode | Claude Code | Codex | OpenCode |
|---|---|---|---|---|
| 实时直播 | workflow 看板+会话 | 会话 | 会话 | 会话 |
| 无人值守 | CronCreate | cron+headless | cron | cron |
| 重试护栏代码化 | workflow 控制流 | hooks | AGENTS.md 规则 | AGENTS.md 规则 |
| 子智能体并行 | workflow fan-out | Task 并发 | cloud task 并发 | subagent 并发 |
