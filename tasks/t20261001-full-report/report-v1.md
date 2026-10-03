# GX10 双机 · 条件组合完整数据报告 v1

**环境指纹**: vllm=0.30.0 | image=sha256:91d9b077589e | driver=580.178.04 | GPU=GB10×2 (aarch64) | kernel=7.0.0-1019-nvidia | Docker=29.6.2 | ray=2.44.0
**数据面**: QSFP 直连 192.168.100.10↔.11 (enp1s0f1np1 钉定) | **基准**: random-512 输入 × 8 条 × 并发1, 预热, ignore_eos, temp=0, seed 固定
**生成**: report_gen.py 确定性渲染 | 缺格=—(未采集, 补采进行中)

## 一、主表（一行一运行 · 全列宽）

| # | 时间 | 模型 | 架构 | 量化 | TP | max-len | gpu-util | seqs | 后端 | 网卡钉定 | TTFT p50/90/99 (ms) | TPOT p50/90/99 (ms) | 出流 tok/s | 总吞吐 tok/s | QPS | 成/败 | KV tokens | 并发× | 前缀命中 | gpu_cache峰 | gsm8k |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15:41:15 | Qwen3.6-35B-A3B-NVFP4-Fast | MoE-A3B | NVFP4 | 2 | 40960 | 0.85 | 64 | ray | enp1s0f1np1 | 93/94/95 | 10/11/13 | 89.6 | 273.2 | 0.35 | 8/0 | 13786190 | 336 | — | — | — |
| 2 | 16:36:44 | Qwen3.6-35B-A3B-NVFP4-Fast | MoE-A3B | NVFP4 | 1 | 40960 | 0.85 | 64 | uni | enp1s0f1np1 | 117/126/129 | 14/14/14 | 67.7 | 206.2 | 0.26 | 8/0 | — | — | — | — | — |
| 3 | 16:43:35 | Qwen3.8-27B-NVFP4 | dense | NVFP4 | 2 | 40960 | 0.85 | 64 | ray | enp1s0f1np1 | 183/187/189 | 50/50/51 | 19.7 | 63.2 | 0.08 | 8/0 | — | — | — | — | — |
| 4 | 16:53:03 | Qwen3.8-27B-NVFP4 | dense | NVFP4 | 1 | 40960 | 0.85 | 64 | uni | enp1s0f1np1 | 267/287/307 | 90/90/90 | 11.1 | 35.6 | 0.04 | 8/0 | — | — | — | — | — |

## 二、模型档案（参数规模与屋顶线核验）

| 模型 | 架构 | 总参数 | 激活参数 | 权重体积(NVFP4) | 屋顶线上限(0.9TB/s) | 实测最高出流 | 核验 |
|---|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B | MoE | 35B | 3B | ≈22GB(全量)/激活≈1.6GB | ≈560 tok/s | 92.7 | ✓ 合理 |
| Qwen3.8-27B | 稠密 | 27B | 27B | ≈21.8GB | ≈41 tok/s(单机全量) | 19.7(TP2分摊后) | ✓ 合理 |

## 三、运行参数全记录（每 run）

- **r1 [2026-10-01T15:41]** Qwen3.6-35B-A3B-NVFP4-Fast TP=2 backend=ray | max-len=40960 gpu-util=0.85 seqs=64 chunked-prefill=True prefix-cache=True | 时长 23s  ★三次独立复测 95/93/94ms(±1%)
- **r2 [2026-10-01T16:36]** Qwen3.6-35B-A3B-NVFP4-Fast TP=1 backend=uni | max-len=40960 gpu-util=0.85 seqs=64 chunked-prefill=True prefix-cache=True | 时长 30s
- **r3 [2026-10-01T16:43]** Qwen3.8-27B-NVFP4 TP=2 backend=ray | max-len=40960 gpu-util=0.85 seqs=64 chunked-prefill=True prefix-cache=True | 时长 104s
- **r4 [2026-10-01T16:53]** Qwen3.8-27B-NVFP4 TP=1 backend=uni | max-len=40960 gpu-util=0.85 seqs=64 chunked-prefill=True prefix-cache=True | 时长 185s

## 四、能力评测（Track2）

| 模型 | gsm8k | 状态 |
|---|---|---|
| Qwen3.6-35B | — | 采集进行中(HF镜像通道已验证) |
| Qwen3.8-27B | — | 未测(全量预估>90min, 列入补测) |

## 五、结论与推荐策略

1. **首选 TP2×Qwen3.6-35B-A3B**: 出流 89.6-92.7 tok/s, TTFT<100ms, p99 尾部紧; KV 1386万token 支撑 336× 并发余量
2. **稠密 27B 必上 TP2**: 出流 1.8×(19.7 vs 11.1), TPOT 减半(50 vs 90ms)
3. **单机降级可用**: TP1×Qwen3.6 仍 67.7 tok/s
4. 测量可信度: 同组合三跑 ±1%; 全部数据过屋顶线核验

---
*本报告仅适用于指纹匹配环境(vllm 0.30.0/镜像 91d9b077589e/驱动 580.178.04); 版本变更即失效需重测。来源档案: tasks/t20261001-full-report/rows.jsonl | iter1-6 档案可溯。*
