# -*- coding: utf-8 -*-
"""报告四大改进. 用后即删."""
import ast

P = 'scripts/report_gen4.py'
src = open(P, encoding='utf-8').read()

# 1) vLLM 参数换行显示
old_argv = '''        L.append("```bash")
        L.append(" ".join(sc["vllm_args"]))
        L.append("```")'''
new_argv = '''        L.append("```bash")
        argv = sc["vllm_args"]
        parts, cur = [], [argv[0], argv[1], argv[2]]
        for i in range(3, len(argv)):
            if argv[i].startswith("--"):
                if cur:
                    parts.append(" ".join(cur))
                cur = [argv[i]]
            else:
                cur.append(argv[i])
        if cur:
            parts.append(" ".join(cur))
        L.append(" \\\\\\n".join(parts))
        L.append("```")'''
if old_argv in src:
    src = src.replace(old_argv, new_argv)

# 2) Part C 简洁化
old_rec_head = '''        L.append(f"### {p['profile']} → **{p.get('winner_label', p['winner'])}**（`{p['winner']}`）")
        L.append("")'''
new_rec_head = '''        L.append(f"### {p['profile']}")
        L.append("")
        L.append(f"**推荐场景** `{p['winner']}`（{p.get('winner_label', '')}）——详见 Part B 对应场景的数据与参数说明。")
        L.append("")
        L.append("**推荐理由**：")'''
if old_rec_head in src:
    src = src.replace(old_rec_head, new_rec_head)

# 3) 参数表格（插到 Benchmark 一 之前）
PARAM_TABLE = '''        L.append("**参数逐项说明**")
        L.append("")
        L.append("| 参数 | 含义与作用 | 我们的值 | 为何这样设置 |")
        L.append("|---|---|---|---|")
        _PD = {
            "--tensor-parallel-size": ("张量并行", "把模型切成几份分到几张 GPU 上同时计算", "TP=2 用满双机；TP=1 单机跑"),
            "--distributed-executor-backend": ("分布式后端", "跨机通信框架选哪个", "ray 是双机集群的标准选择"),
            "--enable-expert-parallel": ("专家并行", "MoE 模型的专家分组到不同节点", "MoE 模型双机时可选；实测收益 <1%"),
            "--speculative-config": ("投机解码（MTP）", "用模型自带的 MTP 头预测多个 token 再一次验证，加速生成", "模型自带 MTP 权重即可开；k=2 是实测最优"),
            "--hf-overrides": ("模型配置覆写", "不改模型文件，运行时覆盖上下文长度（如 YaRN 外拓）", "原生 262K 不够用时外拓到 1M"),
            "--enable-auto-tool-choice": ("自动工具调用", "允许模型在对话中自动决定是否调用工具", "智能体用途必须开启"),
            "--tool-call-parser": ("工具调用解析器", "识别模型输出的工具调用语法并转为结构化 JSON", "须匹配模型的输出格式；Qwen 系用 qwen3_xml"),
            "--reasoning-parser": ("思考链解析器", "把模型的推理过程分离到独立字段", "开启思考模式时用"),
            "--served-model-name": ("服务模型名", "API 调用时 model 参数填的名字", "演示用简短别名"),
            "--gpu-memory-utilization": ("显存利用率", "最多允许 vLLM 占用多少显存", "0.85 留 15% 余量防 OOM"),
            "--max-model-len": ("最大上下文长度", "单次请求的输入+输出 token 上限", "40960 够日常；1M 用于超长文场景"),
            "--max-num-seqs": ("最大并发路数", "同时解码的请求上限，超出排队", "8 路保证每路满血体验"),
            "--max-num-batched-tokens": ("单步批量 token 数", "每个计算步处理多少 token（含预填切片）", "8192 平衡预填吞吐与解码延迟"),
            "--enable-chunked-prefill": ("分片预填", "把长输入切成小片逐片处理，不阻塞其他用户", "多用户场景必开"),
            "--enable-prefix-caching": ("前缀缓存", "相同前缀的 KV 缓存复用，加速多轮对话", "多轮对话场景必开"),
            "--kernel-config": ("内核配置", "控制 FlashInfer 自调优等底层内核行为", "关闭自调优避免跨会话死锁，代价 <1%"),
        }
        _seen = set()
        for _ai in range(3, len(sc["vllm_args"])):
            _arg = sc["vllm_args"][_ai]
            if not _arg.startswith("--") or _arg in _seen:
                continue
            _seen.add(_arg)
            _val = sc["vllm_args"][_ai + 1] if _ai + 1 < len(sc["vllm_args"]) and not sc["vllm_args"][_ai + 1].startswith("--") else "（开关）"
            _info = _PD.get(_arg, ("", "", ""))
            L.append(f"| `{_arg}` | **{_info[0]}**——{_info[1]} | `{_val}` | {_info[2]} |")
        L.append("")

'''
bm1_marker = 'L.append("**Benchmark 一'
idx = src.find(bm1_marker)
if idx > 0:
    last_empty = src.rfind('L.append("")', 0, idx)
    if last_empty > 0:
        src = src[:last_empty + len('L.append("")')] + '\n' + PARAM_TABLE + src[last_empty + len('L.append("")'):]

# 4) 评测导读（插到 Part B 分组之前）
GUIDE = '''    L += ["## 评测导读（每个数字是什么意思）", ""]

    L += ["### 性能指标", "",
          "| 指标 | 含义 | 如何测量 | 分数说明 |",
          "|---|---|---|---|",
          "| TTFT (首字延迟) | 用户发出请求到收到第一个字的等待时间 | 逐请求毫秒级计时 | p50=一半请求比这快; <500ms 体感秒回",
          "| TPOT (每token耗时) | 流式输出中相邻两个字的间隔 | 逐请求(总生成时间÷token数) | p50 越低打字机越流畅; <100ms 阅读无卡顿",
          "| ITL (token间延迟) | 任意两个字之间的最坏间隔 | 逐 chunk 时间戳差 | p99 越小说明没有突然卡顿",
          "| 出流 tok/s | 所有用户加起来每秒产出多少字 | 段内总输出token÷总耗时 | 越高能同时服务的人越多",
          "| goodput | 同时满足 TTFT≤500ms 且 TPOT≤100ms 的请求占比 | 逐请求判定 | 100%=全部秒回; <50%=一半人体感差",
          "| 理论上限校验 | 用物理公式算出这台硬件最高能跑多快 | 显存带宽÷每token需读的权重 | 实测达到上限的百分之几; <80%正常",
          ""]

    L += ["### 能力套件（八项，各测什么、分数什么意思）", "",
          "| 套件 | 测什么 | 怎么算分 | 95%意味着 | 70%意味着 |",
          "|---|---|---|---|---|",
          "| gsm8k | 小学数学应用题 | 200道题答对÷200 | 小学数学基本满分 | 有明显计算错误 |",
          "| mmlu | 大学级多学科知识选择题 | 200题分层抽样 | 知识面广且准确 | 部分领域有盲区 |",
          "| arc | 中学科学推理选择题 | 200题 | 科学推理可靠 | 概念性错误较多 |",
          "| hellaswag | 常识判断（选最合理的后续事件） | 200题四选一 | 常识接近人类水平 | 常识判断偏弱 |",
          "| winogrande | 指代消解（\\"他/她\\"指的是谁） | 200题二选一 | 语义理解精准 | 存在指代混淆 |",
          "| truthfulqa | 事实性与抗幻觉 | 200题 | 回答可信度高 | 容易似是而非 |",
          "| openbookqa | 科普知识推理 | 200题四选一 | 基础科学扎实 | 推理链有断裂 |",
          "| race | 阅读理解（读文章答题） | 200题四选一 | 长文理解强 | 读到后面忘前面 |",
          ""]

    L += ["### 智能体指标", "",
          "| 指标 | 含义 | 怎么算 | 满分意味着 |",
          "|---|---|---|---|",
          "| 工具选择 | 给一堆工具和一个问题，选对该用的那个 | 8题选对÷8 | 不乱调也不漏调 |",
          "| 参数抽取 | 选对工具后参数填对 | 选对题中参数匹配占比 | 能准确提取参数值 |",
          "| 循环成功率 | 调用→回灌→正确回答全环走通 | 2个多步任务全通=1.0 | 智能体工作流可靠 |",
          "| BFCL 无关克制 | 问不需要工具的问题能不乱调 | 100题拒调÷100 | 不画蛇添足 |",
          "| BFCL 结构分 | 函数名对+必填参数齐+类型合理 | 100题结构校验 | 函数调用格式规范 |",
          ""]

    L += ["### vLLM 服务端指标（监考仪）", "",
          "| 指标 | 含义 |",
          "|---|---|",
          "| 成功/失败 | 该段测试期间正常完成/异常中断的请求数 |",
          "| prompt tok / gen tok | 该段读入的上下文总量 / 生成的回答总量 |",
          "| 前缀命中 q/h | 查了多少块缓存 / 命中多少（命中越多预填越快） |",
          "| TTFT/TPOT/ITL/排队 p99 | 服务端视角的延迟分位数 |",
          "| 投机接受率 | MTP 预测的 token 有多少验证通过（越高解码越快） |",
          "| KV 峰值 | 测试时显存缓存了多少上下文 |",
          ""]

'''
partb_marker = 'L += ["## Part B'
idx2 = src.find(partb_marker)
if idx2 > 0:
    src = src[:idx2] + GUIDE + src[idx2:]

open(P, 'w', encoding='utf-8').write(src)
ast.parse(src)
print('4 improvements OK')
