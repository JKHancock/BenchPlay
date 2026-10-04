# -*- coding: utf-8 -*-
"""Track1 性能基准 v4 (契约 REPORT-SPEC-v4 §1.5).

工作负载注册表(负载即契约):
  w1 random-512x256  吞吐上限探针  c1/c8/c32   n 8/32/48
  w2 real-sharegpt   真实分布      c1/c8       n 16/48   (data/prompts.jsonl)
  w3 short-32x8      对话延迟档    c1/c8       n 24/48
  w4 long-4096x256   长文预填      c1/c4       n 4/8
  w5 outladder       TTFT/长输出   c1 n1/out_len
  w6 c64             满序列批      c64 n64
指标族: ttft/tpot{mean,p50,p90,p99,max} · itl{p50,p99,max} · e2e{p50,p90,p99}
        · per_stream{p50,p99} · agg · slo.goodput · reliability · roofline(c1)

用法: python -m bench.track1 --api-base URL --workload w1 --out w1.json \
        [--weights-active-gb 1.7 --bw-gbps 546] [--evidence-dir ev]
"""
import argparse
import json
import os
import random
import re
import time

from .common import Client, Concurrency, GaugePoller, pct, pct3, stdout_utf8, UTF8JSON

VOCAB = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu "
         "nu xi omicron pi rho sigma tau upsilon phi chi psi omega system "
         "vector matrix kernel tensor buffer queue stream cache index shard "
         "compute memory network storage cluster node service request batch "
         "token sequence context window layer attention mlp head expert route "
         "quantize fp4 fp8 int8 gpu cpu dram nvme cuda kernel launch sync "
         "measure latency throughput percentile median tail budget capacity "
         "progress status result summary detail report chapter section item "
         "value number label name type mode flag option config default custom").split()

WORKLOADS = {
    "w1": {"input_len": 512, "output_len": 256, "levels": [1, 8, 32], "np": [8, 32, 48]},
    "w2": {"prompts_file": True, "levels": [1, 8], "np": [16, 48]},
    "w3": {"input_len": 32, "output_len": 8, "levels": [1, 8], "np": [24, 48]},
    "w4": {"input_len": 4096, "output_len": 256, "levels": [1, 4], "np": [4, 8]},
    "w5": {"input_len": 4096, "out_ladder": [1, 16, 256, 1024], "levels": [1], "np": [1]},
    "w6": {"input_len": 512, "output_len": 256, "levels": [64], "np": [64]},
    "wsweep": {"input_len": 512, "output_len": 256,
               "levels": [1, 2, 4, 8, 16, 32], "np": [8, 8, 16, 16, 32, 48]},
    "w2s": {"prompts_file": True, "levels": [1, 2, 4, 8, 16, 32],
            "np": [8, 8, 16, 16, 32, 48]},
    "w7-long128k": {"input_len": 131072, "output_len": 64, "levels": [1], "np": [1]},
}

SLO = {"ttft_ms": 500.0, "tpot_ms": 100.0}


def make_prompt(seed, target_tokens):
    rng = random.Random(seed)
    return " ".join(rng.choice(VOCAB) for _ in range(int(target_tokens * 1.3)))


def load_prompts(data_dir):
    """prompts.jsonl 是预套模板产物(<|im_start|>user ... <|im_end|>), 抽裸 user 文本."""
    path = os.path.join(data_dir, "prompts.jsonl")
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            m = re.search(r"<\|im_start\|>user\n(.*?)<\|im_end\|>", d["prompt"], re.S)
            text = m.group(1).strip() if m else d["prompt"]
            out.append({"text": text, "output_len": int(d.get("output_len") or 256),
                        "input_tokens": d.get("input_tokens")})
    return out


def dist5(vals):
    """{mean,p50,p90,p99,max}."""
    if not vals:
        return {"mean": None, "p50": None, "p90": None, "p99": None, "max": None}
    d = pct3(vals)
    d["mean"] = sum(vals) / len(vals)
    d["max"] = max(vals)
    return {k: round(v, 3) for k, v in d.items()}


def run_level(client, conc, num_prompts, prompts, output_lens, seed_base,
              levels_out, evidence, wl_id, conc_i):
    recs = [None] * num_prompts

    def one(i):
        recs[i] = client.chat_stream(
            [{"role": "user", "content": prompts[i]}],
            max_tokens=output_lens[i], temperature=0.0, seed=seed_base + i,
            ignore_eos=True, no_think=True)

    def run_subset(idxs):
        Concurrency(conc).map_collect(idxs, lambda i, _k: one(i), lambda _r: None)

    t0 = time.perf_counter()
    poller = GaugePoller(client.base).start()
    run_subset(range(num_prompts))
    retried = 0
    for round_ in range(1, 3):
        failed_idx = [i for i, r in enumerate(recs) if r is None or not r["ok"]]
        if not failed_idx:
            break
        retried += len(failed_idx)
        time.sleep(3)
        run_subset(failed_idx)
    wall = time.perf_counter() - t0
    gauge_peaks = poller.stop()

    ok = [r for r in recs if r and r["ok"]]
    failed = len([r for r in recs if r and not r["ok"]])
    dropped = len([r for r in recs if r is None])
    ttfts = [r["ttft_ms"] for r in ok]
    tpots = [r["tpot_ms"] for r in ok if r["tpot_ms"] is not None]
    itls = [x for r in ok for x in (r.get("itl_ms") or [])]
    e2es = [r["e2e_ms"] for r in ok]
    streams = [r["completion_tokens"] / (r["e2e_ms"] / 1000.0) for r in ok if r["e2e_ms"]]
    comp_sum = sum(r["completion_tokens"] for r in ok)
    prompt_sum = sum(r["prompt_tokens"] or 0 for r in ok)
    streams_d = dist5(streams)
    itl_sorted = sorted(itls)
    # SLO goodput: 单请求 TTFT≤500ms 且 TPOT≤100ms
    good = len([r for r in ok if r["ttft_ms"] <= SLO["ttft_ms"]
                and (r["tpot_ms"] is None or r["tpot_ms"] <= SLO["tpot_ms"])])
    phase = {
        "concurrency": conc, "num_prompts": num_prompts, "retried": retried,
        "ttft_ms": dist5(ttfts), "tpot_ms": dist5(tpots),
        "itl_ms": {"p50": round(pct(itl_sorted, 50), 3) if itls else None,
                   "p99": round(pct(itl_sorted, 99), 3) if itls else None,
                   "max": round(max(itls), 3) if itls else None},
        "e2e_ms": {k: v for k, v in dist5(e2es).items() if k in ("p50", "p90", "p99")},
        "per_stream_out_tok_s": {"p50": streams_d.get("p50"),
                                 "p99": streams_d.get("p99")},
        "agg": {"output_tok_s": round(comp_sum / wall, 2) if wall else None,
                "total_tok_s": round((comp_sum + prompt_sum) / wall, 2) if wall else None,
                "qps": round(len(ok) / wall, 4) if wall else None},
        "slo": {"ttft_le_ms": SLO["ttft_ms"], "tpot_le_ms": SLO["tpot_ms"],
                "goodput_pct": round(100.0 * good / len(ok), 1) if ok else None,
                "met": (good == len(ok)) if ok else None},
        "reliability": {"completed": len(ok), "failed": failed + dropped,
                        "rejected": 0, "timeout": failed + dropped},
        "wall_s": round(wall, 1),
        "gauge_peaks": {k: round(v, 4) for k, v in gauge_peaks.items()},
    }
    levels_out.append(phase)
    if evidence:
        with open(os.path.join(evidence, "req_%s_c%d.json" % (wl_id, conc)), "w",
                  encoding="utf-8") as f:
            json.dump(recs, f, **UTF8JSON)
    print("  %s c=%-3d n=%-3d TTFT %s/%s TPOT %s/%s ITLp99 %s out %s tok/s "
          "goodput %s%% ok/f=%d/%d" % (
              wl_id, conc, num_prompts,
              _f(phase["ttft_ms"]["p50"]), _f(phase["ttft_ms"]["p99"]),
              _f(phase["tpot_ms"]["p50"]), _f(phase["tpot_ms"]["p99"]),
              _f(phase["itl_ms"]["p99"]), _f(phase["agg"]["output_tok_s"]),
              _f(phase["slo"]["goodput_pct"]), len(ok), failed + dropped))
    return phase


def _f(x):
    return "—" if x is None else "%.1f" % x


def main():
    stdout_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", required=True)
    ap.add_argument("--model", default="bench")
    ap.add_argument("--workload", required=True, choices=sorted(WORKLOADS))
    ap.add_argument("--request-timeout-s", type=int, default=600)
    ap.add_argument("--cooldown-s", type=int, default=10)
    ap.add_argument("--seed", type=int, default=20260930)
    ap.add_argument("--weights-active-gb", type=float, default=0.0)
    ap.add_argument("--bw-gbps", type=float, default=273.0)
    ap.add_argument("--data-dir", default=os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))) + "/data")
    ap.add_argument("--out", required=True)
    ap.add_argument("--evidence-dir", default=None)
    args = ap.parse_args()

    wl = dict(WORKLOADS[args.workload])
    if args.evidence_dir:
        os.makedirs(args.evidence_dir, exist_ok=True)
    client = Client(args.api_base, args.model, timeout_s=args.request_timeout_s)

    # w5: 长输出阶梯, 每档一个 level 记录
    if "out_ladder" in wl:
        phases = []
        warm = client.chat_stream([{"role": "user", "content": make_prompt(1, wl["input_len"])}],
                                  max_tokens=16, ignore_eos=True)
        if not warm["ok"]:
            raise SystemExit("FAIL warmup: %s" % warm["error"])
        for li, olen in enumerate(wl["out_ladder"]):
            p = [make_prompt(args.seed + 31 * li, wl["input_len"])]
            lv = []
            run_level(client, 1, 1, p, [olen], args.seed + 1000 * li, lv,
                      args.evidence_dir, "%s-o%d" % (args.workload, olen), li)
            phases.append({"out_len": olen, **lv[0]})
        result = {"workload_id": args.workload, "kind": "outladder",
                  "spec": {"input_len": wl["input_len"],
                           "out_ladder": wl["out_ladder"], "seed": args.seed,
                           "temperature": 0.0, "ignore_eos": True, "no_think": True,
                           "warmup": 1},
                  "levels": phases, "duration_s": 0, "gate_pass":
                  all(p["reliability"]["failed"] == 0 for p in phases)}
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, **UTF8JSON)
        print("PASS %s outladder 4档" % args.workload if result["gate_pass"]
              else "FAIL %s 存在失败" % args.workload)
        raise SystemExit(0 if result["gate_pass"] else 1)

    # prompts 数据集(w2) or 合成
    if wl.get("prompts_file"):
        rows = load_prompts(args.data_dir)
        dataset = "sharegpt-real(%d条,输入p50=%dtok)" % (
            len(rows), sorted(r["input_tokens"] or 0 for r in rows)[len(rows) // 2])
        rng = random.Random(args.seed)
        rng.shuffle(rows)
    else:
        dataset = "random-%d" % wl["input_len"]

    phases = []
    warm = client.chat_stream([{"role": "user", "content": make_prompt(1, 512)}],
                              max_tokens=16, ignore_eos=True)
    if not warm["ok"]:
        raise SystemExit("FAIL warmup: %s" % warm["error"])

    t_start = time.time()
    for li, conc in enumerate(wl["levels"]):
        np_ = wl["np"][li]
        if wl.get("prompts_file"):
            sel = rows[(li * 50) % len(rows):][:np_]
            prompts = [r["text"] for r in sel]
            olens = [r["output_len"] for r in sel]
        else:
            prompts = [make_prompt(args.seed + 1000 * li + i, wl["input_len"])
                       for i in range(np_)]
            olens = [wl["output_len"]] * np_
        run_level(client, conc, np_, prompts, olens,
                  args.seed + 1000 * li, phases, args.evidence_dir,
                  args.workload, li)
        if li < len(wl["levels"]) - 1:
            time.sleep(args.cooldown_s)
    dur = round(time.time() - t_start, 1)

    bad = [p for p in phases if p["reliability"]["completed"] <= 0
           or p["reliability"]["failed"] > 0]
    roofline = None
    if args.weights_active_gb > 0:
        ceiling = args.bw_gbps / args.weights_active_gb
        c1 = next((p for p in phases if p["concurrency"] == 1), None)
        warn = None
        if c1 and c1["agg"]["output_tok_s"] and c1["agg"]["output_tok_s"] > ceiling * 0.8:
            warn = ("c1 %.1f tok/s >= 80%%x ceiling %.1f (bw=%.0f/active=%.2fGB)"
                    % (c1["agg"]["output_tok_s"], ceiling, args.bw_gbps,
                       args.weights_active_gb))
            print("  ⚠屋顶线警告: %s" % warn)
        roofline = {"ceiling_tok_s": round(ceiling, 1),
                    "c1_output_tok_s": c1["agg"]["output_tok_s"] if c1 else None,
                    "utilization": (round(c1["agg"]["output_tok_s"] / ceiling, 3)
                                    if c1 and c1["agg"]["output_tok_s"] else None),
                    "warning": warn}

    result = {
        "workload_id": args.workload,
        "spec": {"input_len": wl.get("input_len"), "output_len": wl.get("output_len"),
                 "dataset": dataset, "levels": wl["levels"], "np": wl["np"],
                 "seed": args.seed, "temperature": 0.0, "ignore_eos": True,
                 "no_think": True, "warmup": 1, "cooldown_s": args.cooldown_s},
        "levels": phases, "duration_s": dur, "roofline": roofline,
        "gate_pass": not bad,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, **UTF8JSON)
    if bad:
        print("FAIL %s 失败/空档: %s" % (args.workload, [
            (p["concurrency"], p["reliability"]) for p in bad]))
        raise SystemExit(1)
    print("PASS %s %d档 → %s" % (args.workload, len(phases), args.out))


if __name__ == "__main__":
    main()
