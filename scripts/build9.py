import sys
sys.path.insert(0, "D:/CSharpProject/BenchPlaybook/scripts")
import build_doc as B
import hashlib

# 第九次汇编(2026-10-04): 新增 DeepSeek-V4-Flash FP8 首测场景(M0 档案驱动).
# DS tag 走通用分支(d=B.RAW/tag), argv/sid 按实际 serve 命令覆盖.
B.TAGS = list(B.TAGS) + [
    ("FlashNext-TP2-1M", "Qwen3.8-Flash-Next-NVFP4", 2, False, [], 1048576),
    ("FlashNext-TP2-40960", "Qwen3.8-Flash-Next-NVFP4", 2, False, [], 40960),
    ("DsFlash-TP2-1M", "DeepSeek-V4-Flash-fp8", 2, False, [], 1048576)]
B.MODELS["Qwen3.8-Flash-Next-NVFP4"] = {"quant": "NVFP4", "type": "moe", "params_b": 230,
                                        "active_b": 4, "weights_gb": 132.6, "ctx": 1048576}
B.MODELS["DeepSeek-V4-Flash-fp8"] = {"quant": "FP8", "type": "moe", "params_b": 160,
                                     "active_b": 6, "weights_gb": 159.6, "ctx": 1048576}

RAW_FLASH_1M = "D:/CSharpProject/BenchPlaybook/tasks/t20260930-flashnext-c12/raw"
RAW_FLASH_40K = "D:/CSharpProject/BenchPlaybook/tasks/t20261003-overnight"
RAW_DS = "D:/CSharpProject/BenchPlaybook/tasks/t20261004-dsflash-fp8/raw"
from pathlib import Path as _P
B.RAW2 = _P(RAW_FLASH_1M)  # build_doc 对 FlashNext 标签内部硬编码走 RAW2(1M)


def ds_argv():
    return ["vllm", "serve", "/root/.cache/huggingface/DeepSeek-V4-Flash-fp8",
            "--tensor-parallel-size", "2", "--distributed-executor-backend", "ray",
            "--speculative-config", '{"method":"deepseek_mtp","num_speculative_tokens":2}',
            "--kernel-config", '{"enable_flashinfer_autotune":false}',
            "--enable-auto-tool-choice", "--tool-call-parser", "deepseek_v4",
            "--served-model-name", "ds-flash", "--host", "0.0.0.0", "--port", "8000",
            "--gpu-memory-utilization", "0.85", "--max-model-len", "1048576",
            "--max-num-seqs", "8", "--max-num-batched-tokens", "8192",
            "--enable-chunked-prefill", "--enable-prefix-caching"]


def flash_argv(max_len):
    argv = ["vllm", "serve", "/root/.cache/huggingface/Qwen3.8-Flash-Next-NVFP4",
            "--tensor-parallel-size", "2", "--distributed-executor-backend", "ray",
            "--speculative-config", '{"method":"qwen4_exp_mtp","num_speculative_tokens":2}']
    if max_len > 262144:
        argv += ["--hf-overrides",
                 '{"text_config":{"max_position_embeddings":%d,"rope_scaling":{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":262144}}}' % max_len]
    argv += ["--kernel-config", '{"enable_flashinfer_autotune":false}',
             "--enable-auto-tool-choice", "--tool-call-parser", "qwen3_xml",
             "--reasoning-parser", "qwen3",
             "--served-model-name", "flash-next", "--host", "0.0.0.0", "--port", "8000",
             "--gpu-memory-utilization", "0.85", "--max-model-len", str(max_len),
             "--max-num-seqs", "8", "--max-num-batched-tokens", "8192",
             "--enable-chunked-prefill", "--enable-prefix-caching"]
    return argv


_orig_scenario = B.scenario


def scenario(tag, model, tp, noauto, extra_flags=(), max_len=40960):
    row = _orig_scenario(tag, model, tp, noauto, extra_flags, max_len)
    if tag.startswith("FlashNext"):
        ml = 1048576 if "1M" in tag else 40960
        argv = flash_argv(ml)
        row["notes"] = ("2026-10-04 复测(1M 参数不变, 关 FlashInfer 自调优防死锁): "
                        "能力电池扩至 12 套件(MATH-500 开思考链/CMMLU/CEval/IFEval); "
                        "qwen4_exp 新架构, 132.64GB 权重, MTP k=2") if "1M" in tag else (
            "40960 上下文对照场景(过夜批次, 八套件时期数据); "
            "Track3 工具选择 8/8 但 l2 计算题模型弃用工具直接心算(行为特征如实记录)")
    elif tag.startswith("DsFlash"):
        argv = ds_argv()
        row["notes"] = ("deepseek_v4 架构在本集群首测(M0: models/DeepSeek-V4-Flash-fp8.profile.json); "
                        "159.6GB FP8 原生 1M(配置自带 yarn16, 无需 hf-overrides); "
                        "MLA 单 KV 头; MTP deepseek_mtp k=2; 工具 parser=deepseek_v4")
    else:
        return row
    row["vllm_args"] = argv
    row["scenario_id"] = hashlib.sha1(
        (" ".join(argv) + model + str(tp)).encode()).hexdigest()[:8]
    return row


B.scenario = scenario

from datetime import datetime
from pathlib import Path
import json
PATH_RAW = Path("D:/CSharpProject/BenchPlaybook/tasks/t20260930-matrix-full/raw4")
machines = B.machines_part()
scs = []
for t in B.TAGS:
    tag = t[0]
    if tag.startswith("FlashNext"):
        B.RAW = _P(RAW_FLASH_1M if "1M" in tag else RAW_FLASH_40K)
    elif tag.startswith("DsFlash"):
        B.RAW = _P(RAW_DS)
    else:
        B.RAW = PATH_RAW
    if not (B.RAW / tag).exists():
        continue
    scs.append(B.scenario(*t))
doc = {"meta": {"contract_version": "4",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "source_artifacts": ["tasks/t20260930-matrix-full/raw4",
                                     "tasks/t20261003-overnight",
                                     "tasks/t20260930-flashnext-c12/raw",
                                     "tasks/t20261004-dsflash-fp8/raw"],
                "fingerprint": B.FP},
       "machines": machines, "scenarios": scs,
       "recommendation": B.recommend(scs)}
import jsonschema
jsonschema.validate(doc, B.SCHEMA)
out = PATH_RAW.parent / "report_doc.json"
out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
print("PASS 场景数:", len(scs), [s["scenario_id"] for s in scs])
