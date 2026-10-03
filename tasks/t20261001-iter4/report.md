# t20261001-iter4 部署段全链贯通（substrate → cluster → serve → verify 四门禁）— 报告

> 生成时间: 2026-10-01 ｜ 报告员: 报告员(agent) ｜ **任务状态: completed（首次全脚本化部署成功——底座校验双机 PASS（6-flag + ray 2.44.0 + 模型容器内可见）→ ray 双机集群就绪（Active=2, GPU 2.0/2.0）→ vllm serve TP2 起服（钉定 enp1s0f1np1, max-model-len 40960 < 模型上限 262144）→ URL 三关全过（bench 身份 / 对话冒烟 / 375 个 vllm: 指标）。服务地址 http://192.168.199.129:8000）**

## 一、概览

- **背景**：iter3c 终验后双机回到干净基线（关键清理段全 CLEAN、容器 vllm-node 按策略保留、ray 僵尸已降级 INFO 不阻塞），进入部署段。本轮 = **首次全脚本化部署**：底座（substrate.sh）→ 组网（cluster.sh）→ 起服（serve.sh）→ 验证（verify.sh）四段脚本串行贯通，全程无手工干预。
- **模型**：Qwen3.6-35B-A3B-NVFP4-Fast（iter2 分发对账确认 129 实测 20G 量级真权重），TP2 跨 129（head）+ 134（worker）双 GB10。
- **结果**：四门禁全 PASS，服务在 head 8000 端口就绪。
- **证据口径**：四门禁判定行取自任务下发结果（本 ask 原文），**报告员本会话未重跑远端部署/检测**；下文所有"脚本对照"均为本会话实读 `scripts/*.sh` 逐一核对——四条下发判定与脚本内 PASS 模板逐字吻合（substrate.sh:39、cluster.sh:23、verify.sh:35），构成"门禁由脚本产生"的一致性佐证。

| 角色 | 主机 | 主机名 | QSFP 数据面 | 管理面 | 底座门禁 |
|---|---|---|---|---|---|
| ray 头节点 / vLLM head | 192.168.199.129 | gx10-9f5c | enp1s0f1np1 = 192.168.100.10 | WiFi 199 段 | ✅ PASS |
| ray worker | 192.168.199.134 | gx10-9c05 | enp1s0f1np1 = 192.168.100.11 | WiFi 199 段 | ✅ PASS |

（网卡-IP 对应实读 `machines/192.168.199.129.json` / `machines/192.168.199.134.json` Nics 节核对；主机名同源。）

## 二、部署链路图

```
[底座] substrate.sh <host> syspetro <model>            （双机各跑一次, 只读校验）
   │  容器 vllm-node 运行中 (substrate.sh:16-19)
   │  6-flag: IpcMode=host / NetworkMode=host / GPU Count=-1 / /dev/infiniband
   │           / IPC_LOCK / memlock=-1                      (substrate.sh:23-28)
   │  ray==2.44.0 (容器内 python3 导入核对)                 (substrate.sh:30-31)
   │  模型容器内可见 /root/.cache/huggingface/$MODEL        (substrate.sh:33-37)
   ▼
[组网] cluster.sh <head> <worker> syspetro
   │  幂等先行: 已 2节点/2GPU 直接 PASS                     (cluster.sh:29)
   │  QSFP 自动探测: 宿主 `ip -4 addr` 提取 192.168.100.x   (cluster.sh:14-15)
   │  → head 192.168.100.10 ↔ worker 192.168.100.11
   │  容器内 ray start: head --port=6379 / worker --address (cluster.sh:35-37)
   │  门禁: ray status Active≥2 node_ 行 ∧ x/2.0 GPU        (cluster.sh:17-26)
   ▼  PASS ray 双机集群就绪 (Active=2, GPU 2.0/2.0 GPU)
[起服] serve.sh <head> syspetro $MODEL [key] [40960]     （仅 head 发起, worker 经 ray 调度）
   │  awk 状态机探测 QSFP 网卡 → enp1s0f1np1                (serve.sh:15-18)
   │  幂等清旧 serve: pkill -f '[v]llm serve'               (serve.sh:21)
   │  GLOO/NCCL_SOCKET_IFNAME 钉定该网卡                    (serve.sh:25)
   │  vllm serve TP2 + ray backend + served-model-name=bench
   │    --port 8000 --gpu-memory-utilization 0.85
   │    --max-model-len 40960 (默认值, serve.sh:10; < 模型上限 262144)
   │    --max-num-seqs 64 + chunked-prefill + prefix-caching (serve.sh:23-31)
   │  就绪门禁: 日志 "Application startup complete" ∧ 8000 监听, ≤900s 轮询
   │    + 启动即崩检测                                       (serve.sh:34-45)
   ▼
[验证] verify.sh <head>   （从操作机直连, 与部署侧零耦合）
   │  关1 身份: /v1/models 含 bench                          (verify.sh:9-15)
   │  关2 功能: 对话冒烟, 良构补全即过 (纯 ASCII 提示词)      (verify.sh:17-25)
   │  关3 可观测: /metrics vllm: 指标 ≥10                    (verify.sh:27-33)
   ▼  PASS URL 三关全过: http://192.168.199.129:8000
```

**链路结论**：substrate（双机）→ cluster → serve → verify 依序贯通，四段 PASS；serve 段无独立下发判定行，其成功由后继 verify PASS（服务实际可达）与链路背景（钉定 enp1s0f1np1、max-len 40960）共同佐证。

## 三、四门禁证据（下发判定逐字转录 + 脚本模板对照）

| # | 门禁 script | 下发 verdict（原文转录） | 脚本 PASS 模板（本会话实读） | 对照 |
|---|---|---|---|---|
| 1 | substrate-head | `PASS 底座校验通过 syspetro@192.168.199.129 (容器 vllm-node)` | `PASS 底座校验通过 $USER_@$HOST (容器 $C)`（substrate.sh:39，仅 `$code=0` 时输出，substrate.sh:12,39） | ✅ 逐字吻合（user=syspetro, C=vllm-node） |
| 2 | substrate-worker | `PASS 底座校验通过 syspetro@192.168.199.134 (容器 vllm-node)` | 同上 | ✅ 逐字吻合 |
| 3 | cluster | `PASS ray 双机集群就绪 (Active=2, GPU 2.0/2.0 GPU)` | `PASS ray 双机集群就绪 (Active=$nodes, GPU $gpus)`（cluster.sh:23，判据 `nodes≥2 ∧ gpus 非空`，cluster.sh:20-22） | ✅ 吻合（nodes=2；`2.0/2.0 GPU` = 已用/总量，集群期尚无计算占用，正常） |
| 4 | verify | `PASS URL 三关全过: http://192.168.199.129:8000` | `PASS URL 三关全过: $BASE`（verify.sh:35，三关任一失败即 code=1） | ✅ 逐字吻合 |

**verify 三关明细**（依据下发背景，阈值对照 verify.sh 实读）：

| 关 | 内容 | 本轮观察 | 脚本门限 |
|---|---|---|---|
| 关1 身份 | `curl /v1/models` 含 `"bench"` | ✅ 通过 | 含 bench 即过（verify.sh:11） |
| 关2 功能 | `/v1/chat/completions` 对话冒烟 | ✅ 良构补全（含 `chatcmpl-` 与 `finish_reason`，verify.sh:21 判据） | 良构补全即过，**不判答案正确性**（verify.sh:17 注释） |
| 关3 可观测 | `/metrics` 的 `vllm:` 指标族 | ✅ **375 个** `vllm:` 指标 | ≥10 即过（verify.sh:28-29），实测远超门限 |

## 四、五坑复盘（本轮实测踩坑，经验已沉淀至 `experience/gb10.md`）

| # | 坑 | 现象/真因 | 修复落盘（本会话实读核对） |
|---|---|---|---|
| ① | 网卡探测 grep -B 上下文跨块误抓 lo | `ip -4 addr` 输出按接口分块，`grep -B4` 的上下文窗口跨过前一块边界，持有 192.168.100.x 的接口被误配成上一块（lo）→ `GLOO_SOCKET_IFNAME=lo` 引擎初始化失败 | awk 状态机：`/^[0-9]+: /` 记当前接口名，`/inet 192\.168\.100\./` 才输出该接口（serve.sh:15-16，注释自认"实测翻车"）；另有 `=lo` 兜底拦截（serve.sh:17） |
| ② | 探测正则 `^inet` 漏前导空格 | `ip -4 addr` 的地址行有前导缩进（如 `    inet 192.168.100.10/24 …`），`^inet` 锚定行首永远打不中 → 探测恒空 | 去掉 `^` 锚、按 `inet 192\.168\.100\.` 匹配（serve.sh:16 与 cluster.sh:15 两处一致） |
| ③ | 容器内无 `ip` 也无 `python`（只有 `python3`） | 网络探测在容器内执行直接命令不存在；ray 版本核对用 `python` 也会失败 | 网络探测改走**宿主**执行 `ip -4 addr`——容器 `--network host`，宿主视图=容器视图（cluster.sh:14、serve.sh:18 注释明示）；ray 版本核对用 `python3`（substrate.sh:30） |
| ④ | Git Bash curl 发中文 body 变 GBK | 从操作机（Windows Git Bash）curl 提交含中文的 JSON body，编码退化为 GBK，服务端按 UTF-8 解析失败 → 冒烟假失败 | 冒烟提示词**纯 ASCII**：`"What is 1+1? Answer with the number only."`（verify.sh:20） |
| ⑤ | 推理型模型冒烟 300 token 全耗思考 | Qwen3.6 推理型：小 max_tokens（300）全被思考耗尽，正文无输出——若门禁判"答案正确"必然误 FAIL | 门禁语义定为**良构补全**（响应含 `chatcmpl-` + `finish_reason` 即过，答案仅作信息展示，verify.sh:17 注释 + :21），并将 max_tokens 提至 2000（verify.sh:20）留足思考余量 |

**复盘共性**：五个坑全是"跨环境边界"坑——宿主↔容器（③）、块状文本的上下文匹配（①②）、Windows↔Linux 编码（④）、推理模型与传统门禁语义（⑤）。脚本侧的防御（awk 状态机、去锚匹配、ASCII 提示词、良构门禁）已全部落进 `scripts/*.sh`，后续部署直接继承。

## 五、服务信息

| 项 | 值 |
|---|---|
| 服务地址 | **http://192.168.199.129:8000**（head = gx10-9f5c） |
| served-model-name | `bench`（serve.sh:28；/v1/models 与请求体均用此名） |
| 模型 | Qwen3.6-35B-A3B-NVFP4-Fast（`/root/.cache/huggingface/` 容器内挂载可见） |
| 并行 | TP2（`--tensor-parallel-size 2`）+ `--distributed-executor-backend ray`（129 head + 134 worker） |
| 通信面 | GLOO/NCCL_SOCKET_IFNAME 钉定 enp1s0f1np1（QSFP 192.168.100.0/24：.10↔.11） |
| 上下文 | max-model-len 40960（serve.sh:10 默认值；低于模型上限 262144，本轮按保守值起服） |
| 关键参数 | gpu-memory-utilization 0.85 / max-num-seqs 64 / chunked-prefill / prefix-caching（serve.sh:29-30） |
| 验证口径 | URL 三关（身份/功能/可观测），375 个 vllm: 指标可供监控采集（/metrics） |

## 六、备注与遗留

- **容器复用，未重启**：本轮 substrate 校验的 vllm-node 即 iter3c 按策略保留的容器（下发判定仅核"Running:true + 6-flag + ray 2.44.0 + 模型可见"，无重启动作）。3c 曾记录 ray Z 态尸体"根治=重启容器（部署段复用时顺带完成）"——本轮部署**未含容器重启步骤**，按 3c 口径推断尸体仍在容器内（无端口/GPU 占用、不阻塞服务，本判定为口径推断，本轮未做进程级复检）。
- **空输出/自匹配等前代修复实战复用**：serve.sh:21 幂等清旧 serve 用的即 3b/3c 落盘的 `[v]llm serve` 字符类 pattern（clean.sh:17 同款），本轮起服前实际执行——iter3c 遗留"新 pattern 实战命中未单独验证"在本轮部署链路中被顺带使用，但**停旧进程是否真有目标可杀本轮无日志可查**，仍不做已验证声明。
- **冒烟答案语义**：关2 判良构补全不判正确性（坑⑤），故本轮 PASS 不构成模型推理质量结论；性能/质量评测归后续基准任务（模型已登记 Models=["Qwen3.6-35B-A3B-NVFP4-Fast"]）。
