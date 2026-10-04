#!/usr/bin/env python3
"""gen_scenarios.py v2 — 阶段6场景生成器（三层架构）.

Layer 1: 笛卡尔积展开（仅 serve 轴：TP/EP/MTP/Parser/Autotune）
Layer 2: Agent可行驶决（物理/架构/经验/包含 → feasible/infeasible/subsumed）
Layer 3: 请求轴降维（ctx/concurrency/input_len 移到工作负载，不产独立场景）

用法: python gen_scenarios.py <model_profile.json> [--out scenarios.json]
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

# ═══════════════ Layer 1: 笛卡尔积（仅 serve 轴）═══════════════

SERVE_AXES = {
    "tp": [1, 2],
    "ep": [False, True],
    "mtp_k": [0, 1, 2, 3],
    "parser": [None, "qwen3_xml"],
    "autotune": [False, True],
}


def expand_all(model_profile):
    """Layer 1: 展开全笛卡尔积，不做任何判断."""
    keys = list(SERVE_AXES.keys())
    combos = []
    for values in itertools.product(*SERVE_AXES.values()):
        c = dict(zip(keys, values))
        combos.append(c)
    return combos


# ═══════════════ Layer 2: Agent可行驶决 ═══════════════

def adjudicate(combo, profile, machine_info, experience_entries):
    """Layer 2: 逐组合判定 feasible/infeasible/subsumed/not_applicable.

    Args:
        combo: 笛卡尔积中的一个组合 {tp, ep, mtp_k, parser, autotune}
        profile: M0 model profile (weights_gb, mtp, arch, context...)
        machine_info: {total_mem_gb, usable_mem_gb, num_nodes, gpu_per_node}
        experience_entries: 已知失败/避坑经验条目列表
    Returns:
        {"verdict": "feasible"|"infeasible"|"subsumed"|"not_applicable",
         "reason": str, "subsumed_by": str|None}
    """
    w_gb = profile.get("weights", {}).get("total_gb", 0)
    arch_type = "moe" if profile.get("params", {}).get("expert_weights_present") else "dense"
    has_mtp = profile.get("mtp", {}).get("has_mtp_weights", False)
    native_ctx = profile.get("context", {}).get("native_max_position", 40960)

    # --- 物理不可行 ---
    # TP=n 需要 n 台机器各有足够内存; 单机可用 ≈ total/n
    per_machine = machine_info.get("usable_mem_gb", 200) / max(machine_info.get("num_nodes", 2), combo["tp"])
    mem_per_node = w_gb / combo["tp"]  # TP均分权重
    if mem_per_node > per_machine * 0.95:  # 留5%给激活等
        return {"verdict": "infeasible",
                "reason": f"TP{combo['tp']}均分{mem_per_node:.0f}GB/机 > 可用{per_machine:.0f}GB/机",
                "subsumed_by": None}
    if machine_info.get("num_nodes", 2) < combo["tp"]:
        return {"verdict": "infeasible",
                "reason": f"TP{combo['tp']}需要{combo['tp']}机, 现有{machine_info['num_nodes']}机",
                "subsumed_by": None}

    # --- 架构不适用 ---
    if combo["ep"] and arch_type == "dense":
        return {"verdict": "not_applicable",
                "reason": "稠密模型无专家可并行(EP仅对MoE有意义)", "subsumed_by": None}
    if combo["mtp_k"] > 0 and not has_mtp:
        return {"verdict": "not_applicable",
                "reason": "模型无MTP权重, 投机解码不可用", "subsumed_by": None}
    if combo["ep"] and machine_info.get("num_nodes", 2) < 2:
        return {"verdict": "not_applicable",
                "reason": "EP需要多节点", "subsumed_by": None}

    # --- 已知失败（经验库匹配）---
    for entry in experience_entries:
        text = json.dumps(entry, ensure_ascii=False).lower()
        if combo["autotune"] and "autotune" in text and "死锁" in text:
            return {"verdict": "infeasible",
                    "reason": "FlashInfer自调优跨会话确定性死锁(经验库已确认)",
                    "subsumed_by": None}

    # --- 被包含（subsumption优化）---
    # 规则: 同一 TP/EP/MTP/Parser 下, autotune=True 被 autotune=False 包含
    #        （因为 autotune=False 是我们的默认推荐, 且性能差<1%）
    if combo["autotune"]:
        return {"verdict": "subsumed",
                "reason": "autotune=off 场景已覆盖（实测差<1%, 且on会死锁）",
                "subsumed_by": "autotune=off 同参组合"}

    # MTP k=1 被 k=2 包含（k=2 是实测最优, k=1 是其子集性能）
    if combo["mtp_k"] == 1 and has_mtp:
        return {"verdict": "subsumed",
                "reason": "k=2 场景已覆盖（k=1 接受率是 k=2 的子集）",
                "subsumed_by": "mtp_k=2 同参组合"}

    # --- 可行 ---
    return {"verdict": "feasible", "reason": "", "subsumed_by": None}


# ═══════════════ Layer 3: 场景生成（请求轴=工作负载）═══════════════

REQUEST_AXES = {
    "input_len": [32, 512, 4096, 131072, 524288],
    "concurrency": [1, 8, 16, 32, 64],
    "output_len": [8, 256, 1024],
}


def build_argv(combo, profile, max_len=1048576):
    """从可行组合构建完整 vLLM argv."""
    model_dir = profile.get("model_dir", "MODEL")
    argv = ["vllm", "serve", model_dir,
            "--tensor-parallel-size", str(combo["tp"])]
    if combo["tp"] > 1:
        argv += ["--distributed-executor-backend", "ray"]
    if combo["ep"]:
        argv += ["--enable-expert-parallel"]
    if combo["mtp_k"] > 0:
        method = profile.get("mtp", {}).get("suggested_method", "mtp")
        argv += ["--speculative-config",
                 f'{{"method":"{method}","num_speculative_tokens":{combo["mtp_k"]}}}']
    if combo["parser"]:
        argv += ["--enable-auto-tool-choice", "--tool-call-parser", combo["parser"],
                 "--reasoning-parser", "qwen3"]
    if not combo["autotune"]:
        argv += ["--kernel-config", '{"enable_flashinfer_autotune":false}']
    argv += ["--served-model-name", "bench",
             "--host", "0.0.0.0", "--port", "8000",
             "--gpu-memory-utilization", "0.85",
             "--max-model-len", str(max_len),
             "--max-num-seqs", "64",
             "--max-num-batched-tokens", "8192",
             "--enable-chunked-prefill", "--enable-prefix-caching"]
    return argv


def generate(profile_path, out_path, machine_mem_gb=205, num_nodes=2,
             experience_file=None):
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    machine_info = {"usable_mem_gb": machine_mem_gb, "num_nodes": num_nodes}

    exp_entries = []
    if experience_file and Path(experience_file).exists():
        exp_entries = json.loads(Path(experience_file).read_text(encoding="utf-8"))

    # Layer 1
    all_combos = expand_all(profile)
    print(f"Layer 1 笛卡尔积: {len(all_combos)} 组合")

    # Layer 2
    results = []
    for c in all_combos:
        verdict = adjudicate(c, profile, machine_info, exp_entries)
        results.append({**c, **verdict})

    feasible = [r for r in results if r["verdict"] == "feasible"]
    infeasible = [r for r in results if r["verdict"] == "infeasible"]
    not_app = [r for r in results if r["verdict"] == "not_applicable"]
    subsumed = [r for r in results if r["verdict"] == "subsumed"]
    print(f"Layer 2 裁决: ✅{len(feasible)}可行 | ❌{len(infeasible)}不可行 | "
          f"⚠️{len(not_app)}不适用 | 📦{len(subsumed)}被包含")

    # Layer 3: 为每个可行组合生成 cell 命令
    scenarios = []
    for r in feasible:
        argv = build_argv(r, profile)
        sid = hashlib.sha1((" ".join(argv) + profile.get("model_dir", "")).encode()).hexdigest()[:8]
        scenarios.append({
            "scenario_id": sid,
            "serve_params": {k: r[k] for k in SERVE_AXES},
            "argv": argv,
            "request_axes": REQUEST_AXES,  # 请求轴全扫（不产独立场景）
            "workload_matrix": {
                "input_lengths": REQUEST_AXES["input_len"],
                "concurrency_levels": REQUEST_AXES["concurrency"],
                "output_lengths": REQUEST_AXES["output_len"],
            },
        })
    print(f"Layer 3 最终场景: {len(scenarios)} 个 serve 配置（每个内含完整工作负载矩阵）")

    # 输出
    output = {
        "model": profile.get("model_dir", "?"),
        "layer1_total": len(all_combos),
        "layer2_breakdown": {
            "feasible": len(feasible),
            "infeasible": len(infeasible),
            "not_applicable": len(not_app),
            "subsumed": len(subsumed),
        },
        "layer2_detail": results,
        "layer3_scenarios": scenarios,
    }
    Path(out_path).write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {out_path}")

    # 打印摘要
    print("\n可行场景:")
    for s in scenarios:
        sp = s["serve_params"]
        print(f"  {s['scenario_id']} TP{sp['tp']} EP{'✓' if sp['ep'] else '✗'} "
              f"MTP{sp['mtp_k'] or '✗'} Parser{sp['parser'] or '✗'} "
              f"AT{'✓' if sp['autotune'] else '✗'}")
    print("\n不可行/不适用/被包含:")
    for r in infeasible + not_app + subsumed:
        print(f"  {r['verdict']:>14} TP{r['tp']} EP{'✓' if r['ep'] else '✗'} "
              f"MTP{r['mtp_k']} Parser{r['parser'] or '—'} "
              f"AT{'✓' if r['autotune'] else '✗'} — {r['reason']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", help="models/<name>.profile.json")
    ap.add_argument("--out", default="scenarios.json")
    ap.add_argument("--mem-gb", type=float, default=205, help="双机可用总内存GB")
    ap.add_argument("--nodes", type=int, default=2)
    ap.add_argument("--experience", default=None, help="经验库JSON文件")
    args = ap.parse_args()
    generate(args.profile, args.out, args.mem_gb, args.nodes, args.experience)
