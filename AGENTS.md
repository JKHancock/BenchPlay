# AGENTS.md — 新会话自举入口（ZCode / Claude Code / Codex 通用）

你是被请来执行本地 LLM 集群运维任务的 agent。**先读完本文件，再读 `SKILL.md`（流程法，执行宪法），然后才开始任何动作。**

## 背景（30 秒版）

本目录是一套 agent 无关的运维流程资产：给定若干台机器的
`host|user|password|机型` 和模型清单，执行 **引导→清点→模型分发→报告→经验提炼**。
门禁全部在 `scripts/` 的退出码里——你没有"宣称成功"的权利，只有 exit code 有。
另有一个 C# 平行实现（`D:\CSharpProject\BenchPilot`，MAF+Blazor），**三个库完全隔离**，
仅共用 Qdrant 实例 / D:\ModelHub / 目标机，概念映射见 `docs/TWIN-MAPPING.md`。

## 运行时自检与绑定（开局做一次）

检测顺序（命中即止）：

1. 系统提示声明你是 ZCode，或你的工具面存在 `CreateWorkflow`/`Skill`，
   或环境变量 `ZCODE_PLUGIN_ROOT` 存在，或工作区有 `.zcode/`
   → **ZCode 形态**：多阶段任务**用动态 workflow 编排**（CreateWorkflow），
   阶段循环与重试边界写在 workflow 脚本控制流里（代码级护栏），
   子智能体做档案整理/报告/提炼；也可把 `SKILL.md` 注册为技能用 `/benchpilot` 触发。
2. 系统提示声明 Claude Code → **Claude 形态**：按 `docs/AGENT-BINDING.md` 的
   Claude Code 节执行（Task 子智能体并行 + hooks 校验退出码）。
3. 系统提示声明 Codex → **Codex 形态**：同上对应节（cloud task 并行）。
4. 系统提示声明 OpenCode 或工作区有 `.opencode/` → **OpenCode 形态**：
   同上对应节（subagent 并行）。
5. 都不是 → 通用形态：顺序执行 `scripts/`，严守 SKILL.md 不变式。

**并行纪律（所有形态通用）**：电池执行受 GPU 互斥天然串行，能并行的是
M0 档案分析、数据集准备、电池后处理（build/渲染/index/提炼）、报告分章——
映射表与红线见 `docs/AGENT-BINDING.md` §并行加速。子智能体产出仍必须是
exit code + 证据文件，不得写同一 raw 目录。

## 三条铁律（未读 SKILL.md 前也必须遵守）

1. **密码只用于引导**（`scripts/bootstrap_key.py`），之后抹除；永不写入任何文件/日志/回复。
2. **门禁只认脚本的 exit code 与输出证据**；脚本 FAIL 就停下来诊断（先查知识库），不许绕过重试。
3. **远端路径必须先绝对化**（`echo $HOME`）——`~` 在 scp/SFTP 里是字面量。

另：SKILL.md §7 知识获取链——本地库未命中时用运行时自带的 WebSearch/WebFetch 联网检索
（ZCode/Claude Code 均内置；无此能力时向用户说明并要资料，不得拿训练记忆充当事实）。
联网结论是假设，实测过门禁才是事实。

## 目录导览

`SKILL.md` 流程法 ｜ `docs/`（PIPELINE/LIBRARIES/RUNBOOK/AGENT-BINDING/TWIN-MAPPING）
`scripts/` 门禁脚本（静态工具 + cell 运行档案） ｜ `viewer/app.py` 三库浏览器
**动态层（你写入的地方，只追加不改写）**：`tasks/<id>/raw/` 原始证据 ·
`machines/` 机器档案 · `models/` M0 模型档案 · `experience/` 经验库 ·
`archive/scenario_index.jsonl` 全局索引 · `reports/` 定稿副本。
静态 vs 动态的完整分类表（谁写/何时/是否进 git）见 README §9.1——
**流程只读静态、只追加动态；raw/ 落档后不改写，复测=新任务目录。**

## 修订案同步（2026-10-03）— 新会话必读增量
1. serve 任何模型前必须先跑 M0: `python scripts/model_profile.py <model_dir>`（无 profile 禁 serve，SKILL A1）
2. 验收已升级四关: verify.sh <host> [1]（agent 用途传 1，工具回环 FAIL 级）
3. 场景生成三维化: 模型(M0)×服务flags(TP/EP/MTP/YaRN/parser)×用途；报告按模型分组、组合=argv
4. 经验库已拆分: experience/{serve-vllm,os-network,testing-bench,process-governance}.md + INDEX.md（检索先读 INDEX，规程 LIBRARIES §7）
5. 汇编入口: scripts/build8.py（当前, 8场景含 Flash-Next 复测; build7.py 为上一版运行档案）；渲染 scripts/report_gen4.py doc out [模型过滤]

## 修订案同步（2026-10-04）— 新会话必读增量
6. bench/ 工具与 12 套件数据集已收编进本仓库（bench/ + data/cap/ + requirements.txt）——
   新编排脚本一律用仓库内副本；克隆+装依赖即完整可用
7. Track2 十二套件: 8 老 + math500(开思考链)/cmmlu/ceval/ifeval(指令级口径另报)
8. 数据清空冷启动: scripts/reset_data.sh [show|data|all]（删除物入 .reset_backup 可反悔）
9. **git 提交纪律**: Python 写的文件在工作区是 DLP 密文, 提交前用 PowerShell Copy-Item
   通道洗白再 add（仓库 blob 保持明文, 克隆方可读）; 知识库变动后 `kb.py export` 快照随库提交


## 工具箱目录（阶段→脚本→门禁速查）
详见 [docs/SCRIPTS.md](docs/SCRIPTS.md)——每个阶段该用哪个脚本、怎么调、门禁是什么。
Agent 在进入任何阶段前先查此表，不要凭记忆调脚本名。
核心规则: cell4/5/6/7 是编排脚本(内部调 serve/verify/bench 工具链); bench/ 工具与数据集已收编进本仓库(bench/ + data/cap/, 详见 SCRIPTS.md 规则4)。
