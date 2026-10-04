#!/usr/bin/env python3
"""add_scenario.py — 报告后增量追加新场景.

人类看了报告说"我想试试 TP2+EP+MTP3" → Agent 判断可行性 → 可行则跑电池 → 合入报告.

用法:
  # 交互式(Agent判断): python add_scenario.py <model_profile> "TP2+EP+MTP3+parser"
  # 或直接传参数:     python add_scenario.py <model_profile> --tp 2 --ep --mtp-k 3 --parser qwen3_xml

流程:
  1. 解析人类需求 → 参数组合
  2. gen_scenarios Layer2 裁决 (可行/不可行/被包含/已测)
  3. 可行且未测 → 生成 cell 命令 → 跑电池 → 落 raw/
  4. build7 + report_gen4 重出报告(含新场景)
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

BP = Path(__file__).resolve().parent.parent

# 复用 gen_scenarios 的裁决
sys.path.insert(0, str(BP / "scripts"))
from gen_scenarios import adjudicate, build_argv, REQUEST_AXES


def parse_request(request_str):
    """解析人类自然语言参数组合请求 → dict."""
    combo = {"tp": 1, "ep": False, "mtp_k": 0, "parser": None, "autotune": False}
    s = request_str.lower()
    if "tp2" in s or "tp=2" in s: combo["tp"] = 2
    if "tp1" in s or "tp=1" in s: combo["tp"] = 1
    if "ep" in s and "ep=" not in s: combo["ep"] = True
    if "mtp3" in s or "k=3" in s: combo["mtp_k"] = 3
    elif "mtp2" in s or "k=2" in s: combo["mtp_k"] = 2
    elif "mtp1" in s or "k=1" in s: combo["mtp_k"] = 1
    elif "mtp" in s: combo["mtp_k"] = 2  # 默认k=2
    if "parser" in s or "tool" in s or "agent" in s:
        combo["parser"] = "qwen3_xml"
    return combo


def check_already_tested(combo, report_doc_path):
    """检查该组合是否已在现有报告中（比对 serve 参数）."""
    if not Path(report_doc_path).exists():
        return False, None
    doc = json.loads(Path(report_doc_path).read_text(encoding="utf-8"))
    for sc in doc.get("scenarios", []):
        argv = " ".join(sc.get("vllm_args", []))
        match = True
        if combo["tp"] == 2 and "--tensor-parallel-size 2" not in argv: match = False
        if combo["tp"] == 1 and "--tensor-parallel-size 1" not in argv: match = False
        if combo["ep"] and "--enable-expert-parallel" not in argv: match = False
        if not combo["ep"] and "--enable-expert-parallel" in argv: match = False
        if combo["mtp_k"] > 0 and "--speculative-config" not in argv: match = False
        if combo["mtp_k"] == 0 and "--speculative-config" in argv: match = False
        if combo["parser"] and "--tool-call-parser" not in argv: match = False
        if not combo["parser"] and "--tool-call-parser" in argv: match = False
        if match:
            return True, sc["scenario_id"]
    return False, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile", help="models/<name>.profile.json")
    ap.add_argument("request", nargs="?", help='自然语言: "TP2+EP+MTP3+parser"')
    ap.add_argument("--tp", type=int, default=None)
    ap.add_argument("--ep", action="store_true")
    ap.add_argument("--mtp-k", type=int, default=None)
    ap.add_argument("--parser", default=None)
    ap.add_argument("--report", default=str(BP / "tasks" / "t20260930-matrix-full" / "report_doc.json"))
    ap.add_argument("--mem-gb", type=float, default=205)
    ap.add_argument("--nodes", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true", help="只裁决不执行")
    args = ap.parse_args()

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))

    # 构建参数组合
    if args.request:
        combo = parse_request(args.request)
    else:
        combo = {"tp": args.tp or 1, "ep": args.ep, "mtp_k": args.mtp_k or 0,
                 "parser": args.parser, "autotune": False}
    if args.tp: combo["tp"] = args.tp
    if args.mtp_k is not None: combo["mtp_k"] = args.mtp_k
    if args.parser: combo["parser"] = args.parser

    print(f"请求参数组合: TP{combo['tp']} EP{'✓' if combo['ep'] else '✗'} "
          f"MTP{combo['mtp_k'] or '✗'} Parser{combo['parser'] or '✗'}")

    # Step 1: Layer2 裁决
    machine_info = {"usable_mem_gb": args.mem_gb, "num_nodes": args.nodes}
    verdict = adjudicate(combo, profile, machine_info, [])
    print(f"裁决: {verdict['verdict']} — {verdict['reason'] or 'OK'}")

    if verdict["verdict"] != "feasible":
        print("→ 不执行（不可行/不适用/被包含）")
        return

    # Step 2: 检查是否已测
    already, sid = check_already_tested(combo, args.report)
    if already:
        print(f"→ 已在报告中（场景 {sid}），无需重跑")
        return

    # Step 3: 生成 cell 命令
    argv = build_argv(combo, profile)
    sid = hashlib.sha1((" ".join(argv) + profile.get("model_dir", "")).encode()).hexdigest()[:8]
    print(f"→ 新场景 {sid}，argv:")
    print("  " + " ".join(argv[:8]) + " ...")
    print(f"  工作负载矩阵: {len(REQUEST_AXES['input_len'])}种输入×"
          f"{len(REQUEST_AXES['concurrency'])}种并发×"
          f"{len(REQUEST_AXES['output_len'])}种输出")

    if args.dry_run:
        print("→ dry-run 模式，不执行")
        return

    # Step 4: 输出可执行的 cell 命令
    tag = f"TP{combo['tp']}"
    if combo["ep"]: tag += "EP"
    if combo["mtp_k"]: tag += f"MTP{combo['mtp_k']}"
    if combo["parser"]: tag += "+tool"
    extra_flags = []
    if combo["ep"]: extra_flags.append("--enable-expert-parallel")
    if combo["mtp_k"] > 0:
        method = profile.get("mtp", {}).get("suggested_method", "mtp")
        extra_flags.append(f"--speculative-config {{\"method\":\"{method}\",\"num_speculative_tokens\":{combo['mtp_k']}}}")
    if combo["parser"]:
        extra_flags.extend(["--enable-auto-tool-choice", "--tool-call-parser", combo["parser"],
                            "--reasoning-parser", "qwen3"])
    extra_flags.append("--kernel-config {\"enable_flashinfer_autotune\":false}")

    print(f"\n执行命令:")
    print(f"  bash scripts/cell4.sh {combo['tp']} {profile['model_dir']} "
          f"{profile.get('weights',{}).get('total_gb',10)} {tag} '{' '.join(extra_flags)}'")
    print(f"\n完成后合入报告:")
    print(f"  python scripts/build7.py && python scripts/report_gen4.py <doc> <out> [模型过滤]")


if __name__ == "__main__":
    main()
