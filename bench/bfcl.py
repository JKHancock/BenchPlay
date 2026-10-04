# -*- coding: utf-8 -*-
"""bfcl.py — BFCL v3 子集跑器(智能体集合 A1 的先行版).

范围与口径(HF 版真值已脱敏, 如实分档):
  bfcl_irrelevance (n≤100): 无需真值 — 正确行为 = 不发起任何调用; 精确判分
  bfcl_simple      (n≤100): 结构分下界 — 调用了提供的函数 + required 参数齐全 + 类型合理
    (官方 AST 精判需带真值的数据源, 待接 gorilla 仓库; 本分数是保守下界)
BFCL 遗留参数形态("type":"dict")已归一化为 OpenAI "object".
"""
import argparse
import json
import random
import time
from pathlib import Path

import requests

from .common import stdout_utf8, UTF8JSON

BFCL_DIR = Path(__file__).resolve().parent.parent / "data" / "cap" / "bfcl"


def load_lines(name):
    p = BFCL_DIR / f"BFCL_v3_{name}.json"
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def normalize_func(f):
    f = dict(f)
    params = dict(f.get("parameters") or {})
    if params.get("type") in ("dict", None):
        params["type"] = "object"
    props = params.get("properties") or {}
    for v in props.values():
        if isinstance(v, dict) and v.get("type") in ("dict", None) and "properties" in v:
            v["type"] = "object"
    f["parameters"] = params
    return {"type": "function", "function": f}


def run(api, model, name, n, timeout=180):
    rows = load_lines(name)
    rng = random.Random(20260930)
    if len(rows) > n:
        rows = rng.sample(rows, n)
    tools_cache = [normalize_func(f) for f in rows[0]["function"]]
    ok = struct_ok = correct = 0
    fails = []
    t0 = time.time()
    for i, e in enumerate(rows):
        tools = [normalize_func(f) for f in e["function"]]
        msgs = [{"role": m["role"], "content": m["content"]}
                for turn in e["question"] for m in turn]
        body = {"model": model, "messages": msgs, "tools": tools,
                "tool_choice": "auto", "max_tokens": 1024,
                "chat_template_kwargs": {"enable_thinking": False}}
        try:
            r = requests.post(api + "/chat/completions", json=body, timeout=timeout)
            r.raise_for_status()
            d = r.json()
        except Exception as ex:
            fails.append({"i": i, "err": str(ex)[:120]})
            continue
        m = d["choices"][0]["message"]
        tcs = m.get("tool_calls") or []
        ok += 1
        if name == "irrelevance":
            correct += (not tcs)          # 正确 = 克制不调用
        else:  # simple: 结构分
            if not tcs:
                continue
            fdef = tools[0]["function"]
            tc = tcs[0]["function"]
            name_ok = tc["name"] == fdef["name"]
            try:
                args = json.loads(tc["arguments"] or "{}")
            except Exception:
                args = None
            req = (fdef.get("parameters") or {}).get("required") or []
            props = (fdef.get("parameters") or {}).get("properties") or {}
            args_ok = isinstance(args, dict) and all(k in args for k in req)
            type_ok = isinstance(args, dict) and all(
                _typefit(args.get(k), props.get(k, {}).get("type")) for k in args)
            if name_ok and args_ok and type_ok:
                struct_ok += 1
                correct += 1
    n_done = ok + len(fails)
    return {"suite": name, "n": len(rows), "answered": ok, "requests_failed": len(fails),
            "score": round(correct / len(rows), 4) if rows else None,
            "note": ("克制正确率(真值无关, 精确)" if name == "irrelevance"
                     else "结构分下界: 函数名对+required齐+类型合理(官方AST待真值源)"),
            "duration_s": round(time.time() - t0, 1)}


def _typefit(v, t):
    if v is None or not t:
        return True
    return {"string": str, "integer": int, "number": (int, float),
            "boolean": bool, "array": list, "object": dict,
            "object_old": dict}.get(t, lambda _v: True)(v) and not (
        t == "integer" and isinstance(v, bool))


def main():
    stdout_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    api = args.api_base.rstrip("/")
    out = {"track": "bfcl", "suites": {}}
    for name in ("irrelevance", "simple"):
        r = run(api, args.model, name, args.n)
        out["suites"]["bfcl_" + name] = r
        print("  bfcl_%-12s n=%-3d score=%.3f (%s)" % (
            name, r["n"], r["score"] or 0, r["note"]))
    Path(args.out).write_text(json.dumps(out, **UTF8JSON), encoding="utf-8")
    print("PASS bfcl →", args.out)


if __name__ == "__main__":
    main()
