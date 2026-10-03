# t20261001-iter3b 自匹配与 pattern 修复后的预检→精准清理→复检 — 报告

> 生成时间: 2026-10-01 ｜ 报告人: 报告员(agent) ｜ **任务状态: failed（宽口径复检双机 ok=false——唯一真实障碍 = 宿主级 ray 残留 129 九项 / 134 两项待强杀收尾；但迭代 3 的两处脚本故障已修复并经本轮验证：clean.sh 全程存活、无自杀型 FAIL，窄口径门禁(GPU+8000 端口)双机 PASS，vllm_procs 探测自匹配清零，GPU 计算进程与 8000 端口实质 CLEAN；容器 vllm-node 按策略保留）**

## 一、概览

- **背景**：迭代 3（t20261001-iter3）对 129 手工部署遗留的 TP2 vLLM 栈执行进程级退役（容器/镜像/模型数据全部保留），双机 FAIL。根因有二（均经实测）：① clean.sh 执行段 `pkill -f "raylet|gcs_server"` 的 pattern 文本命中远程 shell 自身 cmdline → 父 shell 被杀 → ssh 255 → 自杀型 FAIL（129 探针复现）；preflight.sh 的 `pgrep -f` 同样自匹配，预检出现幽灵 vllm 进程条目；② 旧 pattern 面向 python -m 时代入口，打不中新 CLI `vllm serve`。
- **迭代 3b**：应用修复（方括号字符类技巧 + pattern 覆盖 `vllm serve`）后重跑「预检→精准清理→复检」，目标 = 验证修复 + 拿最终洁净证据。
- **结果**：修复验证达成（见第二节/第三节）；宽口径复检门禁仍 ok=false（见第四节）——真实残留仅 ray_procs，强杀收尾本就是迭代既定的下一步；另两条 DIRTY 标签一为按策略保留的容器、一为已知误报签名的 port8000，均不计为清理障碍（events.jsonl 第 6 行口径）。

| Host | clean.sh(修复后) | 复检六节(2026-10-01T15:40, 下发 JSON + events 口径) | 真实障碍 | ok |
|---|---|---|---|---|
| 192.168.199.129 | 全程存活，窄口径门禁 PASS | gpu/vllm/model_lock CLEAN(0)；port8000 DIRTY(0 项，误报)；containers DIRTY(1，按策略保留)；ray_procs DIRTY(9 项) | 宿主 ray 9 项 | ❌ false |
| 192.168.199.134 | 同左 | gpu/vllm/model_lock CLEAN(0)；port8000 DIRTY(0 项，误报)；containers DIRTY(1，按策略保留)；ray_procs DIRTY(2 项) | 宿主 ray 2 项 | ❌ false |

## 二、事故复盘与修复

### 2.1 故障一：pkill/pgrep -f 的 pattern 自匹配（同一根因，两侧表现）

- **杀伤侧（pkill）**：iter3 时 clean.sh:20 `pkill -f "raylet|gcs_server"` 以 `bash -c '<脚本全文>'` 在远程运行，pattern 文本就在父 shell 自身 cmdline 里；`pkill -f` 只排除 pkill 进程自己、不排除父 shell → 父 shell 收 SIGTERM，脚本死在该行（"宿主 ray 残留已停"回显缺失），ssh 退 255，clean.sh 判 FAIL，其自带门禁根本未执行。129 探针 `ssh … 'pkill -f ReporterSelfMatchProbe_20261001_xq7; echo SURVIVED'` 复现同签名（详见 iter3 报告第四节）。
- **探测侧（pgrep）**：preflight.sh 旧版 `pgrep -af 'vllm|openai.api_server'` 同理把远程 shell 自身记成 vllm 进程——iter3 双机 vllm_procs 的"残留"条目（129 PID 1792765 / 134 PID 1001927）实为探测命令自身，PID 每次探测都变（幽灵进程型误报，非真实 vllm 进程）。
- **修复（已落盘，本会话实读核对）**：
  - `scripts/clean.sh:20`：`pkill -f "raylet|gcs_server"` → **`pkill -f "[r]aylet|[g]cs_server"`**（方括号字符类使 pattern 文本不再字面匹配自身 cmdline）；
  - `scripts/preflight.sh:23`：**`pgrep -af '[v]llm|[o]penai.api_server'`**（同技巧）；
  - `scripts/preflight.sh:22`：ray_procs 段 `ps -eo pid,comm | grep -E 'raylet|gcs_server|ray::' | grep -v grep`（grep 自身排除）。
- **3b 验证**：clean.sh 双机全程存活，六节复检输出完整返回——iter3 的"回显中断 + FAIL 清理命令执行失败"签名消失；vllm_procs 双机 **CLEAN(0 项)**——幽灵条目不再出现。

### 2.2 故障二：清理 pattern 未随目标 CLI 演进更新

- iter3 旧 pattern 面向 python -m 时代入口（`vllm.entrypoints|openai.api_server`），而 129 遗留栈实际 cmdline 是 `vllm serve /root/.cache/huggingface/Qwen3.8-27B-NVFP4 --tensor-parallel-size 2 --distributed-executor-backend ray --served-model-name bench --host 0.0.0.0 --port 8000 …`（iter3 报告第五节记录）——旧 pattern 打不中新 CLI。
- **修复**：`scripts/clean.sh:17` 容器内段现为 **`pkill -f "[v]llm serve|[v]llm.entrypoints|[a]pi_server"`**——新 CLI `vllm serve` 置于 pattern 首位，逐词加字符类防自匹配。
- **说明（如实记录）**：至 3b 复检时双机 vllm_procs 已 CLEAN(0 项)（vllm serve 在 iter3 阶段已随容器内 ray stop 消失），故该新 pattern 的实战命中未在本轮单独验证；其价值在保证下一轮同类 `vllm serve` 部署可被精准命中，且不会重演自匹配。

## 三、最终洁净证据（3b 复检，覆盖两台机）

**数据源**：任务下发的迭代 3/3b 最终结果 JSON（双机 "after" 六节全文）+ `tasks/t20261001-iter3b/events.jsonl`（6 行，Ts=15:40）。报告员本会话**未重跑远端检测**（与 events.jsonl 第 3 行「档案员仅做记录未重跑检测」口径一致），下表按下发原文逐节转录与定性。

### 192.168.199.129（gx10-9f5c，ray 头节点）

| 复检节 | 输出内容 | 计数 | 定性 |
|---|---|---|---|
| containers | vllm-node ｜ vllm/vllm-openai:latest ｜ Up 22 hours | 1 | 🔒 按策略保留（非清理目标；容器内 ray/vllm 已于 iter3 清空） |
| port8000 | （无条目） | 0 | ✅ 实质 CLEAN（标签 DIRTY 系 preflight.sh:14-17 grep 退出码误报，见 4.3；iter3 直连 ss 已证无监听） |
| gpu_procs | （无条目） | 0 | ✅ CLEAN（iter3 时 677653 占用的 102210 MiB 已释放） |
| ray_procs | 673447 gcs_server、673632 raylet、ray::IDLE×6（674267/273/274/275/279/281）、677653 ray::RayWorkerP | 9 | ❌ 唯一真实残留（PID 与 iter3 残留完全一致；GPU 占用已为 0，卡在优雅退出） |
| vllm_procs | （无条目） | 0 | ✅ CLEAN（自匹配修复生效） |
| model_lock | （无条目） | 0 | ✅ CLEAN |

对照轨迹：ray_procs **22 项（iter3 预检）→ 9 项（iter3 意外 SIGTERM 后）→ 9 项（3b，PID 未变）**；其中 ray::IDLE 19 → 6 → 6。

### 192.168.199.134（gx10-9c05，ray worker 节点）

| 复检节 | 输出内容 | 计数 | 定性 |
|---|---|---|---|
| containers | vllm-node ｜ vllm/vllm-openai:latest ｜ Up 22 hours | 1 | 🔒 按策略保留 |
| port8000 | （无条目） | 0 | ✅ 实质 CLEAN（同款误报签名） |
| gpu_procs | （无条目） | 0 | ✅ CLEAN（iter3 时 778340 占用的 102210 MiB 已释放） |
| ray_procs | 777676 raylet、778340 ray::RayWorkerP | 2 | ❌ 唯一真实残留（PID 与 iter3 预检/残留完全一致） |
| vllm_procs | （无条目） | 0 | ✅ CLEAN（iter3 预检唯一条目本就是探测自匹配） |
| model_lock | （无条目） | 0 | ✅ CLEAN |

**汇总**：双机 6 节 ×2 = 12 节 —— 8 节 CLEAN，2 节按策略保留（containers），2 节真实残留（ray_procs 129×9 / 134×2），另有 port8000 两节标签误报（实质 0 监听）。即任务下发结论：**GPU/端口 CLEAN、vllm/model_lock CLEAN、容器保留；宿主 ray 残留待强杀收尾**。

## 四、门禁判定与口径

1. **窄口径（clean.sh:24-31 自带门禁：GPU compute-apps + 8000 端口监听）**：双机 **PASS**——修复后脚本首次走到门禁段并输出 CLEAN（iter3 时该段因自杀型 FAIL 根本未执行）。
2. **宽口径（preflight 六节复检）**：双机 **ok=false**——唯一障碍是 ray_procs 宿主残留；按既定口径（events.jsonl 第 6 行），port8000 误报与容器保留不计为清理障碍。→ 任务 Status 记 **failed**，放行条件 = 强杀后复检 ok=true。
3. **ok 字段语义**：下发 JSON 的 ok=false 反映宽口径；其三个 DIRTY 标签定性见第三节表格——**勿把 port8000 [DIRTY](0 项) 读成"有监听"**（gb10.md 既有条目：[DIRTY](0 项) 应先怀疑 grep 退出码误报）。

## 五、遗留与建议

1. **宿主 ray 强杀收尾（两机，下一步首项）**：129 建议 `pkill -x raylet; pkill -x gcs_server` + 对 ray:: 前缀 worker 用 `pkill -9 -f "[r]ay::"`（RayWorkerProc 的 comm 被截断为 `ray::RayWorkerP`，-x 精确名不可用，须 -f 加字符类）；134 同法处理 777676/778340。强杀后**必须复检 ray_procs CLEAN** 才算放行。
2. **preflight.sh 判脏误报未修**：section()（preflight.sh:14-17）仍把"退出码非 0"判 DIRTY，port8000/ray_procs/vllm_procs 三段 grep 收尾无匹配即误报——本轮 port8000 双机 [DIRTY](0 项) 即此签名。建议改"只看输出非空"（退出码仅区分命令失败）或段尾 `|| true`（iter3 已沉淀 gb10.md 条目）。
3. **134 密钥面不对称未变**（拒 benchpilot_ed25519、仅认含空格路径的 nvsync.key；脚本 KEYFLAG 未加引号），批量脚本改造时一并处理（gb10.md 既有条目）。
4. **回基线路径**：ray 强杀 → 复检 ok=true → 双机回到 iter2b 之后的干净基线（双机 × 双模型三重门禁在位），即可进入起服阶段。

---

**事实来源**：① 任务下发的迭代 3/3b 最终结果 JSON（双机 "after" 六节全文，本 ask 原文）；② `tasks/t20261001-iter3b/events.jsonl`（6 行，Ts=15:40，执行方所写，原样引用）；③ `scripts/clean.sh`（:17 容器内 pattern 含 `[v]llm serve`、:20 宿主 `[r]aylet|[g]cs_server`、:24-31 窄口径门禁）与 `scripts/preflight.sh`（:14-17 section 判脏逻辑、:22 grep -v grep、:23 pgrep 字符类）——本会话实读核对；④ `tasks/t20261001-iter3/report.md` 与 `run.json`（iter3 前后状态、102210 MiB、PID 对照、`vllm serve` cmdline 证据、探针复现记录）；⑤ `experience/gb10.md`（自匹配/pattern/误报/密钥面相关既有条目）。本会话未重跑远端检测，未引入以上材料之外的事实。
