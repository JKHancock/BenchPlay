# -*- coding: utf-8 -*-
"""Vllm_Benchmark 的 Python 平替(替代 C# llm-bench CLI).

- bench.track1 : 性能基准(多档并发, TTFT/TPOT 分位, 屋顶线检查)
- bench.track2 : 能力评测(gsm8k/mmlu/arc 三套件, 0-shot 关思考链)
- bench.common : 客户端 + /metrics 解析 + 分位数工具

只依赖 venv 现成的 requests/pyarrow, 零新增安装.
"""
