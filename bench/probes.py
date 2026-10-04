# -*- coding: utf-8 -*-
"""探针(REPORT-SPEC-v4 §1.5): prefix-cache 命中加速 + capacity 并发阶梯.

  prefix-cache: 64条请求共享1024tok前缀+32tok独立尾缀; 跑两轮(冷/热),
    指标 = TTFT p50 冷/热、加速比、命中数(由调用方配 /metrics 差值);
  capacity: 并发阶梯 8,16,32,48,64,72,80,每档 min(c,24) 条, 512入/64出,
    全成且无 reject/timeout → 该档 OK; 首败即停, 产出 max_ok_conc + 首败模式.

用法: python -m bench.probes --api-base URL --out probes.json
"""
import argparse
import json
import time

from .common import Client, Concurrency, pct, stdout_utf8, UTF8JSON
from .track1 import make_prompt

PREFIX = make_prompt(777, 1024)  # 固定共享前缀(1024tok 级)
LADDER = [8, 16, 32, 48, 64, 72, 80]


def prefix_probe(client, n=64):
    suffixes = [make_prompt(9000 + i, 32) for i in range(n)]

    def one_round():
        recs = [None] * n

        def one(i):
            recs[i] = client.chat_stream(
                [{"role": "user", "content": PREFIX + " " + suffixes[i]}],
                max_tokens=16, temperature=0.0, seed=9000 + i, ignore_eos=True)

        Concurrency(8).map_collect(range(n), lambda i, _k: one(i), lambda _r: None)
        ok = [r["ttft_ms"] for r in recs if r and r["ok"]]
        return ok, len([r for r in recs if r is None or not r["ok"]])

    cold, f1 = one_round()
    warm, f2 = one_round()  # 同前缀第二轮, KV 前缀缓存应命中
    c50, w50 = pct(sorted(cold), 50), pct(sorted(warm), 50)
    return {"n": n, "fail_round1": f1, "fail_round2": f2,
            "ttft_cold_p50_ms": round(c50, 1) if cold else None,
            "ttft_warm_p50_ms": round(w50, 1) if warm else None,
            "speedup_x": round(c50 / w50, 2) if (cold and warm and w50 > 0) else None,
            "note": "加速比>1 且服务端 prefix_hits 增加 → 前缀缓存生效"}


def capacity_probe(client, ladder=LADDER):
    results = []
    max_ok, first_fail = None, None
    for c in ladder:
        n = min(c, 24)
        prompts = [make_prompt(50000 + c * 100 + i, 512) for i in range(n)]
        recs = [None] * n
        t0 = time.perf_counter()

        def one(i):
            recs[i] = client.chat_stream(
                [{"role": "user", "content": prompts[i]}],
                max_tokens=64, temperature=0.0, ignore_eos=True)

        Concurrency(c).map_collect(range(n), lambda i, _k: one(i), lambda _r: None)
        wall = time.perf_counter() - t0
        ok = [r for r in recs if r and r["ok"]]
        failed = n - len(ok)
        mode = "ok" if failed == 0 else (
            "timeout_or_conn" if all(not (r and r["ok"]) for r in recs) else "partial_fail")
        results.append({"concurrency": c, "n": n, "completed": len(ok),
                        "failed": failed, "wall_s": round(wall, 1),
                        "out_tok_s": round(sum(r["completion_tokens"] for r in ok) / wall, 1)
                        if ok and wall else None,
                        "mode": mode})
        print("  ladder c=%-3d ok=%d/%d %s (%.0fs)" % (c, len(ok), n, mode, wall))
        if failed == 0:
            max_ok = c
        else:
            first_fail = {"concurrency": c, "mode": mode, "failed": failed}
            break
        time.sleep(3)
    return {"ladder": results, "max_ok_conc": max_ok, "first_failure": first_fail,
            "note": "上限=max_num_seqs(64)约束下的实测可用并发"}


def main():
    stdout_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", required=True)
    ap.add_argument("--model", default="bench")
    ap.add_argument("--request-timeout-s", type=int, default=420)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    client = Client(args.api_base, args.model, timeout_s=args.request_timeout_s)

    print("probe: prefix-cache ...")
    t0 = time.time()
    pp = prefix_probe(client)
    print("  cold/warm p50 = %s/%s ms, speedup %sx" % (
        pp["ttft_cold_p50_ms"], pp["ttft_warm_p50_ms"], pp["speedup_x"]))
    print("probe: capacity ladder ...")
    cp = capacity_probe(client)
    out = {"track": "probes", "api_base": args.api_base,
           "prefix_cache": pp, "capacity": cp,
           "duration_s": round(time.time() - t0, 1)}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, **UTF8JSON)
    print("PASS probes → %s (max_ok_conc=%s, speedup=%sx)" % (
        args.out, cp["max_ok_conc"], pp["speedup_x"]))


if __name__ == "__main__":
    main()
