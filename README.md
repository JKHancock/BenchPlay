# BenchPlaybook — GPU 集群大模型推理服务的自动化基准测试与运维流水线

> ## ⚠️ 本文件面向人类，请 Agent 忽略
> **Agent 执行任务时不要依据本文件行动。** 你的入口是 `AGENTS.md`（新会话引导）→ `SKILL.md`（流程法条）→ `docs/PIPELINE.md`（阶段细节）。本 README 是给人的项目说明书。

---

## 1. 背景与动机

在裸机 GPU 集群上部署与评测大模型推理服务（vLLM 等 OpenAI 兼容引擎）时，团队反复遇到四类问题：

1. **环境陷阱多**：分布式后端死锁、量化内核调优、容器与网络细节、跨平台脚本陷阱……每一次踩坑都耗费数小时，且换人就重踩；
2. **测试不体系**：只测单并发吞吐的"儿戏报告"无法支撑选型决策——模型能力、智能体工具调用、服务端指标、不同参数组合的横向对比各说各话；
3. **知识不沉淀**：结论散落在会话记录里，无法复利；
4. **结论不可信**：手写报告无法回答"这个数从哪来"。

BenchPlaybook 的回答：把"部署 → 多参数组合测试 → 报告 → 沉淀"全链变成**任何 Agent 都可执行的流程资产**——用脚本与门禁替代自觉，用三库（档案/经验/知识）让知识复利，用契约化报告让每个数字可回溯。**项目本身引擎无关、机型无关**：给定任意 SSH 可达的 GPU 节点集合与模型清单，按同一套法条执行。


## 2. 适用范围与依赖

- **目标集群**：任意数量、SSH 可达的 GPU 裸机/容器节点（单机到多机；已验证形态：双节点 GB10 统一内存集群，QSFP 直连数据面 + WiFi 管理面）
- **推理引擎**：OpenAI 兼容 API 的服务（以 vLLM 为主靶，容器化部署；参数体系覆盖 TP/EP/投机解码/上下文扩展/工具调用 parser 等）
- **模型**：任意本地权重目录（HuggingFace 布局）；M0 阶段自动做能力画像（MTP/上下文/多模态/parser），无需预先了解模型
- **操作机**：Windows + Git Bash（测试工具链为 Python，venv 独立）
- **依赖安装**：`python -m venv .venv && .venv/Scripts/pip install -r requirements.txt`（requests/pyarrow/jsonschema/fastembed/streamlit，全在仓库内声明）；知识库另需本机 Qdrant（默认 `127.0.0.1:6333`，缺省时可跳过语义检索）
- **跑分工具随库自带**：`bench/`（六轨跑分器）与 `data/cap/`（12 套件数据集）已收编进本仓库，**克隆即完整可用**，无外部代码依赖
- **环境特定值**（IP、机型、镜像 digest 等）只出现在 machines/ 档案与任务目录，流程与文档保持通用


## 3. 核心理念

**四角色框架**：流程为骨（SKILL.md+脚本控制流）· Agent 为脑（只在决策点）· 脚本为手（确定性执行）· exit code 为闸（门禁在脚本里，不靠自觉）。

**两大治理锚**：
- **环境指纹**（vllm 版本/镜像 digest/驱动/GPU）绑定一切数据点——环境漂移则整体标灰失效；
- **报告契约**（REPORT-SPEC v4.2）——一切采集都是为了填报告的格子，本末不许倒置。

**迭代闭环（归因回溯）**：任何阶段失败，Agent 必须先做一次"上游归因检查"——判断这是本阶段问题还是更早阶段的假设错了（凭据→阶段0、环境突变→阶段1指纹复核、镜像/内核/方法名→阶段2、文件校验→阶段3、分布式卡死→阶段5），**幂等重入断点续跑**（已完成阶段不重跑）、同根因最多两轮、禁止原地重试掩盖上游问题、回溯必留事件流记录。

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

### 阶段 2 · 底座适配求解（substrate）
不只是核验容器，而是**求解"模型清单 × 机型 × 镜像候选"三方最优**：以各模型 M0 画像的架构/量化/MTP/上下文需求为约束，本地解读候选镜像（容器内只读核对支持矩阵）+ 联网调研（release notes），产出「镜像×模型」适配矩阵。覆盖全部模型的单镜像优先；无解则报告分组方案。
**门禁**：存在无法适配的模型 → **停在本阶段**，产出《适配报告》（逐模型：不适配原因/换镜像、换量化或放弃的建议），用户裁决后方可降级继续；放行时 GPU 计算进程归零。

### 阶段 3 · 分发（distribute）
模型从分发中心（D:\ModelHub）到节点：`distribute.sh host model root`——远端路径先 `$HOME` 绝对化（SFTP 的 `~` 不展开是实测坑），逐文件本地 sha256 → 传输 → 远端 sha256sum 比对，已存在同哈希跳过（增量续传）。Windows 侧 DLP 密文经 `wash.ps1`（PowerShell Copy-Item 通道）洗白。
**门禁**：任一文件哈希不等立即失败带证据。**产物**：`~/.cache/huggingface/<模型>/`。

### 阶段 4 · 预检与清场（preflight/clean）
**门禁**：端口/显存/残留进程全零。清场必须连杀 `vllm serve`/`RayWorkerProc`/`EngineCore` 三种进程（只杀 serve 会留 worker 占 103GB 显存——实测教训）。

### 阶段 2a · 模型画像（并入底座阶段，任何 serve 之前的硬门禁）★
`scripts/model_profile.py <model_dir>` 四层证据链：
1. **权重实证**（safetensors 索引）：MTP 层有无与层数（**config 不声明 ≠ 没有**——Qwen3.6 实测 config 无键但权重里 19 个）、视觉塔、专家结构、精确权重量 GB（喂屋顶线）；
2. **config 形态**：model_type→方法映射、原生上下文、rope 形态（mrope 混合→直接给出外拓配方提示）；
3. **模板扫描**：`<tool_call>` 标记→parser 候选（**必须探针实测**，有标记≠hermes）；
4. **容器注册表核对**（只读）：该 vLLM 版本的 MTP 方法表/tool parser 名——方法名是版本耦合的。
**门禁**：无 profile 不得 serve。**产物**：`models/{name}.profile.json`（含 k 建议、parser_must_probe 标记）。已夹具化单测（9 断言）。

### 阶段 2b · 联网调研（Agent 职责）
五条检索模板：`<model_type> vllm <版本> recommended flags` / 投机参数 / tool parser 选型 / 已知坑 / 平台专属问题。结果连同来源 URL/日期/版本号写入 profile 的 `external_research`。
**铁律**（知识获取链 local→web→test→distill）：web 结论只是假设，必须本环境试启实测才能写 verified；**三重判定**（文档说的+注册表有的+实测能跑的→以实测为准）三者不一致全记 version_notes；断网降级本地+容器证据并如实标注。

### 阶段 5 · 组网（cluster）
（注：任何阶段失败遵循**归因回溯**——先判断是否上游阶段假设错误（凭据→0、环境突变→1、镜像/内核→2、文件→3、分布式→5），幂等重入断点续跑，同根因最多两轮，禁止原地重试掩盖上游问题）
`cluster.sh`：QSFP 段 awk 状态机探测（grep -B 会跨块误抓 lo，实测坑）→ 容器内 ray head/worker 双机起。
**门禁**：ray status 必须 2 节点且 2 GPU。幂等（已就绪直接 PASS）。

### 阶段 6 · 场景生成（三维正交，`gen_scenarios.py` 代码化）
**模型轴**（M0 能力）× **服务轴**（TP/EP/spec-k/rope/autotune + parser/reasoning-parser/structured-output）× **用途轴**（chat/agent/长文）。一个场景 = 一组完整 vLLM argv = `sha1(argv+model+tp)[:8]` 场景 ID；agent 用途必含能力 flags 开/关两档对比。生成器读取 `models/*.profile.json`（含模型专用参数）自动展开组合矩阵并输出 cell 执行命令。报告按模型分组，组内即参数组合矩阵。

### 阶段 6 执行循环（每场景，cell*.sh 编排）
1. **清场**（双节点 GPU 归零门禁）
2. **serve**：参数经 `docker exec -e` 环境变量通道下发（免疫四层引号穿透）；就绪门禁 15 分钟，MoE 自调优场景自动延长 60 分钟；**KV 池两行启动日志自动落档**（vllm.log 每次 serve 覆盖，不落档即永久丢失）
3. **四关验收** verify.sh：①身份（/v1/models）②功能（对话冒烟）③可观测（metrics≥10 条）④**智能体**（工具调用回环；用途=agent 时 FAIL 级——对话绿≠agent 可用，实测事故教训）
4. **Track1 性能**（bench/track1.py）：w1 随机 512×c1/8/32 · w2 真实 ShareGPT · w3 短对话 · w4 长文 4096 · w5 输出阶梯 · w6 c64 · wsweep 舒适度扫描 · w7 128K 探针；指标族 TTFT/TPOT/ITL/E2E{mean,p50,p90,p99,max}+单流出流+goodput(SLO:TTFT≤500&TPOT≤100)+屋顶线(c1)+**负载中 gauge 峰值轮询**+档内失败自动补跑（WiFi 瞬断免疫，retried 计数）
5. **探针**（bench/probes.py）：前缀缓存（冷/热加速比+命中计数；**复用率是长度函数** 1.5K→0%/4K→37%/16K→83%/64K→97%，探针必扫长度阶梯）+容量阶梯（最大可用并发/首败模式）
6. **Track2 能力**（bench/track2.py）：十二套件——gsm8k/mmlu/arc/hellaswag/winogrande/truthfulqa/openbookqa/race（各 n=200）+ **math500**（竞赛数学 500 题全集，开思考链=公开榜口径，LaTex 归一化容差比对）+ **cmmlu/ceval**（中文知识与中国特色考试，各 n=200）+ **ifeval**（指令遵循，22 种可编程校验器，全部指令通过才计对，另报指令级口径）；统一口径 0-shot·temp=0·固定种子分层抽样，除 math500 外关思考链（**不关思考链会耗尽 max_tokens 出假分**：gsm8k 2%→94.5% 的教训）；截断率>10% 标⚠
7. **Track3 智能体**（bench/track3_agent.py + bench/bfcl.py）：工具选择（含不调用克制）/参数抽取/多轮回环/循环时延；BFCL v3（irrelevance 精确分、simple 结构分下界——HF 版真值脱敏如实标注）；思考链 on/off A/B
8. **三时点 metrics**：每相位 idle→after 差值（vLLM 0.30 计数器名勘误在案：request_success_total{finished_reason}等）+ 每机 nvidia-smi 负载中采样
9. **落档**：`tasks/<id>/raw/<场景>/`（serve/startup/w*.json/probes/cap/agent/bfcl/per-request 明细/host 采样）

**执行加速（宿主 IDE 并行编排，强烈建议用满）**：电池本身受 GPU 互斥天然串行（一个 vLLM 实例一次只测一组服务参数），但 M0 模型画像分析、数据集准备、电池后处理（汇编/渲染/索引/经验提炼）、报告分章写作均无资源冲突，可并行。ZCode 用动态 workflow（CreateWorkflow，子智能体 fan-out + 控制流护栏）；Claude Code 用并行 Task 子智能体 + hooks 验退出码；Codex 用并行 cloud task；OpenCode 用 subagent 并发。红线：子智能体产出仍必须是 exit code + 证据文件，不得写同一 raw 目录。映射表详见 `docs/AGENT-BINDING.md` §并行加速。

### 阶段 7 · 汇编（build8.py，当前入口）
raw → `report_doc.json`：机器 Part A、模型 Profile、场景列表（五要素：模型/机器与每机 ray/四指标集合）、推荐。**门禁**：JSON Schema 校验不过拒绝渲染。

### 阶段 8 · 渲染（report_gen4.py）
`report_v4.md` = Part A 机器环境（硬件+软件表每机，先于一切数据）+ Part A' 模型 Profile + **Part B 按模型分组**（组内=参数组合，每组合六小节：完整 argv→部署/每机 ray→vllm 四组→性能→能力→智能体）+ Part C 确定性推荐（5 profile：综合/延迟/吞吐/能力/单机约束；仅 complete 场景参评；**每条理由必须含数值+对比对象，渲染器回查单元格，查不到即渲染失败**）。支持模型过滤出单模型报告。

### 阶段 9 · 沉淀
经验条目（现象/真因/修复/来源任务 ID/命中计数）append 到对应主题文件并更新 INDEX；达到晋升条件的经 `kb.py` 提名入知识库。

## 6. 三大 Benchmark（每场景各产一套专属指标集合）

每个场景（= 一组 vLLM 参数/集群组合）都跑**三大 benchmark**，每个 benchmark 有**自己专属的指标集合**；另有一套 **vLLM 服务指标集合**贯穿全程同步采集。

### 6.1 Benchmark 一 · 性能（Track1 + 探针）→ 性能指标集合
- 工作负载矩阵：随机吞吐档 / 真实分布(ShareGPT) / 短对话 / 长文预填 / 输出阶梯 / 满序列批 / 舒适度扫描 / 超长上下文探针
- 指标族：TTFT·TPOT·ITL·E2E{mean,p50,p90,p99,max}、单流出流、聚合吞吐/QPS、SLO goodput、屋顶线利用率、前缀缓存复用(长度阶梯)、容量阶梯、档内失败补跑计数
- 来源：SSE 流式逐请求计时（bench/track1、bench/probes）

### 6.2 Benchmark 二 · 模型能力（Track2）→ 能力指标集合
- 套件（12）：数学(gsm8k·**MATH-500**竞赛级,开思考链=公开榜口径)·知识(mmlu·**CMMLU**中文)·考试(**CEval**中国执业资格 16 科)·科学(arc)·常识(hellaswag/openbookqa)·共指(winogrande)·诚实性(truthfulqa)·阅读理解(race)·指令遵循(**IFEval**,22 种可编程校验器)，统一口径 0-shot·temp=0·固定种子分层抽样（除 math500 外关思考链）；发布卡级套件(MMLU-Pro/AIME 等)按 docs/BATTERY.md 排期接入
- 指标族：各套件 acc/截断率/失败数（ifeval 另报指令级口径）→ 维度分 → **C-Score 总分**（权重表随报告公示可复算）
- 来源：bench/track2（+ bench/track2_extra 四套加载器/校验器）

### 6.3 Benchmark 三 · 智能体场景（Track3 + BFCL）→ 智能体指标集合
- 组分：工具选择（含不调用克制）/参数抽取/多轮回环(调用→回灌→作答)/BFCL 函数调用/思考链 on-off A/B
- 指标族：selection/args/loop pass@1、并行调用率、toolcall TTFT、循环 E2E、token 代价 → **A-Score 总分**
- 来源：bench/track3_agent、bench/bfcl

## 7. vLLM 服务指标集合（与三大 benchmark 同步采集）

> 三大 benchmark 是"考卷"；本节是"监考仪"——不是第四个 benchmark，而是在每个 benchmark 运行的全过程中对服务端的同步观测，与三个考卷的成绩一一对应。
- 启动态：KV 池容量/最大并发倍数、投机开关、加载与就绪耗时
- 运行态：投机接受率、负载中 running/waiting/KV 峰值（轮询采样）
- 分段差值：每相位成功(stop+len)/失败(abort+err)、prompt/gen tokens、前缀命中 q/h
- 服务端分位：TTFT/TPOT/ITL/排队 p99（直方图内插）
- 主机层：每节点 GPU 利用率/显存负载中采样
- 来源：/metrics 三时点差值 + GaugePoller + 启动日志两行落档


## 8. 三个库（数据→教训→知识阶梯）

| | 档案库 | 经验库 | 知识库 |
|---|---|---|---|
| 分层 | 对象：tasks/{id}/raw、machines/、models/ | 主题：serve-vllm/os-network/testing-bench/process-governance + INDEX.md | 语义：Qdrant kb_playbook（类型+适用条件+指纹+命中数） |
| 谁写 | 脚本自动写证据，Agent 只整编 | 只有 Agent 写（阶段末/事故后） | Agent 只能提名；事实类 N≥2 复现自动转正，推理类人审 |
| 检索 | IP/模型名/任务 ID 直取；MAC 相似度识别老机 | INDEX 定位→条目 grep→超百条走 KB | kb.py 语义 query |

**总检索协议（§5）**：新机/新模入场按 档案原始数据 → 经验叙事 → KB 结论 的顺序（原始>叙事>结论），三层全空才联网。

**git 策略（三库全部进库，体积小）**：档案库（tasks/+machines/+models/）与经验库（experience/）本身就是文本文件，直接提交；知识库是 Qdrant 派生索引（源数据都在前两库），用 `python scripts/kb.py export` 导出 `archive/kb_snapshot.jsonl` 随库提交，新机用 `kb.py rebuild` 从快照重建（重嵌向量、幂等）。快照在每次知识库变动后导出一次。

## 9. 目录结构与脚本索引

```
AGENTS.md / SKILL.md / README.md     入口三件（Agent 入口 / 流程法条 / 人类说明）
docs/
  SCRIPTS.md                          Agent 工具箱目录（阶段→脚本→门禁速查表）
  PIPELINE.md                         流程全景图 + 阶段详解 + 十条不变量
  REPORT-SPEC-v4.md                   报告契约（schema/渲染规则/采集义务）
  LIBRARIES.md                        三库治理（分层/写入/检索/§5协议）
  BATTERY.md                          套件排期（12套件覆盖计划）
  AGENT-BENCH.md                      智能体基准调研与规格
scripts/                              全部执行脚本（30 个，按阶段分类见 SCRIPTS.md）
  核心管线: bootstrap_key→probe→substrate→model_profile→distribute→preflight→clean→
           cluster→serve→verify→cell*→build8→report_gen4→scenario_index→kb
  场景编排: cell4/cell5/cell6/cell7(单场景电池) matrix4(矩阵) overnight(无人值守)
  增量: gen_scenarios(三层生成) add_scenario(报告后追加)
  诊断: sniff8000(抓包) capture_kv(KV补采) fourcoll(四集合快采)
  运维: serve_demo/serve_demo27b(演示) wash.ps1(DLP洗白)
  配置: excluded_scenarios.json(不可行组合清单)
  legacy/                             已废弃脚本（7 个，保留供考古）
bench/                                跑分工具（六轨, 克隆即带）【静态】
  track1.py(性能) track2.py(能力12套,含4新套) track2_extra.py(新4套加载器/校验器)
  track3_agent.py(智能体) bfcl.py(函数调用) probes.py(探针) common.py(客户端/指标)
data/cap/                             12 套件数据集（parquet/jsonl/csv, 克隆即带）【静态】
requirements.txt                      Python 依赖声明【静态】
machines/                             机器档案（每台一个 JSON）【动态】
models/                               模型 M0 profile（首次 model_profile 后生成）【动态】
experience/                           经验库（4 主题文件 + INDEX.md）【动态】
archive/
  scenario_index.jsonl                全局场景索引（跨任务可查）【动态】
tasks/                                每任务目录（raw/ 全量证据 + 报告）【动态】
reports/                              定稿报告的交付副本【动态】
viewer/                               Streamlit 浏览器【静态】
```

### 9.1 静态资产 vs 运行时数据（谁写、何时写、写在哪）

| 位置 | 性质 | 谁写入 | 何时 | git |
|---|---|---|---|---|
| `AGENTS.md`/`SKILL.md`/`README.md` | 静态·入口 | 维护者（Agent 经确认后可改） | 项目演进时 | ✓ |
| `docs/*.md` | 静态·契约与绑定 | 维护者 | 同上 | ✓ |
| `scripts/`（工具 + `excluded_scenarios.json` + `wash.ps1`） | 静态·工具 | 维护者 | 阶段/套件演进时 | ✓ |
| `scripts/cell*.sh` | 静态·**运行档案** | 每次电池前创建一份，跑后只读不改 | 每个新场景/批次 | ✓ |
| `bench/` + `data/cap/` | 静态·跑分工具与 12 套件数据集 | 维护者 | 套件演进时 | ✓ |
| `viewer/app.py` | 静态·浏览器 | 维护者 | — | ✓ |
| `machines/<ip>.json` | 动态·机器档案 | Agent（阶段 1 清点，字段必绑证据） | 机器首次接入/复核 | ✓ |
| `models/<name>.profile.json` | 动态·模型档案 | `model_profile.py`（M0 硬门禁） | 每模型首次 serve 前 | ✓ |
| `tasks/<id>/raw/<场景>/` | 动态·原始证据 | cell 脚本及其工具链（Agent 不手改） | 电池执行时（一次写入不再改） | ✓ |
| `tasks/<id>/report_doc.json`·`report_v4.md` | 动态·汇编产物 | `build*`/`report_gen4` | 电池完成后 | ✓ |
| `reports/` | 动态·交付副本 | 渲染定稿后拷贝 | 每次定稿 | ✓ |
| `experience/*.md` + `INDEX.md` | 动态·经验库 | Agent 提炼追加（阶段 9 沉淀） | 每次电池后 | ✓ |
| `archive/scenario_index.jsonl` | 动态·全局索引 | `scenario_index.py` 追加（幂等去重） | 每场景入库 | ✓ |
| `archive/kb_snapshot.jsonl` | 动态·知识库快照 | `kb.py export`（Qdrant→文件） | 知识库每次变动后 | ✓ |

**规则**：静态文件定义"怎么做"，动态文件记录"做过了什么"。流程只读静态、只追加动态（`raw/` 落档后不改写，复测=新任务目录）。动态层（tasks/ + machines/ + models/ + experience/ + archive/ + reports/）是全部实验记忆；清空它们即回到"空库冷启动"，框架与工具无损。
## 10. 快速开始（人类操作员）

1. **克隆即完整可用**：`git clone` 后 `python -m venv .venv && .venv/Scripts/pip install -r requirements.txt`——流程文档、门禁脚本、bench 跑分器、12 套件数据集全在仓库内；（可选）装好 Qdrant 并 `python scripts/kb.py rebuild` 复原知识库语义检索
2. **首次**：在目标集群就绪后，让任意 Agent 读 `AGENTS.md`，提供机器清单（`host|user|password|机型`）+ 模型清单 + 用途声明(chat/agent)
3. **产出**：`tasks/<id>/report_<模型>.md` —— 按模型分组、每参数组合四指标集合、C/A-Score、带数值理由的推荐
4. **验真**：报告任何数字可回溯 `raw/` 原始请求记录；`git log` 看版本
5. **复跑**：所有编排脚本幂等，断点续跑安全
6. **清空数据（冷启动）**：`bash scripts/reset_data.sh show`（预览）→ `data`（清实验记忆：tasks/archive/machines/models/reports，经验库保留）或 `all`（再加经验库与 Qdrant 集合，全新冷启动；删除物移入 `.reset_backup/<时间戳>/` 可反悔；`archive/kb_snapshot.jsonl` 仍在 git，可随时 rebuild 复原知识库）


## 11. 红线与安全

SSH 密码一次性使用后永存盘/日志/回复；一切结论证据绑定；缺格如实标「—未采集」禁止臆造；报告仅适用指纹匹配环境；经验库纠错必须立纠偏条目（错误知识比没有知识危险）。

## 12. 版本

- **Main/V1.0（2026-10-03）**：首个定版——四角色流程、M0/M0.5、三维场景、四指标集合、三库治理、七场景实测、打分体系、按模型分组报告
- 历史：v3（单档性能+单套件）→ v3.1（四条采集义务）→ v4（场景化+schema 校验+推荐引擎）→ v4.1（M0/Track3/四关）→ v4.2（agent_metrics+打分）→ v4.3（权重公示+套件扩容）
