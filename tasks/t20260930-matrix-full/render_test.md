# 条件组合完整数据报告（契约 v3 渲染）

**生成**: 确定性渲染自 `render_test.jsonl`（1 行）| 缺格 = —(未采集)

## 一、主表（一行一运行：参数 · 单流性能 · 能力三套件）

| # | 模型 | 架构/量化 | TP | 集群 | max-len | seqs | cp/pc | c1 TTFT p50/90/99 ms | c1 TPOT p50/90/99 ms | c1 出流 tok/s | gsm8k | mmlu | arc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Qwen3.8-27B-NVFP4 | dense/NVFP4 | 1 | single-node | 40960 | 64 | cp/pc | 478/479/479 | 117.5/117.7/117.7 | 8.4 | 1.000 | 1.000 | 1.000 |

## 二、多档并发性能（c1 / c8 / c32，random-512入/256出/ignore_eos/temp=0）

| 组合 | 档 | n | TTFT p50/p99 ms | TPOT p50/p99 ms | 出流 tok/s | 总吞吐 tok/s | QPS | 成/败 | 平均输出tok |
|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-NVFP4·TP1 | 1 | 2 | 478/479 | 117.5/117.7 | 8.4 | 33 | 0.03 | 2/0 | 256 |

### 屋顶线常识检查（单流解码上限 ≈ 带宽 ÷ 激活权重）

| 组合 | 上限 tok/s | c1 实测 | 利用率 | 警告 |
|---|---|---|---|---|
| Qwen3.8-27B-NVFP4·TP1 | — | — | — | — |

## 三、模型能力（统一口径：0-shot · 关思考链 · temp=0 · 每套件 n=8 · 并发8）

| 组合 | gsm8k acc | 对/ n | 平均输出tok | mmlu acc | 对/ n | arc acc | 对/ n | 失败请求 |
|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-NVFP4·TP1 | 1.000 | 8/8 | 256 | 1.000 | 7/7 | 1.000 | 8/8 | 0 |

*注: 0-shot 关思考链口径低于官方 few-shot 属预期, 看横向相对差; 选择题要求仅输出字母(平均输出≈2 tok), 数学题自由推理(平均输出≈250 tok)。*

## 四、vLLM 服务端指标（性能段=idle→Track1后, 能力段=Track1→Track2后, 计数器差值）

| 组合 | 段 | 成功 | 失败 | prompt tok | gen tok | 前缀命中q/h | 缓存prompt tok | KV峰 | running峰 | TTFT p99(服务端) | TPOT p99(服务端) | 请求时延 p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.8-27B-NVFP4·TP1 | perf | — | — | 632 | 274 | 632/0 | 0 | 0.1% | 1 | 0.248 | — | — |
| Qwen3.8-27B-NVFP4·TP1 | cap | — | — | — | — | — | — | — | — | — | — | — |

## 五、每机器运行环境与集群拓扑

### r1 · single-node（无集群, 单机服务）

| 主机名 | 角色 | 管理口 | 数据口 | OS | 内核 | GPU/驱动 | CPU/内存 | Docker | 镜像 | NVMe序列 |
|---|---|---|---|---|---|---|---|---|---|---|
| gx10-9f5c | head | 192.168.199.129(wifi-dhcp) | 192.168.100.10 | Ubuntu 24.04.5 LTS (Noble Numbat) | 7.0.0-1019-nvidia | GB10 + drv 580.178.04 | 20核/121Gi | Docker 29.6.2 | sha256:91d9b077589e | 511250619080002301 |

## 六、vLLM 完整启动参数（逐 flag 原文 + 启动环境变量）

- **r1** `vllm serve /root/.cache/huggingface/Qwen3.8-27B-NVFP4 --tensor-parallel-size 1 --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching`
  - launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}`

## 七、确定性结论（由数据规则推导，非人工撰写）

- **单流延迟最优**: Qwen3.8-27B-NVFP4·TP1 —— c1 TPOT p50 117.5 ms，出流 8.4 tok/s
- **单流吞吐最高**: Qwen3.8-27B-NVFP4·TP1 —— 8.4 tok/s（TP1，dense架构）
- **能力最佳**: Qwen3.8-27B-NVFP4·TP1 —— 三套件均分 1.000 （gsm8k 1.000 / mmlu 1.000 / arc 1.000）

---
*本报告由契约 v3 渲染；仅适用指纹匹配环境，版本变更即失效。*