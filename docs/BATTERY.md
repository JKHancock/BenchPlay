# 标准评测电池（对标旗舰发布卡 · 2026-09-30 定稿）

> 口径: 别人新模型发布时跑什么, 我们就跑什么. 权威=进主流发布卡/榜单.
> 约束: 我们基准的是推理服务(OpenAI兼容API), 判分必须确定性(无LLM裁判/无沙箱优先);
> 需沙箱/裁判/模拟器的如实降级标注, 不装懂.

## 集合③ capability_scores（能力, 发布卡口径）

| 套件 | 维度 | 数据源 | 判分 | 状态 |
|---|---|---|---|---|
| MMLU-Pro | 知识推理(10选项) | TIGER-Lab/MMLU-Pro **探针206✓** | 字母 | **待接(源已通)** |
| MMLU | 知识基线 | cais/mmlu ✓ | 字母 | ✅ 已跑 |
| GPQA-Diamond | 研究生级科学 | Idavidrein/gpqa **gated, 需HF_TOKEN** | 字母 | 待token |
| MMLU-Redux | 知识(降噪版) | TIGER-Lab/MMLU-Redux | 字母 | 路径待核 |
| BBH | 复杂推理 | lukaemon/bbh(逐任务) | 任务异构 | 路径待核 |
| AGIEval | 标准考试 | opencompass/AGIEval | 异构 | 路径待核 |
| GSM8K | 数学 | ✓ | 数值 | ✅ |
| **MATH-500** | 竞赛数学 | HuggingFaceH4/MATH-500 | 数值+boxed | **待接** |
| **AIME-2025** | 顶级数学(n=30) | math-ai/aime25 | 数值 | **待接** |
| TruthfulQA | 诚实性 | ✓ | 字母 | ✅ |
| HellaSwag/ARC/OpenBookQA/Winogrande/RACE-high | 常识/科学/阅读 | ✓ | 字母 | ✅ |
| **IFEval** | 指令遵循 | google/IFEval | **规则校验器(严格/宽松双口径)** | 待实现校验器 |
| CMMLU | 知识(中文) | haonan-li/cmmlu **zip探针206✓** | 字母 | **待接(源已通)** |
| C-Eval | 考试(中文) | ceval/ceval-exam | 字母 | 布局待核 |
| RULER | 长文合成任务 | 微软(生成式, 自构) | 检索/计数 | 与1M场景绑定, P1 |
| HumanEval/MBPP/LiveCodeBench | 代码 | — | **需执行沙箱** | P2(沙箱边界) |
| MT-Bench/Arena-Hard | 对话质量 | — | **需LLM裁判** | 不采(非确定性) |

## 集合④ agent_metrics（智能体, 独立成集）

| 套件 | 测什么 | 判分 | 状态 |
|---|---|---|---|
| **BFCL v3/v4** (Berkeley) | 单步/多函数/并行/无关克制/多轮/记忆 | AST+exec | ✅已接2类(irrelevance精确/simple结构分下界); 多类待带真值源(gorilla仓) |
| **ComplexFuncBench** | 多步/约束/长参数/128k | ComplexEval | 待接(zai-org GitHub) |
| **ACEBench** | 工具使用难度分层(正常/混淆/特定) | 官方脚本 | 待接 |
| **τ²-bench** (Sierra) | 双控协作(智能体+模拟用户), pass^k | 状态检查 | P1: 需用户模拟器LLM(可用GLM) |
| **τ-bench** (taubench.com) | 航空/零售域策略遵循 | pass^1/pass^k | P1 同上 |
| GAIA | 通用助手多步 | 精确匹配 | P2(需工具环境) |
| SWE-bench Verified / Terminal-Bench | 工程/终端智能体 | 测试通过 | P2(沙箱, 超服务边界) |
| WebArena/OSWorld | Web/OS 智能体 | 任务成功 | P2(浏览器/VM编排) |
| MCP系 (MCPBench/LiveMCPBench) | MCP协议工具使用 | 异构 | 关注趋势, P2 |
| 自研循环组(A3) | pass@1/并行调用率/克制/步数预算 | 确定性 | ✅已跑 |

## 打分(不变, v4.3): 原始acc→维度分→C-Score/A-Score, 权重随报告公示

## 接入优先序(下次窗口执行, 不碰在用服务)
1. MMLU-Pro(源已通) + MATH-500 + AIME25 —— 发布卡三大件补齐
2. CMMLU(源已通, zip解包) —— 中文维度
3. BFCL 真值源(gorilla仓 correct路径) → simple精判+multiple/parallel
4. ComplexFuncBench + ACEBench —— 智能体集合权威双件
5. IFEval 校验器实现(严格/宽松)
6. GPQA(申请HF_TOKEN) / BBH / AGIEval / RULER(绑定1M场景)
7. τ²/τ-bench(模拟器方案评审后)

## 完善排期（2026-10-03 确认执行）
三大套件补齐顺序: ①MMLU-Pro+MATH-500+AIME25(能力发布卡三大件, 数据源已通/待接) ②IFEval校验器 ③BFCL真值源→multiple/parallel精判+τ²-lite ④GPQA(申请token)+BBH/AGIEval ⑤27B-MTP档+FlashNext-短上下文档(场景矩阵补格) 每项完成后入对应track并更新打分权重表
