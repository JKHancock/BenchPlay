# -*- coding: utf-8 -*-
"""长会话浸泡测试(soak): N 路持久会话多轮增长到目标上下文, 逐轮采 vLLM 指标.

w1-w6 是一次性请求模式(定长输入×并发×单次输出), 测不到的在这里测:
  - 上下文逐轮增长时 TTFT 是否恶化(前缀缓存能否把"每轮全量重发历史"救回)
  - KV 池随会话增长的真实曲线与峰值(对照产品口径如 500K×3)
  - 多轮间前缀命中率(命中=旧历史预填被跳过)
  - 池到顶时抢占/排队的第一发生点

每轮: 各会话并发发一条新消息(客户端按 chat 协议全量重发历史——历史保存
      真实生成文本, 保证与上一轮服务端缓存的前缀逐 token 一致), 流式计时;
      轮前轮后各抓一次 /metrics 取差值. 新增内容随机生成(会话间/轮间
      互不相同, 防止跨会话前缀缓存污染).

用法:
  python -m bench.soak --api-base http://192.168.199.129:8000/v1 --model flash-next \
      --sessions 3 --chunk-tokens 20000 --target-context 524288 --max-tokens 512 \
      --out soak.json --evidence-dir ev/
门禁: 全程零失败请求且零抢占 → PASS; 否则 FAIL 并给出第一发生点.
"""
import argparse
import json
import os
import random
import time

from .common import (Client, Concurrency, fetch_metrics, metrics_delta,
                     snapshot, stdout_utf8, UTF8JSON)

MKEYS = [
    ("prefix_q", "counter", "vllm:prefix_cache_queries_total"),
    ("prefix_h", "counter", "vllm:prefix_cache_hits_total"),
    ("preempt", "counter", "vllm:num_preemptions_total"),
    ("kv_perc", "gauge", "vllm:kv_cache_usage_perc"),
    ("running", "gauge", "vllm:num_requests_running"),
    ("waiting", "gauge", "vllm:num_requests_waiting"),
]

_WORDS = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu "
          "nu xi omicron pi rho sigma tau upsilon phi chi psi omega nova terra "
          "luna solis aqua ignis ventus silva mons flumen mare stellae via obs "
          "cursor vector matrix tensor kernel cache prefill decode token ctx kv "
          "quant fp8 nvfp4 yarn mtp spec draft accept router expert moe attn").split()


def make_chunk(seed, n_tokens):
    """随机伪文本 ≈n_tokens(英文 ~1.7 字符/token, ~7 字符/词). 内容唯一防缓存污染."""
    rng = random.Random(seed)
    n_words = int(n_tokens * 4 / 1.7 / 7) + 16
    return " ".join(rng.choice(_WORDS) + "abcdefgh"[rng.randint(0, 7)] * rng.randint(0, 3)
                    for _ in range(n_words))


def run_soak(client, n_sessions, chunk_tokens, target_ctx, max_tokens,
             evidence_dir):
    histories = [[] for _ in range(n_sessions)]  # 每会话完整 messages(真实文本)
    ctx_tokens = [0] * n_sessions
    turns = []
    kv_peak = 0.0
    sum_q = sum_h = 0
    first_bad = None
    preempted = False
    m_before = fetch_metrics(client.base)
    t0 = time.time()
    rnd = 0
    while max(ctx_tokens) < target_ctx:
        rnd += 1
        recs = [None] * n_sessions

        def one(i, _k):
            chunk = make_chunk(seed=1000000 + i * 10000 + rnd, n_tokens=chunk_tokens)
            msgs = list(histories[i]) + [{"role": "user", "content": chunk}]
            recs[i] = client.chat_stream(msgs, max_tokens=max_tokens,
                                         temperature=0.0, no_think=True)

        Concurrency(n_sessions).map_collect(range(n_sessions), one, lambda _r: None)
        m_after = fetch_metrics(client.base)
        md = metrics_delta(m_after, m_before, MKEYS)
        m_before = m_after
        kv_peak = max(kv_peak, md.get("kv_perc") or 0)
        sum_q += md.get("prefix_q") or 0
        sum_h += md.get("prefix_h") or 0
        rnd_ok = True
        for i, r in enumerate(recs):
            if r and r.get("ok"):
                row = {"round": rnd, "session": i, "ctx_tokens": r.get("prompt_tokens"),
                       "ttft_ms": round(r["ttft_ms"], 1),
                       "tpot_ms": round(r["tpot_ms"], 1) if r.get("tpot_ms") else None,
                       "e2e_ms": round(r["e2e_ms"], 1),
                       "out_tok": r["completion_tokens"], "ok": True}
            else:
                row = {"round": rnd, "session": i, "ctx_tokens": ctx_tokens[i],
                       "ok": False, "error": (r or {}).get("error")}
                if first_bad is None:
                    first_bad = row
                rnd_ok = False
            turns.append(row)
        # 成功的会话: 把本轮 user 块与真实 assistant 回复写回历史(下轮全量重发)
        for i, r in enumerate(recs):
            if r and r.get("ok"):
                ctx_tokens[i] = r["prompt_tokens"] or ctx_tokens[i]
                turns_row = [t for t in turns
                             if t["round"] == rnd and t["session"] == i and t["ok"]][0]
                chunk = make_chunk(seed=1000000 + i * 10000 + rnd, n_tokens=chunk_tokens)
                histories[i].append({"role": "user", "content": chunk})
                histories[i].append({"role": "assistant", "content": r["text"]})
        ok_ttft = [t["ttft_ms"] for t in turns if t.get("ok") and t["round"] == rnd]
        print("  第%02d轮 ctx_max=%d TTFT均值=%.0fms kv=%.1f%%(峰%.1f%%) "
              "前缀Δ(q/h)=%s/%s 抢占Δ=%s%s" % (
                  rnd, max(ctx_tokens),
                  sum(ok_ttft) / max(len(ok_ttft), 1),
                  (md.get("kv_perc") or 0) * 100, kv_peak * 100,
                  md.get("prefix_q"), md.get("prefix_h"), md.get("preempt"),
                  "" if rnd_ok else " ←失败!"))
        if (md.get("preempt") or 0) > 0:
            preempted = True
        if first_bad or preempted:
            break  # 失败/抢占即停, 保留现场
    wall = time.time() - t0
    if evidence_dir:
        os.makedirs(evidence_dir, exist_ok=True)
        with open(os.path.join(evidence_dir, "soak_turns.jsonl"), "w",
                  encoding="utf-8") as f:
            for t in turns:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
    ok = [t for t in turns if t.get("ok")]
    first3 = [t["ttft_ms"] for t in ok if t["round"] <= 3]
    last_r = max((t["round"] for t in ok), default=0)
    last3 = [t["ttft_ms"] for t in ok if t["round"] > last_r - 3]
    summary = {
        "track": "soak", "sessions": n_sessions, "chunk_tokens": chunk_tokens,
        "target_context": target_ctx, "rounds": rnd, "wall_s": round(wall, 1),
        "final_ctx_tokens": ctx_tokens,
        "ttft_first3_avg_ms": round(sum(first3) / len(first3), 1) if first3 else None,
        "ttft_last3_avg_ms": round(sum(last3) / len(last3), 1) if last3 else None,
        "ttft_growth_ratio": (round(sum(last3) / len(last3) / (sum(first3) / len(first3)), 2)
                              if first3 and last3 else None),
        "kv_peak_perc": round(kv_peak, 4),
        "prefix_hit_rate": round(sum_h / sum_q, 4) if sum_q else None,
        "preempted": preempted,
        "failed_turns": len([t for t in turns if not t.get("ok")]),
        "first_failure": first_bad,
        "note": "ttft_growth_ratio≈1 → 前缀缓存把全量重发救回(多轮聊天不劣化); "
                "kv_peak 对照池上限(如1.92M/1M ctx=1.83x)判容量口径",
    }
    return summary, turns


def _last_user_probe(history):
    for m in reversed(history):
        if m["role"] == "user":
            return m["content"]
    return ""


def main():
    stdout_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--sessions", type=int, default=3)
    ap.add_argument("--chunk-tokens", type=int, default=20000)
    ap.add_argument("--target-context", type=int, default=524288)
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--request-timeout-s", type=int, default=900)
    ap.add_argument("--out", required=True)
    ap.add_argument("--evidence-dir", default=None)
    args = ap.parse_args()

    client = Client(args.api_base, args.model, timeout_s=args.request_timeout_s)
    print("soak: %d 路 × 每轮+%d tok × 目标 %d tok (max_tokens=%d)" % (
        args.sessions, args.chunk_tokens, args.target_context, args.max_tokens))
    if args.evidence_dir:
        os.makedirs(args.evidence_dir, exist_ok=True)
        snapshot(client.base, os.path.join(args.evidence_dir, "metrics_soak_a.json"))
    summary, turns = run_soak(client, args.sessions, args.chunk_tokens,
                              args.target_context, args.max_tokens,
                              args.evidence_dir)
    if args.evidence_dir:
        snapshot(client.base, os.path.join(args.evidence_dir, "metrics_soak_b.json"))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(summary, f, **UTF8JSON)
    if summary["failed_turns"] == 0 and not summary["preempted"]:
        print("PASS soak: %d轮零失败, ctx终态=%s, TTFT首3轮%.0f→末3轮%.0fms "
              "(×%.2f), kv峰=%.1f%%, 前缀命中=%s" % (
                  summary["rounds"], summary["final_ctx_tokens"],
                  summary["ttft_first3_avg_ms"] or 0,
                  summary["ttft_last3_avg_ms"] or 0,
                  summary["ttft_growth_ratio"] or 0,
                  summary["kv_peak_perc"] * 100, summary["prefix_hit_rate"]))
    else:
        print("FAIL soak: 失败=%d 抢占=%s 第一现场=%s → %s" % (
            summary["failed_turns"], summary["preempted"],
            summary["first_failure"], args.out))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
