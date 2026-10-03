# 条件组合完整数据报告（契约 v2 渲染）

**生成**: 确定性渲染自 `rows.jsonl`（4 行）| 缺格 = —(未采集)

## 一、主表（一行一运行）

| # | 模型 | 架构 | TP | 后端 | 集群 | max-len | gpu-util | seqs | cp/pc | TTFT p50/90/99 ms | TPOT p50/90/99 ms | 出流 tok/s | 总吞吐 | QPS | 成/败 | KV tokens | 并发× | gsm8k |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Qwen3.6-35B-A3B-NVFP4-Fast | MoE-A3B | 2 | ray | ray-2node-TP2 | 40960 | 0.85 | 64 | cp/pc | 93/94/95 | 10/11/13 | 89.6 | 273.2 | 0.35 | 8/0 | 13786190 | 336 | — |
| 2 | Qwen3.6-35B-A3B-NVFP4-Fast | MoE-A3B | 1 | uni | single-node | 40960 | 0.85 | 64 | cp/pc | 117/126/129 | 14/14/14 | 67.7 | 206.2 | 0.26 | 8/0 | — | — | 0.0205 |
| 3 | Qwen3.8-27B-NVFP4 | dense | 2 | ray | ray-2node-TP2 | 40960 | 0.85 | 64 | cp/pc | 183/187/189 | 50/50/51 | 19.7 | 63.2 | 0.08 | 8/0 | — | — | — |
| 4 | Qwen3.8-27B-NVFP4 | dense | 1 | uni | single-node | 40960 | 0.85 | 64 | cp/pc | 437/439/440 | 115/117/118 | 8.6 | 27.5 | 0.03 | 8/0 | — | — | — |

## 二、每机器运行环境与集群拓扑

### r1 · ray-2node-TP2（head=192.168.100.10(gx10-9f5c) workers=192.168.100.11(gx10-9c05) 数据面=QSFP直连 192.168.100.0/24 网卡=enp1s0f1np1 ray=2.44.0）

| 主机名 | 角色 | 管理口 | 数据口 | OS | 内核 | GPU/驱动 | CPU/内存 | Docker | 镜像 | NVMe序列 |
|---|---|---|---|---|---|---|---|---|---|---|
| gx10-9f5c | head | 192.168.199.129(wifi-dhcp) | 192.168.100.10 | Ubuntu 24.04.5 LTS (Noble Numbat) | 7.0.0-1019-nvidia | GB10 + drv 580.178.04 | 20核/121Gi | Docker 29.6.2 | sha256:91d9b077589e | 511250619080002301 |
| gx10-9c05 | worker | 192.168.199.134(wifi-dhcp) | 192.168.100.11 | Ubuntu 24.04.5 LTS (Noble Numbat) | Linux 7.0.0-1019-nvidia | GB10 + drv 580.178.04 | 20核/121Gi | Docker 29.6.2 | sha256:91d9b077589e | 511250619080002242 |

### r2 · single-node（无集群, 单机服务）

| 主机名 | 角色 | 管理口 | 数据口 | OS | 内核 | GPU/驱动 | CPU/内存 | Docker | 镜像 | NVMe序列 |
|---|---|---|---|---|---|---|---|---|---|---|
| gx10-9f5c | head | 192.168.199.129(wifi-dhcp) | 192.168.100.10 | Ubuntu 24.04.5 LTS (Noble Numbat) | 7.0.0-1019-nvidia | GB10 + drv 580.178.04 | 20核/121Gi | Docker 29.6.2 | sha256:91d9b077589e | 511250619080002301 |

### r3 · ray-2node-TP2（head=192.168.100.10(gx10-9f5c) workers=192.168.100.11(gx10-9c05) 数据面=QSFP直连 192.168.100.0/24 网卡=enp1s0f1np1 ray=2.44.0）

| 主机名 | 角色 | 管理口 | 数据口 | OS | 内核 | GPU/驱动 | CPU/内存 | Docker | 镜像 | NVMe序列 |
|---|---|---|---|---|---|---|---|---|---|---|
| gx10-9f5c | head | 192.168.199.129(wifi-dhcp) | 192.168.100.10 | Ubuntu 24.04.5 LTS (Noble Numbat) | 7.0.0-1019-nvidia | GB10 + drv 580.178.04 | 20核/121Gi | Docker 29.6.2 | sha256:91d9b077589e | 511250619080002301 |
| gx10-9c05 | worker | 192.168.199.134(wifi-dhcp) | 192.168.100.11 | Ubuntu 24.04.5 LTS (Noble Numbat) | Linux 7.0.0-1019-nvidia | GB10 + drv 580.178.04 | 20核/121Gi | Docker 29.6.2 | sha256:91d9b077589e | 511250619080002242 |

### r4 · single-node（无集群, 单机服务）

| 主机名 | 角色 | 管理口 | 数据口 | OS | 内核 | GPU/驱动 | CPU/内存 | Docker | 镜像 | NVMe序列 |
|---|---|---|---|---|---|---|---|---|---|---|
| gx10-9f5c | head | 192.168.199.129(wifi-dhcp) | 192.168.100.10 | Ubuntu 24.04.5 LTS (Noble Numbat) | 7.0.0-1019-nvidia | GB10 + drv 580.178.04 | 20核/121Gi | Docker 29.6.2 | sha256:91d9b077589e | 511250619080002301 |

## 三、vLLM 完整启动参数（逐 flag 原文 + 启动环境变量）

- **r1** `vllm serve /root/.cache/huggingface/Qwen3.6-35B-A3B-NVFP4-Fast --tensor-parallel-size 2 --distributed-executor-backend ray --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching`
  - launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}`
- **r2** `vllm serve /root/.cache/huggingface/Qwen3.6-35B-A3B-NVFP4-Fast --tensor-parallel-size 1 --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching`
  - launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}`
- **r3** `vllm serve /root/.cache/huggingface/Qwen3.8-27B-NVFP4 --tensor-parallel-size 2 --distributed-executor-backend ray --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching`
  - launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}`
- **r4** `vllm serve /root/.cache/huggingface/Qwen3.8-27B-NVFP4 --tensor-parallel-size 1 --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching`
  - launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}`

## 四、vLLM 服务端指标

| # | KV tokens | 最大并发× | 前缀命中率 | gpu_cache峰 | prompt tokens | gen tokens | MTP接受率 |
|---|---|---|---|---|---|---|---|
| 1 | 13786190 | 336 | — | — | — | — | — |
| 2 | — | — | 0/9484 | — | 9,484 | — | — |
| 3 | — | — | 0/9484 | — | 9,484 | — | — |
| 4 | — | — | 0/180977 | — | 180,977 | — | — |

---
*本报告由契约 v2 渲染；仅适用指纹匹配环境，版本变更即失效。*