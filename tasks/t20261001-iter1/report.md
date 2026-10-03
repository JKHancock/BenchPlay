# t20261001-iter1 双机引导探测建档 — 报告

> 生成时间: 2026-10-01 ｜ 报告人: 报告员(agent) ｜ **任务状态: completed（双机探测建档全部成功）**
> 本报告取代同任务上一迭代（12:16，探测失败版）的 report.md；events.jsonl 为 append-only，未改动。

## 一、概览

| Host | 主机名 | 声明机型 | 状态 | probe 门禁 | 建档产物 | 识别结果 |
|---|---|---|---|---|---|---|
| 192.168.199.129 | gx10-9f5c | GB10 | ✅ completed | 14/14 节 [OK]，无 ABSENT | `profiles/192_168_199_129.json` + `machines/192.168.199.129.json` | 新机器首次建档，RecognizedAs="" |
| 192.168.199.134 | gx10-9c05 | GB10 | ✅ completed | 14 节全 [OK]，无 ABSENT | `profiles/192_168_199_134.json` + `machines/192.168.199.134.json` | 新机器首次建档，RecognizedAs="" |

- 双机 **2/2 完成**，声明机型 GB10 与探测一致（nvidia-smi 报 `NVIDIA GB10, 580.178.04`），配置完全同级：Ubuntu 24.04.5 aarch64 / 内核 7.0.0-1019-nvidia / 20 核 / 121Gi 内存 / NVMe 931.5G（根分区均 49% 已用）/ Docker 29.6.2。
- `machines/` 库在建档前为空（0 个已有档案），两台均无比对对象，故均为新机器首次建档。
- 本任务未进入模型阶段（task.json `Models=[]`）；两台机器上已预置的 vLLM 镜像与 NVFP4 模型/数据集缓存见各机器小节。
- 本会话实测校验（node JSON.parse）：`events.jsonl` 10/10 行合法（129 5 条 + 134 5 条）；两份 profiles 与两份 machines 档案均可解析且 Host 字段正确。

## 二、每台机器

### 192.168.199.129（gx10-9f5c）

- **状态**：completed。probe 14/14 节 [OK]，无 absent 项（events.jsonl 第 1 行 gate/probe）。
- **档案摘要**（`tasks/t20261001-iter1/profiles/192_168_199_129.json`）：
  - 系统：Ubuntu 24.04.5 LTS，aarch64，内核 7.0.0-1019-nvidia，20 逻辑核，121Gi 内存；GPU 节 `NVIDIA GB10, 580.178.04`（nvidia-smi），显存总量 [N/A]（GB10 统一内存，档案未填容量）。
  - 磁盘：`/dev/nvme0n1` 931.5G，序列号 511250619080002301；根分区 `/dev/nvme0n1p2` 916G 已用 423G（49%），余 447G。
  - 容器镜像 5 个：`vllm/vllm-openai:latest` 22.1GB（含 daocloud 同尺寸别名）、`nvcr.m.daocloud.io/nvidia/vllm:26.08-py3` 25.5GB，另有 prometheus 250MB / grafana 1.31GB。
  - 模型缓存（HF 目录 10 项）：顶层 Nemotron-3-Super-120B-NVFP4、Qwen3.5-122B-A10B-NVFP4、Qwen3.8-Flash-Next-NVFP4、Qwen3.6-35B-A3B-NVFP4-Fast、qwen3.8-nvfp4；hub 缓存含 nvidia/RadixArk 双份 Qwen3.8-Flash-Next-NVFP4、Qwen3-0.6B 等；评测数据集 gsm8k / mmlu-pro / gpqa / IFEval / cmmlu 均在位。
  - 网络：管理口 WiFi `wlP9s9`=192.168.199.129/24（DHCP 动态，租约剩约 75994s）；数据面候选 `enp1s0f1np1`=192.168.100.10、`enP2p1s0f1np1`=192.168.101.10 两个 UP 以太口；`enP7s7`/`enp1s0f0np0`/`enP2p1s0f0np0` 三口 NO-CARRIER DOWN；docker0 172.17.0.1 DOWN。
- **新发现**：
  1. 机器未自报机型：identity-model 节（`cat /proc/device-tree/model`）返回 n/a，DeclaredModel=GB10 仅由任务声明给出，由 gpu 节 nvidia-smi 输出佐证一致（events 第 2 行）。
  2. nvidia-smi 读不到 memory.total（报 [N/A]），档案未填显存容量。
  3. 管理 IP 来自 WiFi DHCP 动态租约（剩约 75994s），存在漂移风险；档案已记录稳定指纹：主机名 gx10-9f5c / MAC 族 30:c5:99:3d:9f:5c..62（另 wifi 50:bb:b5:a2:00:48）/ NVMe 序列号 511250619080002301。
  4. events.jsonl 为任务级共享文件：本机 5 条与并行建档 agent 写入的 134 事件共存，10 行均通过格式校验。

### 192.168.199.134（gx10-9c05）

- **状态**：completed。probe.sh 14 节全部 [OK]，无 ABSENT（events.jsonl 第 6 行 info/probe）。
- **档案摘要**（`tasks/t20261001-iter1/profiles/192_168_199_134.json`）：
  - 系统：与 129 同级——Ubuntu 24.04.5、aarch64、内核 Linux 7.0.0-1019-nvidia、20 核、121Gi；GPU `NVIDIA GB10, 580.178.04`，memory.total=[N/A]；`/proc/device-tree/model` 返回 n/a。
  - 磁盘：`/dev/nvme0n1` 931.5G，序列号 511250619080002242；根分区 916G 已用 420G（49%），余 450G。
  - 容器镜像 3 个：`vllm/vllm-openai:latest` 22.1GB（含 daocloud 别名）、`nvcr.m.daocloud.io/nvidia/vllm:26.08-py3` 25.5GB。
  - 模型缓存：顶层 3 个（Nemotron-3-Super-120B-NVFP4 / Qwen3.8-Flash-Next-NVFP4 / Qwen3.5-122B-A10B-NVFP4）+ HF hub 缓存 2 个（nvidia--Qwen3.5-122B-A10B-NVFP4、nvidia--Nemotron-3-Super-120B-A12B-NVFP4），均 NVFP4。
  - 网络：管理口 WiFi `wlP9s9`=192.168.199.134/24（DHCP dynamic，租期 74445s）；`enp1s0f1np1`=192.168.100.11/24、`enP2p1s0f1np1`=192.168.101.11/24 两个有线口 UP，分属 100/101 两个独立网段，与管理 WiFi 199 网段互不重叠；`enP7s7` UP 但无地址；`enp1s0f0np0`/`enP2p1s0f0np0` DOWN；docker0 DOWN。
- **新发现**：
  1. `machines/` 库建档前为空（0 个已有档案），MAC 集合/主机名/机型均无比对对象 → 判定新机器，RecognizedAs=""（events 第 9 行）。
  2. 管理 IP 为 WiFi DHCP 动态租期（74445s），IP 会漂移；跨任务识别应依赖 MAC 族（30:c5:99:3d:9c:05..0b）与主机名 gx10-9c05 / NVMe 序列号 511250619080002242，而非 IP。
  3. 两个有线口分属 100/101 独立网段（.100.11 / .101.11），与 129 的 .100.10 / .101.10 同构，数据面网段规划可直接对齐。

## 三、异常与建议

**异常（均为档案事实，无门禁失败）**

1. **机型自报不可得（双机一致）**：`/proc/device-tree/model` 在两台 GB10 上均返回 n/a，且 nvidia-smi memory.total 报 [N/A]。机型认定只能靠「任务声明 GB10 + nvidia-smi GPU 名一致」交叉佐证（两机均一致，门禁放行）；档案不含显存容量字段值。
2. **管理 IP 漂移风险（双机一致）**：两台管理 IP 均来自 WiFi wlP9s9 的 DHCP 动态租约（129 剩约 75994s，134 租期 74445s），租约更替后 IP 可能变化。
3. **enP7s7 状态两机不一致**：129 上为 DOWN（NO-CARRIER），134 上为 UP 但无地址——布线/组网时需逐台确认，不能按一台推断另一台。
4. **两机缓存不对齐**：129 比 134 多 Qwen3.6-35B-A3B-NVFP4-Fast、Qwen3-0.6B、qwen3.8-nvfp4 等模型目录与 RadixArk 双份缓存，且多 prometheus/grafana 镜像；两机根分区均已用 49%（余 447G/450G）。
5. **历史档案被取代**：同目录上一迭代（12:16）的 task.json/run.json/report.md 记录的是探测失败（`probe.sh: No such file or directory`，详见 experience/gb10.md 首条）；本次迭代双机成功，按任务指示以本版覆盖 task.json/run.json/report.md。events.jsonl append-only 未动。
6. **时间字段口径**：流程未单独落盘任务起止时间，run.json `StartedAt` 如实留空；`EndedAt`=events.jsonl 末条事件时间（12:26:53）；档案侧最早写入证据为 machines/129.json 的 UpdatedAt（12:24:16）。run.json token 字段按任务指示填 0（本次未采集 token 计量）。

**建议**

1. **机器识别弃用 IP**：后续任务按档案已录指纹（hostname / MAC 族 / NVMe 序列号）识别机器；如需稳定管理入口，可做 DHCP 预约或将管理面迁到有线口。
2. **数据面选口**：集群阶段（ray/NCCL）可钉每台两个 UP 有线口所在的 192.168.100.0/24 或 192.168.101.0/24 网段，管理面与数据面天然隔离；选口前先核实 enP7s7 的实际接线。
3. **评测前对齐缓存**：两机模型/数据集缓存存在差异（见异常 4），进入模型分发/评测阶段前先按 models 根目录做一次对齐盘点。
4. **probe 门禁基线**：GB10 上 identity-model=n/a、memory.total=[N/A] 属机型常态，后续机型一致性门禁继续以「声明 + nvidia-smi GPU 名」判定即可，勿因这两项判 FAIL。

---
**事实来源**：① 两份机器档案 `tasks/t20261001-iter1/profiles/192_168_199_{129,134}.json`（逐字段引用，Evidence 节含各命令与输出摘录）；② `machines/192.168.199.{129,134}.json`（RecognizedAs、指纹、UpdatedAt）；③ `tasks/t20261001-iter1/events.jsonl`（10 行，本会话以 node JSON.parse 逐行校验通过）；④ 任务下发的双机机器摘要（newFindings，与档案一致）。本报告未引入档案之外的事实。
