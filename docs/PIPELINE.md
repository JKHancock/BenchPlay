# BenchPlaybook 总体流程设计（v4.2 全景 · 2026-09-30 · 含修订案 A1/A2）

> 四角色框架: **流程为骨**(SKILL.md+脚本控制流) · **Agent为脑**(只在决策点) · **脚本为手**(确定性) · **exit code为闸**(门禁)
> 两大治理锚: **环境指纹**(防漂移, 全程) · **报告契约**(REPORT-SPEC v4.2, 一切采集为填格)

## 一、总体管线（阶段流 + 门禁 + 库读写）

```
┌─────────────────── 输入契约 ───────────────────┐
│ machines: host|user|password|机型 · 模型清单 · 用途声明(chat/agent) │
└─────────────────────────────────────────────────────┘
   ▼
[0 引导] 密码一次性换密钥 ──◆ whoami=用户名
   ▼
[1 清点 probe] 十项只读探测 → machines/{host}.json(含identity, MAC相似度识别换IP老机器)
   ▼                     ↖ 读: 经验库(WSL/bash陷阱) + KB(machine_profiles)
[2 底座 substrate] 镜像/digest/容器核验 ──◆ GPU计算进程归零
   ▼
[3 分发 distribute] 模型上机(sha256逐文件门禁+增量续传, DLP经wash.ps1洗白)
   ▼
[4 预检 preflight + 清场 clean] ──◆ 端口/显存/残留进程全零
   ▼
╔═[M0 模型调研] model_profile.py · 四层证据链 ════════════════════════╗
║ ①权重实证(safetensors: MTP层/视觉塔/精确权重量GB→屋顶线)              ║
║ ②config形态(model_type→方法映射/原生ctx/rope形态→外拓配方)            ║
║ ③模板扫描(<tool_call>标记→parser候选, 必须探针实测定)                 ║
║ ④容器注册表核对(该vLLM版本的方法/parser名, 版本耦合)                  ║
║ → models/{name}.profile.json        ◆ 无profile不得serve            ║
╚═════════════════════════════════════════════════════════════════════╝
   ▼
╔═[M0.5 联网调研](Agent职责) ════════════════════════════════════════╗
║ 5条检索模板(模型×vllm版本: 推荐flags/投机k/parser/已知坑/平台专属)     ║
║ 铁律: web=假设 → 试启实测才verified; 三重判定(文档/注册表/实测→以实测为准)║
╚══════→ profile.external_research(源URL/日期/版本号)═══════════════════╝
   ▼
[5 组网 cluster](按需) ray head/worker · QSFP数据面 ──◆ 2节点2GPU
   ▼
╔═[6 场景生成器 · 三维正交] ═════════════════════════════════════════╗
║ 模型轴(M0能力) × 服务轴(TP/EP/spec-k/rope/autotune + parser/         ║
║ reasoning-parser/structured-output) × 用途轴(chat/agent/长文)        ║
║ agent用途必含能力flags开/关两档对比; 场景id=完整argv的sha1[:8]         ║
╚═════════════════════════════════════════════════════════════════════╝
   ▼
┌──────── 对每场景循环(见 §二放大图) ────────┐
│ serve→verify四关→Track1-4→三时点metrics→落档 │
└──────────────────────────────────────────────┘
   ▼
[7 汇编 build_doc] report_doc.json ──◆ jsonschema校验不过拒绝渲染
   ▼
[8 渲染 report_gen4] ──◆ 推荐理由数值回查(单元格查不到即失败)
   ▼
┌────────── 报告 v4 ──────────┐
│ Part A  机器环境(硬件表+软件表/机, 先于一切数据)  │
│ Part A' 模型Profile节(M0/M0.5产物)            │
│ Part B  场景×N六小节: argv原文→部署/每机ray→    │
│         vllm四组→perf负载+探针→能力→agent四组   │
│ Part C  确定性推荐(5profile, 仅complete参评,    │
│         理由全带数值+次优差距, partial落选声明)  │
└───────────────────────────────┘

 侧线·三库治理(全程):
   档案库 tasks/{id}/raw + machines/ + models/   ←只写事实+证据
   经验库 experience/{topic}.md                  ←阶段末写教训
   知识库 Qdrant kb_playbook                     ←只提名; 事实类N≥2转正, 推理类人审
 ↕ §5检索协议(新机/新模): 档案相似度 → 经验叙事 → KB结论(原始数据>叙事>结论)
```

## 二、单场景执行循环（放大 · cell4/cell5.sh + bench/*）

```
场景(=一组完整vllm argv)
 ├─[6.1 清场] pkill vllm/RayWorkerProc/EngineCore ◆ 双节点GPU计算进程=0
 ├─[6.2 serve] 参数走docker -e环境通道(免疫四层引号地狱)
 │      ◆ 就绪门禁: 自调优场景15→60min延长; KV容量两行自动落档(vllm.log会覆盖)
 ├─[6.3 verify四关] ◆身份(/v1/models) ◆功能(对话) ◆可观测(metrics≥10)
 │      ◆智能体(工具回环; 用途=agent时FAIL级, chat时提示级)
 ├─[6.4 Track1 性能] w1随机512×c1/8/32 · w2真实ShareGPT · w3短对话 ·
 │      w4长文4096 · w5输出阶梯 · w6 c64 · wsweep舒适度扫描 · w7 128K探针
 │      指标族: TTFT/TPOT/ITL/E2E{mean,p50,p90,p99,max} · 单流出流 ·
 │      goodput(SLO:TTFT≤500&TPOT≤100) · roofline(c1) ·
 │      GaugePoller负载中峰值 · 档内失败自动补跑(retried计数)
 ├─[6.5 探针] prefix-cache(冷/热加速比+命中计数; 复用率是长度函数须扫长度)
 │      · capacity阶梯(最大可用并发/首败模式)
 ├─[6.6 Track2 能力] gsm8k/mmlu/arc(P0)+hellaswag/winogrande(P1)
 │      统一口径: 0-shot·关思考链·temp=0·固定种子·分层n=200; 截断率>10%标⚠
 ├─[6.7 Track3 智能体] A1 BFCL五类AST(P0) · A3循环(pass@1/并行调用率/
 │      干扰克制/步数预算) · A4服务(toolcall_ttft/loop_e2e/reasoning on-off A/B)
 │      [实现中: BFCL loader+AST评分器待接入]
 ├─[6.8 Track4] (预留: 结构化输出/guided decoding)
 ├─[6.9 三时点metrics] 每相位idle→after差值: stop/len/abort/err · prompt/gen ·
 │      prefix q/h · 服务端TTFT/TPOT/ITL/queue分位 · spec接受率
 └─[6.10 主机采样] 每机nvidia-smi负载中采样 → host_*.log
 ▼
raw/<tag>/{serve,startup,w*.json, probes.json, cap.json,
           metrics_*_a/b.json, per_request明细, host_*.log}
```

## 三、数据流与产物链

```
真机 ─ssh→ scripts(serve/cell/verify) ─HTTP→ bench(track1/2/3,probes,common)
                                            │
            ┌──── 档案库 raw/ 全量证据 ←──────┘
envfingerprint(每任务复核, 漂移即灰标)
                    │ build_doc.py
                    ▼
            report_doc.json ◆jsonschema
                    │ report_gen4.py ◆推荐数值回查
                    ▼
        report_v4.md(Part A/A'/B/C) + viewer(Streamlit回放)
                    │
   经验库沉淀(阶段末)┴ 知识库提名(N≥2转正/人审)
```

## 四、阶段×产物×门禁×库 时刻表

| 阶段 | 脚本 | 产物 | 门禁◆ | 写库 | 读库 |
|---|---|---|---|---|---|
| 0引导 | bootstrap_key.py | 密钥 | whoami=用户名; 密码零残留 | 档案 | 经验(ssh陷阱) |
| 1清点 | probe.sh | machines/{ip}.json | 非空字段必有证据 | 档案 | KB机器档案 |
| 2底座 | substrate.sh | 容器+digest | 6-flag校验+GPU归零 | 档案 | — |
| 3分发 | distribute.sh | 模型上机 | sha256逐文件全对 | 档案 | 经验(DLP/SFTP/~路径) |
| 4预检 | preflight/clean.sh | 干净现场 | 端口/显存/进程零 | — | 经验(pkill自匹配) |
| M0调研 | model_profile.py | models/{name}.profile.json | 无profile禁serve | 档案 | 容器注册表 |
| M0.5调研 | Agent检索 | external_research | 实测后才verified | 档案+KB提名 | web |
| 5组网 | cluster.sh | ray双机 | 2节点2GPU | 档案 | 经验(ray僵尸/QSFP) |
| 6场景 | cell*.sh+bench/* | raw/<tag>/全量 | 四关+档门禁+屋顶线+截断率 | 档案 | profile/经验/KB |
| 7汇编 | build_doc.py | report_doc.json | schema校验 | 档案 | — |
| 8渲染 | report_gen4.py | report_v4.md | 推荐数值回查 | 档案 | — |
| 9沉淀 | Agent | 经验条目/KB提名 | 复现门槛(N≥2) | 经验+KB | 全库 |

## 五、阶段细节补遗（沿用旧版仍有效项）

- **1 清点·机器识别=查库启发式非验证机制**：MAC 集合相似度 + 机型一致 → 视为同机换 IP 继承历史经验（`RecognizedAs`），判断依据入事件流。
- **2 拓扑(多机)三层法**：手(网卡/ping矩阵原始数据) → 脑(本地库→web→候选路径假设) → 闸(双向连通实测才可采用)；QSFP 段 awk 状态机探测（grep -B 会跨块误抓）。
- **3 分发·DLP**：分发中心源盘即密文，非白名单进程读乱码；洗白走 PowerShell Copy-Item 通道（唯一已验证解密通道）；SFTP `~` 不展开须 `$HOME` 绝对化。
- **测试纪律（2026-10-01 订 + 09-30 增）**：p99 必报；性能/能力/智能体分开跑不混跑；结论级吞吐用真实分布(prompts.jsonl)，固定长度仅限同分布横比；屋顶线超 80% 报警人工复核；能力评测必须关思考链（否则 max_tokens 被思考耗尽出假分）。

## 六、不变量（十条）

1 密码一次性 2 先只读后变更 3 证据绑定结论 4 门禁必须在脚本里 5 契约收敛(报告是唯一出口)
6 远端路径绝对化 7 幂等可断点重跑
8 **无模型 profile 不得 serve**（M0 硬门禁）
9 **验收契约必须含目标用途的真实调用形态**（四关，对话绿≠agent可用）
10 **parser/方法名必须探针实测**（文档与注册表都只是参考：有`<tool_call>`标记≠hermes）
