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
