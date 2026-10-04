#!/usr/bin/env python3
"""矩阵产物 → rows.jsonl (schema v3).

输入: tasks/t20260930-matrix-full/raw/<tag>/{perf,cap}.json + metrics_{idle,perf,cap}.json
环境块(machines/cluster/vllm_args/launch_env/params)沿用 t20261001-full-report 实测
(本会话未动环境, merge 时可传 --fingerprint 复核), 只重采 bench/capability/metrics.
行序: r001=TP2-35B r002=TP1-35B r003=TP2-27B r004=TP1-27B(与旧报告对齐).

用法: python merge_rows.py <raw_dir> <old_rows.jsonl> <out_rows.jsonl>
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "D:/CSharpProject/Vllm_Benchmark")
from bench.common import metrics_delta, METRIC_KEYS

ORDER = [  # (run_id, tp, model子串, 新tag)
    ("r001", 2, "Qwen3.6", "TP2-Qwen3.6"),
    ("r002", 1, "Qwen3.6", "TP1-Qwen3.6"),
    ("r003", 2, "Qwen3.8", "TP2-Qwen3.8"),
    ("r004", 1, "Qwen3.8", "TP1-Qwen3.8"),
]

# KV 容量/最大并发倍数: 源自 vLLM 启动日志(kv_cache_utils), 旧serve未持久化启动日志,
# 有实测值的组合如实标注来源, 没有的标 None(渲染为 —, v3.1 起serve.sh持久化该两行).
KV_INFO = {
    "TP2-Qwen3.6": {"kv_capacity_tokens": 13786190, "max_concurrency_x": 336,
                    "kv_source": "t20261001 r001 实测(同指纹环境)"},
    "TP1-Qwen3.8": {"kv_capacity_tokens": 1942496, "max_concurrency_x": 47.4,
                    "kv_source": "本会话 vllm.log 启动行"},
}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def main():
    raw = Path(sys.argv[1])
    old_rows = [json.loads(l) for l in open(sys.argv[2], encoding="utf-8") if l.strip()]
    out_path = Path(sys.argv[3])
    lines = []
    for rid, tp, mkey, tag in ORDER:
        d = raw / tag
        old = next((o for o in old_rows
                    if o.get("params", {}).get("tp") == tp
                    and mkey in o.get("params", {}).get("model", "")), None)
        if old is None:
            print(f"WARN {tag}: 旧行缺失, 环境块将为空")
            old = {}
        perf = load(d / "perf.json")
        cap = load(d / "cap.json")

        # perf: phases → c{n} 键
        perf_levels = {("c%d" % p["concurrency"]): p for p in perf["phases"]}

        # vllm_metrics: 两段差值(idle→perf, perf→cap)
        m_idle = load(d / "metrics_idle.json")
        m_perf = load(d / "metrics_perf.json")
        m_cap = load(d / "metrics_cap.json")
        vm = {
            "perf": metrics_delta(m_perf, m_idle, METRIC_KEYS),
            "cap": metrics_delta(m_cap, m_perf, METRIC_KEYS),
        }
        # 派生: 成功=stop+length(正常完结), 失败=abort+error
        for seg in ("perf", "cap"):
            segd = vm[seg]
            segd["requests_success"] = round(
                (segd.pop("requests_stop", 0) or 0) + (segd.pop("requests_length", 0) or 0), 3)
            segd["requests_failed"] = round(
                (segd.pop("requests_abort", 0) or 0) + (segd.pop("requests_error", 0) or 0), 3)

        cap_out = {}
        for s, v in cap["suites"].items():
            cap_out[s] = {"acc": v["acc"], "n": v["n"], "correct": v["correct"],
                          "avg_completion_tokens": v["avg_completion_tokens"],
                          "requests_failed": v["requests_failed"],
                          "mode": v["mode"]}

        # serve 就绪耗时(serve.log: "PASS vLLM 就绪 (..., 耗时约 Ns)")
        serve_s = None
        slog = d / "serve.log"
        if slog.exists():
            for ln in slog.read_text(encoding="utf-8", errors="replace").splitlines():
                if "耗时约" in ln and "就绪" in ln:
                    serve_s = int("".join(ch for ch in ln.split("耗时约")[1] if ch.isdigit()))

        row = {
            "schema": "v3", "run_id": rid,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "env_base": "沿用t20261001实采环境块(本会话未变更环境; 指纹复核一致: vllm0.30.0/91d9b07/580.178.04)",
            "serve_ready_s": serve_s,
            "vllm_args": old.get("vllm_args", []),
            "launch_env": old.get("launch_env", {}),
            "machines": old.get("machines", []),
            "cluster": old.get("cluster", {}),
            "params": old.get("params", {}),
            "perf": {
                "dataset": perf["dataset"],
                "params": perf["params"],
                "levels": perf_levels,
                "duration_s": perf["duration_s"],
                "gate_pass": perf["gate_pass"],
            },
            "roofline": perf.get("roofline"),
            "capability": cap_out,
            "capability_params": cap["params"],
            "vllm_metrics": vm,
            "notes": (old.get("notes", "") or "")
                     .replace("能力分待复核", "")
                     .replace(", 指标沿用iter5原测", "")
                     .replace("指标沿用iter5原测", "")
                     .strip(" |"),
        }
        vm["capacity"] = KV_INFO.get(tag, {"kv_capacity_tokens": None,
                                           "max_concurrency_x": None,
                                           "kv_source": "旧serve未持久化启动日志(v3.1起持久化)"})
        if tag == "TP2-Qwen3.6":
            # 第五轮口径: 关 FlashInfer 自调优(跨会话 serve 时自调优确定性死亡 ~33min)
            row["vllm_args"] = row["vllm_args"] + [
                "--kernel-config", '{"enable_flashinfer_autotune": false}']
            row["params"]["flashinfer_autotune"] = False
            row["notes"] = (row["notes"] + " | 本行关FlashInfer自调优口径(自调优跨会话"
                            "确定性死亡~33min后改--kernel-config关闭, 150s即就绪; "
                            "对比旧自调优口径c1=89.6tok/s, 差<1%)").strip(" |")
        if tag == "TP1-Qwen3.8":
            row["notes"] = (row["notes"] + " | 首轮c1档遇管理面WiFi瞬时断连(8条中7条"
                            "连接失败, c8/c32正常), 本行为整组合重跑").strip(" |")
        lines.append(json.dumps(row, ensure_ascii=False))
        ok = all(v["acc"] is not None for v in cap_out.values())
        print(f"{rid} {tag}: perf={list(perf_levels)} "
              f"cap={{{', '.join('%s:%s' % (s, v['acc']) for s, v in cap_out.items())}}} "
              f"gate={'PASS' if perf['gate_pass'] else 'FAIL'} capok={ok}")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"PASS rows.jsonl(v3): {out_path} ({len(lines)} 行)")


if __name__ == "__main__":
    main()
