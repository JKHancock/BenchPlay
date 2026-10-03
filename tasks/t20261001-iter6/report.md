# t20261001-iter6 条件组合矩阵（TP1/TP2 × 双模型）— 报告

> 生成时间: 2026-10-01 ｜ 报告员: 报告员(agent) ｜ **任务状态: completed_with_failure（矩阵 4 组：3 过 1 败——TP1-Qwen3.6 / TP2-Qwen3.8 / TP1-Qwen3.8 三组 serve+verify+bench 全过；TP2-Qwen3.6 组 serve 起服失败（KeyboardInterrupt terminated + leaked shared_memory），如实记败、无指标。可比组合内 TP2 对 Qwen3.8 全维度领先（出流 1.78×），Qwen3.6 单机 TP1 即达 67.7 tok/s≈Qwen3.8 的 6.1×）**

## 一、概览

- **背景**：iter5 完成双实现握手（TP2 部署 × 孪生 C# llm-bench CLI，快速档 PASS）后，本轮进入**条件组合矩阵**：并行度 {TP1, TP2} × 模型 {Qwen3.6, Qwen3.8} 共 2×2=4 组，每组走同一链路 serve → verify → bench，组名后缀 `40960` 对应 `--max-model-len 40960`（iter4 部署链 serve.sh:10 默认值，按组名与既有部署配置推断）。
- **模型（两模型，= task.json Models）**：
  - **Qwen3.6-35B-A3B-NVFP4-Fast**——MoE 35B 总参/A3B 激活（激活量为名称推断），双机 du 实测 23,690,108,390 字节（iter2b 补全后一致）；
  - **Qwen3.8-27B-NVFP4**——27B（名称无 AxB 激活标注，按 dense 理解，此为命名推断），du 实测 23,444,515,546 字节。
- **结果**：4 组中 **3 组 PASS、1 组 FAIL**。PASS 组全为「serve+verify+bench 全过」；FAIL 组（TP2-Qwen3.6）卡在 serve 段，verify/bench 未执行。
- **证据口径（如实声明）**：本轮 4 组的判定行与指标**全部转录自任务下发结果原文（本 ask 材料），报告员本会话未重跑任何 serve/verify/bench**；报告员本会话实际执行的核查=①指标自洽交叉验算（1/TPOT_p50 vs 出流，node 实算，见 §三）；②组合间比值换算（同上）；③跨迭代对照数据（iter5 TP2-Qwen3.6=94.19ms/10.44ms/92.74tok/s）实读 `tasks/t20261001-iter5/report.md` §三档案表。

## 二、横比表（核心）

| 组合 | TTFT_p50 | TPOT_p50 | 出流 tok/s | 结论 |
|---|---|---|---|---|
| TP1-Qwen3.6-40960 | **117 ms** | **14.4 ms** | **67.7** | ✅ serve+verify+bench 全过（并发1×8条，成8/败0） |
| TP2-Qwen3.8-40960 | **183 ms** | **50.2 ms** | **19.7** | ✅ serve+verify+bench 全过（并发1×8条，成8/败0） |
| TP1-Qwen3.8-40960 | **267 ms** | **89.6 ms** | **11.1** | ✅ serve+verify+bench 全过（并发1×8条，成8/败0） |
| TP2-Qwen3.6-40960 | — | — | — | ❌ **FAIL：serve 起服失败**（KeyboardInterrupt terminated），verify/bench 未执行，无指标 |

**跨迭代参照行（非本轮矩阵成员，仅供 Qwen3.6 TP2 侧对照）**：

| 参照 | TTFT_p50 | TPOT_p50 | 出流 tok/s | 来源 |
|---|---|---|---|---|
| TP2-Qwen3.6-40960（iter5 档案 20261001-154442） | 94.19 ms | 10.44 ms | 92.74 | 实读 tasks/t20261001-iter5/report.md §三（并发1×8，同门禁口径） |

**速读**：① Qwen3.8 侧同轮可比，TP2 全面优于 TP1（TTFT 1.46×、TPOT 1.78×、出流 1.78×）；② Qwen3.6 侧本轮只剩 TP1 存活，其 67.7 tok/s 仍远高于 Qwen3.8 任何组合（TP1 口径 6.10×）；③ Qwen3.6 TP2 本轮失败，但 iter5 同组合曾 PASS 且 92.74 tok/s 为全矩阵最高参照值——失败属通道/环境性质疑点而非组合不可行（定性依据见 §五）。

## 三、逐组过程与自洽校验

四组同链路：serve（vllm serve，served-model-name=bench）→ verify → bench（快速档：并发1 × 8条，512in/256out 同 iter5 口径）。逐组判定与指标转录自下发原文：

### ① TP2-Qwen3.6-40960 —— ❌ FAIL

- 过程：serve 段失败，服务未就绪，verify/bench 顺延未执行。
- 下发 detail 原文转录：`serve FAIL: 024) KeyboardInterrupt: terminated`，伴 `multiprocessing/resource_tracker.py:254 UserWarning: resource_tracker: There appear to be 1 leaked shared_memory objects to clean up at shutdown`。
- 定性边界（如实）：KeyboardInterrupt=进程收到中断信号被终止，属**外部终止/中断形态**；leaked shared_memory 是 vLLM 多进程引擎被中途打断时的典型伴生征状（resource_tracker 在 shutdown 时清不完共享内存）。**真因本轮材料不可得**（无 serve 日志全文回传），不下结论；该组无 metrics，detail 记 `-`。
- 对照：同组合 iter5 曾 PASS（§二参照行），排除「该组合本质上起不来」的解读。

### ② TP1-Qwen3.6-40960 —— ✅ PASS

- 下发 metrics：`并发1 x 8条: TTFT_p50=117ms TPOT_p50=14.4ms 出流=67.7tok/s (成8/败0)`；8 条全成、零失败。
- 报告员交叉验算（本会话 node 实算）：1/14.4ms=69.4 tok/s vs 实测 67.7，偏差 2.6%——并发1 单流下出流≈1/TPOT 自洽，数据可信。

### ③ TP2-Qwen3.8-40960 —— ✅ PASS

- 下发 metrics：`并发1 x 8条: TTFT_p50=183ms TPOT_p50=50.2ms 出流=19.7tok/s (成8/败0)`。
- 交叉验算：1/50.2ms=19.9 tok/s vs 实测 19.7，偏差 1.1%，自洽。

### ④ TP1-Qwen3.8-40960 —— ✅ PASS（全矩阵最慢存活组）

- 下发 metrics：`并发1 x 8条: TTFT_p50=267ms TPOT_p50=89.6ms 出流=11.1tok/s (成8/败0)`。
- 交叉验算：1/89.6ms=11.2 tok/s vs 实测 11.1，偏差 0.5%，自洽。三组 PASS 数据全部自洽，无一项超过 2.6% 偏差。

## 四、解读

### 4.1 TP1 vs TP2（并行度维度）

- **Qwen3.8（同轮直接可比，结论最硬）**：TP2 对 TP1 = TTFT 267→183ms（1.46×）、TPOT 89.6→50.2ms（1.78×）、出流 11.1→19.7 tok/s（1.78×）。**TP2 全维度领先**——decode 端近打满 2× 理想值（1.78/2=89% 线性度，跨双机 ray 通信损耗下属正常偏好），prefill 端 512in 小提示词场景也未被通信开销反噬。
- **Qwen3.6（本轮 TP2 缺席，跨迭代对照仅供参考）**：TP1 本轮 117ms/14.4ms/67.7 tok/s；iter5 TP2 档案 94.19ms/10.44ms/92.74 tok/s。若两轮条件可比（同快速档 1×8、同 40960 上下文、同 bench 门禁），TP2 出流为 TP1 的 1.37×、TPOT 1.38×——**TP2 对 MoE 模型的增益（~1.4×）明显小于对 dense 27B 的增益（~1.8×）**，方向上符合「A3B 仅 3B 激活、单机算力已够喂饱 decode」的机理（激活量为命名推断）。⚠️ 该对照跨迭代（不同时刻、TP2 通道本轮另有失败疑点），只作方向性参考，不进硬结论。

### 4.2 两模型差异（模型维度）

- **同在 TP1（同轮可比）**：Qwen3.6 出流 67.7 tok/s = Qwen3.8 11.1 tok/s 的 **6.10×**；TPOT 14.4ms vs 89.6ms（6.22×）；TTFT 117ms vs 267ms（2.28×）。**模型差异远大于并行度差异**——换模型的影响（6×）比换并行度的影响（1.8×）高一个量级。
- 机理（按命名推断，如实标注）：Qwen3.6-35B-**A3B** 是 MoE、每 token 仅激活 ~3B 参数；Qwen3.8-27B 按 dense 理解、每 token 全参 27B 参与计算——decode 每 token 计算量差 ~9×，实测出流差 6.1× 量级吻合。**结论：吞吐敏感场景优先 Qwen3.6；Qwen3.8 的价值须到质量侧（Track2）找，速度侧不占优。**

### 4.3 部署取舍建议（数据导向）

1. **默认档**：Qwen3.6 + TP2（iter5 参照 92.7 tok/s，矩阵最高）——但本轮 TP2-Qwen3.6 serve 失败提示该通道（跨双机 ray）稳定性需先复跑定位（见 §五）。
2. **稳健档**：Qwen3.6 + TP1（67.7 tok/s）——单机部署、无 ray 双机依赖，失败面小；本轮它恰是 Qwen3.6 侧唯一存活组合，**当 TP2 通道不稳时 TP1 是可立即切换的降级路径，性能代价约 -27%（92.7→67.7，跨迭代口径）**。
3. **Qwen3.8 只在需要其质量/能力差异时上，且应配 TP2**（TP1 下 11.1 tok/s 的交互体验已近不可用边缘）。

## 五、失败组如实记录（TP2-Qwen3.6-40960）

- **判定**：`ok: false`，metrics `-`（无任何基准指标，不许补造）。
- **失败形态原文**（下发 detail 转录）：`serve FAIL: 024) KeyboardInterrupt: terminated`；`/usr/lib/python3.12/multiprocessing/resource_tracker.py:254: UserWarning: resource_tracker: There appear to be 1 leaked shared_memory objects to clean up at shutdown`。
- **三条边界**（如实，不越界下结论）：
  1. KeyboardInterrupt 是**信号中断形态**而非模型加载/OOM 类报错——大概率是 serve 进程被外部终止（超时击杀/人工中断/编排层 timeout），但本轮无 serve 日志全文，**根因不可判**，记「待复跑定位」；
  2. leaked shared_memory(1 个)是进程树被中途打断的伴生征状，本身不构成独立故障，但提示**复跑前应确认无残留共享内存/僵尸进程**（iter3b/3c 的 Z 态尸体经验：kill 不掉、根治靠容器重启，可带尸部署但别混算）；
  3. **该组合 iter5 曾 PASS**（92.74 tok/s），「组合不可行」解读被跨迭代证据排除；当前最经济的下一步=同参数复跑 1 次——复现则深挖 serve 日志，消失则记偶发中断并回填该组指标。
- **对矩阵结论的影响**：Qwen3.6 的 TP1-vs-TP2 对比本轮**不成立**（缺同轮 TP2 数据），§四 4.1 中相关表述均已标注「跨迭代对照/方向性参考」。

## 六、新发现沉淀（已追加 experience/gb10.md，INDEX 已更新）

| # | 条目 | 要点 |
|---|---|---|
| 23 | TP1/TP2 部署差异：TP2 通道多一层 ray 双机依赖，serve 中断形态=KeyboardInterrupt+leaked shared_memory | TP1 单机无 ray 依赖、失败面小，是 TP2 通道异常时的现成降级路径（Qwen3.6: 92.7→67.7 tok/s, -27%）；KeyboardInterrupt+resource_tracker 泄漏告警是进程被外部中断的伴生征状，复跑前清场；同组合跨迭代可 FAIL 可 PASS（iter5 PASS/iter6 FAIL），单次失败不定罪组合 |
| 24 | 组合矩阵性能事实：并行度增益 ~1.8×（dense 27B）< 模型差异 ~6×（MoE-A3B vs dense） | Qwen3.8 TP2/TP1=出流 1.78×、TPOT 1.78×、TTFT 1.46×（同轮硬数据）；TP1 口径 Qwen3.6/Qwen3.8 出流 6.10×；并发1 下出流≈1/TPOT_p50（偏差 ≤2.6%）可作数据自洽速检 |

## 七、备注与遗留

- **主机归属口径推断（如实标注）**：本轮下发材料未给逐组主机，事件 Machine 字段按部署惯例填 head 192.168.199.129——TP2 组=129(head)+134(worker) 经 ray 分摊，TP1 组=单机（按 playbook 惯例在 head 起 serve）。此为口径推断，非逐组实测。
- **bench 口径沿用 iter5**：快速档并发1×8；512in/256out、temp=0、ignore_eos、seed 等参数未在本轮下发材料中出现，按 iter5 快速档口径推断（report 已标注），不影响组间横比（各组同口径）。
- **遗留**：① TP2-Qwen3.6 复跑 1 次（同参数），定「偶发中断 vs 通道不稳」；② 复跑前清场检查（残留共享内存/ray 僵尸，参照 iter3b/3c 口径）；③ Qwen3.8 的选型价值验证归 Track2 质量通道（前置=操作机 `HF_ENDPOINT=https://hf-mirror.com`，iter5 条目21）；④ 4 组矩阵只有 3 组有效指标，Qwen3.6 TP2 格子回填后矩阵才完整。

## 八、产物清单（本任务目录）

| 文件 | 说明 |
|---|---|
| `report.md` | 本报告 |
| `task.json` / `run.json` | 任务档案（Id=t20261001-iter6, Models=[Qwen3.6-35B-A3B-NVFP4-Fast, Qwen3.8-27B-NVFP4]） |
| `events.jsonl` | 10 条事件（每组 2-3 条 + task-close 收口） |
