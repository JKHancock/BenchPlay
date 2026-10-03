# 双实现映射（BenchPlaybook ↔ BenchPilot C#/MAF）

两个平行实现，**代码零共享，物理资源共用**，思路同一份（本目录的 SKILL.md 是共同上层规格）。

## 概念映射

| 概念 | BenchPlaybook（本文档，任意 agent） | BenchPilot（D:\CSharpProject\BenchPilot） |
|---|---|---|
| 骨（编排） | 动态 workflow / agent 会话控制流 | MAF ChatClientAgent + TaskRunner |
| 脑 | 执行 agent 本身（GLM/Claude/…） | Director/Bootstrap/Report agent（deepseek） |
| 手 | scripts/（bash/ps1/py） | BenchPilot.Core（SSH.NET/SftpChannel/…） |
| 闸 | 脚本 exit code + 文档门禁清单 | ProfileGate/ReportGate/sha256 校验（C#） |
| 实时可视 | 会话直播 + workflow 看板 | Blazor 500ms 轮询 + 思考中指示 |
| token 统计 | agent usage / workflow 日志 | ReasoningCapturePolicy 从响应体提取 |
| 无人值守 | Cron automation | 常驻进程 |

## 资源边界（三个库完全隔离，仅基础设施与物理资源共用）

| 资源 | 归属 | 说明 |
|---|---|---|
| 知识库 | **隔离** | 本流程用 Qdrant `kb_playbook`；C# 实现用 `kb`；互不读写 |
| 机器状态库 | **隔离** | 本流程用文件 `machines/{host}.json`；C# 用 Qdrant `machine_profiles` |
| 档案/经验库 | **隔离** | 各自目录（本目录 `tasks/`、`experience/` vs BenchPilot/tasks），格式兼容但物理分开 |
| Qdrant 实例 | 共用基础设施 | 同一个 127.0.0.1:6333 服务，不同集合 |
| 分发中心 | 共用 | 同一个 `D:\ModelHub`（内容资产，洗白一次两边受益；如需隔离另设目录+env） |
| 目标机 | 共用 | authorized_keys 各自密钥（benchplaybook_ / benchpilot_），互不干扰 |

## 分工建议

- **探索、开发期、在环诊断、一次性任务** → BenchPlaybook（agent 驾驶）：
  改流程=改文档；诊断质量高；无 key 依赖。
- **无人值守、定时矩阵、给人演示产品** → BenchPilot（C# 驾驶）：
  常驻 + Blazor 界面 + 全自动。
- 一条规则：**先在 Playbook 上探索跑通，再决定是否值得固化进 BenchPilot**——
  相当于"实验台 → 生产线"的两段式。

## 验收等价性（两实现都过才算沉淀完成）

同一任务（同机器同模型）两边各跑一次，diff 以下产物：
`profiles/*.json` 字段一致；`report.md` 覆盖度一致（事实相同）；
`events.jsonl` 阶段序一致；知识库新增条目一致。
