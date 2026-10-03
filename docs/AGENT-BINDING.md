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

## 通用绑定检查清单（任何新 agent 接入先过这四条）

1. 能读 `SKILL.md` 并按阶段序执行，不跳门禁；
2. 能运行 `scripts/`（bash/powershell/python 可用，或让 agent 现场按文档规格重写等价脚本——
   **门禁语义不得弱化**）；
3. 能按 `docs/LIBRARIES.md` 的格式读写三库；
4. 密码处理合规（SKILL.md 不变式 #1）。

## 能力差异备忘

| 能力 | ZCode | Claude Code | Codex |
|---|---|---|---|
| 实时直播 | workflow 看板+会话 | 会话 | 会话 |
| 无人值守 | CronCreate | cron+headless | cron |
| 重试护栏代码化 | workflow 控制流 | hooks | AGENTS.md 规则 |
| 多机并行 | workflow fan-out | 顺序为主 | 顺序为主 |
