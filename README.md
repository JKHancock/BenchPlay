# BenchPlaybook — GX10 双机 vLLM 基准测试与运维流水线

> ## ⚠️ 本文件面向人类，请 Agent 忽略
> **Agent 执行任务时不要依据本文件行动。** 你的入口是 `AGENTS.md`（新会话引导）→ `SKILL.md`（流程法条）→ `docs/PIPELINE.md`（阶段细节）。本 README 是给人的项目说明书。

---

## 1. 背景与动机

我们在两台 NVIDIA DGX Spark 级 GX10（GB10 Grace-Blackwell 统一内存）组成的双机集群上部署 vLLM 推理服务。实践中反复遇到四类问题：

1. **环境陷阱多**：跨节点 FlashInfer 自调优死锁、Windows 管理面的 DLP 加密与 GBK 编码、bash 引号四层穿透、SSH 通道吃 stdin……每一次踩坑都耗费数小时。
2. **测试不体系**：只测单并发吞吐的"儿戏报告"无法支撑选型决策；模型能力、智能体工具调用、服务端指标各说各话。
3. **知识不沉淀**：换一个会话/换一个人，同样的坑再踩一遍。
4. **结论不可信**：手写报告无法回答"这个数从哪来"。

BenchPlaybook 的回答是：把整个"部署→测试→报告→沉淀"过程变成**任何 Agent 都可执行的流程资产**，用脚本和门禁替代自觉，用三库让知识复利。

## 2. 硬件与运行环境（本项目实测对象）

| 项 | 值 |
|---|---|
| 节点 | gx10-9f5c（head）、gx10-9c05（worker），各 1×GB10 |
| 内存 | 每机 121GB 统一内存（GPU/CPU 共享） |
| 数据面 | QSFP 直连 192.168.100.0/24（enp1s0f1np1，200G 级） |
| 管理面 | OTA WiFi DHCP（192.168.199.x，会漂移、有瞬断史） |
| 软件 | Ubuntu 24.04 / 驱动 580.178.04 / Docker 29.6.2 / vLLM 0.30.0 容器（host 网络）/ ray 2.44 |
| 已测模型 | Qwen3.6-35B-A3B-NVFP4-Fast（19GB）、Qwen3.8-27B-NVFP4（23.4GB）、Qwen3.8-Flash-Next-NVFP4（132.6GB，qwen4_exp） |

## 3. 核心理念

**四角色框架**：流程为骨（SKILL.md+脚本控制流）· Agent 为脑（只在决策点）· 脚本为手（确定性执行）· exit code 为闸（门禁在脚本里，不靠自觉）。

**两大治理锚**：
- **环境指纹**（vllm 版本/镜像 digest/驱动/GPU）绑定一切数据点——环境漂移则整体标灰失效；
- **报告契约**（REPORT-SPEC v4.2）——一切采集都是为了填报告的格子，本末不许倒置。

**十条不变量**：①密码一次性（换密钥后零密码存留）②先只读后变更 ③证据绑定结论 ④门禁必须在脚本里 ⑤契约收敛（报告是唯一出口）⑥远端路径绝对化 ⑦幂等可断点重跑 ⑧无模型 profile 不得 serve ⑨验收契约必须含目标用途的真实调用形态 ⑩parser/方法名必须探针实测（文档与注册表只是参考）。

## 4. 总体架构

```
输入契约(机器SSH | 模型清单 | 用途chat/agent)
   ↓ 阶段0-4: 引导→清点→底座→分发→预检清场
   ↓ M0 模型调研(四层证据链) → M0.5 联网调研(5条检索模板)
   ↓ 5 组网(ray双机/QSFP)
   ↓ 6 场景生成(三维: 模型×vLLM参数×集群组合; 场景id=完整argv哈希)
   ↓ ┌── 每场景执行循环: 清场→serve→四关验收→三benchmark→三时点metrics→落档 ──┐
   ↓ └──────────────────────────────────────────────────────────────────────────┘
   ↓ 7 汇编 report_doc.json ◆JSON Schema 校验
   ↓ 8 渲染 ◆推荐数值回查 → 按模型分组的报告(四指标集合+打分+推荐)
   ↓ 9 沉淀: 经验库条目 + 知识库提名(事实类N≥2转正/推理类人审)
 侧线: 三库全程治理 · 环境指纹 · 嗅探器/计数器监护
```

## 5. 流程详解（每阶段：目的 → 动作 → 门禁 → 产物）

### 阶段 0 · 引导（bootstrap）
一次性凭据降级。`scripts/bootstrap_key.py host user password` 把密码换成 ed25519 密钥（authorized_keys 先查重再追加，幂等），之后全程非交互、密码即弃。
**门禁**：新连接用密钥跑 `whoami` 必须等于用户名。**产物**：本机密钥 + 目标机授权行。

### 阶段 1 · 清点（probe/inventory）
`scripts/probe.sh` 十项只读探测（OS/内核/GPU/驱动/Docker/镜像/模型目录/磁盘/网卡/内存）。Agent 把原始输出整编为机器档案 JSON，**每个非空字段必须绑定 Evidence{command, excerpt}**，探测失败记 absent（同样要证据）。
**机器识别 = 查库启发式而非验证机制**：以 MAC 集合相似度 + 机型一致判定"老机器换 IP"，继承其历史经验并记 `RecognizedAs`，判断依据入事件流可追溯。
**门禁**：非空字段无证据打回重做。**产物**：`machines/{ip}.json`（含 identity 字段供下次识别）。

### 阶段 2 · 底座（substrate）
核验目标容器存在、镜像 digest 一致、ray 版本、模型目录可见。
**门禁**：GPU 计算进程归零。**产物**：容器/镜像档案字段。

### 阶段 3 · 分发（distribute）
模型从分发中心（D:\ModelHub）到节点：`distribute.sh host model root`——远端路径先 `$HOME` 绝对化（SFTP 的 `~` 不展开是实测坑），逐文件本地 sha256 → 传输 → 远端 sha256sum 比对，已存在同哈希跳过（增量续传）。Windows 侧 DLP 密文经 `wash.ps1`（PowerShell Copy-Item 通道）洗白。
**门禁**：任一文件哈希不等立即失败带证据。**产物**：`~/.cache/huggingface/<模型>/`。

### 阶段 4 · 预检与清场（preflight/clean）
**门禁**：端口/显存/残留进程全零。清场必须连杀 `vllm serve`/`RayWorkerProc`/`EngineCore` 三种进程（只杀 serve 会留 worker 占 103GB 显存——实测教训）。

### 阶段 M0 · 模型调研（任何 serve 之前的硬门禁）★
`scripts/model_profile.py <model_dir>` 四层证据链：
1. **权重实证**（safetensors 索引）：MTP 层有无与层数（**config 不声明 ≠ 没有**——Qwen3.6 实测 config 无键但权重里 19 个）、视觉塔、专家结构、精确权重量 GB（喂屋顶线）；
2. **config 形态**：model_type→方法映射、原生上下文、rope 形态（mrope 混合→直接给出外拓配方提示）；
3. **模板扫描**：`<tool_call>` 标记→parser 候选（**必须探针实测**，有标记≠hermes）；
4. **容器注册表核对**（只读）：该 vLLM 版本的 MTP 方法表/tool parser 名——方法名是版本耦合的。
**门禁**：无 profile 不得 serve。**产物**：`models/{name}.profile.json`（含 k 建议、parser_must_probe 标记）。已夹具化单测（9 断言）。

### 阶段 M0.5 · 联网调研（Agent 职责）
五条检索模板：`<model_type> vllm <版本> recommended flags` / 投机参数 / tool parser 选型 / 已知坑 / 平台专属问题。结果连同来源 URL/日期/版本号写入 profile 的 `external_research`。
**铁律**（知识获取链 local→web→test→distill）：web 结论只是假设，必须本环境试启实测才能写 verified；**三重判定**（文档说的+注册表有的+实测能跑的→以实测为准）三者不一致全记 version_notes；断网降级本地+容器证据并如实标注。

### 阶段 5 · 组网（cluster）
`cluster.sh`：QSFP 段 awk 状态机探测（grep -B 会跨块误抓 lo，实测坑）→ 容器内 ray head/worker 双机起。
**门禁**：ray status 必须 2 节点且 2 GPU。幂等（已就绪直接 PASS）。

### 阶段 6 · 场景生成（三维正交）
**模型轴**（M0 能力）× **服务轴**（TP/EP/spec-k/rope/autotune + parser/reasoning-parser/structured-output）× **用途轴**（chat/agent/长文）。一个场景 = 一组完整 vLLM argv = `sha1(argv+model+tp)[:8]` 场景 ID；agent 用途必含能力 flags 开/关两档对比。报告按模型分组，组内即参数组合矩阵。

### 阶段 6 执行循环（每场景，cell*.sh 编排）
1. **清场**（双节点 GPU 归零门禁）
2. **serve**：参数经 `docker exec -e` 环境变量通道下发（免疫四层引号穿透）；就绪门禁 15 分钟，MoE 自调优场景自动延长 60 分钟；**KV 池两行启动日志自动落档**（vllm.log 每次 serve 覆盖，不落档即永久丢失）
3. **四关验收** verify.sh：①身份（/v1/models）②功能（对话冒烟）③可观测（metrics≥10 条）④**智能体**（工具调用回环；用途=agent 时 FAIL 级——对话绿≠agent 可用，实测事故教训）
4. **Track1 性能**（bench/track1.py）：w1 随机 512×c1/8/32 · w2 真实 ShareGPT · w3 短对话 · w4 长文 4096 · w5 输出阶梯 · w6 c64 · wsweep 舒适度扫描 · w7 128K 探针；指标族 TTFT/TPOT/ITL/E2E{mean,p50,p90,p99,max}+单流出流+goodput(SLO:TTFT≤500&TPOT≤100)+屋顶线(c1)+**负载中 gauge 峰值轮询**+档内失败自动补跑（WiFi 瞬断免疫，retried 计数）
5. **探针**（bench/probes.py）：前缀缓存（冷/热加速比+命中计数；**复用率是长度函数** 1.5K→0%/4K→37%/16K→83%/64K→97%，探针必扫长度阶梯）+容量阶梯（最大可用并发/首败模式）
6. **Track2 能力**（bench/track2.py）：八套件 n=200——gsm8k/mmlu/arc/hellaswag/winogrande/truthfulqa/openbookqa/race；统一口径 0-shot·关思考链·temp=0·固定种子分层抽样（**不关思考链会耗尽 max_tokens 出假分**：gsm8k 2%→94.5% 的教训）；截断率>10% 标⚠
7. **Track3 智能体**（bench/track3_agent.py + bench/bfcl.py）：工具选择（含不调用克制）/参数抽取/多轮回环/循环时延；BFCL v3（irrelevance 精确分、simple 结构分下界——HF 版真值脱敏如实标注）；思考链 on/off A/B
8. **三时点 metrics**：每相位 idle→after 差值（vLLM 0.30 计数器名勘误在案：request_success_total{finished_reason}等）+ 每机 nvidia-smi 负载中采样
9. **落档**：`tasks/<id>/raw/<场景>/`（serve/startup/w*.json/probes/cap/agent/bfcl/per-request 明细/host 采样）

### 阶段 7 · 汇编（build7.py）
raw → `report_doc.json`：机器 Part A、模型 Profile、场景列表（五要素：模型/机器与每机 ray/四指标集合）、推荐。**门禁**：JSON Schema 校验不过拒绝渲染。

### 阶段 8 · 渲染（report_gen4.py）
`report_v4.md` = Part A 机器环境（硬件+软件表每机，先于一切数据）+ Part A' 模型 Profile + **Part B 按模型分组**（组内=参数组合，每组合六小节：完整 argv→部署/每机 ray→vllm 四组→性能→能力→智能体）+ Part C 确定性推荐（5 profile：综合/延迟/吞吐/能力/单机约束；仅 complete 场景参评；**每条理由必须含数值+对比对象，渲染器回查单元格，查不到即渲染失败**）。支持模型过滤出单模型报告。

### 阶段 9 · 沉淀
经验条目（现象/真因/修复/来源任务 ID/命中计数）append 到对应主题文件并更新 INDEX；达到晋升条件的经 `kb.py` 提名入知识库。

## 6. 四个指标集合（每场景必挂）

| 集合 | P0 内容 | 主要来源 |
|---|---|---|
| vllm_metrics | KV 池容量/最大并发×、投机接受率、负载中 running/waiting/kv 峰值、分段成功(stop+len)/失败(abort+err)计数、prompt/gen tokens、前缀命中 q/h、服务端 TTFT/TPOT/ITL/排队 p99 | /metrics 三时点差值+GaugePoller+启动日志 |
| perf_metrics | 六工作负载全指标族+舒适度扫描+SLO goodput+屋顶线+两探针 | track1/probes（逐请求 SSE 计时） |
| capability_scores | 八套件 acc+截断率+维度分+C-Score（权重：数学.18 知识.22 常识.18 科学.12 诚实.18 共指.12） | track2 |
| agent_metrics | BFCL 五类、循环 pass@1/并行调用率/克制/步数预算、toolcall TTFT、思考 on/off A/B、A-Score（克制.25 结构.25 循环.30 选择.20） | track3/bfcl |

打分规则：**原始 acc → 维度分（成员等权）→ 总分（Σ权重×维度分）×100**；原始>维度>总分，总分是派生视图，权重表随报告公示可复算。

## 7. 三个库（数据→教训→知识阶梯）

| | 档案库 | 经验库 | 知识库 |
|---|---|---|---|
| 分层 | 对象：tasks/{id}/raw、machines/、models/ | 主题：serve-vllm/os-network/testing-bench/process-governance + INDEX.md | 语义：Qdrant kb_playbook（类型+适用条件+指纹+命中数） |
| 谁写 | 脚本自动写证据，Agent 只整编 | 只有 Agent 写（阶段末/事故后） | Agent 只能提名；事实类 N≥2 复现自动转正，推理类人审 |
| 检索 | IP/模型名/任务 ID 直取；MAC 相似度识别老机 | INDEX 定位→条目 grep→超百条走 KB | kb.py 语义 query |

**总检索协议（§5）**：新机/新模入场按 档案原始数据 → 经验叙事 → KB 结论 的顺序（原始>叙事>结论），三层全空才联网。

## 8. 目录结构

```
AGENTS.md/SKILL.md/README.md   入口三件（Agent 入口/法条/人类说明）
docs/    PIPELINE(全景图) REPORT-SPEC-v4(契约) LIBRARIES(三库治理) BATTERY(套件排期) AGENT-BENCH(智能体基准调研)
scripts/ bootstrap_key/probe/substrate/distribute/preflight/clean/cluster/serve/verify(四关)
         cell4-cell6(场景电池编排) matrix/matrix4 serve_demo*(演示服务) model_profile(M0)
         build7(汇编) report_gen4(渲染) kb(知识库) sniff8000(网络嗅探) envfingerprint
bench/（位于 ../Vllm_Benchmark） track1性能 track2能力 track3智能体 bfcl probes common(客户端/metrics/分位)
machines/ models/   机器档案 / 模型 profile
experience/         四主题文件 + INDEX.md（41 条真机经验）
tasks/              每任务 raw 全量证据 + 报告（按模型分组）
viewer/             Streamlit 浏览器
```

## 9. 快速开始（人类操作员）

1. **首次**：在容器就位的两台 GX10 上，让任意 Agent 读 `AGENTS.md`，提供 `host|user|password|机型` + 模型清单 + 用途(chat/agent)
2. **产出**：`tasks/<id>/report_<模型>.md` —— 按模型分组、每参数组合四指标集合、C/A-Score、带数值理由的推荐
3. **验真**：报告任何数字可回溯 `raw/` 原始请求记录；`git log` 看版本
4. **复跑**：所有编排脚本幂等，断点续跑安全

## 10. 已实测成果摘要（环境指纹绑定，漂移即失效）

- 7 场景全电池（3 模型 × TP/EP/MTP/上下文组合），~1 万真实请求，7/7 complete
- **MTP2 投机**：单流 +37%（3.6: 88.6→121 tok/s）~+97%（27B: 19.6→38.6），接受率 62-83%
- **1M 上下文 YaRN 配方**（原生 262K，hf-overrides 嵌套 text_config 直写目标值——vLLM 0.30 yarn 设计上不乘 factor）
- **EP2 双机**：c32 微胜 +0.7%，单流 -7%（两机规模不值得开）
- **前缀缓存**：复用率长度阶梯（64K→97%）；多轮会话每轮只预填尾部，但 Mamba 检查点粒度决定尾巴恒存
- **KV 池即多路容量**：15.9M/5.1M/1.9M（三模型）→ 满血 1M 并发路数 15/4/1
- **冷预填 ~3K tok/s 是算力墙**（调大切片无效，实测证伪；288K≈98s）
- 智能体：BFCL 结构 93-94%、克制 75-86%（弱项跟踪）、工具选择满分但计算题有心算倾向
- 经验库 41 条：自调优死锁对策（--kernel-config 关闭，150s 就绪代价<1%）、引号四层穿透（docker -e 通道）、xet 禁用、parser 探针实测方法论等

## 11. 路线图（BATTERY.md 排期）

能力三大件（MMLU-Pro/MATH-500/AIME，源已通）→ IFEval 校验器 → BFCL 真值精判+τ²-lite → GPQA/BBH/AGIEval → 场景补格（27B-MTP 档、Flash-Next 短上下文档）→ DeepSeek-V4-Flash-0731-NVFP4（176GB，双机部署临界，下载中）。

## 12. 红线与安全

SSH 密码一次性使用后永存盘/日志/回复；一切结论证据绑定；缺格如实标「—未采集」禁止臆造；报告仅适用指纹匹配环境；经验库纠错必须立纠偏条目（错误知识比没有知识危险）。

## 13. 版本

- **Main/V1.0（2026-10-03）**：首个定版——四角色流程、M0/M0.5、三维场景、四指标集合、三库治理、七场景实测、打分体系、按模型分组报告
- 历史：v3（单档性能+单套件）→ v3.1（四条采集义务）→ v4（场景化+schema 校验+推荐引擎）→ v4.1（M0/Track3/四关）→ v4.2（agent_metrics+打分）→ v4.3（权重公示+套件扩容）
