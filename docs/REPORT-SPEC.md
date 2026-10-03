# 报告规格 v3（契约 · 2026-09-30 在 v2 基础上与用户共同确定）

> **[现行契约为 v4](REPORT-SPEC-v4.md)**（场景化: 机器先行 / vLLM 参数定场景 / 三集合 P0-P2 / schema 校验 / 确定性推荐）。本 v3 文本保留作历史与差异参照，v3.1 的四条采集义务在 v4 §3 中继承生效。

> 原则：报告永远从档案库生成，绝不手写；缺格如实标 `—(未采集)`，禁止臆造。
> v2 三项硬性要求保留：**① 行内嵌完整 vLLM 启动参数（逐 flag 原文）；② 每行带全部参与机器的运行环境档案；③ 环境必须含集群拓扑（是否组网/head/worker/数据面）。**
> **v3 三项硬性新增（"报告太儿戏"纠正）：① 每行必须含多套件能力跑分（gsm8k/mmlu/arc 三套起步，统一口径 0-shot·关思考链·temp=0·固定种子抽样）；② 性能必须是多档并发（c1/c8/c32），只测单档不合格；③ vLLM 指标按段取差值（性能段 idle→Track1、能力段 Track1→Track2），并含服务端分位数（TTFT/TPOT/ITL/排队 p99，vLLM 0.30 计数器名见 vllm_metrics）。**

## 一、行 schema（rows.jsonl，一行 = 一次运行组合）

```json
{
  "run_id": "r001", "ts": "...", "duration_s": 23,
  "vllm_args": ["vllm","serve","/root/.cache/huggingface/<model>",
    "--tensor-parallel-size","2","--distributed-executor-backend","ray",
    "--served-model-name","bench","--host","0.0.0.0","--port","8000",
    "--gpu-memory-utilization","0.85","--max-model-len","40960",
    "--max-num-seqs","64","--enable-chunked-prefill","--enable-prefix-caching"],
  "launch_env": {"CUTE_DSL_ARCH":"sm_121a","HF_ENDPOINT":"https://hf-mirror.com",
    "GLOO_SOCKET_IFNAME":"enp1s0f1np1","NCCL_SOCKET_IFNAME":"enp1s0f1np1",
    "RAY_memory_monitor_refresh_ms":"0"},
  "machines": [{
      "host":"192.168.199.129","hostname":"gx10-9f5c","role":"head",
      "mgmt_ip":"192.168.199.129(wifi-dhcp)","data_ip":"192.168.100.10",
      "os":"Ubuntu 24.04.5 LTS","kernel":"7.0.0-1019-nvidia","arch":"aarch64",
      "cpu":"20","memory":"121Gi","gpu":"GB10","driver":"580.178.04",
      "docker":"29.6.2","image_digest":"sha256:91d9b077589e",
      "nvme_serial":"...","macs":["..."]}],
  "cluster": {"mode":"ray-2node-TP2 | single-node",
      "head":"192.168.100.10(gx10-9f5c)","workers":["192.168.100.11(gx10-9c05)"],
      "data_plane":"QSFP 直连 192.168.100.0/24","iface":"enp1s0f1np1","ray":"2.44.0"},
  "params":   { tp, model, quant, arch, params_b, active_b, max_model_len,
                gpu_mem_util, max_num_seqs, chunked_prefill, prefix_caching,
                backend, pinned_iface, served_name },
  "perf":    { dataset: "random-512", params: {input_len,output_len,levels,warmup,...},
               levels: { c1:{num_prompts,ttft_ms{p50,p90,p99},tpot_ms{...},
                          output_tok_s,total_tok_s,qps,completed,failed,
                          avg_completion_tokens,wall_s},
                          c8:{...}, c32:{...} },
               duration_s, gate_pass },
  "roofline": { ceiling_tok_s, c1_output_tok_s, utilization, warning },
  "vllm_metrics": {   // 两段差值: perf=idle→Track1, cap=Track1→Track2
      perf: { requests_success(stop+length), requests_failed(abort+error),
              prompt_tokens, gen_tokens, prefix_queries, prefix_hits,
              prompt_tokens_cached, kv_cache_usage, running_peak,
              ttft_p99_server_s, ttft_p50_server_s, tpot_p99_server_s,
              itl_p99_server_s, queue_p99_server_s },
      cap: { 同上 } },
  "capability": { gsm8k: {acc,n,correct,avg_completion_tokens,requests_failed,mode},
                  mmlu: {同}, arc: {同} },
  "capability_params": { n_per_suite:200, concurrency:8, seed, mode:"0-shot,no-think,temp=0" },
  "serve_ready_s": 312,
  "notes": ""
}
```

> vLLM 0.30 计数器名（实测，写死在 bench/common.py METRIC_KEYS）：
> `request_success_total{finished_reason=stop|length|abort|error}`（旧名 num_requests_success_total 不存在）、
> `prompt_tokens_total`/`generation_tokens_total`/`prompt_tokens_cached_total`、
> `prefix_cache_{queries,hits}_total`、直方图 `time_to_first_token_seconds`/
> `request_time_per_output_token_seconds`/`inter_token_latency_seconds`/`request_queue_time_seconds`
> （分位数由直方图桶内插得到）。

## 二、渲染规则（report_gen.py，确定性）

1. **主表**：一行一 run。参数列紧凑渲染（TP/后端/max-len/gpu-util/seqs/cp/pc），
   **完整 vLLM 参数原文进"运行参数全记录"节**（逐 flag + launch_env）；
2. **机器环境表**（每 run 一张或共用一张按 cluster 分组）：hostname/管理口/数据口/
   OS/内核/驱动/GPU/Docker/镜像 digest/NVMe 序列；
3. **集群拓扑**：mode/head/workers/数据面/网卡/ray 版本——**单机行必须显式标"无集群"**；
4. 缺格渲染 `—(未采集)`；同组合多 run 并列标注重复性；
5. 表尾：屋顶线核验列 + 环境指纹声明（版本变更即失效）。

## 三、各阶段采集义务（单元格来源）

| 阶段 | 必采 | 填充 |
|---|---|---|
| 引导/清点 | machines/{host}.json 全字段 | machines[] |
| 底座/组网 | 镜像 digest、ray 版本、QSFP 拓扑 | machines[].image_digest + cluster |
| 服务 | **完整 vllm argv 原文 + launch_env**、serve 就绪耗时 | vllm_args/launch_env + serve_ready_s |
| 验证 | /metrics 快照（idle/perf 后/cap 后三时点） | vllm_metrics 两段差值 |
| 基准 | bench/track1 perf json（c1/c8/c32 三档） | perf.levels + roofline |
| 能力 | bench/track2 cap json（gsm8k/mmlu/arc） | capability + capability_params |
| 指纹 | envfingerprint.sh | env（每机器） |

**v3.1 采集义务（本轮实测教训追加）**：
① serve 就绪后必须把启动日志的 `GPU KV cache size`/`Maximum concurrency` 两行落档
   （vllm.log 每次 serve 覆盖，不落档即永久丢失）；
② KV/running 峰值必须负载中轮询（相位后快照已回落 0%，bench.GaugePoller 2s 采样）；
③ 能力评测必须 `enable_thinking=false`（思考链耗尽 max_tokens → gsm8k 2%假象，实测关链后 94.5%）；
④ 性能档内网络失败条目自动补跑并记 retried 数（管理面 WiFi 瞬断实测会废整档）。
