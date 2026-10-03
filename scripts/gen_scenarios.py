#!/usr/bin/env python3
"""gen_scenarios.py — 阶段6 场景生成器(代码化): profile → 参数×集群×模型专用 组合矩阵.

输入: models/*.profile.json (2a/2b/2c 产物, 含 dedicated 字段)
输出: 场景清单 JSON(每场景: argv/部署/用途/专用flags/电池命令) + 打印 cell 命令行
规则(SKILL A1/A4): 一组合=完整argv=场景; agent用途含能力flags开关两档; 专用参数来自profile.
用法: python gen_scenarios.py [--models a,b] [--out scenarios.json]
"""
import argparse
import glob
import hashlib
import json
from pathlib import Path

BP = Path(__file__).resolve().parent.parent
PROFILES = BP / "models"


def load_profile(name):
    p = PROFILES / f"{name}.profile.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def combos_for(prof, model_dir_name):
    """按 profile 展开该模型的场景组合(服务轴×集群轴×专用轴)."""
    mtp = prof.get("mtp", {})
    ctx_native = (prof.get("context") or {}).get("native_max_position") or 40960
    is_moe = (prof.get("params", {}).get("experts") or 0) > 1 or \
             "moe" in (prof.get("model_type") or "")
    method = mtp.get("suggested_method") or "mtp"
    k = mtp.get("k_suggestion") or 0
    q = (prof.get("quant") or "").upper()
    # 模型专用 flags(来自 2a/2b 调研, 落在 profile.dedicated 或按已知家族推导)
    ded = prof.get("dedicated") or {}
    no_auto_tune = is_moe and "flashinfer" in json.dumps(prof).lower()
    rope_1m = ctx_native < 1048576
    rope_flag = (f'--hf-overrides {{"text_config":{{"max_position_embeddings":1048576,'
                 f'"rope_scaling":{{"rope_type":"yarn","factor":4.0,'
                 f'"original_max_position_embeddings":{ctx_native}}}}}}}') if rope_1m else ""
    spec_flag = (f"--speculative-config {{\"method\":\"{method}\","
                 f"\"num_speculative_tokens\":{k}}}") if mtp.get("has_mtp_weights") and k else ""
    combos = []
    # 基线档: TP1(单机) / TP2(双机), 上下文 native
    for tp in (1, 2):
        combos.append({"tag": f"TP{tp}", "tp": tp, "ep": False, "spec": False,
                       "ctx": ctx_native, "extra": [], "cluster": "single" if tp == 1 else "ray-2node"})
    # 双机扩展档
    if is_moe and 2 in (1, 2):
        combos.append({"tag": "TP2+EP", "tp": 2, "ep": True, "spec": False,
                       "ctx": ctx_native, "extra": ["--enable-expert-parallel"], "cluster": "ray-2node"})
    if spec_flag:
        base_extra = (["--enable-expert-parallel"] if is_moe else []) 
        combos.append({"tag": "TP2+MTP", "tp": 2, "ep": is_moe, "spec": True,
                       "ctx": ctx_native, "extra": base_extra, "spec_flag": spec_flag,
                       "cluster": "ray-2node"})
        if rope_1m:
            combos.append({"tag": "TP2+MTP+1M", "tp": 2, "ep": is_moe, "spec": True,
                           "ctx": 1048576, "extra": base_extra + [rope_flag],
                           "spec_flag": spec_flag, "cluster": "ray-2node"})
    # agent用途档: 工具flags开关两档(基于最优组合)
    if combos:
        best = combos[-1]
        combos.append({**best, "tag": best["tag"] + "+agent", "usage": "agent",
                       "tool_flags": ["--enable-auto-tool-choice",
                                      "--tool-call-parser",
                                      prof.get("tool_calling", {}).get("parser_hint") or "hermes",
                                      "--reasoning-parser", "qwen3"]})
        combos.append({**best, "tag": best["tag"] + "+agent-off", "usage": "agent-对比(工具flags关)"})
    out = []
    for c in combos:
        argv = ["vllm", "serve", f"/root/.cache/huggingface/{model_dir_name}",
                "--tensor-parallel-size", str(c["tp"])]
        if c["tp"] > 1:
            argv += ["--distributed-executor-backend", "ray"]
        argv += c.get("extra", [])
        if c.get("spec"):
            argv += [c["spec_flag"]]
        argv += c.get("tool_flags", [])
        if no_auto_tune:
            argv += ["--kernel-config", '{"enable_flashinfer_autotune":false}']
        argv += ["--served-model-name", "bench", "--host", "0.0.0.0", "--port", "8000",
                 "--gpu-memory-utilization", "0.85", "--max-model-len", str(c["ctx"]),
                 "--max-num-seqs", "64", "--enable-chunked-prefill", "--enable-prefix-caching"]
        out.append({**c, "argv": argv,
                    "scenario_id": hashlib.sha1(
                        (" ".join(argv) + model_dir_name + str(c["tp"])).encode()).hexdigest()[:8]})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(
        Path(p).stem.replace(".profile", "") for p in glob.glob(str(PROFILES / "*.profile.json"))))
    ap.add_argument("--out", default=str(BP / "tasks" / "scenarios_pending.json"))
    args = ap.parse_args()
    allsc = {}
    for name in args.models.split(","):
        name = name.strip()
        prof = load_profile(name)
        if not prof:
            print(f"⚠ {name}: 无 profile(阶段2a未跑) — 跳过, 先跑 model_profile.py")
            continue
        scs = combos_for(prof, prof.get("model_dir_name") or name)
        allsc[name] = scs
        print(f"== {name} ({len(scs)} 组合) ==")
        for s in scs:
            print(f"  {s['scenario_id']} {s['tag']:<22} {s['cluster']:<10} ctx={s['ctx']}")
    Path(args.out).write_text(json.dumps(allsc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("→", args.out)


if __name__ == "__main__":
    main()
