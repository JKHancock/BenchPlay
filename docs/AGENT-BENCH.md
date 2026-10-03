# 智能体基准调研与第四指标集合规格（agent_metrics · 2026-09-30）

> 定位: 在三集合(vllm/perf/capability)之外补第四集合 **agent_metrics**, 服务于"模型作为智能体引擎"的场景.
> 选型约束: 我们基准的是**推理服务**(OpenAI兼容API+tools), 不做环境编排 — 沙箱级基准(SWE/terminal/web)只注记不纳入.

## 一、格局调研(2026-09 现状)

| 基准 | 维度 | 形态 | 对我们的适配度 |
|---|---|---|---|
| **BFCL v3/v4** (Berkeley) | 单步/并行/无关检测/多轮/记忆 | 静态数据+AST/exec 评分, 数据在 HF | ★★★ P0: 经API即可测, hf-mirror 实测可达(BFCL_v3_simple.json 200) |
| **ComplexFuncBench** (智谱/清华) | 多步骤/约束/长参数填充/128k长上下文 | 1000样本+ComplexEval评分 | ★★ P1: 直击"参数值推理"短板, 与我们1M场景天然契合 |
| **ACEBench** (阿里) | 工具使用难度分层/正常-混淆-特定场景 | 静态 | ★★ P1: 混淆场景(distractor)恰好补我们的克制测试 |
| **τ²-bench** (Sierra) | 双控协作(智能体+模拟用户共同改世界状态), pass^k | 需用户模拟器LLM | ★ P2: 依赖第二个LLM当用户, 结果噪声大, 后置 |
| SWE-bench/terminal-bench/WebArena | 环境级智能体 | 需docker/浏览器编排 | ✗ 超服务基准边界, 仅注记 |
| MCP化趋势 (ICLR26 博客提议: 基准环境暴露为MCP server) | 生态方向 | — | 注记: track3 未来可加 MCP 适配层 |

## 二、agent_metrics 集合 schema(REPORT-SPEC v4.2 第四集合)

```json
"agent_metrics": {
  "A1_call_correctness": {          // P0(用途=agent): BFCL v3 AST 子集, 每类抽样n≥50
    "bfcl_simple_acc": .., "bfcl_multiple_acc": .., "bfcl_parallel_acc": ..,
    "bfcl_parallel_multiple_acc": .., "bfcl_irrelevance_acc": ..,   // 克制: 无关问题不乱调
    "ast_match_rate": .., "n_per_cat": 50
  },
  "A2_complex": {                   // P1: ComplexFuncBench 子集(约束/多步/长参数)
    "multi_step_acc": .., "constraint_acc": .., "long_param_acc": ..,
    "context_128k_acc": ..
  },
  "A3_loop": {                      // P0(自研, 已有雏形): 智能体循环行为
    "loop_pass_at_1": ..,           // 调用→回灌→正确作答 全环成功率
    "avg_steps_per_task": .., "over_budget_rate": ..,
    "parallel_call_rate": ..,       // 一句话多意图时的并行调用能力(实测弱项跟踪)
    "restraint_acc": ..             // 干扰工具下的不调用克制
  },
  "A4_serving": {                   // P0: 智能体流量下的服务侧指标
    "toolcall_ttft_ms": {"p50":..,"p99":..},
    "loop_e2e_ms": {"p50":..,"p99":..},
    "reasoning_ab": {"on_toolcall_ttft_ms":..,"off_toolcall_ttft_ms":..,
                     "on_tokens_per_loop":..,"off_tokens_per_loop":..},
    "spec_acceptance_under_tools": ..
  },
  "settings": {"tool_choice":"auto","parser":"qwen3_xml(探针实测定)",
               "thinking":"off(P0)/on(P1)","temperature":0,"seed":20260930}
}
```

**完整性规则**: 用途=agent 的场景, A1+A3+A4 为 P0, 不齐 → status=partial 不进推荐;
A1 各类与 Selection≥0.85 为推荐参与门槛.

**评分器**: BFCL 开源 AST checker 的移植简化版(函数名精确 + 参数树匹配; 数值容忍/字符串归一),
exec 类(需真调用REST)与 multi_turn 的 state checker 降级为 P1(需桩工具实现).

## 三、实现路线(track3_agent.py 扩展)

1. BFCL loader: `data/cap/bfcl/BFCL_v3_{simple,multiple,parallel,parallel_multiple,irrelevance}.json`
   (hf-mirror `gorilla-llm/Berkeley-Function-Calling-Leaderboard/resolve/main/` 已实测可达)
2. 请求构造: BFCL 条目(funcs+question) → tools+user; auto 模式; 关思考; n=50/类
3. AST scorer + 分类汇总 → A1; 现有 loop 用例升级为 A3(加并行/干扰/预算维度)
4. A4: 从 A1/A3 请求的时延统计 + spec counters 差值
5. P1: ComplexFuncBench(zai-org GitHub json)/ACEBench 接入, τ² 后置

## 四、与既有事故的呼应

- auto-parser 静默失败事故 → A1 全类自动覆盖此风险(修复前 bfcl_*_acc≈0)
- 并行调用弱项(一句话两城市只调第一个) → parallel_call_rate 持续跟踪
- 思考链烧尽 max_tokens 事故 → A4 reasoning_ab 量化 on/off 的 token 与时延代价
