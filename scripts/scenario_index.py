#!/usr/bin/env python3
"""scenario_index.py — 场景索引层：从 report_doc.json 抽取扁平记录 → 全局可查.

每条记录 = 一个场景的关键字段（跨任务持久累积），用于：
  1. 新机器/新模型入场时的 §5 检索（"近似场景做了什么配置，结果如何"）
  2. 跨任务趋势查询（"所有 MTP 场景的接受率趋势"）
  3. 喂入知识库 Qdrant 的结构化来源

用法:
  # 索引单个任务: python scenario_index.py <report_doc.json>
  # 查询:        python scenario_index.py --query "TP2+MTP"
  #               python scenario_index.py --query "model=Flash-Next metric=mtp_acc"
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

BP = Path(__file__).resolve().parent.parent
INDEX = BP / "archive" / "scenario_index.jsonl"


def extract_records(doc_path):
    """从 report_doc.json 抽取每个场景的扁平记录."""
    doc = json.loads(Path(doc_path).read_text(encoding="utf-8"))
    records = []
    for sc in doc.get("scenarios", []):
        md = sc["model"]
        st = sc["vllm_metrics"]["startup"]
        argv = " ".join(sc["vllm_args"])
        dep = sc["deployment"]
        caps = {c["suite_id"]: c["score"]["acc"] for c in sc["capability_scores"]["suites"] if c.get("score")}
        ag = (sc.get("agent_metrics") or {}).get("metrics", {})

        # 性能关键数（取 w1 的各档）
        workloads = sc.get("perf_metrics", {}).get("workloads", [])
        perf_levels = {}
        roofline_util = None
        for w in workloads:
            for lv in w.get("levels", []):
                key = f"c{lv['concurrency']}"
                perf_levels[key] = {
                    "ttft_p50_ms": (lv.get("ttft_ms") or {}).get("p50"),
                    "tpot_p50_ms": (lv.get("tpot_ms") or {}).get("p50"),
                    "output_tok_s": (lv.get("agg") or {}).get("output_tok_s"),
                    "goodput_pct": (lv.get("slo") or {}).get("goodput_pct"),
                }
            if w.get("roofline"):
                roofline_util = w["roofline"].get("utilization")

        # MTP 接受率（从 vllm_metrics 的直方图段取或从 notes 解析）
        mtp_acc = None
        vm = sc.get("vllm_metrics", {})
        for seg_name in ("perf", "cap"):
            seg = vm.get("counters", {}).get(f"phase:{seg_name}", {})

        record = {
            # 身份
            "scenario_id": sc["scenario_id"],
            "model": md["name"],
            "model_arch": md.get("arch", {}).get("type"),
            "model_quant": md.get("quant"),
            "model_params_b": md.get("arch", {}).get("params_b"),
            "model_active_b": md.get("arch", {}).get("active_b"),
            "weights_gb": md.get("weights_gb"),
            "context_len": md.get("context_len"),
            "native_context": md.get("native_context"),

            # 集群
            "tp": dep.get("mode", "").count("tp") and int(re.search(r"tp(\d+)", dep.get("mode", "")).group(1)) if "tp" in dep.get("mode", "") else 1,
            "cluster_mode": dep.get("mode"),
            "machines": len(dep.get("machines", [])),

            # 关键 vLLM 参数
            "has_ep": "--enable-expert-parallel" in argv,
            "has_mtp": "--speculative-config" in argv,
            "mtp_k": int(re.search(r"num_speculative_tokens.{0,3}(\d+)", argv).group(1)) if "num_speculative_tokens" in argv else 0,
            "has_tool_parser": "--tool-call-parser" in argv,
            "tool_parser": re.search(r"--tool-call-parser (\S+)", argv).group(1) if "--tool-call-parser" in argv else None,
            "autotune_off": "enable_flashinfer_autotune" in argv and "false" in argv,

            # 服务端
            "kv_pool_tokens": st.get("kv_cache_tokens"),
            "max_concurrency_x": st.get("max_concurrency_x"),
            "ready_s": st.get("ready_s"),
            "gpu_mem_util": st.get("gpu_mem_util"),

            # 性能关键数
            "perf": perf_levels,
            "roofline_util": roofline_util,

            # 能力（各套件 acc）
            "capability": caps,

            # 智能体
            "agent_selection": ag.get("selection_acc"),
            "agent_loop": ag.get("loop_success"),
            "agent_args": ag.get("args_acc"),

            # 元数据
            "status": sc.get("status"),
            "task_id": doc.get("meta", {}).get("source_artifacts", [""])[0].split("/")[-2] if doc.get("meta", {}).get("source_artifacts") else None,
            "fingerprint": doc.get("meta", {}).get("fingerprint", {}),
            "indexed_at": datetime.now().isoformat(timespec="seconds"),
            "raw_dir": sc.get("evidence", {}).get("raw_dir"),
        }
        records.append(record)
    return records


def append_index(records, index_path=INDEX):
    """追加到全局索引（幂等：同 scenario_id 覆盖旧记录）."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if index_path.exists():
        for line in index_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                existing[rec["scenario_id"]] = rec
    for r in records:
        existing[r["scenario_id"]] = r  # 覆盖同 ID
    lines = [json.dumps(existing[k], ensure_ascii=False) for k in sorted(existing)]
    index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"索引: {len(records)} 条追加/更新 → {index_path}（总计 {len(existing)} 条）")


def query_index(query_str, index_path=INDEX):
    """简易查询: 关键词匹配 + 数值比较."""
    if not index_path.exists():
        print("索引为空")
        return
    records = [json.loads(l) for l in index_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    # 解析查询: "model=Flash-Next" / "tp=2" / "mtp_acc>0.7" / "TP2+MTP"
    filters = []
    for part in query_str.split():
        if "=" in part:
            k, v = part.split("=", 1)
            filters.append(("eq", k, v))
        elif ">" in part:
            k, v = part.split(">", 1)
            filters.append(("gt", k, float(v)))
        elif "<" in part:
            k, v = part.split("<", 1)
            filters.append(("lt", k, float(v)))
        else:
            filters.append(("kw", None, part))

    results = []
    for r in records:
        match = True
        for op, key, val in filters:
            if op == "kw":
                s = json.dumps(r, ensure_ascii=False).lower()
                if val.lower() not in s:
                    match = False
                    break
            elif op == "eq":
                rv = _get(r, key)
                if str(rv).lower() != str(val).lower():
                    match = False
                    break
            elif op == "gt":
                rv = _get(r, key)
                if rv is None or not isinstance(rv, (int, float)) or rv <= val:
                    match = False
                    break
            elif op == "lt":
                rv = _get(r, key)
                if rv is None or not isinstance(rv, (int, float)) or rv >= val:
                    match = False
                    break
        if match:
            results.append(r)

    print(f"命中 {len(results)}/{len(records)} 条:")
    for r in results:
        c1 = (r.get("perf", {}).get("c1", {}) or {})
        print(f"  {r['scenario_id']} | {r['model'][:28]:<28} | {r['cluster_mode']:<16} "
              f"| MTP{r.get('mtp_k', 0)} | c1={c1.get('output_tok_s', '—')} "
              f"| gsm8k={r.get('capability', {}).get('gsm8k', '—')} "
              f"| kv={r.get('kv_pool_tokens', '—')}")
    return results


def _get(record, dotpath):
    """按 a.b.c 取嵌套值."""
    parts = dotpath.split(".")
    cur = record
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return None
    return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("doc", nargs="?", help="report_doc.json（索引模式）")
    ap.add_argument("--query", "-q", help="查询模式")
    ap.add_argument("--index", default=str(INDEX))
    args = ap.parse_args()

    if args.query:
        query_index(args.query, Path(args.index))
    elif args.doc:
        records = extract_records(args.doc)
        append_index(records, Path(args.index))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
