# BenchPlaybook — 本地 LLM 集群的 Agent 运维流程法

一套 **agent 无关** 的流程资产：任何 CLI agent（ZCode / Claude Code / Codex）打开本目录、
读 `SKILL.md` 即可执行"给定 SSH + 机型 + 模型清单 → 引导 → 摸底 → 模型分发 → 报告"的完整流程。

## 四角色纲领（两个平行实现共享的哲学）

> **流程为骨（文档+脚本控制流），Agent 为脑（只在决策点），脚本为手（确定性），exit code 为闸（门禁）。**
> LLM 永远没有执行权，只有决策权与表达权；能碰机器的只有脚本；通过与否只认脚本的退出码与证据。

## 目录导览

| 路径 | 作用 |
|---|---|
| `SKILL.md` | **核心流程法**：输入契约、阶段流水、门禁清单、库权限、失败处理、不变式。执行前必读 |
| `docs/PIPELINE.md` | 阶段流水详解（每阶段目的/动作/门禁/证据） |
| `docs/LIBRARIES.md` | 三个库的契约：格式、路径、读写权限、积累与晋升规则 |
| `docs/RUNBOOK.md` | 操作员手册：发任务、加机器、导模型（DLP 洗白）、人工介入 |
| `docs/AGENT-BINDING.md` | 各 agent 运行时如何绑定本流程（ZCode/Claude Code/Codex） |
| `docs/TWIN-MAPPING.md` | 与 C# 实现（BenchPilot/MAF）的映射与共享资源边界 |
| `scripts/` | 确定性手 + 门禁（密钥引导/探测/DLP 洗白/分发/知识库） |
| `experience/` | 经验库（agent 收尾提炼写入，人可读） |
| `tasks/` | 档案库（每次任务一个目录；`tsample-demo` 为界面验收示例，可删） |
| `viewer/app.py` | **三库浏览器**（Streamlit）：任务对话回放（2s 实时刷新）/档案/报告/经验库/知识库检索 |
| `machines/` | 机器状态库（`{host}.json`，任务收尾幂等覆盖） |

## 人机界面

- **三库浏览器**：`streamlit run viewer/app.py --server.port 8501 --server.headless true`
  （venv：`Vllm_Benchmark/python/.venv`；已装 streamlit 1.64）——任务回放区每 2 秒自动刷新，
  运行中任务可围观；知识库页语义检索（fastembed + Qdrant `kb_playbook`）。
- **知识库浏览器版**：Qdrant Dashboard `http://127.0.0.1:6333/dashboard`（按 tags/hits 过滤）。
- **任务三层入口**：① 自然语言（主契约，SKILL.md 解析为机器字段并回显确认）；
  ② 任务文件 `tasks-inbox/*.md`（可重复/进版本管理）；③ 定时（Cron automation 唤起）。

## 报告先行原则（2026-10-01 立法）

**最终目的 = 完整详细报告 + 三库填充，流程只是手段。**
报告规格即契约（`docs/REPORT-SPEC.md`）：行 schema → 各阶段采集义务 →
`report_gen.py` 确定性渲染。缺的单元格如实标 —(未采集)，禁止臆造。
三库与报告同源：档案库=行数据，经验库=洞察（报告洞察段引用它），知识库=可复用结论。

## 快速开始（对 agent 说的一句话）

```
读 AGENTS.md 和 SKILL.md，按其执行任务：
机器 192.168.199.129|syspetro||GB10 与 192.168.199.134|syspetro|<密码>|GB10，
分发模型 Qwen3.6-35B-A3B-NVFP4-Fast，完成后出报告并做经验提炼。
（ZCode 里可直接说"用动态 workflow 跑"）
```

新会话的自举：ZCode/Codex 自动读根目录 `AGENTS.md`（背景+运行时自检+路由）；
Claude Code 读 `CLAUDE.md`（可软链到本文件）。

## 环境事实（本机实测，勿凭假设）

- 分发中心：`D:\ModelHub`（干净模型），源库 `D:\LocalAIResources`（DLP 密文，须洗白）
- Qdrant：`http://127.0.0.1:6333`（本流程用独立集合 `kb_playbook`，**与 C# 实现的三库完全隔离**；
  机器状态存本目录 `machines/{host}.json` 文件）
- 目标机模型根：`~/.cache/huggingface/<模型名>/`（**远端路径必须绝对化**，见不变式 #6）
- DLP 三事实：盘上文件是密文；.NET/cmd 读到密文；**PowerShell Copy-Item 是唯一实测解密通道**
