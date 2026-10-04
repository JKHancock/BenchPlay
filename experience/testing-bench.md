# testing-bench 经验条目(自动拆分自gb10.md)

## GB10 不自报机型且 nvidia-smi 无显存容量, 机型认定只能"声明+nvidia-smi 名"交叉佐证
- 阶段: 清点(探测) | 现象: 双机 /proc/device-tree/model 均不存在(probe identity-model 节返回 n/a), nvidia-smi memory.total 报 [N/A]
- 结论/修复: 属 GB10 机型常态而非探测故障; 门禁按 DeclaredModel(任务声明)与 gpu 节 `NVIDIA GB10` 输出一致判定放行, 档案不填显存容量; 后续勿因这两项判 FAIL
- 来源: t20261001-iter1 | 命中: 2 (129/134 双机一致)

## 部署段五坑之五: 推理型模型冒烟 300 token 全耗思考正文空 → 门禁语义=良构补全而非精确答案
- 阶段: 部署(verify) | 现象: Qwen3.6 推理型模型小 max_tokens(300)下全部预算耗于思考, 正文无输出——
  若冒烟门禁判"答案正确"必然误 FAIL(模型与服务实际正常)
- 结论/修复: ① 冒烟门禁语义定为**良构补全**: 响应含 `chatcmpl-` ∧ `finish_reason` 即过, 答案仅作信息展示
  (verify.sh:17 注释 + :21); ② max_tokens 提至 2000 留足思考余量(verify.sh:20); 推理型模型的质量评测
  归基准任务, 不与"服务就绪"门禁混算
- 来源: t20261001-iter4 | 命中: 1 (Qwen3.6-35B-A3B-NVFP4-Fast 冒烟)

## 组合矩阵性能事实: 并行度增益 ~1.8×(dense 27B) < 模型差异 ~6×(MoE-A3B vs dense); 并发1 下出流≈1/TPOT_p50 可作自洽速检
- 阶段: 矩阵(基准) | 现象: {TP1,TP2}×{Qwen3.6-35B-A3B, Qwen3.8-27B} 四组快速档(并发1×8)实测——
  Qwen3.8 TP2/TP1=出流 1.78×/TPOT 1.78×/TTFT 1.46×(decode 89% 线性度); TP1 口径 Qwen3.6/Qwen3.8
  出流 6.10×/TPOT 6.22×/TTFT 2.28×
- 结论: ① 换模型的影响(~6×)比换并行度(~1.8×)高一个量级, 吞吐敏感场景先选模型再调并行;
  MoE-A3B 每 token 激活 ~3B vs dense 全参 27B(计算量差 ~9×), 实测 6.1× 量级吻合(激活量为命名推断);
  ② TP2 对 dense 增益(~1.8×)大于对 MoE 的跨迭代参考值(~1.4×)——MoE 激活小、单机算力已近喂饱 decode;
  ③ 数据自洽速检: 并发1 单流出流≈1/TPOT_p50(本轮三组偏差 0.5%~2.6%), 报告先算这个再下结论
- 来源: t20261001-iter6 | 命中: 3 (TP2-Qwen3.8 / TP1-Qwen3.8 / TP1-Qwen3.6 三组)

## 门禁陷阱: ok=$(cmd) 后 echo "$ok" || ... 测的是 echo 的退出码, 门禁形同虚设
- 阶段: 测试 | 现象: bench.sh 在服务已停时跑出 成0/败8 仍报 PASS——bash 门禁结构缺陷被真实故障触发
- 修复: python 直出 + `if ! python ... <<PY; then FAIL` 直检退出码; 任何 $(...)+echo||结构的门禁都要复查
- 关联: 屋顶线检查是第二道独立防线(成0/出流0 这类明显异常, 指标行本身就可疑)——门禁也要有冗余
- 来源: t20261001-治理修订 | 命中: 1

## 能力评测必须显式关思考链: gsm8k 2.05% → 94.5% 只差一个 chat_template_kwargs
- 阶段: 测试 | 现象: lm_eval 默认口径下 Qwen3.8-27B gsm8k 仅 2.05%(flexible)/0%(strict), 疑似"模型变笨"
- 真因: 思考链模型默认输出 <think>..., 评测 max_tokens 被思考耗尽, 答案截断; 模型能力无问题
- 修复: chat completions 带 `chat_template_kwargs: {"enable_thinking": false}` + 提示词要求 "#### <integer>" 收尾; 实测 27B: gsm8k 94.5%(189/200), mmlu 82-85.5%, arc 96.5-97.5%
- 统一口径(跨行可比): 0-shot · 关思考链 · temp=0 · 固定种子抽样 n=200/套件 · 并发8; 选择题"仅输出字母"平均输出≈2tok(极快), 数学题自由推理≈280tok
- 来源: t20260930-matrix-full | 命中: 1(直接命中) + 旧 t20261001 r002 存疑项就此关闭

## 2026-10-04 十二套件扩容实战(cell7, t20260930-flashnext-c12)
- 现象: track2.py 接入 math500/cmmlu/ceval/ifeval 后首跑, math500 校验器 \frac{1}{2} vs 0.5 不匹配
- 真因: _norm_answer 只做 float() 直转, 分数形式不数值化
- 修复: 归一化兜底 eval 简单算式("1/2"→0.5); 符号/小数混合(pi/4 vs 0.785)保留为已知可接受边界
- 现象: math500(思考链,500题)耗时 66min, 是 8 个老套件总和的 4 倍
- 结论: 思考链套件是电池时长主导项, 排期上放最后并预留 1-1.5h; 并发 8/超时 900s 够用(零失败)
- 现象: Track3 args_acc 首测与复测都是 0.75, 天花板伪影
- 真因: 克制题(n1/n2) args=None 但计入分母, 满分上限 6/8; Flash-Next 实际 6/6
- 修复: track3_agent.py 分母改为 n_call(排除 no_call 题); 旧数据解读时注意口径
- 现象: loop_success 首测 0.5 → 复测 1.0, "弃工具心算"是间歇性行为
- 结论: 智能体行为指标单次测量不可作为定论, 至少双次; 报告里写"行为特征"不写"缺陷"
- 现象: probes.py 对 flash-next 1M 服务两批次(1003/1004)同样 64/64 失败(timeout_or_conn, 12s)
- 真因: 待查(probe 侧超时/负载形态), 非服务侧(同期 w6 c64 全过); 前缀缓存热加速比因此缺测

## deepseek_v4 首测: enable_thinking=True 思考链不进 reasoning 字段而是直混 content
- 阶段: 测试(思考链探针+能力评测) | 现象: think_probe.log 两行实锤——enable_thinking=False → content="1+1=2" 干净无思考;
  enable_thinking=True → reasoning=False 且 content="我们被问到：…这是一个简单的问题。1+1=2。所以答案应…"(思考链全文进了 content)
- 真因: deepseek_v4 聊天模板(vLLM chat API)不产出 reasoning/reasoning_content 分离字段, 此前的"reasoning 字段兼容层"对该模板失效
- 修复/口径: ① 答案型套件一律显式 enable_thinking=False(track2 实跑对新套件逐个标注 no-think: cmmlu/ceval/ifeval, 仅 math500 标 think);
  ② think 套件(math500)判分器必须做 content 内答案抽取, 不能假设字段分离(本轮 acc=0.684 抽取成功);
  ③ think 代价实测量级: math500 500 题 9812s≈2.7h(并发8, 平均输出 1799 tok) — 超出旧指引"预留 1-1.5h", FP8 大 MoE 排期按实测另估
- 来源: t20261004-dsflash-fp8 | 命中: 1

## probes 全灭仍打印 PASS + "speedup Nonex": 探针门禁缺口跨模型二次复发
- 阶段: 测试(probes) | 现象: probes.json——prefix 缓存探针 fail_round1=64/64、fail_round2=64/64(TTFT 冷/热全 None);
  容量阶梯 c=8 completed=0/failed=8, mode=timeout_or_conn(wall 12.5s); max_ok_conc=null; probes.log 却输出 "PASS probes → …(max_ok_conc=None, speedup=Nonex)"
- 真因: ① 探针请求超时被覆写成 12s(probes.py 默认本为 420s, bench/probes.py:88 --request-timeout-s default=420), 远低于该机 TTFT 包络——
  实测 c=8 短提示 TTFT p50 1.46s(w1.log)但 c=32 均值 60.3s、c=64 均值 84.6s/峰 174s(w1/w6.log), 15K ctx 单路也 14.2s(soak 第1轮) → 12s 必然全灭;
  ② 判定只看"跑完"不看"有成": completed=0 仍 PASS; ③ f"{speedup}x" 把 None 拼成 "Nonex"
- 修复: 探针超时按目标 TTFT 定标(≥单路冷预填实测, 建议 ≥120s 或不覆写 420 默认); completed=0 → FAIL/DEGRADED 而非 PASS;
  None 禁止直接进 f-string; 本条为 t20260930-flashnext "真因待查"补证: qwen4_exp 与 deepseek_v4 双模型复发, 探针侧系统性问题实锤(同期 w6 c64 全过, 非服务侧)
- 来源: t20261004-dsflash-fp8 | 命中: 2(flash-next 1003/1004 + ds-flash 1004)

## vllm:kv_cache_usage_perc 整场 0.0%: 容量结论用 cache_config_info/池行算术, gauge 先对账
- 阶段: 测试(soak) | 现象: soak 3 路×~520K ctx(final_ctx=[519071,521119,526265] 合计≈1.57M tok≈池 2.22M 的 70%),
  33 轮 kv=0.0%(峰 0.0%), soak.json kv_peak_perc=0.0; metrics 快照里 vllm:kv_cache_usage_perc 存在但=0.0(相位末已回落), 连"峰"都全 0 → 采样点系统性错过负载窗口
- 修复/口径: ① 新引擎×新模型组合首跑先做一次"手算占用 vs gauge"对账; ② 对不上即以恒值指标 vllm:cache_config_info 为准
  (本轮 kv_cache_size_tokens=2220027, kv_cache_max_concurrency=2.117, num_gpu_blocks=22819)或 startup 池行换算, 报告注明容量口径(soak.json note 已自带此口径);
  ③ 旁证: prefix 计数器(queries 26.85M/hits 25.03M≈0.93)与 soak 前缀命中 0.9398 吻合 — 计数器可信, gauge 存疑
- 来源: t20261004-dsflash-fp8 | 命中: 1

## 2026-10-04 NVFP4 分片内容损坏逃过尺寸校验(NVFP4 场景, 监工首雷)
- 现象: serve 加载 safetensors 报 "incomplete metadata, file not fully covered"(134/TP1), EngineCore 退出
- 真因: model-00040 尾部多 176KB 垃圾(curl -C 续传污染的变体)——尺寸偏差 <1MB, 逐字节**尺寸**校验(±1MB 容差)放过; 尺寸≠内容
- 修复: scripts/st_check.py 头解析级校验(header 长度+张量覆盖区间==文件字节数), 每片秒级; 坏片从对侧节点容器管道 LAN 中转(cat|docker exec -i, 两跳SSH ~5min, 免外网)
- 规程: 大模型下载门禁必须 st_check 内容级过一遍, 尺寸校验只是初筛; 节点间有好片优先 LAN 中转
- 监工体系首战: foreman 3 级检查抓到服务死亡 → 监工子智能体只诊断不动手(纪律生效) → 电池工作流归因回跳并行诊断 → 双控制器无打架

## NVFP4 池比 FP8 小 43%, 且 soak 活 ctx 合计超池 22% 仍零抢占 — 池行并发上限是保守下界, 不是硬闸
- 阶段: 测试(soak)+容量口径 | 现象: 同日同模型(deepseek_v4/DsFlash)双量化、同 TP2+1M ctx、同 gpu_memory_utilization=0.85——
  NVFP4 池 1,275,550 tok/kv_cache_max_concurrency=1.216/num_gpu_blocks=13111 vs FP8 2,220,027 tok/2.117/22819
  (DsFlashN-TP2-1M/startup.log:1 + metrics_soak_b.json cache_config_info, fp8 侧同源); 权重更小的 NVFP4 池反而小 43%
- 超池实测: NVFP4 soak 三路 final_ctx=[525823,514969,512185] 合计 1.553M = 池的 121.8%, 33 轮零失败零抢占(preempted=false), 前缀命中 0.9398(soak.json/soak.log:35)
- 真因(部分定位): ① 池规模逐配方实测, 禁止"量化更小→池更大"推断; ② 超池可过: cache_config_info 证实 sliding_window=128 混合滑窗注意力、
  无 CPU offload(num_cpu_blocks/kv_offloading_size 均 None), 且 num_gpu_blocks×block_size=13111×4=52,444 ≪ 池 token 数 → 混合多池结构,
  池行"满长并发 x"按保守口径换算, 滑窗层驻留远小于 ctx 全长(此为架构推断, 未逐层验证); soak.py:12-13 三路内容 seed 隔离, 跨会话前缀共享已排除
- 修复/口径: ① fp8 条目的"sessions×target≤池"降级为**规划安全下界**, 不得作事后否决(本跑超 22% PASS); ② 容量证据链=cache_config_info 全字段+实测 ctx, kv gauge 两跑整场 0.0% 仍不可用; ③ 双量化对照时池差异(43%)必须写入画像, 直接影响产品并发承诺
- 来源: t20261004-dsflash-nvfp4(对照 t20261004-dsflash-fp8) | 命中: 1

## deepseek_v4 500K 级 soak TTFT 增长 ×2.2-2.4 是健康基线 — "ratio≈1=不劣化"的判读期望对该模型不成立
- 阶段: 测试(soak 判读) | 现象: NVFP4 TP2 首3轮 13.9s→末3轮 32.9s(×2.36)@ctx≈513-526K; FP8 同日 15.7s→34.3s(×2.19);
  两跑均 33 轮零失败、前缀命中同为 0.9398(soak 固定 seed, 数字自洽)
- 真因: 94% 前缀命中只救回"历史全量重发", 每轮新增 ~20K/路 的纯预填+超长 ctx 注意力开销随长度增长是物理下限;
  soak.py:143 note 的 "ttft_growth_ratio≈1 → 多轮聊天不劣化" 期望对 512K 级深上下文不现实
- 修复/口径: 判读阈值校准——该模型 500K 级 soak ×≤2.5 且零失败即健康; >3 或出现抢占才报劣化; 首测新模型先建立自身基线再定阈值, 不沿用 note 的 ≈1 期望
- 来源: t20261004-dsflash-nvfp4(对照 fp8 同日) | 命中: 2
