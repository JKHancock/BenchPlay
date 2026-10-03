# BenchPlaybook

> ## ⚠️ 本文件仅供人类阅读
> **Agent 执行任务时请忽略本文件**。你的行为规范在 `AGENTS.md`（新会话入口）与 `SKILL.md`（流程法条）；流程细节见 `docs/PIPELINE.md`。

## 这是什么

给两台 NVIDIA GX10（GB10 统一内存，QSFP 直连）组成的裸机集群，**从 SSH 凭据出发，全自动完成 vLLM 大模型服务的部署、多参数组合基准测试、并产出带推荐的完整数据报告**的多智能体工程。任何 Agent（ZCode / Claude Code / Codex）按同一套法条执行，产出可复现。

核心理念（四角色）：**流程为骨**（SKILL+脚本控制流）、**Agent 为脑**（只在决策点）、**脚本为手**（确定性执行）、**exit code 为闸**（门禁在脚本里，不靠自觉）。

## 一分钟架构

```
输入(机器SSH+模型清单+用途chat/agent)
→ 引导(密码换密钥) → 清点 → 底座 → 分发(sha256门禁) → 清场
→ M0 模型调研(权重实证MTP/上下文/parser; 无profile禁serve) → M0.5 联网调研(web必须实测)
→ 场景生成(三维: 模型×vLLM参数×集群组合; 一组合=完整argv=一个场景)
→ 每场景: serve→四关验收(含工具调用回环)→三benchmark→落档
→ 汇编(schema校验)→渲染(推荐数值回查)→报告
→ 经验库/知识库沉淀
```

**三个 benchmark、四个指标集合**（每场景必挂）：

| 集合 | 内容 |
|---|---|
| vllm_metrics | KV池/投机接受率/负载峰值/分段计数器/服务端分位时延 |
| perf_metrics | 六工作负载+舒适度扫描+探针（TTFT/TPOT/ITL/E2E 分位、goodput、屋顶线） |
| capability_scores | 八套件（gsm8k/mmlu/arc/hellaswag/winogrande/truthfulqa/openbookqa/race）+ C-Score 打分 |
| agent_metrics | BFCL+工具循环+思考链 A/B + A-Score 打分 |

**三个库**（数据→教训→知识阶梯）：
- 档案库（事实+证据，脚本自动写，全程）
- 经验库（按主题拆分+INDEX，Agent 写，阶段末）
- 知识库（Qdrant，Agent 只能提名；事实类 N≥2 复现转正，推理类人审）

## 仓库结构

```
AGENTS.md            Agent 新会话入口(必读)
SKILL.md             流程法条(含修订案A1/A2: M0/四关/三维场景)
README.md            本文件(人类向, Agent 忽略)
docs/                PIPELINE(全景) REPORT-SPEC(契约v4.2) BATTERY(套件排期) AGENT-BENCH LIBRARIES(三库治理)
scripts/             引导/清点/底座/分发/组网/serve/verify(四关)/matrix(编排)/model_profile(M0)
                     build7(汇编) report_gen4(渲染) kb(知识库) sniff8000(抓包)
bench/ (在 ../Vllm_Benchmark)  track1性能 track2能力 track3智能体 bfcl probes common
machines/ models/    机器档案 / 模型profile
experience/          经验库(按主题+INDEX)
tasks/               每任务全量原始证据(raw/)与报告
viewer/              Streamlit 浏览器(回放/报告/经验/KB)
```

## 快速开始（人类操作员视角）

1. 在 `machines/` 声明目标机（或首跑由清点阶段建档）
2. 新会话让任意 Agent 读 `AGENTS.md`，给出：机器 SSH、模型清单、用途(chat/agent)
3. Agent 按法条走完全程；产物在 `tasks/<id>/`：原始证据 + `report_<模型>.md`（按模型分组、每参数组合四指标集合 + C-Score/A-Score + 确定性推荐）
4. 报告由 `report_doc.json`（过 JSON Schema 校验）确定性渲染——**零手写数字，每个格可回溯到原始请求**

## 已实测成果（双 GX10，环境指纹绑定）

- 7 场景 × 全电池（3 模型 × TP/EP/MTP/上下文组合），~1 万真实请求
- 关键实测结论：MTP2 投机单流 +37%（接受率 75-82%）；1M 上下文 YaRN 配方（原生 262K）；前缀缓存复用率是长度函数(64K→97%)；KV 池决定多路容量（15.9M/5.1M/1.9M 三模型）；冷预填 ~3K tok/s 为算力墙
- 沉淀 41 条真机经验（自调优死锁对策、引号四层穿透、YaRN 嵌套配方等）

## 红线（人也要知道）

SSH 密码一次性使用后永存盘；一切结论必须证据绑定；缺格如实标「未采集」禁止臆造；报告仅适用指纹匹配环境。
