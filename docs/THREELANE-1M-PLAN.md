# 三车道 300K→1M 长会话压测计划（v1.0 · 2026-10-03 · 待老板空闲窗口执行）

> 被测对象 = 当前演示服务原样冻结：TP2+EP2+MTP2+YaRN4x+1M+8路硬顶+qwen3_xml+batched8192
> 配置不改、不重启；全程零接触服务进程；sniffer(/tmp/sse8000.log)持续在收

## 0. 要回答的七个问题（赛后逐条对账）

| # | 问题 | 预判（依据实测物理量） |
|---|---|---|
| Q1 | 单流 decode 速度随上下文衰减曲线 | 118 → 可能 30-60 tok/s（每token读全部历史KV）——**最大未知数** |
| Q2 | 稳态轮 TTFT 曲线 | 恒 ~7-8s（尾巴≈22K÷3K tok/s），不随水位显著变化 |
| Q3 | 工具调用在 500K+ 的鲁棒性 | qwen3_xml 未在长上下文验证过——真未知 |
| Q4 | 三客户端并行互相影响 | 轮尾预填串行化 → 20-30s 排队尖峰；8路内无解码挤兑 |
| Q5 | 1M 实际可达性与可用性 | 只能增量养（1M冷预填≈350s必死）；decode 到顶是否可用是关键 |
| Q6 | 三种客户端形态对比 | 给产品化选型（裸HTTP / workflow自建harness / sysmind） |
| Q7 | 长会话质量漂移 | 远距离召回探针（对早期种子数据的提问） |

## 1. 种子与任务（三车道同题同料）

**合成"运营数据平台"**（本地确定性生成，seed=20261003）：
- `sales_2026Q3.csv`（约5万行）、`inventory.json`、`web_logs.txt`、`policy.md`（制度文档，报告引用用）
- 初始 300K 会话种子 = 系统提示（数据分析师助理）+ 平台/接口说明 + 首批数据摘要（~250K tok）

**任务链**（每轮一个办公任务，对应老板原话"登录取数→分析→报告"）：
1. 登录销售系统，查华东区上周订单，算同比，表格呈现
2. 库存周转异常 SKU 结合日志找原因
3. 把本季度分析写成报告第 N 章（长输出轮，兼测 decode）
4. 远距离探针轮："第一章引用的制度第 X 条原文是什么"（质量检查）
5. ……循环 2/3/4 变体，每轮工具结果注入 5-20K 新数据

**爬坡数学**：300K + ~20K/轮 × ~36 轮 ≈ 1.03M；历史上限设 **1.03M 冻结**（留 8K 给输出，防 prompt+max_tokens 超 1,048,576 被拒）。

**工具集（L2/L3）**：login_web / query_sales / query_inventory / get_logs / calc / write_report_section——mock 后端 = 读本地合成文件（L2 用 ZCode bash；sysmind 接自己的 mock，语义等价即可）。L1 无工具，同款数据直接贴 prompt。

## 2. 三车道协议

| | L1 curl 基线 | L2 ZCode 动态workflow | L3 sysmind |
|---|---|---|---|
| 形态 | 纯HTTP对话流 | workflow脚本自建agent环：HTTP直连vLLM(SSE解析+tool_calls回环)+world.run执行工具 | 你们的智能体框架 |
| 模型 | 同服务 | 同服务（HTTP直发，历史驻文件不占workflow上下文） | 同服务 |
| 工具 | 无（赛前发1发静态tools证JSON通路） | 6个mock工具真回环 | 同语义工具 |
| 超时 | --max-time 600 | requests timeout 900 | **必须≥180s（60s实测必死，红色要求）** |
| 并发 | 1路 | 1路 | 1路 |
| 其他 | python组包防GBK坑；-w time_starttransfer=TTFT | 每轮记TTFT/工具数/loop e2e | 统一日志格式(§4) |
| 温度 | 0.7，enable_thinking:false 全车道统一 | | |

## 3. 检查点与测量块

水位：**300K(基线) → 500K → 700K → 850K → 1M(冻结)**

每个水位每车道执行测量块（约5轮，10分钟）：
- M1 冷尾轮：正常下一轮（含缓存尾巴）→ TTFT
- M2 热轮：紧随的小问题 → TTFT（纯尾巴成本）
- M3 decode轮：max_tokens 512 长输出 → 流式 tok/s（Q1核心）
- M4 工具往返（L2/L3）：→ toolcall TTFT + loop e2e + parser成败（Q3核心）
- M5 质量探针：远距离召回 → 对/错（Q7）
- 服务端同步：metrics 快照（直方图/前缀命中/投机/gauge）+ sniffer 持续

**错峰**：三车道轮次启动交错 20-40s，预填不互踩；赛中老板随时插入（8路硬顶内：3车道+老板≤6路）。

## 4. 日志与对账格式（三方统一）

每轮一行 JSONL：`{lane, turn, ctx_tokens, ttft_ms, decode_tok_s, tool_calls, loop_e2e_ms, ok, timeout, retry, ts}`
服务端：metrics 快照按水位存 `server/metrics_<plateau>.json`；sniffer 赛后拉全量做连接时间线（谁断/第几秒/重试链）与三车道日志对账。
落盘：`tasks/t20261003-threelane-1m/{L1,L2,L3,server,sniffer}/`

## 5. 预检、护栏、中止条件

预检（全只读）：verify 四关 / sniffer 存活 / metrics 基线快照 / **sniffer+连接数确认老板空闲**（用户口令开赛）
护栏：三车道合计≤3路；每车道状态落盘可断点续跑；L1 大响应体存文件后解析
**中止条件**（取证不重启）：vLLM 进程死 / 连续5轮全超时 / GPU OOM 迹象 → 立即停三车道，保现场（log/metrics/sniffer），诊断优先

## 6. 赛后交付

1. 核心曲线：decode速度 vs 上下文（Q1）、TTFT vs 上下文（Q2）、工具成功率 vs 上下文（Q3）
2. 三车道轮次全表 + sniffer 连接时间线三方对账（含超时/重试链）
3. 结论：1M 可用性判定（"能聊到1M"的物理边界）、三客户端形态适用性、产品化参数建议（超时/重试/会话策略）
4. 入库：经验条目 + 场景矩阵新增"长会话爬坡"场景 + 若 Q3 出问题则 parser 修复项

## 7. 时间预算

每车道 ~36轮 + 5×4测量轮；单轮 30-90s（尾巴预填+生成）→ 三车道错峰并行 **约 60-100 分钟**（不含 sysmind 自身调试）。

## 8. 待办（老板空闲前完成，零发包）

- [ ] 种子生成脚本（synth_platform.py，确定性）
- [ ] L1 脚本（python组包+curl流式+TTFT+落盘）
- [ ] L2 workflow 脚本（agent环：SSE解析/tool回环/断点续跑）
- [ ] L3 对齐规范单页发 sysmind 团队
- [ ] 预检脚本（一键：四关+空闲判定+基线快照）
