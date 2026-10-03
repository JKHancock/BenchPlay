# GX10 双机 vLLM 条件组合完整报告（契约 v4 场景化）

**生成**: 确定性渲染自 `report_doc.json` | 2 机 × 1 场景 | 缺格 = —(未采集)

**适用指纹**: vLLM `0.30.0` · 镜像 `sha256:91d9b077589e` · 驱动 `580.178.04` · ray `2.44.0` （2026-09-30T22:45:35 复核）——环境漂移即整体失效

## Part A · 机器环境清单（先于一切数据）

### GX10 Node1（machine_id: `gx10-9f5c`）

| 硬件 | 值 |
|---|---|
| GPU | GB10 × 1（统一内存 121Gi(统一内存)） |
| CPU | 20核 aarch64 |
| 内存 | 121Gi |
| NVMe | 见档案 |
| 网卡·data | enp1s0f1np1 = 192.168.100.10（QSFP直连 192.168.100.0/24） |
| 网卡·mgmt | wlan/ether = 192.168.199.129（OTA WiFi-DHCP） |

| 软件 | 值 |
|---|---|
| OS/内核/架构 | Ubuntu 24.04.5 LTS (Noble Numbat) / 7.0.0-1019-nvidia / aarch64 |
| GPU 驱动 | 580.178.04 |
| 容器运行时 | Docker 29.6.2 |
| vLLM 容器 | `vllm-node`（镜像 sha256:91d9b077589e，network=host，vllm 0.30.0 · ray 2.44.0 · py 3.12） |

### GX10 Node2（machine_id: `gx10-9c05`）

| 硬件 | 值 |
|---|---|
| GPU | GB10 × 1（统一内存 121Gi(统一内存)） |
| CPU | 20核 aarch64 |
| 内存 | 121Gi |
| NVMe | 见档案 |
| 网卡·data | enp1s0f1np1 = 192.168.100.11（QSFP直连 192.168.100.0/24） |
| 网卡·mgmt | wlan/ether = 192.168.199.134（OTA WiFi-DHCP） |

| 软件 | 值 |
|---|---|
| OS/内核/架构 | Ubuntu 24.04.5 LTS (Noble Numbat) / Linux 7.0.0-1019-nvidia / aarch64 |
| GPU 驱动 | 580.178.04 |
| 容器运行时 | Docker 29.6.2 |
| vLLM 容器 | `vllm-node`（镜像 sha256:91d9b077589e，network=host，vllm 0.30.0 · ray 2.44.0 · py 3.12） |

## Part B · 场景（按模型分组；组内场景 = 同模型的不同 vLLM 参数/集群组合）

### 模型 1 · Qwen3.8-Flash-Next-NVFP4（1 个参数组合）

### 场景 S1 · `58df5374` — Qwen3.8-Flash-Next-NVFP4（moe，230B/激活4B，NVFP4） [完整]

**① vLLM 完整启动参数**（逐 flag 原文，场景唯一定义源）

```bash
vllm serve /root/.cache/huggingface/Qwen3.8-Flash-Next-NVFP4 --tensor-parallel-size 2 --distributed-executor-backend ray --speculative-config {"method":"qwen4_exp_mtp","num_speculative_tokens":2} --hf-overrides {"text_config":{"max_position_embeddings":1048576,"rope_scaling":{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":262144}}} --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3 --served-model-name flash-next --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 1048576 --max-num-seqs 8 --max-num-batched-tokens 8192 --enable-chunked-prefill --enable-prefix-caching
```
launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}` · 备注: qwen4_exp新架构首次在本集群实测; 132.64GB权重; Track3工具选择8/8满分但l2计算题模型弃用工具直接心算(loop=0.5, 行为特征如实记录)

**② 部署拓扑与每机 ray 设置**

- 模式: **ray-tp2-2node** · 数据面: QSFP直连 192.168.100.0/24（iface enp1s0f1np1）

| machine_id | 角色 | ray 设置 | GPU 占用 |
|---|---|---|---|
| gx10-9f5c | head | `ray start --head --port=6379 --node-ip-address=192.168.100.10` env=`{"RAY_memory_monitor_refresh_ms": "0"}` 资源={"GPU": 1} | TP0/2 shard |
| gx10-9c05 | worker | `ray start --address=192.168.100.10:6379 --node-ip-address=192.168.100.11` env=`{"RAY_memory_monitor_refresh_ms": "0"}` 资源={"GPU": 1} | TP1/2 shard |

**③ vLLM 服务端指标集合**

| 组 | 指标 |
|---|---|
| 启动 | 就绪 480s · KV容量 1,899,278 tok · 最大并发 1.8× · cudagraph PIECEWISE · autotune True · max_num_seqs 64 |
| 负载中峰值 | KV占用 — · running — · waiting —（最重相 w1:c1） |

| 相位 | 成功 | 失败 | prompt tok | gen tok | 前缀q/h | TTFT p99 | TPOT p99 | ITL p99 | 排队 p99 |
|---|---|---|---|---|---|---|---|---|---|
| phase:w1 | 0 | 0 | 66,485 | 22,544 | 66,485/0 | 67.867 | 0.074 | 0.425 | 40.900 |
| phase:w2 | 0 | 0 | 6,089 | 16,400 | 6,089/0 | 59.200 | 0.074 | 0.324 | 39.757 |
| phase:w3 | 0 | 0 | 4,883 | 592 | 4,883/0 | 49.467 | 0.074 | 0.320 | 39.439 |
| phase:w4 | 0 | 0 | 71,584 | 3,088 | 71,584/0 | 47.733 | 0.074 | 0.334 | 39.383 |
| phase:w5 | 0 | 0 | 29,618 | 1,313 | 29,618/3,200 | 47.067 | 0.074 | 0.326 | 39.361 |
| phase:w6 | 0 | 0 | 48,581 | 16,400 | 48,581/0 | 142.171 | 0.074 | 0.409 | 112.512 |
| phase:probe | 0 | 0 | 0 | 0 | 0/0 | 142.171 | 0.074 | 0.409 | 112.512 |
| phase:cap | 3,198 | 3,198 | 247,877 | 49,337 | 247,877/0 | 72.938 | 0.252 | 0.308 | 74.112 |

**④ 性能指标集合**（SLO: TTFT≤500ms 且 TPOT≤100ms）

- **w1**（random-512，入512→出256）

| 档 | n | TTFT p50/p90/p99 ms | TPOT p50/p90/p99 ms | ITL p99/max | E2E p99 | 单流出流 p50 | 出流 tok/s | QPS | goodput | 成/败 | retried |
|---|---|---|---|---|---|---|---|---|---|---|---|
| c1 | 8 | 301.3/411.66/421.1 | 22/26.925/27.88 | 73.3/123.8 | 7531 | 43.3 | 41.1 | 0.16 | 100% | 8/0 | 0 |
| c8 | 32 | 678.3/3770.191/3772 | 47.52/58.602/64.33 | 442.7/3291.7 | 19687 | 19.6 | 145.3 | 0.57 | 25% | 32/0 | 0 |
| c32 | 48 | 3.114e+04/39729.395/4.057e+04 | 46.96/57.391/65.03 | 423.4/2517.1 | 52527 | 5.9 | 155.6 | 0.61 | 2% | 48/0 | 0 |

  屋顶线: 上限 136 tok/s · c1 利用率 30% · 无警告

- **w2**（sharegpt-real(100条,输入p50=35tok)，入—→出—）

| 档 | n | TTFT p50/p90/p99 ms | TPOT p50/p90/p99 ms | ITL p99/max | E2E p99 | 单流出流 p50 | 出流 tok/s | QPS | goodput | 成/败 | retried |
|---|---|---|---|---|---|---|---|---|---|---|---|
| c1 | 16 | 173.9/365.54/442.6 | 24.08/30.529/34.23 | 75.7/128.4 | 9028 | 40.8 | 38.9 | 0.15 | 100% | 16/0 | 0 |
| c8 | 48 | 377.8/476.723/614.5 | 46.01/59.569/67.91 | 202.1/2610.9 | 17800 | 21.2 | 150.6 | 0.59 | 98% | 48/0 | 0 |

  屋顶线: 上限 136 tok/s · c1 利用率 28% · 无警告

- **w3**（random-32，入32→出8）

| 档 | n | TTFT p50/p90/p99 ms | TPOT p50/p90/p99 ms | ITL p99/max | E2E p99 | 单流出流 p50 | 出流 tok/s | QPS | goodput | 成/败 | retried |
|---|---|---|---|---|---|---|---|---|---|---|---|
| c1 | 24 | 133.8/207.708/244.4 | 22.41/29.918/31.92 | 146.0/170.4 | 374 | 27.8 | 27.3 | 3.41 | 100% | 24/0 | 0 |
| c8 | 48 | 372.5/445.917/458.2 | 42.11/58.801/65.52 | 194.2/216.7 | 803 | 12.0 | 93.6 | 11.70 | 100% | 48/0 | 0 |

  屋顶线: 上限 136 tok/s · c1 利用率 20% · 无警告

- **w4**（random-4096，入4096→出256）

| 档 | n | TTFT p50/p90/p99 ms | TPOT p50/p90/p99 ms | ITL p99/max | E2E p99 | 单流出流 p50 | 出流 tok/s | QPS | goodput | 成/败 | retried |
|---|---|---|---|---|---|---|---|---|---|---|---|
| c1 | 4 | 2884/3118.91/3172 | 26.12/29.233/29.72 | 81.2/140.2 | 10746 | 26.9 | 27.8 | 0.11 | 0% | 4/0 | 0 |
| c4 | 8 | 5388/9313.213/1.048e+04 | 50.34/77.76/86.75 | 1719.8/3922.9 | 28964 | 13.7 | 53.9 | 0.21 | 0% | 8/0 | 0 |

  屋顶线: 上限 136 tok/s · c1 利用率 20% · 无警告

- **w5**（—，入4096→出—）

| 档 | n | TTFT p50/p90/p99 ms | TPOT p50/p90/p99 ms | ITL p99/max | E2E p99 | 单流出流 p50 | 出流 tok/s | QPS | goodput | 成/败 | retried |
|---|---|---|---|---|---|---|---|---|---|---|---|
| c1 | 1 | 755.8/755.782/755.8 | — | —/— | 756 | 1.3 | 1.3 | 1.32 | 0% | 1/0 | 0 |
| c1 | 1 | 1610/1609.801/1610 | 32.87/32.869/32.87 | 77.6/79.5 | 2103 | 7.6 | 7.6 | 0.48 | 0% | 1/0 | 0 |
| c1 | 1 | 2690/2690.381/2690 | 27.01/27.008/27.01 | 77.3/111.3 | 9578 | 26.7 | 26.7 | 0.10 | 0% | 1/0 | 0 |
| c1 | 1 | 2325/2325.248/2325 | 25.1/25.098/25.1 | 75.5/125.5 | 28001 | 36.6 | 36.6 | 0.04 | 0% | 1/0 | 0 |

- **w6**（random-512，入512→出256）

| 档 | n | TTFT p50/p90/p99 ms | TPOT p50/p90/p99 ms | ITL p99/max | E2E p99 | 单流出流 p50 | 出流 tok/s | QPS | goodput | 成/败 | retried |
|---|---|---|---|---|---|---|---|---|---|---|---|
| c64 | 64 | 5.068e+04/92231.024/9.96e+04 | 51.85/59.739/65.53 | 422.7/1311.4 | 112351 | 4.0 | 145.7 | 0.57 | 2% | 64/0 | 0 |

  屋顶线: 上限 136 tok/s · c1 利用率 — · 无警告

- **探针**: 前缀缓存 冷/热 TTFT p50 —/— ms → 加速 —× · 容量阶梯 最大可用并发 **—**（首败 8@timeout_or_conn）

**⑤ 能力分数集合**（统一口径 0-shot · 关思考链 · temp=0 · n=200 · 并发8）

| 套件 | 维度 | acc | 对/n | 平均输出tok | 失败 | 状态 |
|---|---|---|---|---|---|---|
| gsm8k | math | 0.965 | 193/200 | 233 | 0 | 实测 |
| mmlu | knowledge | 0.895 | 179/200 | 2 | 0 | 实测 |
| arc | science | 0.970 | 194/200 | 2 | 0 | 实测 |
| hellaswag | commonsense | 0.960 | 192/200 | 2 | 0 | 实测 |
| winogrande | coref | 0.865 | 173/200 | 2 | 0 | 实测 |
| truthfulqa | ? | 0.905 | 181/200 | 2 | 0 | 实测 |
| openbookqa | ? | 0.970 | 194/200 | 2 | 0 | 实测 |
| race | ? | 0.930 | 186/200 | 2 | 0 | 实测 |
| math500 | - | — | — | — | — | 缺: 数据集布局不兼容(hf-mirror 404) |
| cmmlu/ceval | - | — | — | — | — | 缺: 同上, 中文套件下轮接 datasets 库 |
| ifeval | - | — | — | — | — | 缺: 需可验证规则引擎(P2) |

证据目录: `tasks/t20260930-matrix-full/raw4/FlashNext-TP2-1M`

---

## Part C · 推荐（确定性规则推导，数值可回查）

### 综合推荐 → **Qwen3.6-35B-A3B-NVFP4-Fast(TP2+EP+MTP2+1M)**（`e64080d1`）

- 综合分 0.591(权重 c32吞吐0.35/c1吞吐0.2/能力0.25/KV容量0.1/省一机0.1)
- c32 出流 768.1 tok/s, c1 出流 121.4 tok/s, 三套件均分 0.915

### 延迟敏感 → **Qwen3.6-35B-A3B-NVFP4-Fast(TP2+EP+MTP2+1M)**（`e64080d1`）

- c1 TPOT p50 ms (越低越好): 7.774 vs 次优 10.82(Qwen3.6-35B-A3B-NVFP4-Fast(TP2))
- 差距: -3.05 (-28.2%)
- 次优: Qwen3.6-35B-A3B-NVFP4-Fast(TP2)

### 吞吐优先 → **Qwen3.6-35B-A3B-NVFP4-Fast(TP2+EP+MTP2+1M)**（`e64080d1`）

- c32 出流 tok/s: 768.1 vs 次优 615.4(Qwen3.6-35B-A3B-NVFP4-Fast(TP2+EP))
- 差距: +152.7 (+24.8%)
- 次优: Qwen3.6-35B-A3B-NVFP4-Fast(TP2+EP)

### 能力优先 → **Qwen3.8-Flash-Next-NVFP4(TP2+MTP2+1M)**（`58df5374`）

- 三套件(gsm8k/mmlu/arc)均分: 0.9433 vs 次优 0.92(Qwen3.8-27B-NVFP4(TP2))
- 差距: +0.02333 (+2.5%)
- 次优: Qwen3.8-27B-NVFP4(TP2)

### 单机约束(无集群) → **Qwen3.6-35B-A3B-NVFP4-Fast(TP1)**（`c82510df`）

- 单机场景中 c32 出流 431.1 tok/s 最高

---
*本报告由契约 v4 渲染（schema 校验 + 推荐数值回查双门禁）；仅适用指纹匹配环境。*