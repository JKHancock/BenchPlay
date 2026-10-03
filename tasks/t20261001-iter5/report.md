# t20261001-iter5 测试段对接（双实现握手：部署侧服务 × 孪生 C# 基准实现）— 报告

> 生成时间: 2026-10-01 ｜ 报告员: 报告员(agent) ｜ **任务状态: completed（双实现握手首次贯通——BenchPlaybook(zcode agent 驾驶)经 iter4 部署链交付的 TP2 vLLM 服务(http://192.168.199.129:8000, served-model-name=bench)，由孪生 C# 实现 llm-bench CLI(Vllm_Benchmark 仓库)完成 Track1 性能基准；bench.sh 封装调用并带门禁(每层 completed>0 且 failed=0)，快速档(并发1×8) PASS：TTFT_p50=94ms / TPOT_p50=10.4ms / 出流=92.7 tok/s / 成8败0。Track2 质量通道本轮被 HF Hub 直连阻断，修复通道(HF_ENDPOINT=hf-mirror)已验证，完整档执行）**

## 一、概览

- **背景**：iter4 首次全脚本化部署四门禁全 PASS 后，服务在 head 129 的 8000 端口就绪。本轮进入测试段：**双实现握手**——BenchPlaybook 侧（zcode agent 驾驶的 bash playbook）负责部署与门禁封装，孪生 C# 实现（`Vllm_Benchmark` 仓库的 llm-bench CLI）负责真正跑基准；两者在 OpenAI 兼容 HTTP API 上握手，产物由 `bench.sh` 门禁验收。
- **模型**：Qwen3.6-35B-A3B-NVFP4-Fast（iter4 部署实测，TP2 跨 129+134，served-model-name=`bench`）。⚠️ 命名差异如实注明：CLI 配置 `configs/gx10-dual.yaml` 的展示名仍是 `qwen3.5-122b-a10b`（2026-09-29 旧部署遗留，`node.extract.tokenizer_path` 注释自证），结果目录名 `20261001-*-qwen3.5-122b-a10b` 同源——**实测发请求的 model 字段是 `bench`，指向的服务即 iter4 部署的 Qwen3.6-35B-A3B-NVFP4-Fast**；展示名未随部署更新，列遗留。
- **结果**：快速档（并发1×8）**三连跑全过门禁**（15:35:46 / 15:41:15 / 15:44:42 三个结果目录，指标量级一致），档案证据取最终跑 `20261001-154442`。
- **证据口径**：报告员本会话**未重跑基准、未重跑 lm_eval**。基准数字全部实读自 `results/*/perf_run_result.json` 与 `summary.json`；`HF_ENDPOINT=hf-mirror` 修复通道中的「gsm8k 经镜像实测可达」**转录自任务下发材料（驱动 agent 实测）**；镜像可达性另由报告员本会话 `curl` 独立复核（见 §四）。脚本行为均本会话实读源码核对。

## 二、双实现握手图

```
[BenchPlaybook 侧 — zcode agent 驾驶]                      [Vllm_Benchmark 侧 — 孪生 C# 实现 llm-bench CLI]
                                                            (D:/CSharpProject/Vllm_Benchmark)
 iter4 部署链(已归档 t20261001-iter4):                        configs/gx10-dual.yaml
  substrate → cluster → serve → verify 四门禁 PASS             model.served_name = "bench"
  → vllm serve Qwen3.6-35B-A3B-NVFP4-Fast TP2                  model.api_base   = http://192.168.199.129:8000/v1
    (129 head + 134 worker, 钉 enp1s0f1np1)                    engine = vllm
  ▼                                                            ▼
 http://192.168.199.129:8000  ◀━━ 握手点: OpenAI 兼容 HTTP API ━━┓  scripts/bench.sh (playbook 侧封装+门禁)
   /v1/models 含 bench (verify 关1 已验)                        ┃   dotnet run --project src/LocalLlmBench.Cli --
   /v1/chat/completions 冒烟良构 (关2)                          ┃     run -c configs/gx10-dual.yaml
   /metrics 375 个 vllm: 指标 (关3)                             ┃     --concurrency 1 --num-prompts 8   (bench.sh:13-14)
                                                            ┏━━┛
                                                            ▼
                                                [Track1 性能基准 (随机数据集零依赖)]
                                                  8 条 × input_len 512 / output_len 256
                                                  temperature=0, ignore_eos, seed=20260924
                                                  POST /v1/completions (model="bench")
                                                  并行轮询 /metrics 采集服务端指标 (poll 10s)
                                                            ▼
                                                results/20261001-154442-qwen3.5-122b-a10b/
                                                  perf_run_result.json   (47KB, Track1 全量+服务端指标快照)
                                                  capability_result.json (Track2, 本轮 tasks=[])
                                                  summary.json + lm_eval.log
                                                            ▼
                                                bench.sh 门禁: 读 perf_run_result.json phases,
                                                  每层 completed>0 ∧ failed=0                  (bench.sh:22-35)
                                                            ▼
                                     PASS Track1 基准完成, 产物: …/20261001-154442-…/perf_run_result.json  (bench.sh:36)
                                                            ▼
                                     档案归档: perf_run_result.json → tasks/t20261001-iter5/ (cmp 字节一致)
```

**握手结论**：部署侧交付的服务身份（`bench`）与 CLI 配置的 `served_name` 对上；CLI 发出的请求全部成功返回（8/8 completed, 0 failed）；服务端 `/metrics` 侧证——`perf_run_result.json` 内嵌 before/after 的 `vllm:num_requests_running{engine="0",model_name="bench"}` 快照（1→0）与 `prefix_cache_queries_total` 13177→14226，证明流量真实穿过该 vLLM 实例；playbook 门禁按产物 JSON 判定 PASS。双实现握手成立。

## 三、基准数据（快速档：并发1 × 8条）

**档案运行 20261001-154442**（实读 `perf_run_result.json`，JSON 原值）：

| 指标 | 值 | 指标 | 值 |
|---|---|---|---|
| completed / failed | **8 / 0** | duration | 22.082 s |
| TTFT mean / p50 | 96.92 / **94.19 ms** | TTFT p90 / p99 | 102.77 / 113.49 ms |
| TPOT mean / p50 | 10.44 / **10.44 ms** | TPOT p90 / p99 | 10.49 / 10.50 ms |
| ITL p50 / p90 / p99 | 10.38 / 12.04 / 16.22 ms | | |
| 出流 throughput | **92.74 tok/s** | 总 token throughput | 282.67 tok/s |
| 请求吞吐 | 0.362 req/s | input / output tokens | 4194 / 2048 |

**配置快照**（`perf_run_result.json` config_snapshot 节）：并发档 [1]（CLI `--concurrency 1` 覆盖配置的 [1,8,16,32,55,100]）、num_prompts 8（同上覆盖 100）、warmup=true、cooldown 5s、temperature=0、ignore_eos=true、seed=20260924、percentiles [50,90,99]、request_timeout 600s、dataset=random input_len 512、output_len 256。

**内部一致性交叉验算**（报告员计算，非工具输出）：8 条串行（并发1）总时长 22.082s → 单条 2.760s；单条输出恰 256 token（ignore_eos，2048=8×256）→ 256/2.760 = **92.75 tok/s**，与吞吐原值 92.7436 吻合；且 2.760s ≈ TTFT 94ms + 255×TPOT 10.44ms ≈ 2.76s，三数自洽——数据链完整可信。

**三连跑对比**（三次 `bench.sh` 快速档触发，实读各目录 `summary.json`）：

| 结果目录 | TTFT p50 | TPOT p50 | 出流 | 判定 |
|---|---|---|---|---|
| 20261001-153546 | 94.99 ms | 10.51 ms | 90.40 tok/s | 同门禁口径下过 |
| 20261001-154115 | 93.02 ms | 10.46 ms | 89.64 tok/s | 同门禁口径下过（下发背景「≈93ms/≈90tok/s」即此跑） |
| **20261001-154442** | **94.19 ms** | **10.44 ms** | **92.74 tok/s** | **本轮档案证据（PASS 行所指）** |

三次出流 89.6–92.7 tok/s、TTFT p50 93–95ms，量级稳定；单机 TP2 GB10 出流 ~90 tok/s 为当前部署档的基准参照值。

## 四、Track2 通道验证（质量通道：本轮受阻，修复已验证，完整档执行）

**① 受阻证据（实读 `results/20261001-154442-…/lm_eval.log`）**：lm_eval 正常起跑——Selected Tasks = 6 项（mmlu_pro_physics/chemistry/biology, gsm8k, ifeval, humaneval），local-completions 模型指向 `http://192.168.199.129:8000/v1/completions`、tokenizer 用本地 `data/tokenizer-qwen35`；随后在**任务加载期**（`datasets.load_dataset` 路径）直连 `https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro/resolve/main/README.md` 连续 `WinError 10054/10060`（远程主机强制关闭/连接超时），重试 5 次后 traceback——**HF Hub 直连被网络阻断，6 任务 0 打分**。`capability_result.json` 实读 `tasks: []`、`lm_eval_version: null`。

**② 告警与判定语义（源码实读）**：CLI 对缺分任务发 `no score for …; the task counts as failed (DD §9)`（`src/LocalLlmBench.Cli/Commands/RunCommand.cs:554`，与下发输出转录逐字吻合）；全部任务缺分时 capability 状态判 `Failed`（RunCommand.cs:557-561）。该告警**只影响 Track2 判定**，不进 `bench.sh` 的 Track1 门禁（bench.sh:23-33 只读 phases）。

**③ 修复通道验证**：
- **驱动 agent 实测**（任务下发材料转录，报告员未重跑）：`HF_ENDPOINT=https://hf-mirror.com` 后 gsm8k 可达。
- **报告员独立复核（本会话执行）**：`curl -sIL --max-time 25 https://hf-mirror.com/datasets/openai/gsm8k/resolve/main/README.md` → `final=200`（307 跳 `hf-mirror.com/api/resolve-cache/...` 后 200）——镜像通道从操作机可达，与 ① 的直连失败形成对照。注：此复核只证网络通道，不等于完整 `datasets.load_dataset` 流程验证（后者为驱动 agent 的实测口径）。

**④ 分档取舍**：快速档只跑 Track1，Track2 留完整档——理由：Track2 首跑需下载 6 个数据集（含 MMLU-Pro/humaneval），重量级下载与快速档「验通道+验量级」的定位不匹配。CLI 原生开关为 `--track perf|capability|both`（RunCommand.cs:68-70，默认 both）。⚠️ 如实注明：**本轮 `bench.sh` 并未传 `--track perf`**（bench.sh:13-14），配置 `track2.enabled: true` 使 CLI 实际尝试了 Track2 并以上述告警收场——本轮 Track2 是「**试了但失败**」而非「跳过」，告警行如实入档；后续快速档封装应显式加 `--track perf`（列遗留）。

## 五、教训（已沉淀 `experience/gb10.md` 两条）

| # | 教训 | 要点 | 落盘 |
|---|---|---|---|
| ① | `HF_ENDPOINT` 修 datasets 通道 | 评测机 Python 侧 `lm_eval/datasets` 的数据通道与 vLLM 起服侧的 HF 通道是**两回事**：服务端 `HF_ENDPOINT=hf-mirror`（iter4 已入 kb 种子）管 vLLM 拉权重，**操作机跑 Track2 前也要 export 同款变量**，否则任务加载期直连 huggingface.co 必挂（WinError 10054/10060 实录）。完整档 Track2 前置条件 +1 | gb10.md 条目21 |
| ② | 快速档只跑 Track1 的取舍 | 快速档(1×8)定位是验握手与量级，配置 `track2.enabled: true` 时 CLI 仍会起 lm_eval 撞重下载且必产 no-score 告警(DD §9 记 failed)；取舍=快速档显式 `--track perf`，Track2 留完整档（数据集全量落 cache 后再跑）。封装脚本不传开关时，「失败」与「跳过」要如实区分，勿把告警吞成绿 | gb10.md 条目22 |

## 六、备注与遗留

- **档案复制偏差（主动决策，如实报告）**：下发原文写「从最新目录(20261001-154115*)复制」，但实测 `results/` 最新目录是 **20261001-154442**（`ls -1dt` 首位；且 PASS 行 `bench.sh:36` 所指产物即 154442，其指标 94ms/10.4ms/92.7tok/s 与下发捕获输出逐数吻合；154115 是上一跑，93ms/89.6tok/s 对应背景文字）。故按「最新目录」本义复制 **154442/perf_run_result.json**（`cmp` 字节一致），非 154115。
- **展示名遗留**：`gx10-dual.yaml` 的 `model.name`（qwen3.5-122b-a10b）与实际部署模型（Qwen3.6-35B-A3B-NVFP4-Fast，iter4）不一致，结果目录命名随之带旧名——不影响 API 握手（发的是 `bench`），但报告/看板读展示名时会被误导，建议完整档前更新配置展示名。
- **bench.sh 门禁残余风险（实读发现，未做实验验证）**：门禁产物定位用 `ls -1dt … | head -1` 取最新目录（bench.sh:17），与本次调用无强绑定——若某次 CLI 崩在「未产目录」之前的极早阶段，理论上会拿上一跑的目录判 PASS。本轮三连跑目录时间戳与触发时间逐次对应，未受此影响；加固方向=校验目录 mtime>触发时刻或解析本次 run_id。另：门禁只看 JSON phases，不消费 dotnet 退出码（bench.sh:13-14 管道 `tail -6`），Track2 失败不影响 Track1 PASS 属本轮预期语义。
- **`/tmp/bench_last_dir`**：bench.sh:37 落最新目录路径供后续段使用；本档案以显式复制代替对该临时文件的依赖。
- **Track2 完整档清单**：`export HF_ENDPOINT=https://hf-mirror.com` → `--track capability`（或 both）全量 6 任务 + `data/tokenizer-qwen35` 已就位（实读 `data/` 目录确认存在）→ 产出 capability_result.json 有分版。

## 七、产物清单（本任务目录）

| 文件 | 说明 |
|---|---|
| `report.md` | 本报告 |
| `task.json` / `run.json` | 任务档案（Id=t20261001-iter5, Models=["Qwen3.6-35B-A3B-NVFP4-Fast"]） |
| `events.jsonl` | 5 条事件（gate/track1、track2 受阻、镜像验证、pitfalls、task-close） |
| `perf_run_result.json` | 基准证据（复制自 `results/20261001-154442-qwen3.5-122b-a10b/`，cmp 字节一致） |
