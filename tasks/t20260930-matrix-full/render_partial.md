# GX10 双机 vLLM 条件组合完整报告（契约 v4 场景化）

**生成**: 确定性渲染自 `report_doc.json` | 2 机 × 4 场景 | 缺格 = —(未采集)

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

## Part B · 场景（按 vLLM 完整启动参数划分，一参数集一场景）

### 场景 S1 · `080ea122` — Qwen3.8-27B-NVFP4（dense，27B/激活27B，NVFP4） [⚠partial:perf.w2,perf.w3,perf.w4]

**① vLLM 完整启动参数**（逐 flag 原文，场景唯一定义源）

```bash
vllm serve /root/.cache/huggingface/Qwen3.8-27B-NVFP4 --tensor-parallel-size 2 --distributed-executor-backend ray --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching
```
launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}`

**② 部署拓扑与每机 ray 设置**

- 模式: **ray-tp2-2node** · 数据面: QSFP直连 192.168.100.0/24（iface enp1s0f1np1）

| machine_id | 角色 | ray 设置 | GPU 占用 |
|---|---|---|---|
| gx10-9f5c | head | `ray start --head --port=6379 --node-ip-address=192.168.100.10` env=`{"RAY_memory_monitor_refresh_ms": "0"}` 资源={"GPU": 1} | TP0/2 shard |
| gx10-9c05 | worker | `ray start --address=192.168.100.10:6379 --node-ip-address=192.168.100.11` env=`{"RAY_memory_monitor_refresh_ms": "0"}` 资源={"GPU": 1} | TP1/2 shard |

**③ vLLM 服务端指标集合**

| 组 | 指标 |
|---|---|
| 启动 | 就绪 110s · KV容量 4,485,740 tok · 最大并发 109.5× · cudagraph PIECEWISE · autotune True · max_num_seqs 64 |
| 负载中峰值 | KV占用 — · running — · waiting —（最重相 w1:c1） |

| 相位 | 成功 | 失败 | prompt tok | gen tok | 前缀q/h | TTFT p99 | TPOT p99 | ITL p99 | 排队 p99 |
|---|---|---|---|---|---|---|---|---|---|
| phase:w1 | 89 | 0 | 66,485 | 22,544 | 66,485/0 | 7.125 | 0.148 | 0.358 | 7.750 |

**④ 性能指标集合**（SLO: TTFT≤500ms 且 TPOT≤100ms）

- **w1**（random-512，入512→出256）

| 档 | n | TTFT p50/p90/p99 ms | TPOT p50/p90/p99 ms | ITL p99/max | E2E p99 | 单流出流 p50 | 出流 tok/s | QPS | goodput | 成/败 | retried |
|---|---|---|---|---|---|---|---|---|---|---|---|
| c1 | 8 | 221.4/230.838/232.4 | 50.59/50.637/50.64 | 57.3/96.2 | 13139 | 19.5 | 19.5 | 0.08 | 100% | 8/0 | 0 |
| c8 | 32 | 812.6/1198.142/1613 | 63.5/65.213/65.56 | 202.0/418.7 | 17611 | 15.1 | 119.9 | 0.47 | 12% | 32/0 | 0 |
| c32 | 48 | 1739/5421.46/6215 | 101.3/103.458/105.4 | 397.8/403.7 | 30942 | 9.1 | 256.2 | 1.00 | 2% | 48/0 | 0 |

  屋顶线: 上限 35 tok/s · c1 利用率 55% · 无警告

**⑤ 能力分数集合**（统一口径 0-shot · 关思考链 · temp=0 · n=200 · 并发8）

| 套件 | 维度 | acc | 对/n | 平均输出tok | 失败 | 状态 |
|---|---|---|---|---|---|---|
| math500 | - | — | — | — | — | 缺: 数据集布局不兼容(hf-mirror 404) |
| cmmlu/ceval | - | — | — | — | — | 缺: 同上, 中文套件下轮接 datasets 库 |
| ifeval | - | — | — | — | — | 缺: 需可验证规则引擎(P2) |

证据目录: `tasks/t20260930-matrix-full/raw4/TP2-Qwen3.8`

---

### 场景 S2 · `2212ac57` — Qwen3.6-35B-A3B-NVFP4-Fast（moe，35B/激活3B，NVFP4） [⚠partial:perf.w1,perf.w2,perf.w3]

**① vLLM 完整启动参数**（逐 flag 原文，场景唯一定义源）

```bash
vllm serve /root/.cache/huggingface/Qwen3.6-35B-A3B-NVFP4-Fast --tensor-parallel-size 2 --distributed-executor-backend ray --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching --kernel-config {"enable_flashinfer_autotune":false}
```
launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}` · 备注: FlashInfer自调优关闭口径(跨会话自调优确定性死亡, 实测代价<1%)

**② 部署拓扑与每机 ray 设置**

- 模式: **ray-tp2-2node** · 数据面: QSFP直连 192.168.100.0/24（iface enp1s0f1np1）

| machine_id | 角色 | ray 设置 | GPU 占用 |
|---|---|---|---|
| gx10-9f5c | head | `ray start --head --port=6379 --node-ip-address=192.168.100.10` env=`{"RAY_memory_monitor_refresh_ms": "0"}` 资源={"GPU": 1} | TP0/2 shard |
| gx10-9c05 | worker | `ray start --address=192.168.100.10:6379 --node-ip-address=192.168.100.11` env=`{"RAY_memory_monitor_refresh_ms": "0"}` 资源={"GPU": 1} | TP1/2 shard |

**③ vLLM 服务端指标集合**

| 组 | 指标 |
|---|---|
| 启动 | 就绪 —s · KV容量 — tok · 最大并发 —× · cudagraph PIECEWISE · autotune False · max_num_seqs 64 |

| 相位 | 成功 | 失败 | prompt tok | gen tok | 前缀q/h | TTFT p99 | TPOT p99 | ITL p99 | 排队 p99 |
|---|---|---|---|---|---|---|---|---|---|

**④ 性能指标集合**（SLO: TTFT≤500ms 且 TPOT≤100ms）

**⑤ 能力分数集合**（统一口径 0-shot · 关思考链 · temp=0 · n=200 · 并发8）

| 套件 | 维度 | acc | 对/n | 平均输出tok | 失败 | 状态 |
|---|---|---|---|---|---|---|
| math500 | - | — | — | — | — | 缺: 数据集布局不兼容(hf-mirror 404) |
| cmmlu/ceval | - | — | — | — | — | 缺: 同上, 中文套件下轮接 datasets 库 |
| ifeval | - | — | — | — | — | 缺: 需可验证规则引擎(P2) |

证据目录: `tasks/t20260930-matrix-full/raw4/TP2-Qwen3.6`

---

### 场景 S3 · `c82510df` — Qwen3.6-35B-A3B-NVFP4-Fast（moe，35B/激活3B，NVFP4） [⚠partial:perf.w1,perf.w2,perf.w3]

**① vLLM 完整启动参数**（逐 flag 原文，场景唯一定义源）

```bash
vllm serve /root/.cache/huggingface/Qwen3.6-35B-A3B-NVFP4-Fast --tensor-parallel-size 1 --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching
```
launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}`

**② 部署拓扑与每机 ray 设置**

- 模式: **single-node** · 数据面: 无(仅管理口)

| machine_id | 角色 | ray 设置 | GPU 占用 |
|---|---|---|---|
| gx10-9f5c | standalone | none(uni后端,单进程) | TP0/1 shard |

**③ vLLM 服务端指标集合**

| 组 | 指标 |
|---|---|
| 启动 | 就绪 —s · KV容量 — tok · 最大并发 —× · cudagraph PIECEWISE · autotune True · max_num_seqs 64 |

| 相位 | 成功 | 失败 | prompt tok | gen tok | 前缀q/h | TTFT p99 | TPOT p99 | ITL p99 | 排队 p99 |
|---|---|---|---|---|---|---|---|---|---|

**④ 性能指标集合**（SLO: TTFT≤500ms 且 TPOT≤100ms）

**⑤ 能力分数集合**（统一口径 0-shot · 关思考链 · temp=0 · n=200 · 并发8）

| 套件 | 维度 | acc | 对/n | 平均输出tok | 失败 | 状态 |
|---|---|---|---|---|---|---|
| math500 | - | — | — | — | — | 缺: 数据集布局不兼容(hf-mirror 404) |
| cmmlu/ceval | - | — | — | — | — | 缺: 同上, 中文套件下轮接 datasets 库 |
| ifeval | - | — | — | — | — | 缺: 需可验证规则引擎(P2) |

证据目录: `tasks/t20260930-matrix-full/raw4/TP1-Qwen3.6`

---

### 场景 S4 · `06802822` — Qwen3.8-27B-NVFP4（dense，27B/激活27B，NVFP4） [⚠partial:perf.w1,perf.w2,perf.w3]

**① vLLM 完整启动参数**（逐 flag 原文，场景唯一定义源）

```bash
vllm serve /root/.cache/huggingface/Qwen3.8-27B-NVFP4 --tensor-parallel-size 1 --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching
```
launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}`

**② 部署拓扑与每机 ray 设置**

- 模式: **single-node** · 数据面: 无(仅管理口)

| machine_id | 角色 | ray 设置 | GPU 占用 |
|---|---|---|---|
| gx10-9f5c | standalone | none(uni后端,单进程) | TP0/1 shard |

**③ vLLM 服务端指标集合**

| 组 | 指标 |
|---|---|
| 启动 | 就绪 —s · KV容量 — tok · 最大并发 —× · cudagraph PIECEWISE · autotune True · max_num_seqs 64 |

| 相位 | 成功 | 失败 | prompt tok | gen tok | 前缀q/h | TTFT p99 | TPOT p99 | ITL p99 | 排队 p99 |
|---|---|---|---|---|---|---|---|---|---|

**④ 性能指标集合**（SLO: TTFT≤500ms 且 TPOT≤100ms）

**⑤ 能力分数集合**（统一口径 0-shot · 关思考链 · temp=0 · n=200 · 并发8）

| 套件 | 维度 | acc | 对/n | 平均输出tok | 失败 | 状态 |
|---|---|---|---|---|---|---|
| math500 | - | — | — | — | — | 缺: 数据集布局不兼容(hf-mirror 404) |
| cmmlu/ceval | - | — | — | — | — | 缺: 同上, 中文套件下轮接 datasets 库 |
| ifeval | - | — | — | — | — | 缺: 需可验证规则引擎(P2) |

证据目录: `tasks/t20260930-matrix-full/raw4/TP1-Qwen3.8`

---

## Part C · 推荐（确定性规则推导，数值可回查）

**未参评场景**: `080ea122`(partial: 缺 perf.w2,perf.w3,perf.w4,perf.w5); `2212ac57`(partial: 缺 perf.w1,perf.w2,perf.w3,perf.w4); `c82510df`(partial: 缺 perf.w1,perf.w2,perf.w3,perf.w4); `06802822`(partial: 缺 perf.w1,perf.w2,perf.w3,perf.w4)

---
*本报告由契约 v4 渲染（schema 校验 + 推荐数值回查双门禁）；仅适用指纹匹配环境。*