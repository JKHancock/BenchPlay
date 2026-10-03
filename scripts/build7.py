import sys
sys.path.insert(0, "D:/CSharpProject/BenchPlaybook/scripts")
import build_doc as B

# 运行时注入第七场景(Flash-Next), 不动已脏的源文件
B.TAGS = list(B.TAGS) + [("FlashNext-TP2-1M", "Qwen3.8-Flash-Next-NVFP4", 2, False, [], 1048576)]
B.MODELS["Qwen3.8-Flash-Next-NVFP4"] = {"quant": "NVFP4", "type": "moe", "params_b": 230,
                                        "active_b": 4, "weights_gb": 132.6, "ctx": 1048576}

CELL6_ARGV = ["vllm", "serve", "/root/.cache/huggingface/Qwen3.8-Flash-Next-NVFP4",
              "--tensor-parallel-size", "2", "--distributed-executor-backend", "ray",
              "--speculative-config", '{"method":"qwen4_exp_mtp","num_speculative_tokens":2}',
              "--hf-overrides", '{"text_config":{"max_position_embeddings":1048576,"rope_scaling":{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":262144}}}',
              "--enable-auto-tool-choice", "--tool-call-parser", "qwen3_xml",
              "--reasoning-parser", "qwen3",
              "--served-model-name", "flash-next", "--host", "0.0.0.0", "--port", "8000",
              "--gpu-memory-utilization", "0.85", "--max-model-len", "1048576",
              "--max-num-seqs", "8", "--max-num-batched-tokens", "8192",
              "--enable-chunked-prefill", "--enable-prefix-caching"]

_orig_scenario = B.scenario
def scenario(tag, model, tp, noauto, extra_flags=(), max_len=40960):
    row = _orig_scenario(tag, model, tp, noauto, extra_flags, max_len)
    if tag == "FlashNext-TP2-1M":
        row["vllm_args"] = CELL6_ARGV
        import hashlib
        row["scenario_id"] = hashlib.sha1((" ".join(CELL6_ARGV) + model + str(tp)).encode()).hexdigest()[:8]
        row["notes"] = ("qwen4_exp新架构首次在本集群实测; 132.64GB权重; Track3工具选择8/8满分"
                        "但l2计算题模型弃用工具直接心算(loop=0.5, 行为特征如实记录)")
    return row
B.scenario = scenario

# raw目录路由: FlashNext 在新任务目录
from pathlib import Path
RAW2 = Path("D:/CSharpProject/BenchPlaybook/tasks/t20261003-flashnext/raw")
_orig_load = B.load
def load(p):
    p = Path(p)
    if p.name.startswith(("w", "m", "c", "p", "s", "h")) and not p.exists() and "FlashNext" in str(p):
        pass
    return _orig_load(p)
B.load = load
# 简化: 直接把RAW切到新目录不行(6场景在旧目录) — 给 scenario 用的 d 路径按 tag 路由:
import types
_src_scenario2 = B.scenario
def scenario2(tag, model, tp, noauto, extra_flags=(), max_len=40960):
    if tag.startswith("FlashNext"):
        old = B.RAW
        B.RAW = RAW2
        try:
            return _src_scenario2(tag, model, tp, noauto, extra_flags, max_len)
        finally:
            B.RAW = old
    return _src_scenario2(tag, model, tp, noauto, extra_flags, max_len)
B.scenario = scenario2

# 内联 main()(绕开其用旧RAW做的exists过滤)
from datetime import datetime
from pathlib import Path
import json
PATH_RAW = Path("D:/CSharpProject/BenchPlaybook/tasks/t20260930-matrix-full/raw4")
machines = B.machines_part()
scs = []
for t in B.TAGS:
    tag = t[0]
    B.RAW = RAW2 if tag.startswith("FlashNext") else PATH_RAW
    if not (B.RAW / tag).exists():
        continue
    scs.append(B.scenario(*t))
doc = {"meta": {"contract_version": "4",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "source_artifacts": ["tasks/t20260930-matrix-full/raw4",
                                     "tasks/t20261003-flashnext/raw"],
                "fingerprint": B.FP},
       "machines": machines, "scenarios": scs,
       "recommendation": B.recommend(scs)}
import jsonschema
jsonschema.validate(doc, B.SCHEMA)
out = PATH_RAW.parent / "report_doc.json"
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print("PASS 7场景:", len(scs), [s["scenario_id"] for s in scs])
