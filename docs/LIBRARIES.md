# 三个库的契约

## 1. 档案库（发生了什么）— `tasks/{id}/`

append-only，流程自动写入，格式与 C# 实现（BenchPilot）逐字段兼容：

```
tasks/{taskId}/
├─ task.json            { Id, Name, CreatedAt, Status, MachineHosts[], Models[],
│                         RemoteModelsRoot, MachineStatus{host→status} }
├─ events.jsonl         每行一个事件 { Ts, Machine, Level, Source, Message }
│                         Level: info/tool/gate/kb/llm/error  Source: stage/agent/model/
│                         context/reasoning/qdrant/diff/director/report/...
├─ transcripts/         agent 轮次转录（对话式回放的来源）
│   ├─ director.json    [ { Ts, Agent, Round, Reasoning, Answer,
│   ├─ bootstrap-*.json     Calls: [ { CallId, Name, Arguments, Result } ] } ]
│   └─ report.json
├─ profiles/{host}.json 机器档案 { Host, DeclaredModel, Os, Arch, Kernel, Cpu, Memory,
│                         Gpu, Driver, DockerVersion, Images[], Models[], Disks[],
│                         Nics[{Name,State,Ips[]}], Evidence{字段→{Command,Excerpt}}, Summary }
├─ report.md            报告全文
└─ run.json             收尾清单 { Id, Name, StartedAt, EndedAt, Status,
                          InputTokens, OutputTokens, Machines[{Host,Status,Summary}] }
```

规则：写入者=流程（脚本+agent）；任务结束任何人不得改历史条目。

**机器状态库**（档案库的组成部分，与 MAF 版隔离）：`machines/{host}.json`（本目录内，
每机一个文件，任务收尾时用最新档案幂等覆盖）——不使用 Qdrant，纯文件。

## 2. 经验库（学到了什么）— `experience/`

```
experience/
├─ INDEX.md          索引：主题 → 条目列表（人可读导航）
└─ {topic}.md        主题文件（gb10.md / ray-vllm.md / qwen3.x.md / dlp.md ...）
```

条目格式：

```markdown
## <一句话标题>
- 阶段: cluster | 现象: gloo connection refused 127.0.0.1
- 结论/修复: GLOO_SOCKET_IFNAME 钉 QSFP 网卡
- 来源: t20261001-014115 | 命中: 2
```

规则：agent 每任务收尾必写（报告之后）；条目必注来源任务 ID；
同主题追加不新建文件；诊断中复用成功 → 该条"命中"+1。

## 3. 知识库（公共沉淀）— Qdrant `kb_playbook` 集合

**与 MAF 版隔离**：C# 实现用 `kb` 集合，本流程用 `kb_playbook`（env `KB_COLLECTION` 可覆盖），
互不读写，各自积累。

```
点结构: { id: hash(content前64), vector: 384维(MiniLM 多语言),
          payload: { content, fix, tags[], provenance, hits } }
tags 约定: [横向阶段, 纵向归属...] 如 ["serving","ray","vllm","failure"]
```

- 查询：`scripts/kb.py query "症状" [--tag cluster]` → 向量召回 + 标签过滤（+可选 LLM 重排）
- 写入：`scripts/kb.py upsert --content ... --fix ... --tags ...`（同内容幂等，hits++）
- **晋升规则**：经验条目命中 ≥2 或人工确认 → agent 写成正式条目入库；
  单次巧合不进公共库。

## 积累闭环（一张图）

```
任务 → 档案库(自动) → 收尾提炼 → 经验库(每任务) → 命中≥2 晋升 → 知识库(Qdrant)
                          ▲                                        │
                          └──────── 诊断复用成功 hits++ ────────────┘
新任务开始 / 阶段失败 → 必查知识库（查询是积累的对价）
```

## 4. 环境指纹与时效（2026-10-01 修订：防漂移）

知识条目 payload 增加三个必填字段：

```
env: "vllm=0.30.0; image=sha256:91d9b077589e; driver=580.178.04; gpu=GB10"   # scripts/envfingerprint.sh
recorded_at: "2026-10-01T18:51:06"
status: "nominated" | "confirmed"    # 提名态/已转正(事实类 N≥2 自动转正; 推论类人审转正)
```

灰标规则：查询时条目 `env` 的 vllm/镜像/驱动与当前实测指纹不一致 → 输出加 `⚠旧环境` 前缀，
只可作历史参考，不得作当前决策依据。过版本（vllm/镜像变更）即重测关键基线。

## 5. 新机近似跑分检索协议（2026-10-01 增补）

**场景**: 新机器来了，Agent 要回答"这台机大概能跑多少分/推荐什么配置"。四步，顺序不可乱：

1. **清点新机 → 指纹**: probe.sh 产出 GPU 型号/驱动/架构/核数/内存/NVMe；
2. **先查档案库（最诚实层）**: 在 `tasks/*/rows.jsonl` 里按 env 指纹相似度找历史行
   （gpu== && arch== 优先，driver 允许差、标灰）——返回的是**原始实测数**，不是结论；
3. **再查经验库（叙事层）**: `experience/{机型}.md`（如 gb10.md）给该机型家族的坑与调优叙事；
4. **最后查知识库（结论层）**: `kb.py query "GB10 NVFP4 TP2 吞吐"` 命中的
   **perf_profile 条目**（推论类，人审转正后才有决策资格）。

**永远从 2→3→4 的顺序读**：原始数据 > 叙事经验 > 已转正结论；任何一层与上层冲突，信上层。
**写回**：新机首跑后，其 rows 成为档案库新行；若与历史机型家族复现一致（N≥2），
提名 perf_profile 入知识库（带指纹+适用条件），人审转正。

### perf_profile 条目（知识库新增 kind）

```
kb.py upsert --content "GB10×1 单机 Qwen3.6-35B-A3B(NVFP4): 单流 67.7 tok/s, TTFT 117ms (TP1/40960)"
  --tags perf,gb10,qwen3.6,a3b --applicable "GB10 单机 + vLLM 0.30.x + NVFP4" --env "<指纹>"
```

## 6. 三库阶段时刻表（什么阶段、进什么、读什么）

| 阶段 | 档案库（发生了什么） | 经验库（学到了什么） | 知识库（可复用结论） |
|---|---|---|---|
| 引导 | 写: machines/{host}.json（identity 字段） | — | 读: 机器识别（相似度认机） |
| 清点 | 写: profiles/{host}.json（字段+证据） | — | 读: 机型 quirks（如显存 N/A） |
| 分发 | 写: events（逐文件 sha256 证据） | — | 读: 分发失败签名 |
| 预检/清理 | 写: events（清理前后对照） | — | 读: 清理决策（僵尸无害等） |
| 部署段 | 写: events + vllm_args 原文 + serve.log | — | 读: 底座/组网/服务的坑 |
| 验证 | 写: metrics 快照（负载前后） | — | — |
| 测试 | 写: **rows.jsonl 行**（契约 v2 全列） | — | — |
| 报告 | 读: 全档案 → report_gen.py 渲染 | 读: 洞察段引用 | — |
| 收尾提炼 | 写: task.json/run.json 封档 | **写: 按阶段提炼条目**（任务ID+指纹） | — |
| 失败诊断 | 读: events/transcripts | 读+命中++: 复用老经验 | 读: 签名查询; **写(提名)**: 新坑 |
| 晋升 | — | 条目命中 ≥2 | **写**: 事实类自动转正 / 推论类(perf_profile 等)人审转正 |
| 新机接入 | 读: rows 指纹相似度（§5 协议①层） | 读: 机型家族叙事（②层） | 读: perf_profile（③层） |

规则：**读取顺序 = 原始数据 > 叙事经验 > 已转正结论**；任何写入口径见本文件 §1-§3，报告渲染见 REPORT-SPEC.md。

## §7 经验库检索规程（2026-10-03 拆分后生效）
库结构: experience/{serve-vllm, os-network, testing-bench, process-governance}.md + INDEX.md(条目→文件映射)
检索三级: ①读INDEX按标题定位→读对应文件条目 ②按阶段/关键词grep条目标题(每条含 阶段/现象/修复/来源/命中数) ③条目>100或语义模糊查询时走KB(kb.py query)
写入规则: 新教训append到对应主题文件(找不到主题进misc.md), 同步更新INDEX; 命中计数在下次命中时+1

## §8 三库 git 持久化（2026-10-04 生效）
- 档案库/经验库是文本文件, 直接随仓库提交;
- 知识库(Qdrant kb_playbook)是派生索引: 变动后 `kb.py export` → archive/kb_snapshot.jsonl 随仓库提交,
  新机 `kb.py rebuild` 从快照重建(重嵌向量, 保留命中数, 幂等);
- **提交纪律**: Python 新写的文件在工作区是 DLP 密文, git add 前用 PowerShell Copy-Item 通道洗白
  (wash.ps1), 保证仓库 blob 是明文、克隆方可读;
- 全量清空走 scripts/reset_data.sh（见 README §10）, 删除物入 .reset_backup 可反悔。
