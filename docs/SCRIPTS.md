# 脚本工具索引（Agent 执行手册）

> 本文件是 Agent 的**工具箱目录**：每个阶段该用哪个脚本、怎么调、门禁是什么。
> 新会话 Agent 在进入任何阶段前先查此表。

## 按阶段分类（执行顺序）

### 阶段 0 · 引导
| 脚本 | 用法 | 门禁 |
|---|---|---|
| `bootstrap_key.py <host> <user> <password>` | 密码一次性换密钥 | 新连接密钥跑 `whoami` = 用户名 |

### 阶段 1 · 清点
| 脚本 | 用法 | 门禁 |
|---|---|---|
| `probe.sh <host>` | 十项只读探测→机器档案 JSON | 非空字段必有证据 |

### 阶段 2 · 底座与模型适配
| 脚本 | 用法 | 门禁 |
|---|---|---|
| `substrate.sh <host>` | 容器/镜像/digest 核验 | GPU 进程归零 |
| `model_profile.py <model_dir> [--container-check host:container]` | M0 四层画像→`models/<name>.profile.json` | 无 profile 禁 serve |
| `gen_scenarios.py <profile> [--mem-gb N] [--experience file]` | 三层场景生成（L1 笛卡尔→L2 裁决→L3 降维） | 可行组合>0 |
| `add_scenario.py <profile> "TP2+EP+MTP3" [--dry-run]` | 增量追加新场景 | 裁决=feasible 且未测 |

### 阶段 3 · 分发
| 脚本 | 用法 | 门禁 |
|---|---|---|
| `distribute.sh <host> <model> <root>` | 模型→节点（sha256 门禁+增量续传） | 逐文件哈希全对 |
| `wash.ps1 <src> <dst>` | DLP 密文→明文（PowerShell 通道） | config.json 可解析 |

### 阶段 4 · 预检清场
| 脚本 | 用法 | 门禁 |
|---|---|---|
| `preflight.sh <host>` | 端口/显存/残留进程检查 | 全零 |
| `clean.sh <host>` | 杀 vllm/ray/EngineCore 三进程族 | GPU 归零 |

### 阶段 5 · 组网
| 脚本 | 用法 | 门禁 |
|---|---|---|
| `cluster.sh <head> <worker> <user>` | ray 双机起 | 2 节点 2 GPU |

### 阶段 6 · 服务与测试
| 脚本 | 用法 | 门禁 |
|---|---|---|
| `serve.sh <host> <user> <model> [key] [maxlen] [tp] [extra]` | vLLM serve（引号安全通道） | 就绪门禁+KV 两行落档 |
| `verify.sh <host> [expect_tools=1]` | 四关验收 | 全过 |
| `cell4.sh <tp> <model> <gb> <tag> [extra]` | 通用场景全电池 | 四关+档门禁+屋顶线 |
| `cell5.sh` | 1M 上下文场景电池 | 同上 |
| `cell6.sh` | Flash-Next(qwen4_exp)专用电池(八套件时期) | 同上 |
| `cell7.sh` | Flash-Next 12套件复测电池(关自调优, math500开思考链) | 同上 |
| `matrix4.sh` | 多场景矩阵编排（调 cell4/5/6） | 全场景完成 |

### 阶段 7-8 · 汇编渲染
| 脚本 | 用法 | 门禁 |
|---|---|---|
| `build7.py` | raw→report_doc.json（含 agent_metrics） | JSON Schema 校验 |
| `report_gen4.py <doc> [out] [模型过滤]` | 渲染 markdown 报告 | 推荐数值回查 |

### 阶段 9 · 沉淀
| 脚本 | 用法 | 门禁 |
|---|---|---|
| `scenario_index.py <doc>` | 场景→全局索引 jsonl | 幂等追加 |
| `scenario_index.py -q "tp=2"` | 跨任务查询 | — |
| `kb.py upsert/query/export/rebuild` | 知识库 Qdrant 客户端（export=快照进 git，rebuild=从快照重建） | 提名制 |
| `envfingerprint.sh <host>` | 环境指纹 | — |
| `reset_data.sh show|data|all` | 数据清空冷启动（data=清实验记忆留经验库；all=全清+删Qdrant集合） | 删除物入 .reset_backup 可反悔 |

### 运维与诊断
| 脚本 | 用法 | 场景 |
|---|---|---|
| `serve_demo.sh` | 演示服务（3.6 当前最优组合） | 老板演示 |
| `serve_demo27b.sh` | 演示服务（27B 当前最优组合） | 老板演示 |
| `fourcoll.sh` | 四指标集合快速采集 | 服务侧体检 |
| `sniff8000.py` | 8000 端口 SYN/FIN/RST 嗅探 | SSE 超时诊断 |
| `capture_kv.sh <tp> <model> <tag> [extra]` | KV 启动行补采 | startup.log 丢失时 |
| `overnight.sh [DS_EXTRA] [skip-ds] [all|b-only]` | 整夜无人值守编排 | 批量测试 |

### 配置
| 文件 | 用途 |
|---|---|
| `excluded_scenarios.json` | 每模型的不可行/待测/不适用组合清单 |

## Agent 使用规则

1. **按阶段查此表选脚本**——不要凭记忆调脚本名
2. **先看门禁列**——门禁不过不进下一步
3. **cell4/5/6/7 是编排脚本**——它们内部调 serve/verify/bench 工具链
4. **bench/ 工具与数据集已收编进本仓库**（`bench/` + `data/cap/`）——track1(性能) track2(能力12套) track2_extra(新四套) track3(智能体) bfcl(函数调用) probes(探针)；依赖 `pip install -r requirements.txt`。旧位置 `../Vllm_Benchmark/bench/` 仅作历史运行档案(cell7 前)的路径参考
5. **DLP 注意**：Python 写文件可能触发 DLP 加密；**git 提交前先洗白**（Python 新写的 JSON/log 用 PowerShell Copy-Item 通道过一遍再 add，git 仓库内保持明文），如遇"文件不可读"用 `wash.ps1`
