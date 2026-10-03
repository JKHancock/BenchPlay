# 条件组合完整数据报告（契约 v3 渲染）

**生成**: 确定性渲染自 `rows.jsonl`（4 行）| 缺格 = —(未采集)

## 一、主表（一行一运行：参数 · 单流性能 · 能力三套件）

| # | 模型 | 架构/量化 | TP | 集群 | max-len | seqs | cp/pc | c1 TTFT p50/90/99 ms | c1 TPOT p50/90/99 ms | c1 出流 tok/s | gsm8k | mmlu | arc |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Qwen3.6-35B-A3B-NVFP4-Fast | MoE-A3B/NVFP4 | 2 | ray-2node-TP2 | 40960 | 64 | cp/pc | 143/154/171 | 10.7/10.8/10.9 | 88.9 | 0.945 | 0.820 | 0.975 |
| 2 | Qwen3.6-35B-A3B-NVFP4-Fast | MoE-A3B/NVFP4 | 1 | single-node | 40960 | 64 | cp/pc | 142/152/155 | 14.4/14.5/14.5 | 67.0 | 0.940 | 0.820 | 0.970 |
| 3 | Qwen3.8-27B-NVFP4 | dense/NVFP4 | 2 | ray-2node-TP2 | 40960 | 64 | cp/pc | 239/246/248 | 50.3/50.4/50.4 | 19.6 | 0.945 | 0.855 | 0.965 |
| 4 | Qwen3.8-27B-NVFP4 | dense/NVFP4 | 1 | single-node | 40960 | 64 | cp/pc | 282/298/300 | 90.2/90.2/90.2 | 11.0 | 0.945 | 0.820 | 0.965 |

## 二、多档并发性能（c1 / c8 / c32，random-512入/256出/ignore_eos/temp=0）

| 组合 | 档 | n | TTFT p50/p99 ms | TPOT p50/p99 ms | 出流 tok/s | 总吞吐 tok/s | QPS | 成/败 | 平均输出tok |
|---|---|---|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B-NVFP4-Fast·TP2 | 1 | 8 | 143/171 | 10.7/10.9 | 88.9 | 349 | 0.35 | 8/0 | 256 |
| Qwen3.6-35B-A3B-NVFP4-Fast·TP2 | 8 | 32 | 520/721 | 21.1/22.3 | 348.7 | 1367 | 1.36 | 32/0 | 256 |
| Qwen3.6-35B-A3B-NVFP4-Fast·TP2 | 32 | 48 | 790/2516 | 43.6/45.1 | 614.2 | 2406 | 2.40 | 48/0 | 256 |
| Qwen3.6-35B-A3B-NVFP4-Fast·TP1 | 1 | 8 | 142/155 | 14.4/14.5 | 67.0 | 263 | 0.26 | 8/0 | 256 |
| Qwen3.6-35B-A3B-NVFP4-Fast·TP1 | 8 | 32 | 617/793 | 29.2/30.6 | 253.3 | 993 | 0.99 | 32/0 | 256 |
| Qwen3.6-35B-A3B-NVFP4-Fast·TP1 | 32 | 48 | 974/2973 | 62.9/64.6 | 429.0 | 1680 | 1.68 | 48/0 | 256 |
| Qwen3.8-27B-NVFP4·TP2 | 1 | 8 | 239/248 | 50.3/50.4 | 19.6 | 77 | 0.08 | 8/0 | 256 |
| Qwen3.8-27B-NVFP4·TP2 | 8 | 32 | 816/1566 | 63.1/65.2 | 120.7 | 473 | 0.47 | 32/0 | 256 |
| Qwen3.8-27B-NVFP4·TP2 | 32 | 48 | 1833/6262 | 101.2/104.9 | 255.8 | 1002 | 1.00 | 48/0 | 256 |
| Qwen3.8-27B-NVFP4·TP1 | 1 | 8 | 282/300 | 90.2/90.2 | 11.0 | 43 | 0.04 | 8/0 | 256 |
| Qwen3.8-27B-NVFP4·TP1 | 8 | 32 | 1418/2104 | 103.0/105.8 | 73.8 | 289 | 0.29 | 32/0 | 256 |
| Qwen3.8-27B-NVFP4·TP1 | 32 | 48 | 2607/8664 | 157.5/162.6 | 161.8 | 634 | 0.63 | 48/0 | 256 |

### 屋顶线常识检查（单流解码上限 ≈ 带宽 ÷ 激活权重）

| 组合 | 上限 tok/s | c1 实测 | 利用率 | 警告 |
|---|---|---|---|---|
| Qwen3.6-35B-A3B-NVFP4-Fast·TP2 | 321 | 88.9 | 28% | — |
| Qwen3.6-35B-A3B-NVFP4-Fast·TP1 | 161 | 67.0 | 42% | — |
| Qwen3.8-27B-NVFP4·TP2 | 35 | 19.6 | 56% | — |
| Qwen3.8-27B-NVFP4·TP1 | 18 | 11.0 | 62% | — |

## 三、模型能力（统一口径：0-shot · 关思考链 · temp=0 · 每套件 n=200 · 并发8）

| 组合 | gsm8k acc | 对/ n | 平均输出tok | mmlu acc | 对/ n | arc acc | 对/ n | 失败请求 |
|---|---|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B-NVFP4-Fast·TP2 | 0.945 | 189/200 | 277 | 0.820 | 164/200 | 0.975 | 195/200 | 0 |
| Qwen3.6-35B-A3B-NVFP4-Fast·TP1 | 0.940 | 188/200 | 280 | 0.820 | 164/200 | 0.970 | 194/200 | 0 |
| Qwen3.8-27B-NVFP4·TP2 | 0.945 | 189/200 | 290 | 0.855 | 171/200 | 0.965 | 193/200 | 0 |
| Qwen3.8-27B-NVFP4·TP1 | 0.945 | 189/200 | 281 | 0.820 | 164/200 | 0.965 | 193/200 | 0 |

*注: 0-shot 关思考链口径低于官方 few-shot 属预期, 看横向相对差; 选择题要求仅输出字母(平均输出≈2 tok), 数学题自由推理(平均输出≈250 tok)。*

## 四、vLLM 服务端指标（性能段=idle→Track1后, 能力段=Track1→Track2后, 计数器差值）

| 组合 | 段 | 成功(stop+len) | 失败(abort+err) | prompt tok | gen tok | 前缀命中q/h | TTFT p99(服务端) | TPOT p99(服务端) | ITL p99 | 排队 p99 |
|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3.6-35B-A3B-NVFP4-Fast·TP2 | perf | 89 | 0 | 66,485 | 22,784 | 66,485/0 | 2.436 | 0.050 | 0.203 | 2.050 |
| Qwen3.6-35B-A3B-NVFP4-Fast·TP2 | cap | 600 | 0 | 63,964 | 56,342 | 63,964/0 | 2.007 | 0.090 | 0.092 | 1.444 |
| Qwen3.6-35B-A3B-NVFP4-Fast·TP1 | perf | 89 | 0 | 66,485 | 22,784 | 66,485/0 | 4.679 | 0.074 | 0.219 | 2.750 |
| Qwen3.6-35B-A3B-NVFP4-Fast·TP1 | cap | 600 | 0 | 63,964 | 56,995 | 63,964/0 | 2.536 | 0.140 | 0.076 | 1.910 |
| Qwen3.8-27B-NVFP4·TP2 | perf | 89 | 0 | 66,485 | 22,784 | 66,485/0 | 7.179 | 0.148 | 0.371 | 8.500 |
| Qwen3.8-27B-NVFP4·TP2 | cap | 600 | 0 | 63,964 | 58,754 | 63,964/0 | 5.036 | 0.136 | 0.188 | 4.188 |
| Qwen3.8-27B-NVFP4·TP1 | perf | 89 | 0 | 66,485 | 22,784 | 66,485/0 | 9.679 | 0.199 | 0.597 | 9.591 |
| Qwen3.8-27B-NVFP4·TP1 | cap | 600 | 0 | 63,964 | 57,009 | 63,964/0 | 7.536 | 0.257 | 0.157 | 6.864 |

### KV 缓存容量与最大可并发倍数（启动日志 kv_cache_utils 实测行）

| 组合 | KV 容量(tokens) | 最大并发×(40,960/请求) | 来源 |
|---|---|---|---|
| Qwen3.6-35B-A3B-NVFP4-Fast·TP2 | 13,786,190 | 336.0 | t20261001 r001 实测(同指纹环境) |
| Qwen3.6-35B-A3B-NVFP4-Fast·TP1 | — | — | 旧serve未持久化启动日志(v3.1起持久化) |
| Qwen3.8-27B-NVFP4·TP2 | — | — | 旧serve未持久化启动日志(v3.1起持久化) |
| Qwen3.8-27B-NVFP4·TP1 | 1,942,496 | 47.4 | 本会话 vllm.log 启动行 |

*注: 前缀命中 0 属预期——random 数据集与各题独立问句无共享前缀块; KV/running 为相位后 gauge(已回落), 负载中峰值采样自 v3.1 起为采集义务。*

## 五、每机器运行环境与集群拓扑

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

## 六、vLLM 完整启动参数（逐 flag 原文 + 启动环境变量 + 就绪耗时）

- **r1** `vllm serve /root/.cache/huggingface/Qwen3.6-35B-A3B-NVFP4-Fast --tensor-parallel-size 2 --distributed-executor-backend ray --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching --kernel-config {"enable_flashinfer_autotune": false}`
  - launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}` · serve就绪耗时: 710s
  - ⚠备注: 三次复测95/93/94ms(±1%); 补采serve两次失败(开放问题:自调优后init fail) | 本行关FlashInfer自调优口径(自调优跨会话确定性死亡~33min后改--kernel-config关闭, 150s即就绪; 对比旧自调优口径c1=89.6tok/s, 差<1%)
- **r2** `vllm serve /root/.cache/huggingface/Qwen3.6-35B-A3B-NVFP4-Fast --tensor-parallel-size 1 --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching`
  - launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}` · serve就绪耗时: 160s
- **r3** `vllm serve /root/.cache/huggingface/Qwen3.8-27B-NVFP4 --tensor-parallel-size 2 --distributed-executor-backend ray --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching`
  - launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}` · serve就绪耗时: 120s
- **r4** `vllm serve /root/.cache/huggingface/Qwen3.8-27B-NVFP4 --tensor-parallel-size 1 --served-model-name bench --host 0.0.0.0 --port 8000 --gpu-memory-utilization 0.85 --max-model-len 40960 --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching`
  - launch_env: `{"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com", "GLOO_SOCKET_IFNAME": "enp1s0f1np1", "NCCL_SOCKET_IFNAME": "enp1s0f1np1", "RAY_memory_monitor_refresh_ms": "0"}` · serve就绪耗时: 180s
  - ⚠备注: 补采复测(v2采集) | 首轮c1档遇管理面WiFi瞬时断连(8条中7条连接失败, c8/c32正常), 本行为整组合重跑

## 七、确定性结论（由数据规则推导，非人工撰写）

- **单流延迟最优**: Qwen3.6-35B-A3B-NVFP4-Fast·TP2 —— c1 TPOT p50 10.7 ms，出流 88.9 tok/s
- **单流吞吐最高**: Qwen3.6-35B-A3B-NVFP4-Fast·TP2 —— 88.9 tok/s（TP2，MoE-A3B架构）
- **能力最佳**: Qwen3.8-27B-NVFP4·TP2 —— 三套件均分 0.922 （gsm8k 0.945 / mmlu 0.855 / arc 0.965）
- **高并发吞吐最高**: Qwen3.6-35B-A3B-NVFP4-Fast·TP2 —— c32 出流 614 tok/s，QPS 2.40

---
*本报告由契约 v3 渲染；仅适用指纹匹配环境，版本变更即失效。*