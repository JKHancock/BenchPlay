# t20261001-iter3c 遗留 TP2 vLLM 栈退役终验（空输出语义 + ray 僵尸分级修复后复检）— 报告

> 生成时间: 2026-10-01 ｜ 报告员: 报告员(agent) ｜ **任务状态: completed（双机终验 ok=true——iter3→3b 两轮修复经本轮全部验证生效：关键清理段 port8000/gpu_procs/vllm_procs/ray_procs/model_lock 双机全 CLEAN(0 项)；容器 vllm-node 按策略保留供部署段复用；ray 僵尸 129×8 项 / 134×2 项为容器未收割的 Z 态尸体，无端口无 GPU 不阻塞部署；129 手工 TP2 vLLM 栈进程级退役完成）**

## 一、概览

- **背景**：129 手工部署遗留的 TP2 vLLM 栈（Qwen3.8-27B-NVFP4，`--tensor-parallel-size 2 --distributed-executor-backend ray`，跨 129 头节点 + 134 worker）自 iter3 起做进程级退役（容器/镜像/模型数据全部保留）。iter3 双机 FAIL（自匹配自杀 + pattern 漏新 CLI），3b 修复后清理 PASS 但复检暴露两级新问题（grep 空输出误标 DIRTY；raylet/ray:: 实为 Z 态尸体被混入"活残留"口径）。
- **迭代 3c**：落盘最终四项修复（方括号防自匹配、`vllm serve` pattern、空输出即 CLEAN、僵尸降级 INFO，落盘位置见 2.3）后重跑「精准清理→终验复检」，目标 = 拿最终洁净证据、闭环整个事故弧线。
- **结果**：双机终验 **ok=true**，迭代门禁（预检 DIRTY → 精准清理 → 复检 CLEAN）**达成**。

| Host | 主机名/角色 | 终验 ok | 关键段（port8000/gpu_procs/vllm_procs/ray_procs/model_lock） | ray 僵尸(INFO) | 容器 | 结论 |
|---|---|---|---|---|---|---|
| 192.168.199.129 | gx10-9f5c，ray 头节点 | ✅ true | 全 CLEAN（各 0 项） | 8 项 | vllm-node Up 22 hours（保留） | 手工 TP2 栈退役完成 |
| 192.168.199.134 | gx10-9c05，ray worker 节点 | ✅ true | 全 CLEAN（各 0 项） | 2 项 | vllm-node Up 22 hours（保留） | 同上 |

## 二、完整事故弧线复盘（iter3 → 3b → 3c）

### 2.1 第一幕：iter3 双机 FAIL——pkill/pgrep -f 自匹配 + pattern 漏 `vllm serve`

- **杀伤侧（pkill）**：clean.sh 旧版 `pkill -f "raylet|gcs_server"` 以 `bash -c '<脚本全文>'` 在远程运行，pattern 文本就在父 shell 自身 cmdline 里；`pkill -f` 只排除自己不排除父 shell → 父 shell 收 SIGTERM，脚本死在该行，ssh 退 255 → 自杀型 FAIL，clean.sh 自带门禁根本未执行（129 探针 `pkill -f ReporterSelfMatchProbe_20261001_xq7` 实测复现，见 iter3 报告第四节）。
- **探测侧（pgrep）**：preflight.sh 旧版 `pgrep -af 'vllm|openai.api_server'` 同根因把远程 shell 自身记成 vllm 进程——iter3 双机 vllm_procs"残留"实为幽灵条目（PID 每次探测都变）。
- **pattern 漏新 CLI**：旧 pattern 面向 python -m 时代入口，打不中遗留栈实际 cmdline `vllm serve /root/.cache/huggingface/Qwen3.8-27B-NVFP4 --tensor-parallel-size 2 …`。

### 2.2 第二幕：3b 清理 PASS，复检又现两级问题

- **修复验证达成**：方括号字符类（clean.sh:17/:19/:21、preflight.sh:22-23）落盘后 clean.sh 双机全程存活（自杀型 FAIL 签名消失），窄口径门禁（GPU+8000）双机 PASS，vllm_procs 幽灵条目清零。
- **新问题一（误报方向）**：preflight.sh 旧 section() 把"退出码非 0"也判 DIRTY，port8000/ray_procs/vllm_procs 三段以 grep 收尾、无匹配 exit 1 → 空输出被错标 **[DIRTY](0 项)**（3b 双机 port8000 即此签名，实质无监听）。
- **新问题二（口径混淆）**：复检 ray_procs 的 9 项（129）/2 项（134）中，raylet/ray:: 实为**容器内 Z 状态僵尸**——强杀/退出后进程已死、只剩待收割尸体，却被混在"活残留"口径里按 DIRTY 阻塞门禁。

### 2.3 第三幕：3c 四项最终修复（本会话实读脚本核对）

| # | 修复 | 落盘位置（本会话实读） |
|---|---|---|
| 1 | 方括号字符类防自匹配（pkill 侧 + pgrep 侧） | `scripts/clean.sh:17` `[v]llm serve|[v]llm.entrypoints|[a]pi_server`；`:19` `[r]aylet|[g]cs_server|[r]ay::`；`:21` `[r]aylet|[g]cs_server`；`scripts/preflight.sh:26` `pgrep -af '[v]llm|[o]penai.api_server'` |
| 2 | pattern 覆盖新 CLI `vllm serve`（置于首位） | `scripts/clean.sh:17` |
| 3 | 空输出即 CLEAN（grep 无匹配退出码非 0 不再判脏，退出码仅区分"命令失败"与"真无输出"） | `scripts/preflight.sh:15-16` `if [ -z "$out" ]; then tag=CLEAN; n=0;`（注释：输出为空即无发现） |
| 4 | ray 僵尸降级 INFO：独立 `ray_zombies` 节按 stat^Z 计数，ray_procs 排除 Z 态 | `scripts/preflight.sh:22-24`（注释：容器未收割尸体, 无端口/GPU 不阻塞部署 → 信息项；计数 `ps -eo stat,comm \| awk '$1 ~ /^Z/ && $2 ~ /^ray/' \| wc -l`）+ `:25` ray_procs 条件加 `$2 !~ /^Z/` |

### 2.4 修复验证对照表（3b 遗留签名 → 3c 终验观察）

| 3b 遗留签名 | 对应修复 | 3c 终验观察 | 判定 |
|---|---|---|---|
| iter3 自杀型 FAIL（父 shell 被杀，ssh 255） | 修复 #1 | 终验复检七节全文回传，无中断无 FAIL | ✅ 验证生效 |
| vllm_procs 幽灵条目（探测自匹配） | 修复 #1 | 双机 vllm_procs CLEAN(0 项) | ✅ 验证生效 |
| port8000 [DIRTY](0 项) 双机（grep 退出码误报） | 修复 #3 | 双机 port8000 **CLEAN(0 项)**——同一检测对象标签由 DIRTY 翻 CLEAN，为空输出语义修复的直接证据 | ✅ 验证生效 |
| ray_procs 9/2 项按"活残留"阻塞门禁 | 修复 #4 | ray_procs 双机 CLEAN(0 项)；ray_zombies INFO 8/2 项单列 | ✅ 验证生效 |
| pattern 漏 `vllm serve`（iter3 根因之二） | 修复 #2 | 目标进程 iter3 阶段已消失，双机本就无 vllm 进程可命中——新 pattern 实战命中**至今未单独验证**（如实记录，部署段首停/首起时补验） | ⚠️ 未单独验证 |

## 三、终态证据（双机逐节转录，覆盖两台机）

**数据源**：任务下发的迭代 3c 终验结果 JSON（双机 `ok=true` + `after` 七节全文，本 ask 原文，格式与 `scripts/preflight.sh` 输出一致）。报告员本会话**未重跑远端检测**，下表按下发原文逐节转录定性；与 3b 复检（`tasks/t20261001-iter3b/report.md` 第三节）的对照用于证明修复生效。

### 192.168.199.129（gx10-9f5c，ray 头节点）— ok=true

| 终验节 | 下发内容 | 计数 | 定性 |
|---|---|---|---|
| containers | vllm-node ｜ vllm/vllm-openai:latest ｜ Up 22 hours | 1（DIRTY 标签） | 🔒 按策略保留供部署段复用（非清理目标） |
| port8000 | （无条目） | 0 | ✅ CLEAN（对照 3b 同节 [DIRTY](0 项)：空输出语义修复生效） |
| gpu_procs | （无条目） | 0 | ✅ CLEAN（iter3 时 677653 占用的 102210 MiB 此前已确认释放） |
| ray_zombies | （INFO 行） | 8 | ℹ️ Z 态无害尸体（口径与构成见第四节：raylet + ray::IDLE×6 + RayWorkerP；gcs_server 同为尸体但 comm 不以 ray 开头未计入该数） |
| ray_procs | （无条目） | 0 | ✅ CLEAN（对照 3b 同节 9 项：活进程口径清零，原 9 项已全部死亡转 Z 尸体） |
| vllm_procs | （无条目） | 0 | ✅ CLEAN（vllm serve 已退役，无自匹配幽灵条目） |
| model_lock | （无条目） | 0 | ✅ CLEAN |

**129 退役清单闭环**：vllm serve（Qwen3.8-27B-NVFP4，TP2+ray，served-model-name=bench，端口 8000）✅（iter3 已消失）；8000 监听 ✅；GPU 102210 MiB ✅；宿主/容器 ray 22 项（iter3 预检）→ 9 项（iter3 后）→ 活进程 0 + Z 尸体 8 项计数（3c 终验）✅；容器/镜像/模型数据 🔒 全程未触碰（Up 22 hours 未变）。

### 192.168.199.134（gx10-9c05，ray worker 节点）— ok=true

| 终验节 | 下发内容 | 计数 | 定性 |
|---|---|---|---|
| containers | vllm-node ｜ vllm/vllm-openai:latest ｜ Up 22 hours | 1（DIRTY 标签） | 🔒 按策略保留供部署段复用 |
| port8000 | （无条目） | 0 | ✅ CLEAN（本就无监听，3b 误报标签已翻正） |
| gpu_procs | （无条目） | 0 | ✅ CLEAN（778340 的 102210 MiB 此前已确认释放） |
| ray_zombies | （INFO 行） | 2 | ℹ️ Z 态无害尸体（与 3b ray_procs 的 raylet 777676 + RayWorkerP 778340 PID 一一对应） |
| ray_procs | （无条目） | 0 | ✅ CLEAN（对照 3b 同节 2 项） |
| vllm_procs | （无条目） | 0 | ✅ CLEAN（本就无真实 vllm 进程） |
| model_lock | （无条目） | 0 | ✅ CLEAN |

**汇总**：双机 7 节 ×2 = 14 节——10 节 CLEAN（全部关键清理段）、2 节按策略保留（containers）、2 节 INFO（僵尸计数，非门禁项）。**双机 ok=true，终验放行。**

## 四、僵尸知识点（ray Z 态尸体：识别、机制、运维口径）

1. **是什么**：Z（zombie）= 进程已终止、仅剩退出状态待父进程 `wait()` 收割的尸体；`ps` stat 列以 Z 开头——`ray_zombies` 节即按此过滤（preflight.sh:23 `$1 ~ /^Z/`）。
2. **为什么"不可杀"**：kill 对 Z 进程无效果（没有执行流可接收信号）——preflight.sh:22 注释固化"不可杀"; 唯一根治 = 父进程收割，或父进程消失。容器场景下即**重启容器**（PID namespace 整体销毁，尸体随之消失）。
3. **为什么是容器未收割尸体**：ray 进程树随 vllm serve 在容器内启动（`--distributed-executor-backend ray`），父进程亡后被容器 init 收养；容器 init（`sleep infinity`）不 `wait()` → 尸体永存。口径张力如实记录：iter3 报告曾记"`docker top vllm-node` 仅剩 sleep infinity"并把 ray 进程称"宿主级"，3c 弧线将其定性为容器内 Z 尸体（preflight.sh:22 注释固化）——两种记录的张力本会话未重跑远端检测复核，按弧线口径记录。
4. **为什么无害（不阻塞部署）**：不占端口（终验 port8000 双机 CLEAN）、不占 GPU（gpu_procs 双机 CLEAN）、不占 CPU（已停止调度）；仅占一个 PID/进程表条目。**可带尸部署。**
5. **计数口径（8 与 9 差一的解释）**：`ray_zombies` 按 stat^Z ∧ **comm 以 ray 开头**计数（preflight.sh:23 `$2 ~ /^ray/`）——129 的 8 = raylet 673632 + ray::IDLE×6 + RayWorkerP 677653；gcs_server 673447 同为尸体但 comm `gcs_server` 不以 ray 开头**未计入**，故 INFO 数 8 比上轮 ray_procs 的 9 项少一（此为脚本口径推断，本会话未单独实测）。134 的 2 = raylet 777676 + RayWorkerP 778340，与 3b 记录 PID 一一对应。
6. **沉淀为规则**：① 复检判"活残留"必须按进程状态列排除 Z 态，否则尸体永远阻塞门禁；② 探测器对"无法清理但无害"的对象单列 INFO 档，不与 DIRTY 混算；③ 根治时机挂在部署段的容器重启上，不单独停机清尸。

## 五、遗留与建议

1. **部署段容器重启 = 僵尸根治时机**：部署段复用 vllm-node 时若重启/重建容器，129×8 + 134×2 尸体自动消失；不重启亦可带尸起服（无端口/GPU 冲突，见第四节）。
2. **`[v]llm serve` 新 pattern 实战命中未验证**（目标 iter3 已消失）：部署段首次起服/停服时观察一次命中与防自匹配表现（弧线内如实标注，见 2.4 末行）。
3. **134 密钥面不对称 + KEYFLAG 未加引号未处理**：134 仅认 nvsync.key（路径含空格），preflight.sh:9 / clean.sh:9 的 `KEYFLAG="-i $KEY"` 展开未加引号——批量脚本改造时一并处理（gb10.md 既有条目）。
4. **下一步**：双机已回到 iter2b 之后的干净基线（双机 × 双模型三重门禁在位 + 本轮关键段全 CLEAN + 容器/模型保留），可进入部署段（底座→组网→起服）。

---

**事实来源**：① 任务下发的迭代 3c 终验结果 JSON（双机 `ok=true` 与 `after` 七节全文，本 ask 原文——本报告第三节逐节转录，未重跑远端检测）；② `tasks/t20261001-iter3/report.md`、`tasks/t20261001-iter3b/report.md`、两轮 `events.jsonl`/`run.json`（事故弧线第一二幕、PID/显存对照、误报签名）；③ `scripts/preflight.sh`（:15-16 空输出即 CLEAN、:22-24 僵尸 INFO 节、:25 ray_procs 排除 Z、:26 pgrep 字符类）与 `scripts/clean.sh`（:17 `[v]llm serve` pattern、:19 容器内 `[r]ay::`、:21 宿主 `[r]aylet|[g]cs_server`、:26-30 窄口径门禁）——本会话实读核对；④ 2.3/2.4 修复对照与第四节第 5 点中"8 与 9 差一"的解释为基于脚本口径的推断（已标注），非独立实测。**时钟口径备注**：3b 档案事件 Ts=15:40 晚于本会话 `date` 实测（15:04）——时间源不一致，本任务档案事件按本会话 date 实测时间记录。本报告未引入以上材料之外的事实。
