# serve-vllm 经验条目(自动拆分自gb10.md)

## GX10 双机数据面候选: 每台两个 UP 以太口分属 192.168.100.0/24 与 192.168.101.0/24
- 阶段: cluster | 现象: 129=enp1s0f1np1 .100.10 + enP2p1s0f1np1 .101.10, 134=同两口 .100.11/.101.11; 100/101 两网段互不重叠且与管理 WiFi 199 网段隔离; 其余口 NO-CARRIER(仅 134 的 enP7s7 UP 无地址, 129 上同口为 DOWN——两口状态逐台确认, 不能互推)
- 结论/修复: 组 ray/NCCL 集群数据面可钉 100 或 101 网段有线口, 管理面走 199 WiFi; GLOO/NCCL_SOCKET_IFNAME 选口用这两口
- 来源: t20261001-iter1 | 命中: 2 (双机)

## 远程 pkill -f 的 pattern 文本会匹配调用它的 shell 自身 → "自杀型 FAIL"; 用 pkill -x 或 [r] 字符类防自匹配
- 阶段: 清理 | 现象: 双机 cleanLog 同签名——"容器 ray 已停"回显后直接 `FAIL 清理命令执行失败`, "宿主 ray 残留已停"回显缺失;
  clean.sh:20 `pkill -f "raylet|gcs_server"` 的 pattern 文本就在 ssh 远程脚本自身 cmdline 里(bash -c 全文), pkill -f 只排除自己不排除父 shell
  → 父 shell 被 SIGTERM, sleep 4 未跑, ssh 退出 255 → clean.sh:22 FAIL, 自身门禁(:24-31)根本没执行; 连带效果: 宿主 ray 进程同收 SIGTERM,
  GPU 计算占用清零但部分进程(gcs_server/raylet/ray::IDLE/RayWorkerProc)以原 PID 卡在优雅退出
- 实测复现: 报告员在 129 跑探针 `ssh … 'pkill -f ReporterSelfMatchProbe_20261001_xq7; echo SURVIVED'` → 脚本死在该行无 SURVIVED, ssh RC=255, 与 clean.sh 失败签名一致
- 结论/修复: 远程 pkill -f 的 pattern 一律 `pkill -x`(精确 comm)或字符类 trick(`pkill -f "[r]aylet|[g]cs_server"`)防自匹配;
  排障先看"哪条回显缺失"定位脚本死点; FAIL 后勿假定清理未生效, 必须只读复检拿真实前后状态
- 来源: t20261001-iter3 | 命中: 3 (129/134 双机同签名失败 + 129 探针复现)

## 预检判脏混用"输出为空"与"退出码 0": grep 收尾的段无匹配时被误判 DIRTY(0 项)
- 阶段: 预检 | 现象: 134 清理前 port8000 [DIRTY](0 项)、129 复检 port8000 [DIRTY](0 项), 直连 ss 实测均无监听(误报);
  preflight.sh:14-17 section() 把退出码非 0 也判 DIRTY, 而 :20-23 的 port8000/ray_procs/vllm_procs 三段以 grep 收尾, 无匹配 exit 1 → 空输出误判 DIRTY;
  model_lock 段管道收尾是 head(exit 0)故不受影响
- 结论/修复: 判脏只看输出非空(退出码仅用于区分"命令失败"与"真无输出"), 或段尾加 `|| true`;
  读预检结果时 [DIRTY](0 项)应先怀疑误报再下结论
- 来源: t20261001-iter3 | 命中: 2 (134 清理前 port8000 + 129 复检 port8000)

## pgrep -f 预检同样自匹配: 探测把远程 shell 自身记成"真实进程"(幽灵 DIRTY), 方括号 trick 对 pgrep 同样适用
- 阶段: 预检 | 现象: iter3 双机 vllm_procs 残留条目(129 PID 1792765 / 134 PID 1001927)每次探测 PID 都变, 实为 preflight.sh 旧版
  `pgrep -af 'vllm|openai.api_server'` 命中 ssh 远程 shell 自身 cmdline——与 pkill 自匹配同根, 表现不同
- 结论/修复: pkill -f 自匹配 = 自杀型 FAIL(见上条), pgrep -f 自匹配 = 幽灵进程型误报——探测/清理两侧都要防;
  修复 = `pgrep -af '[v]llm|[o]penai.api_server'`(preflight.sh:23) + ps|grep 段尾 `grep -v grep`(preflight.sh:22);
  iter3b 复检 vllm_procs 双机 CLEAN(0 项)验证生效, 读预检时"残留 PID 每次都变"是识别幽灵条目的指纹
- 来源: t20261001-iter3 → t20261001-iter3b | 命中: 3 (iter3 双机幽灵条目 + iter3b 修复验证)

## 清理/探测 pattern 必须随目标 CLI 演进更新: vLLM 启动已从 python -m 入口变为 `vllm serve`
- 阶段: 清理 | 现象: 旧 pattern 面向 python -m 时代入口(`vllm.entrypoints|openai.api_server`), 129 手工遗留栈实际 cmdline 为
  `vllm serve <模型路径> --tensor-parallel-size 2 --distributed-executor-backend ray …`, 旧 pattern 打不中新 CLI
- 结论/修复: 定 pattern 前先 pgrep/ps 抽样目标真实 cmdline, pattern 按"实测 cmdline"维护而非按历史记忆;
  clean.sh:17 现为 `pkill -f "[v]llm serve|[v]llm.entrypoints|[a]pi_server"`(新 CLI 置首 + 字符类防自匹配);
  注: 3b 复检时目标已消失, 新 pattern 实战命中未单独验证
- 来源: t20261001-iter3b | 命中: 1 (129 TP2 vllm serve 栈)

## pkill/pgrep -f 自匹配陷阱弧线闭环: 同一根因两侧表现, 方括号字符类两侧通用(修复终验生效)
- 阶段: 清理+预检 | 弧线: iter3 杀伤侧(pkill -f 命中父 shell cmdline→ssh 255 自杀型 FAIL, 129 探针复现)与探测侧
  (pgrep -f 把远程 shell 记成 vllm 进程→幽灵 DIRTY 条目)同根不同表; 3b 落盘方括号修复(clean.sh:17/19/21 + preflight.sh:26),
  3c 终验双机 ok=true 全链 PASS——复检七节全文回传无中断、vllm_procs 双机 CLEAN(0 项), 自杀/幽灵签名双双消失
- 结论/修复: 同一 pattern 同时进 pkill 与 pgrep 时, 两侧都必须防自匹配(字符类 `[r]aylet` 使 pattern 文本不再字面匹配自身
  cmdline); 修复必须经"复检签名消失"验证而非只看单次退出码; 细节见上方两条专项条目
- 来源: t20261001-iter3 → t20261001-iter3b → t20261001-iter3c | 命中: 3 (iter3 双机 FAIL + 3b 修复验证 + 3c 终验闭环)

## ray 僵尸 = 容器未收割的 Z 态尸体: kill 无效『不可杀』, 无端口/GPU 不阻塞部署, 根治 = 重启容器
- 阶段: 清理/预检 | 现象: 3b 复检 raylet/ray:: 按活残留口径阻塞门禁(129 九项/134 两项), 实则进程已死仅剩退出状态待收割
  (ps stat 列 Z 开头); 3c 终验 ray_zombies INFO 129×8/134×2 项, ray_procs(排除 Z)双机 CLEAN(0 项)
- 机制: 尸体随 vllm serve 的 ray 进程树生于容器内, 父进程亡后被容器 init(sleep infinity)收养, init 不 wait() → 尸体永存;
  kill 对 Z 无效果; 唯一根治 = 重启容器(PID namespace 整体销毁)
- 口径: ① preflight.sh:23 按 stat^Z ∧ comm^ray 计数——gcs_server 同为尸体但 comm 不以 ray 开头未计入(129 的 8 较上轮
  ray_procs 9 项差一即此); ② 判"活残留"必须排除 Z 态, 无害对象单列 INFO 不与 DIRTY 混算; ③ 可带尸部署, 根治时机挂部署段
  容器重启, 不单独停机清尸
- 来源: t20261001-iter3b → t20261001-iter3c | 命中: 2 (双机: 129×8/134×2)

## 部署段五坑之一: 网卡探测 grep -B 上下文跨块误抓 lo → GLOO_SOCKET_IFNAME=lo 引擎初始化失败, awk 状态机按块配对
- 阶段: 部署(serve) | 现象: `ip -4 addr` 输出按接口分块, grep -B4 的上下文窗口会跨过前一块边界,
  持有 192.168.100.x 的接口被误配成上一块(常为 lo)→ GLOO/NCCL 钉到 lo, vLLM 分布式引擎初始化失败
- 结论/修复: 块状文本的"地址→接口"归属必须用 awk 状态机——`/^[0-9]+: /` 记当前接口名, `/inet 192\.168\.100\./`
  才输出该接口(serve.sh:15-16, 注释自认"grep -B 上下文会跨块误抓 lo, 实测翻车"); 另加 `=lo` 兜底拦截(serve.sh:17)
- 来源: t20261001-iter4 | 命中: 1 (129 首次起服)

## 部署段五坑之二: 探测正则 ^inet 漏前导空格 → 匹配恒空; ip 输出缩进行不能锚行首
- 阶段: 部署(组网/起服) | 现象: `ip -4 addr` 的地址行有前导缩进(`    inet 192.168.100.10/24 …`),
  `^inet` 锚定行首永远打不中 → QSFP 地址探测恒返回空
- 结论/修复: 按 `inet 192\.168\.100\.` 匹配去掉 `^` 锚(serve.sh:16 与 cluster.sh:15 两处一致);
  对带缩进的命令输出写正则先看原始字节, 勿默认顶格
- 来源: t20261001-iter4 | 命中: 1 (探测函数两处)

## 部署段五坑之三: 容器内无 ip 命令也无 python(只有 python3) → 网络探测走宿主(--network host 视图等价)
- 阶段: 部署(全段) | 现象: vllm-node 容器内既无 `ip` 也无 `python`, 容器内网络探测/版本核对直接命令不存在
- 结论/修复: ① 网络探测在宿主执行 `ip -4 addr`——容器 `--network host`, 宿主视图=容器视图
  (cluster.sh:14、serve.sh:18 注释明示); ② 容器内脚本一律用 `python3`(substrate.sh:30);
  ③ 依赖容器外工具时先确认宿主有, 依赖容器内工具时先确认镜像有
- 来源: t20261001-iter4 | 命中: 2 (ip + python 两项)

## 部署段五坑之四: Git Bash curl 发中文 body 变 GBK → 服务端 UTF-8 解析失败; 冒烟提示词纯 ASCII
- 阶段: 部署(verify) | 现象: 从操作机(Windows Git Bash) curl 提交含中文的 JSON body, 编码退化为 GBK,
  vLLM 服务端按 UTF-8 解析失败 → 冒烟假失败(服务本身无恙)
- 结论/修复: 跨 Windows→Linux 的 HTTP 冒烟提示词**纯 ASCII**("What is 1+1? Answer with the number only.",
  verify.sh:20); 判"服务异常"前先排除客户端编码侧假因
- 来源: t20261001-iter4 | 命中: 1 (关2 对话冒烟)

## HF_ENDPOINT 是两台机器两个通道: 服务端设了镜像不等于评测机设了, lm_eval/datasets 任务加载期必挂直连
- 阶段: 基准(Track2) | 现象: lm_eval 起跑正常(6 任务选中, local-completions 已指向 /v1/completions + 本地 tokenizer),
  但任务加载期 `datasets.load_dataset` 直连 `https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro/...` 连续
  WinError 10054/10060 重试 5 次后 traceback → 6 任务 0 打分(capability_result.json tasks=[]), CLI 发
  `no score for …; the task counts as failed (DD §9)` 告警(RunCommand.cs:554)
- 结论/修复: ① vLLM 起服拉权重(服务端容器)与 lm_eval/datasets 拉数据(操作机 Python venv)是**两个独立 HF 通道**,
  各自都要 `HF_ENDPOINT=https://hf-mirror.com`——iter4 入库的 kb 种子只覆盖了前者; ② 修复已验证: 驱动 agent
  实测 gsm8k 经镜像可达 + 报告员 curl 复核 `curl -sIL hf-mirror/datasets/openai/gsm8k/resolve/main/README.md`
  final=200(直连对照组失败); ③ 完整档 Track2 前置条件: 操作机 export HF_ENDPOINT 后再 `--track capability`
- 来源: t20261001-iter5 | 命中: 1 (操作机 datasets 通道; 服务端同款问题见 INDEX 种子第 4 条)

## TP1/TP2 部署差异: TP2 多一层 ray 双机依赖, serve 中断形态=KeyboardInterrupt+leaked shared_memory; TP1 单机是现成降级路径
- 阶段: 矩阵(部署/起服) | 现象: 组合矩阵轮 TP2-Qwen3.6 serve FAIL——`KeyboardInterrupt: terminated` +
  resource_tracker "1 leaked shared_memory" 告警; 同组合 iter5 档案(92.74 tok/s)曾 PASS, 跨迭代可 FAIL 可 PASS
- 口径/结论: ① KeyboardInterrupt=信号中断形态(非模型加载/OOM 报错), 大概率 serve 进程被外部终止
  (超时击杀/人工中断/编排 timeout), leaked shared_memory 是进程树被中途打断的伴生征状(resource_tracker
  shutdown 清不完), 不构成独立故障; 根因要 serve 日志全文, 无则记"待复跑", 单次失败不定罪组合;
  ② 复跑前清场: 残留共享内存/ray 僵尸按 iter3b/3c 口径(Z 态 kill 不掉、根治靠容器重启、可带尸部署不混算);
  ③ TP1 单机部署无 ray 依赖、失败面小, 是 TP2 通道异常时的现成降级路径(Qwen3.6: 92.7→67.7 tok/s 约 -27%,
  跨迭代口径); TP2 性能增益真实(dense 27B 同轮 TP2/TP1 出流 1.78×), 取舍=默认 TP2、通道不稳即切 TP1
- 来源: t20261001-iter6 | 命中: 1 (TP2-Qwen3.6 serve 段; TP1-Qwen3.6 同轮存活佐证降级路径)

## MoE 模型(NVFP4) TP 首次加载必经 FlashInfer 自调优, 时长远超常规加载门禁
- 阶段: 服务 | 现象: TP2 部署 Qwen3.6-35B(A3B MoE) 反复"卡死"于 shm_broadcast 60s 心跳, 15-16 分钟门禁超时; 同链路稠密 Qwen3.8-27B 秒过
- 真因: 新节点(无 autotune 缓存)首次加载 MoE 模型触发 FlashInfer trtllm::fused_moe 自调优(16 配置/内核×多内核), 实测 40 分钟级; 129 有缓存故迭代4 首跑仅 5 分钟——"快慢差异"正是缓存有无
- 修复: serve.sh 门禁两段化——15 分钟未就绪时检测日志含 Autotun/Tuning 则延长至 60 分钟(一次性成本, 调优结果落 /root/.cache/vllm/flashinfer_autotune_cache); 判死前先看是不是在调优
- 关联教训: 杀 TP2 旧实例必须连杀 RayWorkerProc/EngineCore(只杀 vllm serve 会留 worker 占 103GB 显存, 新实例等显存真死锁)
- 来源: t20261001-iter6 | 命中: 3(两次超时误判死锁 + 自调优实锚)

## [开放] 134 节点 FlashInfer MoE 自调优后 EngineCore 初始化不稳定
- 现象: TP2-Qwen3.6 首次部署成功(iter4, 自调优完成后 5 分钟就绪); 同日后续 3 次重部署全部 EngineCore init failed(自调优部分完成后崩溃, 16/16 计数停在 12)
- 待查方向: 自调优缓存半写状态损坏? /dev/shm 残留(resource_tracker leaked 警告)? ray head 与残留 worker 代际混用? 
- 临时规避: TP2+MoE 重部署前重跑 cluster.sh(全新 ray); 或容器重启清 shm; 或删 /root/.cache/vllm/flashinfer_autotune_cache 重调
- 来源: t20261001-iter6 | 命中: 1 | 状态: 未关闭

## [已缓解] FlashInfer MoE 自调优跨会话确定性死亡(~33min) — 关调优 flag 150s 就绪且代价 <1%
- 阶段: 服务 | 现象: TP2-Qwen3.6(35B MoE) 本会话连续 4 次 serve 全部在自调优开始后 ~33 分钟整死亡(EngineCore init failed, 无 traceback; 129 侧 GPU 96% 在调, 134 侧 0% 等 handshake, head 侧 shm_broadcast 空转)——旧条目"[开放] 134 自调优后 init 不稳定"的升级: 不是偶发, 是确定性
- 真因定位: vLLM 0.30 optimization level≥2 默认 enable_flashinfer_autotune=True(config/vllm.py), 跨会话 serve 重入自调优路径必死; 自调优缓存(88K/5文件)远小于全量调优结果, 从未真正持久化成功
- 修复(实测): serve 加 `--kernel-config '{"enable_flashinfer_autotune": false}'` → 150s 就绪(对比 33min 死亡×4); c1 出流 88.9 vs 旧自调优口径 89.6 tok/s, 代价 <1%
- 引号坑: 该 JSON 经 本地bash→ssh→远端login shell→容器bash 三层解析, 双引号必被剥; 唯一可靠通道是 `ssh ... "docker exec -i vllm-node bash -s" <<'EOS'` stdin 落脚本(round5.sh)
- 来源: t20260930-matrix-full | 命中: 4(四连死+第五轮立解) | 状态: 已缓解(关调优口径写入报告 vllm_args, 透明可查)

## vLLM 0.30 服务端指标计数器名(实测勘误) + 相位后 gauge 已回落无峰值意义
- 勘误: 成功/失败 = `request_success_total{finished_reason=stop|length|abort|error}`(旧名 num_requests_success_total 不存在); TPOT 直方图 = `request_time_per_output_token_seconds`(带 request_ 前缀); 可用新指标: inter_token_latency/request_queue_time/request_inference_time 直方图
- 坑: 相位结束后才抓 /metrics, kv_cache_usage_perc/num_requests_running 已回落 0——峰值必须负载中轮询(bench/common.GaugePoller, 2s 采样)
- 坑: vllm.log 每次 serve 覆盖, `GPU KV cache size`/`Maximum concurrency` 两行不落档即永久丢失(serve.sh 已在就绪后自动落档)
- 来源: t20260930-matrix-full | 命中: 3

## 引号地狱第二课 + 运行中编辑脚本两连坑
- 现象1: JSON flag(`--kernel-config {"enable_flashinfer_autotune":false}`)经 本地bash→ssh→远端shell→容器bash 四层, 非引号heredoc($extra展开)会让容器bash把JSON双引号剥掉 → vllm 12秒拒参退出
- 修复(实测): 参数全部走 `docker exec -e VAR=...` 环境变量 + 引号heredoc `<<'EOS'` 落脚本 — env展开只分词不剥引号, JSON原样进argv; 单独只给extra留`-e 'EXTRA_ARGS=...'`(远端单引号包住)
- 现象2: cell4.sh 在某组合执行中途被编辑(修别的组合的bug), 该执行实例从字节偏移处读到错乱内容直接死亡(serve就绪后电池全跳过) — bash流式读脚本, 运行中编辑=自毁
- 规则: 脚本热修只能等当前实例退出后生效; 编排脚本要幂等可单组合重跑(cell4.sh <tp> <model> <gb> <tag> [extra])就是为此设计
- 来源: t20260930-matrix-full/raw4 | 命中: 2

## vLLM 0.30 上下文外拓(YaRN)配方 — 三次失败换来的正解
- 坑1: --rope-scaling 参数已不存在(unrecognized arguments); 坑2: hf_overrides 打在顶层无效(multimodal 包装, 真实字段在 text_config 里)
- 坑3(最反直觉): vLLM 0.30 对 yarn 故意不乘 factor("YaRN variants leave max_position_embeddings already scaled") — 只给 rope_scaling 不改 max_position_embeddings, derived 永远是原值
- 正解: --hf-overrides '{"text_config":{"max_position_embeddings":1048576,"rope_scaling":{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":262144,<原config的mrope/partial_rotary/theta字段必须带上>}}}'
- 判config结构别猜: 容器内 transformers AutoConfig 直接看 has text_config / rope_parameters(Transformers v5改名)
- 来源: t20260930-matrix-full/raw4/TP2EP2MTP-1M | 命中: 3次失败+第4次成

## Qwen3.6-35B-A3B-NVFP4-Fast 自带 MTP 权重 — 判断模型能力要看权重不能只看 config 键
- 教训: 我曾凭 config.json 无 mtp 键断言"无MTP头", 被用户纠正; 实际 model.safetensors.index.json 里有 19 个 mtp.*(fc+layers.0, MoE结构), config 就是不声明
- 方法: vLLM 0.30 用 qwen3_5_mtp(已deprecated, 等价 mtp); 单MTP层 k=2 可行(递归起草), 官方警告 k>1 接受率会降
- 实测: 接受率 75.2%(19759/26298 accepted/draft), 单流 88.6→121.4 tok/s(+37%), TPOT 10.7→7.8ms; 五套件能力分无回退(gsm8k 94.5→95.5), 无损性实证
- 来源: t20260930-matrix-full/raw4/TP2EP2MTP-1M | 命中: 1

## spec解码模式会把 max_num_scheduled_tokens 压到 2048 — 长预填大幅变慢
- 现象: 1M场景 128K输入单请求 TTFT 57.7s(≈2.3k tok/s 预填); 启动日志明示 warning: max_num_scheduled_tokens=2048 based on spec settings, 建议调大 max_num_batched_tokens
- 影响: 投机模式对解码+37%但对超长预填是负资产; 对话型输入(<8K)无感, 贴大文档场景需调参或非spec实例分流
- 来源: t20260930-matrix-full/raw4/TP2EP2MTP-1M | 命中: 1

## [重要纠错] 前缀缓存完全有效 — 我此前"命中为0/无效"的结论是探针伪影, 已收回
- 错误结论来源: prefix探针用~1.5K共享前缀 → 命中0/加速0.9x, 我错误外推为"本栈前缀缓存无效"
- 判决实验(2026-09-30, 1M实例): 72K文档 同文重发 TTFT 13.7s→1.2s(11x), 命中68,096/71,971=94.6%; 真多轮(历史+新问题)同样1.3s
- 真实机制: 混合Mamba架构(Qwen3.5系)的前缀复用随前缀长度增长 — 实测 1.5K→~0%, 4K→37%, 16K→83%, 64K→97%(20.2s→1.3s, 16x)
- 推论: 多轮长会话每轮只预填未复用尾部(≈3%+新增), 积累到1M的会话单轮TTFT≈(30K+新增)/预填速率, 而全新1M输入才要付全量(≈7-8分钟)
- 方法论教训: 单一长度点的探针结论不可外推到全长度域; 命中率是长度函数, 探针必须扫长度阶梯(已列v4.1义务)
- 来源: t20260930-matrix-full 判决实验 | 命中: 1(直接推翻前结论)

## [致命流程教训] 两次事故同根: 场景缺"模型能力轴"与"用途轴"
- 事故1: 未做模型调研就上 — 凭config无mtp键误判"无MTP"(权重里19个), 原生上下文/rope形态(mrope混合)靠4次试错撞出YaRN配方
- 事故2: 智能体用途的服务没配 --enable-auto-tool-choice/--tool-call-parser — 对话三关全绿, agent客户端首call即400("auto tool choice requires ...")
- 根因: 场景只按性能轴(TP/量化)定义. 修复(SKILL修订案A1): ①M0模型调研阶段硬门禁(model_profile.py: 权重实证+config形态+模板扫描+容器方法核对, 无profile不得serve) ②Track3智能体测试(selection/args/loop/时延) ③verify三关→四关, 关4由用途驱动(agent用途FAIL级) ④场景生成器三维化(模型×服务flags×用途, 能力类flags开关两档对比入矩阵)
- 方法论: 判断模型能力=看权重+容器注册表实测, config只是参考; 验收契约必须包含目标用途的真实调用形态(对话绿≠agent可用)
- 来源: t20260930 老板演示前夕 | 命中: 2

## [开放→已定位] tool_choice=auto 全灭: hermes parser 与 Qwen3.5系XML语法不匹配
- 现象: required全对(约束解码绕过parser), auto下模型在content里输出真实工具调用但parser不接 — finish=stop, tool_calls空, 智能体框架静默失败(比400更隐蔽)
- 证据: auto原始content含 <tool_call><function=search_docs><parameter=query>Q3财报</parameter></function></tool_call> — XML语法, hermes期望JSON语法
- 修复方向: --tool-call-parser qwen3_xml 重启(待窗口); M0教训: 有<tool_call>标记≠hermes, parser必须探针实测(model_profile已改parser_must_probe)
- 附带实测(required模式): 嵌套参数(数组+枚举+中文抽取)完美, 两步链(搜→算→答)完美, 但一句话多城市只调第一个(并行调用弱, 框架侧需拆分)
- 来源: t20260930-agent-tools | 命中: 1 | 状态: 定位待修

## [实测纠偏] 调大 max_num_batched_tokens 并未加速 GB10 长文冷预填 — 预填是算力瓶颈
- 实测: 8192 生效确认(旧2048警告消失)后, 288K 冷预填仍 97.8s(≈2.9K tok/s), 与 2048 时同量级 → 长上下文预填在 GB10 上 compute-bound(注意力/MoE), 切片调度不是瓶颈; 我此前"预填可提速数倍"的预期被实测证伪, 予以纠正
- 冷启动 300K ≈ 90-120s 是这套硬件的物理量级, 任何 chunk 旋钮都改不动; 出路只有: 前缀缓存稳态(实测 288K 同文重发 2.6s, 命中28.5万token) + 客户端 SSE 超时≥120s + 冷启动错峰
- 附带: 新进程投机接受率(纯随机文本) 64.8%, 单流 118 tok/s 不变 — MTP 与 batched_tokens 正交, 可放心同开
- 来源: 2026-10-03 演示服务调优 | 命中: 1

## hf-mirror 下载 nvidia 仓库必须禁 xet + Flash-Next 首测画像
- 坑: hf download 拉 nvidia 仓库报 "CAS Client Error"(xet 协议 mirror 不支持) → export HF_HUB_DISABLE_XET=1 强制 HTTP 即通
- Flash-Next(qwen4_exp/132.64GB/TP2+MTP2+1M) 首测: 能力八套件全场最佳(gsm8k96.5/mmlu89.5/truthfulqa90.5), 单流41tok/s(与27B相当), 但KV池仅1.9M tok=1.81个满1M会话 — 132GB权重把内存吃干; "保守1M多路"在此模型上不成立, 500K×3-4路是上限
- Track3行为特征: 计算类问题模型弃用工具直接心算(选择8/8但loop=0.5) — 智能体框架需在系统提示词中强制"计算必须走工具"
- 来源: t20261003-flashnext | 命中: 2

## 1M ctx 模型首测: KV 池行(kv_cache_max_concurrency)是 soak/容量档规模的唯一设计输入
- 现象: ds-flash(deepseek_v4 FP8, TP2, gpu_memory_utilization=0.85) startup 一行同给两事实:
  "GPU KV cache size: 2,220,027 tokens, Maximum concurrency for 1,048,576 tokens per request: 2.12x" — 满长 1M 请求全池只装 ~2 路;
  本轮 soak 3路×524288(合计 1.57M<2.22M)成立, 零抢占(vllm:num_preemptions_total=0)
- 规程: ① 起 soak/容量档前先从 startup 池行或 vllm:cache_config_info(kv_cache_max_concurrency=2.117)换算 sessions×target_ctx ≤ 池, 否则 preempt/排队失真;
  ② 与 Flash-Next(池 1.9M=1.81 路满长)同规律: 大权重 FP8/MoE 的 1M 服务"保守 1M 多路"不成立, 500K×3 两模型实测成立;
  ③ startup.log 常被裁剪(本轮只剩池行, serve.log 只剩 LAUNCHED), /metrics 的 cache_config_info 是等效可再生的池证据
- 来源: t20261004-dsflash-fp8 | 命中: 2(ds-flash + flash-next 同规律)

## NVFP4 首测 serve 三投两败: "See root cause above" 尾部截取必丢根因, 修复重投后仍会再败一次
- 现象(t20261004-dsflash-nvfp4, DsFlashN-TP2-1M): 20:03 首投 3min 即退(raw/progress.log:1-2, 捕获的"退出尾部"为**空**);
  20:12 修复 shard-00040 后重投 4min 再退(fix_shard40_relaunch.log:2-4); 20:23 第三投 ~460s 就绪(progress.log:3-4)
- 真因(取证缺陷): ① 二败尾部只有 APIServer 侧堆栈, 终于 "RuntimeError: Engine core initialization failed. See root cause above.
  Failed core proc(s): {}"(fix_shard40_relaunch.log:26-27) — 它指向的根因在 EngineCore 进程输出里, 位于截取窗口上方, tail 必然丢;
  且 Failed core proc(s) 为空集, APIServer 视角连进程号都没有; ② 两次失败(尤其二败)至今无根因证据行; ③ 二败唯一残留线索:
  resource_tracker "1 leaked shared_memory objects"(fix_shard40_relaunch.log:28)提示首败 EngineCore 残留未清净
- 修复: ① serve 崩溃取证禁用纯 tail — 全量日志先 grep -nE "ERROR|Traceback|CUDA|NCCL|RuntimeError" 定位后带上下文截取, 必含
  (EngineCore pid=...) 行; ② serve 发起时把完整命令行+解析后参数 echo 进 serve.log(本跑仅 "LAUNCHED" 1 行, 池/调度差异事后无法排查);
  ③ 修复重投前核查上一轮 EngineCore 进程/shm 已净, 不能只信"清场完成"日志行; 关联: 分片损坏本体见 testing-bench.md NVFP4 分片条目
- 来源: t20261004-dsflash-nvfp4 | 命中: 1

## 2026-10-05 DS NVFP4 降 max-model-len 反而砍 KV 池(500K×3 产品口径的正确实现)
- 现象: max-model-len 1048576→524288(其余全同), KV 池 1,389,961→909,846 token(-35%), 500K 满载并发 2.65×→1.74×
- 真因: vLLM 0.30 对 deepseek_v4(MLA/混合+dspark 草稿)的 KV 池分配与 max_len 正相关(池 tokens 估计含随 max_len 缩放的预留)
- 修复: "500K×N"产品口径不靠降 max-len 实现——保持原生 1M(池最大)+ --max-num-seqs N 准入控制; seqs 3/8 对池无影响(隔离实验双向验证)
- 教训: 容量调优先做单变量隔离(本次 500K×{3,8} 两发即定位), 不凭直觉假设"上下文越小池越大"
