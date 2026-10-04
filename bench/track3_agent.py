# -*- coding: utf-8 -*-
"""Track3 智能体测试(契约 v4.1): 工具调用能力 + 智能体循环性能.

背景: 2026-09-30 事故 — 智能体场景服务没开 --enable-auto-tool-choice/--tool-call-parser,
     对话型验收(三关)全绿但工具调用 400. 结论: 验收契约必须由用途驱动, 智能体场景必须过 Track3.

四组指标:
  selection_acc  该调哪个工具(含不调用克制 no-call 用例)
  args_acc       调用参数抽取正确率(键值包含匹配)
  loop_success   多轮回环: 发起调用→回灌结果→正确作答
  loop_e2e_ms / toolcall_ttft_ms  循环时延

用法: python -m bench.track3 --api-base URL --model qwen3.6-35b-a3b --out t3.json
"""
import argparse
import json
import time

import requests

from .common import stdout_utf8, UTF8JSON


def _tool(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required}}}


W = _tool("get_weather", "查询城市当前天气",
          {"city": {"type": "string"}}, ["city"])
S = _tool("search_docs", "在知识库中搜索文档",
          {"query": {"type": "string"}, "top_k": {"type": "integer"}}, ["query"])
C = _tool("calc", "四则运算",
          {"expr": {"type": "string"}}, ["expr"])
M = _tool("send_email", "发邮件",
          {"to": {"type": "string"}, "subject": {"type": "string"},
           "body": {"type": "string"}}, ["to", "subject", "body"])

CASES = [
    # (id, tools, user, expect)  expect: {"call":name,"args":{...}} | {"no_call":True}
    ("w1", [W, S], "上海现在天气如何?", {"call": "get_weather", "args": {"city": "上海"}}),
    ("w2", [W, S], "帮我搜一下Q3财报文档", {"call": "search_docs", "args": {"query": "Q3财报"}}),
    ("w3", [W, C], "算一下 (123+456)*2 等于多少", {"call": "calc", "args": {"expr": "(123+456)*2"}}),
    ("w4", [W, S, C], "北京今天会下雨吗?", {"call": "get_weather", "args": {"city": "北京"}}),
    ("w5", [M, S], "给 zhang@x.com 发邮件主题'周报'正文'见附件'", {"call": "send_email",
        "args": {"to": "zhang@x.com", "subject": "周报"}}),
    ("n1", [W, S], "你好，请介绍一下你自己，不要调用任何工具。",
     {"no_call": True}),
    ("n2", [W, S, C], "用一句话说明什么是KV缓存(不要查询)",
     {"no_call": True}),
    ("w6", [S], "搜索 vllm prefix caching 相关文档, 取前5条",
     {"call": "search_docs", "args": {"query": "vllm prefix caching", "top_k": 5}}),
]

LOOP_CASES = [
    ("l1", [W], "深圳天气怎么样?",
     {"call": "get_weather", "args": {"city": "深圳"}},
     '{"temp_c": 28, "condition": "多云"}',
     ["28", "多云"]),
    ("l2", [C], "计算 89*76",
     {"call": "calc", "args": {"expr": "89*76"}},
     '{"result": 6764}',
     ["6764"]),
]


def chat(api, model, msgs, tools=None, tool_choice=None, timeout=120,
         no_think=True):
    body = {"model": model, "messages": msgs, "max_tokens": 2048,
            "chat_template_kwargs": {"enable_thinking": no_think}}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice or "auto"
    t0 = time.perf_counter()
    r = requests.post(api + "/chat/completions", json=body, timeout=timeout)
    r.raise_for_status()
    return r.json(), (time.perf_counter() - t0) * 1000


def check_call(msg, expect):
    tcs = msg.get("tool_calls") or []
    if expect.get("no_call"):
        return (not tcs), None
    if not tcs:
        return False, False
    tc = tcs[0]["function"]
    sel = tc["name"] == expect["call"]
    try:
        args = json.loads(tc["arguments"] or "{}")
    except Exception:
        args = {}
    exp = expect.get("args", {})
    argv_ok = all(str(exp.get(k)) in str(args.get(k)) for k in exp)
    return sel, argv_ok


def main():
    stdout_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    api = args.api_base.rstrip("/")

    sel_ok = args_ok = 0
    details = []
    for cid, tools, user, expect in CASES:
        try:
            d, ms = chat(api, args.model, [{"role": "user", "content": user}],
                         tools, "auto")
            msg = d["choices"][0]["message"]
            sel, argv = check_call(msg, expect)
            sel = bool(sel)
            argv = bool(argv) if sel and not expect.get("no_call") else None
            if sel:
                sel_ok += 1
                if argv:
                    args_ok += 1
            details.append({"id": cid, "sel": sel, "args": argv, "ms": round(ms, 0),
                            "got": (msg.get("tool_calls") or [{}])[0]
                                   .get("function", {}).get("name")})
            print("  %-3s sel=%-5s args=%-5s %5.0fms" % (cid, sel, argv, ms))
        except Exception as e:
            details.append({"id": cid, "error": str(e)[:150]})
            print("  %-3s ERROR %s" % (cid, str(e)[:100]))

    loops = []
    loop_ok = 0
    for cid, tools, user, expect, tool_result, answer_must in LOOP_CASES:
        try:
            t0 = time.perf_counter()
            d1, _ = chat(api, args.model, [{"role": "user", "content": user}],
                         tools, "auto")
            tc = (d1["choices"][0]["message"].get("tool_calls") or [None])[0]
            if not tc:
                loops.append({"id": cid, "stage": "no_call"})
                continue
            msgs = [{"role": "user", "content": user},
                    d1["choices"][0]["message"],
                    {"role": "tool", "tool_call_id": tc["id"], "content": tool_result}]
            d2, _ = chat(api, args.model, msgs)
            e2e = (time.perf_counter() - t0) * 1000
            ans = d2["choices"][0]["message"].get("content") or ""
            ok = all(k in ans for k in answer_must)
            loop_ok += ok
            loops.append({"id": cid, "loop_ok": ok, "e2e_ms": round(e2e, 0)})
            print("  %-3s loop=%-5s e2e=%.0fms 答:%s" % (cid, ok, e2e, ans[:40]))
        except Exception as e:
            loops.append({"id": cid, "error": str(e)[:150]})

    n = len(CASES)
    n_call = sum(1 for c in CASES if not c[3].get("no_call"))  # 克制题不计入参数分母
    out = {"track": "track3", "api_base": api, "model": args.model,
           "metrics": {"selection_acc": round(sel_ok / n, 4),
                       "args_acc": round(args_ok / n_call, 4) if n_call else None,
                       "restraint_included": True, "n": n,
                       "loop_success": round(loop_ok / len(LOOP_CASES), 4),
                       "n_loops": len(LOOP_CASES)},
           "details": details, "loops": loops,
           "gate_pass": sel_ok >= n * 0.85 and loop_ok == len(LOOP_CASES)}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, **UTF8JSON)
    print("Track3: selection=%.3f args=%.3f loop=%s → %s [%s]" % (
        out["metrics"]["selection_acc"], out["metrics"]["args_acc"],
        out["metrics"]["loop_success"], args.out,
        "PASS" if out["gate_pass"] else "FAIL"))
    raise SystemExit(0 if out["gate_pass"] else 1)


if __name__ == "__main__":
    main()
