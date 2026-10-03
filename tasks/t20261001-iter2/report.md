# t20261001-iter2 双机双模型分发 — 报告

> 生成时间: 2026-10-01 ｜ 报告人: 报告员(agent) ｜ **任务状态: completed（双机 allOk=true，按任务指示以 allOk 定状态；但 du 体积复核暴露完整性疑点，见异常 1–3）**

## 一、概览

任务：向 192.168.199.129 与 192.168.199.134 分发 **Qwen3.6-35B-A3B-NVFP4-Fast** 与 **Qwen3.8-27B-NVFP4** 至远端 `~/.cache/huggingface`（`/home/syspetro/.cache/huggingface`）。

| Host | 分发 allOk | Qwen3.6-35B-A3B-NVFP4-Fast (du) | Qwen3.8-27B-NVFP4 (du) | 复核到模型目录 | 状态 |
|---|---|---|---|---|---|
| 192.168.199.129 | ✅ true | **20G**（符合 35B NVFP4 量级，判完整） | **16K** ⚠ 疑似存根 | 6 个目录 | completed（附疑） |
| 192.168.199.134 | ✅ true | **16K** ⚠ 近乎为空 | **16K** ⚠ 疑似存根 | 5 个目录 | completed（附疑） |

- 双机 `allOk=true` → task.json `Status="completed"`（按任务指示"Status=按 allOk"）。
- **关键保留意见**：du 复核显示 Qwen3.8-27B-NVFP4 在**两台机器均仅 16K**，Qwen3.6-35B-A3B-NVFP4-Fast 在 134 仅 16K（同模型在 129 实测 20G）。16K 量级只够目录骨架，放不下任何权重分片——分发命令成功 ≠ 权重落盘完整（events.jsonl 第 2、4 行 gate 级已记录同一疑点）。
- `events.jsonl` 共 6 行（129 占 4–6 行、134 占 1–3 行），本会话以 node JSON.parse 逐行校验 **6/6 合法**。

## 二、每机分发统计

### 192.168.199.129（gx10-9f5c）

- **分发结果**：allOk=true（events.jsonl 第 4 行）。
- **目标模型 du 实测**：Qwen3.6-35B-A3B-NVFP4-Fast = **20G**（35B 级 NVFP4 约 20G 量级，吻合，判完整）；Qwen3.8-27B-NVFP4 = **16K**（远小于 27B 权重应体积，疑似仅存根/未完成下载，events 第 4–5 行同判）。
- **远端目录复核**：实际存在 **6 个模型目录**——Nemotron-3-Super-120B-NVFP4、Qwen3.5-122B-A10B-NVFP4、Qwen3.6-35B-A3B-NVFP4-Fast、Qwen3.8-27B-NVFP4、Qwen3.8-Flash-Next-NVFP4、qwen3.8-nvfp4；datasets/hub/modules/xet 为缓存基础设施目录，不计模型（events 第 4 行）。
- **档案更新**：`machines/192.168.199.129.json` 的 Models 按 ls 实际从 10 项改为 6 项——移除 5 个 hub/models--* 条目（hub 内层本次未复核）、新增 Qwen3.8-27B-NVFP4；仅改动 Models 字段，其余字段保持原值（events 第 5–6 行）。
- **对照迭代1**：Qwen3.6-35B-A3B-NVFP4-Fast 在迭代1已存在于 129（本地原有），本迭代实为补齐 Qwen3.8-27B-NVFP4——后者恰是 16K 存根，即**本迭代在 129 的新增分发疑似未落盘权重**。

### 192.168.199.134（gx10-9c05）

- **分发结果**：allOk=true（events.jsonl 第 1 行）。
- **目标模型 du 实测**：Qwen3.6-35B-A3B-NVFP4-Fast = **16K** ⚠、Qwen3.8-27B-NVFP4 = **16K** ⚠——两目录近乎为空，远小于 NVFP4 模型权重应体积，**分发完整性待复查**（events 第 2 行 gate 原话）。
- **远端目录复核**：实际存在 **5 个模型目录**——Nemotron-3-Super-120B-NVFP4、Qwen3.5-122B-A10B-NVFP4、Qwen3.6-35B-A3B-NVFP4-Fast、Qwen3.8-27B-NVFP4、Qwen3.8-Flash-Next-NVFP4（events 第 1 行）。
- **档案更新**：`machines/192.168.199.134.json` 的 Models 已按 ls 实际更新为上述 5 项，移除旧条目 hub/models--nvidia--Qwen3.5-122B-A10B-NVFP4 与 hub/models--nvidia--NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4（hub 内层本次未复核）（events 第 3 行）。
- **对照迭代1**：134 在迭代1**没有** Qwen3.6-35B-A3B-NVFP4-Fast 顶层目录（仅 3 顶层 + 2 hub），Qwen3.8-27B-NVFP4 亦为新出现——即 134 的两个目标模型目录均为本迭代新增，而两者 du 都只有 16K：**本迭代在 134 的分发疑似整体未落盘权重**。

## 三、复核证据

1. **任务下发双机 verification 原文**（本轮结果的唯一远端证据，与 events.jsonl 第 1–6 行一致）：
   - 129：`20G /home/syspetro/.cache/huggingface/Qwen3.6-35B-A3B-NVFP4-Fast`、`16K /home/syspetro/.cache/huggingface/Qwen3.8-27B-NVFP4`，随后 ls 列出 datasets/hub/modules + 6 个模型目录 + xet。
   - 134：`16K /home/syspetro/.cache/huggingface/Qwen3.6-35B-A3B-NVFP4-Fast`、`16K /home/syspetro/.cache/huggingface/Qwen3.8-27B-NVFP4`，随后 ls 列出 hub + 5 个模型目录。
2. **events.jsonl 校验（本会话实际执行）**：`node -e` 逐行 JSON.parse，6/6 行合法；按机分组 129=第 4/5/6 行、134=第 1/2/3 行；gate 级体积疑点各 1 条（129 第 4 行、134 第 2 行）。
3. **体积合理性算术**：35B 级 NVFP4 权重约 20G 量级——129 的 Qwen3.6 实测 20G 恰好吻合，说明 du 口径能如实计入权重；故同为 du 口径下的 16K 只能解释为"目录骨架/存根"，不存在"du 漏计大文件"的解释空间。
4. **证据边界（如实声明）**：本任务复核依据为**分发方回传的远端 ls/du 输出**，events 第 6 行自述"本任务未另行登录远端执行命令"；报告员亦未直接 SSH 复测。两目标模型的逐文件校验和（sha256）本次未做，"20G 即完整"为体积量级推断而非逐字节校验。

## 四、异常与建议

**异常**

1. **Qwen3.8-27B-NVFP4 双机均 16K（最严重）**：两台机器上该模型目录都近乎为空，本迭代对它的分发在双机均疑似未落盘权重。
2. **同一模型两机体积差 6 个数量级**：Qwen3.6-35B-A3B-NVFP4-Fast 在 129 为 20G、在 134 为 16K——134 侧分发实际未完成，与 allOk=true 直接矛盾。
3. **完成判据缺陷**：`allOk` 只证明分发命令/传输流程成功，未含远端体积或文件数校验；按 allOk 置 completed 的状态下必须保留本节疑点记录。
4. **129 疑似重复目录**：存在小写 `qwen3.8-nvfp4` 目录（本次未测体积）。真权重是否错放其中是**未验证假设**，需实测排除。
5. **两机目录集仍不对齐**：129 多 `qwen3.8-nvfp4` 与 datasets/modules/xet，134 无；两机根分区余量此前已仅约 450G，重推 27B+35B 权重前应先核对磁盘空间。

**建议**

1. **对 16K 目录重跑分发**：Qwen3.8-27B-NVFP4（129+134）与 Qwen3.6-35B-A3B-NVFP4-Fast（134）需重推或核对分发日志定位失败环节；重推前勿在这两处直接起服。
2. **分发门禁加体积下限**：完成判定改为"allOk ∧ 远端 du/文件数 ≥ 量级下限"双条件，经验库已沉淀本条（experience/gb10.md 第 6 条）。
3. **实测 129 的 qwen3.8-nvfp4 体积**：排除权重错放/重复占盘；确认后清理多余目录。
4. **下一步可用基线**：当前唯一经 du 佐证完整的是 **129 的 Qwen3.6-35B-A3B-NVFP4-Fast（20G）**，单机冒烟可先用它；134 两模型在复验通过前视为不可用。
5. **复核升级**：后续任务 SSH 直登远端逐文件校验和（或 HF snapshot hash）对账，替代单点 du 抽查。

---
**事实来源**：① 任务下发的双机分发结果与 verification 原文（du 两行 + ls 列表）；② `tasks/t20261001-iter2/events.jsonl`（6 行，本会话 node JSON.parse 校验通过，第 2/4 行为 gate 级体积疑点）；③ `tasks/t20261001-iter1/report.md` 与两份 `machines/*.json` 更新记录（对照迭代1基线）；④ `docs/LIBRARIES.md`（task.json/run.json 契约）。本报告未引入上述之外的事实；"疑似存根/未完成下载"为体积推断，均如实标注。
