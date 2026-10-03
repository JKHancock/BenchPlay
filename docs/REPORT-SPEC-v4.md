# 报告契约 v4 —— 场景化报告规范（schema 表达 · 2026-09-30 与用户共同确定）

> **一句话**: 报告 = 机器环境清单(Part A) + 按 vLLM 完整运行参数划分的 scenario 列表(Part B, 每场景五要素: 模型/机器布局含每机ray/vLLM指标集合/性能指标集合/能力分数集合) + 确定性推荐(Part C)。文档必须通过 JSON Schema 校验才可渲染, 缺格如实标注, 禁止臆造。

## 0. 设计原则

1. **机器先行**: 环境清单在一切数据之前。每台机(如 GX10 Node1/Node2)分别交代硬件环境与软件环境(含驱动、容器), 全文只声明一次, 场景里按 machine_id 引用, 不重复。
2. **场景为纲**: `vllm serve` 的**完整 argv 原文**唯一定义一个 scenario; argv 不同即不同场景。scenario_id = sha1(argv + model_path + tp) 前 8 位。
3. **五要素完备**: 每个 scenario 必须有 模型 / 运行机器与每机 ray 设置 / vllm_metrics / perf_metrics / capability_scores。P0 指标族不齐 → status=partial, **不得进入推荐环节**。
4. **三集合足够多**: 三集合各定义 P0(必测)/P1(扩展)/P2(可选) 指标族全清单——集合的丰富度即 benchmark 覆盖度义务(见 §3)。
5. **校验即门禁**: report_doc.json 先过 `jsonschema.validate`, 再确定性渲染; 推荐由规则引擎从数据推导, 同输入必同输出, 每条理由必须引用具体单元格。

## 1. 文档结构与 JSON Schema

### 1.1 顶层 ReportDoc

```json
{
  "meta": {          // 必填
    "contract_version": "4",
    "generated_at": "ISO8601",
    "source_artifacts": ["tasks/<id>/raw/..."],
    "fingerprint": {"vllm": "...", "image_digest": "...", "driver": "...",
                    "gpu": "...", "ray": "...", "recorded_at": "..."}
  },
  "machines":  [Machine, ...],        // ≥1, Part A
  "scenarios": [Scenario, ...],       // ≥1, Part B
  "recommendation": Recommendation    // Part C
}
```

### 1.2 Machine（Part A：硬件环境 + 软件环境）

```json
{
  "machine_id": "gx10-9f5c",              // = hostname, 场景引用键
  "alias": "GX10 Node1",
  "identity": {"hostname": "...", "mgmt_ip": "192.168.199.129(OTA-DHCP,会漂移)",
               "data_ip": "192.168.100.10"},
  "hardware": {                            // 全部必填
    "gpu": "GB10", "gpu_count": 1, "unified_memory": "121Gi(GB10统一内存)",
    "cpu": "20核 aarch64", "memory": "121Gi",
    "nvme": [{"size": "...", "serial": "..."}],
    "nics": [{"name": "enp1s0f1np1", "ip": "192.168.100.10", "net": "QSFP直连",
              "bandwidth": "...", "role": "data"},
             {"name": "...", "ip": "192.168.199.x", "net": "WiFi-DHCP", "role": "mgmt"}]
  },
  "software": {                            // 全部必填
    "os": "Ubuntu 24.04.5 LTS", "kernel": "7.0.0-1019-nvidia", "arch": "aarch64",
    "gpu_driver": "580.178.04",
    "container_runtime": {"docker": "29.6.2"},
    "container": {"name": "vllm-node", "image": "...", "image_digest": "sha256:91d9b077589e",
                  "network_mode": "host", "vllm_ver": "0.30.0",
                  "ray_ver": "2.44.0", "python_ver": "3.12"}
  }
}
```

### 1.3 Scenario（Part B）

```json
{
  "scenario_id": "a1b2c3d4",              // sha1(argv+model+tp)[:8]
  "vllm_args": ["vllm","serve","...","--tensor-parallel-size","2", ...],  // 逐token原文, 唯一定义源
  "launch_env": {"CUTE_DSL_ARCH":"sm_121a", "NCCL_SOCKET_IFNAME":"enp1s0f1np1", ...},
  "model": {                              // 必填
    "name": "Qwen3.6-35B-A3B-NVFP4-Fast", "path": "/root/.cache/huggingface/...",
    "quant": "NVFP4", "arch": {"type":"moe","params_b":35,"active_b":3},
    "weights_gb": 19.0, "context_len": 40960, "served_name": "bench"
  },
  "deployment": {                         // 必填; 集群必须逐机说明 ray 设置
    "mode": "single-node | ray-tp2-2node",
    "machines": [                         // 每台参与机器一条
      {"machine_id": "gx10-9f5c", "role": "head|worker|standalone",
       "ray": {"role": "head",
               "start_cmd": "ray start --head --port=6379 --node-ip-address=192.168.100.10",
               "env": {"RAY_memory_monitor_refresh_ms":"0"},
               "resources": {"GPU": 1}},
       "gpu_alloc": "TP0 shard 9.5GB权重+KV"}
    ],
    "data_plane": {"topology": "QSFP直连 192.168.100.0/24 | 无(仅管理口)",
                   "iface": "enp1s0f1np1", "measured_bw_gbps": null}
  },
  "vllm_metrics":      VllmMetrics,       // §1.4, 必填
  "perf_metrics":      PerfMetrics,       // §1.5, 必填
  "capability_scores": CapabilityScores,  // §1.6, 必填
  "status": "complete | partial",
  "missing": ["perf_metrics.workloads[w4-long]", ...],   // partial 时的缺失清单
  "evidence": {"raw_dir": "tasks/<id>/raw/<tag>/", "files": ["perf.json","cap.json",...]},
  "fingerprint": {/* 与 meta.fingerprint 同构, 允许复用 */},
  "notes": "..."
}
```

### 1.4 vllm_metrics 集合（指标族全清单）

```json
{
  "startup": {                            // P0 全必填(取自启动日志, serve 就绪时落档)
    "ready_s": 150, "load_s": null,
    "kv_cache_tokens": 13786190, "max_concurrency_x": 336.0,
    "tensor_parallel": 2, "pipeline_parallel": 1,
    "cudagraph_mode": "PIECEWISE|FULL|NONE", "flashinfer_autotune": false,
    "compile_cache": "hit|miss|n.a.",
    "weights_gb": 19.0, "gpu_mem_reserved_gb": 87.0,
    "max_num_seqs": 64, "max_model_len": 40960, "gpu_mem_util": 0.85
  },
  "gauges_peak": {                        // P0: 负载中轮询(GaugePoller 2s), 按相位
    "phase:perf:c32": {"kv_cache_usage_perc": 0.31, "gpu_cache_usage_perc": 0.31,
                        "num_requests_running": 32, "num_requests_waiting": 16},
    "phase:cap:*":        { 同上 }
  },
  "counters": {                           // P0: 相位差值(成功=stop+length, 失败=abort+error)
    "phase:perf": {"requests_stop":80,"requests_length":9,"requests_abort":0,
                   "requests_error":0,"prompt_tokens":66485,"generation_tokens":22784,
                   "prefix_cache_queries":66485,"prefix_cache_hits":0,
                   "prompt_tokens_cached":0},
    "phase:cap":  { 同上 },
    "phase:w2-real": { 同上 }             // P1: 每工作负载单独一相
  },
  "histograms": {                         // P0: 服务端直方图分位(vLLM 0.30 实测键名)
    "phase:perf": {"ttft_s":{"p50":0.790,"p99":2.436},
                    "tpot_s":{"p50":0.0436,"p99":0.0451},
                    "itl_s":{"p99":0.203}, "queue_s":{"p99":2.050}},
    "phase:cap":  { 同上 }
  },
  "host_per_machine": {                   // P1: 负载中 nvidia-smi 采样, 每机一条
    "gx10-9f5c": {"gpu_util_perc_peak": 98, "gpu_mem_used_gb_peak": 103,
                   "power_w_avg": null}
  }
}
```

**vLLM 0.30 计数器名勘误**（写死在 bench/common.py METRIC_KEYS）：
`request_success_total{finished_reason=stop|length|abort|error}`（旧名 num_requests_success_total 不存在）·
`request_time_per_output_token_seconds`（TPOT 直方图带 request_ 前缀）· `inter_token_latency_seconds` ·
`request_queue_time_seconds` · `request_prefill_time_seconds` · `request_inference_time_seconds`。

### 1.5 perf_metrics 集合（工作负载 × 并发 × 指标族）

工作负载矩阵（**负载即契约**——覆盖短/中/长/真实分布/纯延迟/长输出六型）：

| id | 型 | 输入→输出 | 分布 | 并发档 | 级 |
|---|---|---|---|---|---|
| w1-random-512x256 | 吞吐上限探针 | 512→256 | 合成随机 | c1,c8,c32 | **P0** |
| w2-real-sharegpt | 真实分布 | 抽取分布 | ShareGPT 提取(prompts.jsonl 已备) | c1,c8 | **P0** |
| w3-short-32x8 | 对话延迟档 | 32→8 | 合成 | c1,c8 | P1 |
| w4-long-4096x256 | 长文预填压力 | 4096→256 | 合成 | c1,c4 | P1 |
| w5-outladder | TTFT/长输出曲线 | 4096→{1,16,256,1024} | 合成 | c1 | P1 |
| w6-c64 | 满序列批 | 512→256 | 合成 | c64(=max_num_seqs上限) | P1 |

每 (负载, 档) 指标族（P0 加粗）：

```json
{
  "workload_id": "w1-random-512x256",
  "spec": {"input_len":512,"output_len":256,"dataset":"random|sharegpt",
           "ignore_eos":true,"temperature":0.0,"seed":20260930,"warmup":1,"cooldown_s":10},
  "levels": [{
    "concurrency": 32, "num_prompts": 48, "retried": 0,
    "ttft_ms":  {"mean":912,"p50":790,"p90":1580,"p99":2516,"max":2610},
    "tpot_ms":  {"mean":44.0,"p50":43.6,"p90":44.8,"p99":45.1,"max":45.9},
    "itl_ms":   {"p50":43.6,"p99":61.2,"max":118.0},
    "e2e_ms":   {"p50":12040,"p90":14200,"p99":15600},
    "per_stream_out_tok_s": {"p50":22.9,"p99":22.4},
    "agg": {"output_tok_s":614.2,"total_tok_s":2406,"qps":2.40},
    "slo": {"ttft_p99_le_ms":500,"tpot_p99_le_ms":100,
            "goodput_pct":100.0,"met":true},
    "reliability": {"completed":48,"failed":0,"rejected":0,"timeout":0},
    "roofline": {"ceiling_tok_s":321.2,"util":0.277,"warning":null}   // 仅c1档
  }]
}
```

探针（独立于工作负载）：

| 探针 | 产出 | 级 |
|---|---|---|
| prefix-cache-probe: 同前缀 1024tok×64条重复请求 | hit_rate、TTFT 加速比 | P1 |
| capacity-staircase: 并发阶梯爬升直至拒绝/超时 | max_ok_conc、首败模式 | P1 |
| soak-30min: 固定 c8 持续压测 | 出流漂移%、内存漂移 | P2 |

### 1.6 capability_scores 集合（套件全清单 × 维度 × 口径）

| suite | 维度 | n | 判分 | 级 |
|---|---|---|---|---|
| gsm8k | 数学推理 | ≥200 | ####数值精确匹配 | **P0** |
| mmlu(57科分层) | 知识(EN) | ≥200/科池 | 字母匹配 | **P0** |
| arc_challenge | 科学推理 | ≥200 | 字母匹配 | **P0** |
| cmmlu 或 ceval | 知识(ZH) | ≥200 | 字母匹配 | P1 |
| hellaswag | 常识 | ≥200 | 字母匹配 | P1 |
| winogrande | 共指消解 | ≥200 | 字母匹配 | P1 |
| math500 | 高难数学 | 全量500 | 数值匹配 | P1 |
| ifeval | 指令遵循 | ≥200 | 可验证规则 | P1 |
| humaneval | 代码 | 全量164 | pass@1(需执行沙箱) | P2 |
| needle-in-haystack | 长文检索 | 3深度×3长度 | 检索命中 | P2 |
| gsm8k-thinking-on | 数学(思考链口径) | ≥150 | 同gsm8k | P2 |
| capability@c8 | 负载下质量退化 | 每套件100 | 同各套件 | P2 |

统一口径（P0 硬约束）：`0-shot · enable_thinking=false · temp=0 · seed=20260930 · 分层抽样 · 并发8`。
**实测依据**: 思考链不关会耗尽 max_tokens → gsm8k 2.05% 假分；关链后 94.5%。

```json
{
  "suites": [{
    "suite_id": "gsm8k", "dimension": "math",
    "settings": {"n":200,"shots":0,"thinking":"off","temperature":0.0,
                 "max_tokens":1024,"seed":20260930,"concurrency":8},
    "score": {"acc":0.945,"correct":189,"n":200,
              "unanswered":0,"truncated":0},
    "tokens": {"avg_out":277.0,"std_out":null},
    "reliability": {"requests_failed":0}, "duration_s": 522
  }],
  "thinking_model_dual_mode": true    // 思考型模型 P2 需补 on/off 双口径
}
```

### 1.7 Recommendation（Part C：确定性规则引擎）

```json
{
  "method": "规则可复算: score(profile, s) = 加权归一(延迟/吞吐/能力/资源), 权重表随报告输出",
  "profiles": [{
    "profile": "综合推荐 | 延迟敏感 | 吞吐优先 | 能力优先 | 单机约束(无集群)",
    "winner": "scenario_id",
    "reasons": ["c32 出流 614.2 tok/s 高于次优 429.0 (+43%)",
                 "c1 TPOT p50 10.7ms 为全场最低(次优 14.4ms)",
                 "三套件能力 0.945/0.820/0.975, 与能力最佳场景差≤3.5pt"],
    "runner_up": {"scenario_id":"...", "gaps":["c32 出流 -30%", "..."]}
  }],
  "ineligible": [{"scenario_id":"...", "cause":"status=partial, 缺 w2-real"}]
}
```

规则要点：①只有 status=complete 的场景参评；②每条 reason 必须含**数值+对比对象**；③单机约束 profile 只在 single-node 场景中选；④权重组随报告明示（可审计、可复算）。

### 1.8 校验 Schema（draft-07, 摘要）

```json
{ "$schema":"http://json-schema.org/draft-07/schema#", "type":"object",
  "required":["meta","machines","scenarios","recommendation"],
  "properties":{
    "meta":{"type":"object","required":["contract_version","generated_at","fingerprint"]},
    "machines":{"type":"array","minItems":1,"items":{"$ref":"#/definitions/Machine"}},
    "scenarios":{"type":"array","minItems":1,"items":{"$ref":"#/definitions/Scenario"}},
    "recommendation":{"type":"object","required":["profiles"],"minProperties":1}},
  "definitions":{
    "Machine":{"type":"object","required":["machine_id","hardware","software"],
      "properties":{
        "machine_id":{"type":"string"},
        "hardware":{"type":"object","required":["gpu","gpu_count","cpu","memory","nvme","nics"]},
        "software":{"type":"object","required":["os","kernel","arch","gpu_driver",
                     "container_runtime","container"]}}},
    "Scenario":{"type":"object",
      "required":["scenario_id","vllm_args","launch_env","model","deployment",
                  "vllm_metrics","perf_metrics","capability_scores","status"],
      "properties":{
        "scenario_id":{"type":"string","pattern":"^[0-9a-f]{8}$"},
        "vllm_args":{"type":"array","minItems":3},
        "model":{"type":"object","required":["name","quant","arch","context_len"]},
        "deployment":{"type":"object","required":["mode","machines","data_plane"],
          "properties":{"machines":{"type":"array","minItems":1}}},
        "vllm_metrics":{"type":"object","required":["startup","gauges_peak","counters","histograms"]},
        "perf_metrics":{"type":"object","required":["workloads"],
          "properties":{"workloads":{"type":"array","minItems":1}}},
        "capability_scores":{"type":"object","required":["suites"],
          "properties":{"suites":{"type":"array","minItems":3}}},
        "status":{"enum":["complete","partial"]}}}}}
```

`status=complete` 的判定（校验后置规则，report_gen 内实现）：P0 全齐 = w1 全档 + w2 ≥c1 + 三套件(gsm8k/mmlu/arc) + startup/gauges_peak/counters/histograms 四组非空。**P0 不齐 → partial → 不进推荐**。

## 2. 渲染规则（确定性，report_gen 实现）

1. **Part A 先行**: 每机两张表——硬件表(GPU/CPU/内存/NVMe序列/网卡含数据面与管理面) + 软件表(OS/内核/驱动/Docker/镜像digest/容器内 vllm·ray 版本)；
2. **Part B 每场景一节**, 小节序 = 场景列表序：① vllm argv 原文 + launch_env + scenario_id；② 部署拓扑(参与机器表 + **每机 ray 设置** + 数据面)；③ vLLM 指标组(startup/峰值/计数器/直方图四表)；④ 性能(每工作负载一表, 行=并发档)；⑤ 能力(套件表, 含口径行)；⑥ status 与 missing(如有)；
3. **Part C 推荐**: 每 profile 一小节, winner+数值化理由+次优差距+落选原因(含 partial 落选声明)；
4. 缺格渲染 `—(未采集)`, 有值禁改写、禁四舍五入到失真；报告尾输出指纹声明与环境漂移失效条款；
5. 渲染器对 report_doc.json 先 `jsonschema.validate`, 不过即拒绝渲染(门禁在脚本)。

## 3. 采集义务矩阵（阶段 → 单元格；三集合的 P0/P1/P2 即覆盖度契约）

| 阶段 | 采集 | 填充 |
|---|---|---|
| 引导/清点 | machines/{host}.json | Machine(Part A) |
| 底座 | 镜像 digest、容器内版本 | Machine.software |
| 组网 | 每机 ray start 命令/env/资源、QSFP 拓扑与实测带宽 | Scenario.deployment |
| 服务 | argv 原文、launch_env、启动两行(KV容量/最大并发×)、就绪耗时 | vllm_args + vllm_metrics.startup |
| 验证 | /metrics 三时点快照(每工作负载一相) | counters/histograms |
| 基准 | w1-w6 工作负载 × 档 + GaugePoller 峰值 + 探针 | perf_metrics + gauges_peak |
| 能力 | 套件全清单(按级) 统一口径 | capability_scores |
| 主机 | 负载中 nvidia-smi 采样(每机) | host_per_machine |
| 推理 | 规则引擎跑分 | recommendation |

## 4. 门禁

1. **schema 门禁**: validate 不过 → 不渲染；
2. **数值闸门**: 每档 completed>0 且 failed=0；能力 requests_failed < 5%；截断率(truncated/n) < 10% 否则标 ⚠；屋顶线 > 80% 报警人工复核；
3. **完整性闸门**: P0 不齐 → partial → 推荐环节排除并在报告明示；
4. **复算门禁**: recommendation 的每条 reason 中数值必须能在对应 scenario 单元格中找到(渲染器校验, 找不到即渲染失败)。

## 5. 与 v3 的差异 & 实施差距清单（gap）

结构差异：行模式(rows.jsonl 每行重复 machines) → **场景模式**(machines 声明一次被引用)；报告从"全表拼合" → Part A/B/C 三段自洽；新增 deployment 每机 ray、推荐引擎、schema 校验、SLO/goodput、探针、主机采样。

实施差距（按优先级）：

| # | 缺口 | 动作 | 量级 |
|---|---|---|---|
| 1 | 场景化文档+校验器 | rows.jsonl → report_doc.json + jsonschema(venv 装包) | 小 |
| 2 | w2 真实分布接线 | bench/track1 支持 prompts.jsonl 数据集(数据已备) | 小 |
| 3 | 推荐规则引擎 | report_gen 内确定性评分+理由生成(含数值回查) | 小 |
| 4 | GaugePoller 按相位入档 | 已有工具, 接 phase 键 | 小 |
| 5 | P1 能力套件 | cmmlu/ceval、hellaswag、winogrande、math500、ifeval 接入 track2 | 中 |
| 6 | P1 性能负载 | w3/w4/w5/w6 + prefix-cache 探针 + capacity 阶梯 | 中 |
| 7 | 主机负载中采样 | ssh 并行 nvidia-smi 采样器 | 小 |
| 8 | P2 | humaneval 沙箱、needle、思考链口径、负载下质量 | 大, 后置 |
| 9 | 历史数据迁移 | t20260930 四行映射为 4 场景(已有数据填 P0 大半) | 小 |

---
*本契约为报告与 benchmark 覆盖度的共同上游；三集合 P0/P1 清单即测试完备性验收标准。*

---

## v4.1 增量（2026-09-30 · 智能体维度补全）

1. **Machine/Part A 之前新增 Model Profile 节**: 每 profiled 模型一节(MTP能力/method/k建议、原生上下文、rope形态、权重量GB、多模态、parser建议) — 数据源 `models/<name>.profile.json`
2. **scenario 增 serving_profile**: `chat | agent`; agent 档 argv 必含 `--enable-auto-tool-choice --tool-call-parser <p>`(来自M0建议), 且推荐 开/关 两场景成对入矩阵
3. **capability_scores 增 track3 组**(agent用途P0): `selection_acc / args_acc / loop_success / loop_e2e_ms`; `status=complete` 判定: 用途=agent 的场景 Track3 不齐 → partial
4. **vllm_metrics 增 spec 组(P0, 计数器已有)**: `acceptance_rate = accepted/draft_tokens`、`num_drafts_total` — 投机档必报
5. **M0 义务表新行**: 服务阶段前置 → model_profile.py → Part A' Model Profile + 场景生成输入

## v4.2 增量（2026-09-30 · 第四指标集合 agent_metrics）

三集合 → 四集合: `vllm_metrics / perf_metrics / capability_scores / agent_metrics`.
规格全文见 [AGENT-BENCH.md](AGENT-BENCH.md). 要点:
1. A1(BFCL v3 AST 五类, hf-mirror 可达) + A3(循环: pass@1/并行率/克制/预算) + A4(服务: toolcall_ttft/loop_e2e/reasoning on-off A/B) = **agent 用途场景的 P0**, 不齐 partial 不进推荐;
2. A2(ComplexFuncBench 约束/多步/128k)为 P1; τ²-bench(需用户模拟器)/沙箱级(SWE/terminal) P2 或注记;
3. 数据集落 `data/cap/bfcl/`, 评分器为 BFCL AST checker 移植简化版, 实现 track3_agent.py 扩展.

## v4.3 增量（2026-09-30 · 打分体系与套件扩容）

**打分规则（三层数学, 权重随报告输出可复算）**:
套件原始acc → 维度分(成员等权均值) → 总分(Σ维度权重×维度分)×100
- C-Score 权重: 数学.18 知识.22 常识.18 科学.12 诚实.18 共指.12（成员变动时权重表随报告重算公示）
- A-Score 权重: BFCL克制.25 BFCL结构.25 循环.30 工具选择.20
- 报告同时呈现三层（原始>维度>总分, 总分是派生视图不得替代原始）
**套件扩容现状**: 能力 8 套件(gsm8k/mmlu/arc/hellaswag/winogrande/truthfulqa/openbookqa/race);
BFCL 两类接入(irrelevance精确分, simple结构分下界 — HF版真值脱敏, 官方AST精判待真值源, 如实标注);
待接: ceval/cmmlu(布局不兼容)/math500/IFEval/BFCL multiple·parallel(需真值)/τ².
