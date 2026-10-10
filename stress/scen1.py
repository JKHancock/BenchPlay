import json, urllib.request, time, threading, os, random

URL = "http://127.0.0.1:3000/v1/chat/completions"
TOK = open(os.path.expanduser("~/gb10/secrets/newapi-token.txt")).read().strip()
N = 16
MAXTOK = 200

WORDS = ["量子计算", "引力波", "神经网络", "基因编辑", "超导材料", "暗物质", "区块链", "自动驾驶",
         "核聚变", "光合作用", "板块运动", "免疫系统", "芯片制程", "航天轨道", "深海生态", "气候变化"]

def build_prompt(i):
    r = random.Random(1000 + i)
    parts = ["【路径%d独有标记%d】以下是参考资料:" % (i, r.randrange(10**9))]
    n_chars = 0
    while n_chars < 33000:
        s = "%d. %s的原理涉及%s与%s的交互,其数量级约为%d,该现象在%s条件下尤为显著。" % (
            len(parts), r.choice(WORDS), r.choice(WORDS), r.choice(WORDS),
            r.randrange(10**6), r.choice(WORDS))
        parts.append(s)
        n_chars += len(s)
    parts.append("请基于以上资料,写一段%d字总结。" % 100)
    return "".join(parts)

results = [None] * N

def one(i, prompt, go):
    go.wait()
    body = {"model": "qwen3.8-27b", "messages": [{"role": "user", "content": prompt}],
            "max_tokens": MAXTOK, "stream": True}
    req = urllib.request.Request(URL, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + TOK)
    t0 = time.time(); ttft = None; chunks = 0; last_tok_t = None
    try:
        for line in urllib.request.urlopen(req, json.dumps(body).encode(), timeout=900):
            line = line.decode().strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            d = json.loads(line[6:])
            ch = d.get("choices")
            if not ch:
                continue
            delta = ch[0].get("delta", {})
            if (delta.get("content") or delta.get("reasoning_content")) and ttft is None:
                ttft = time.time() - t0
            if delta.get("content"):
                chunks += 1
                last_tok_t = time.time()
        results[i] = {"i": i, "ttft": ttft, "tok": chunks,
                      "total": time.time() - t0, "ok": True}
    except Exception as e:
        results[i] = {"i": i, "ok": False, "err": str(e)[:80]}

print("场景一: %d路 同时冷启 33K字符prompt 流式" % N)
prompts = [build_prompt(i) for i in range(N)]
go = threading.Event()
ths = [threading.Thread(target=one, args=(i, prompts[i], go)) for i in range(N)]
for t in ths: t.start()
T0 = time.time()
go.set()
for t in ths: t.join()
print("窗口 unix=%d..%d 总耗时%.1fs" % (T0, time.time(), time.time() - T0))

ok = [r for r in results if r and r.get("ok")]
bad = [r for r in results if r and not r.get("ok")]
if bad: print("失败:", bad[:3])
tt = sorted(r["ttft"] for r in ok)
print("\n每路TTFT(秒,升序):", " ".join("%.1f" % x for x in tt))
pt = 0
for r in sorted(ok, key=lambda x: x["ttft"]):
    dpsec = r["tok"] / max(0.1, r["total"] - r["ttft"]) if r["tok"] else 0
    print("路%-2d TTFT=%6.1fs  解码TPS=%5.1f  输出=%d tok  总时长=%.1fs" % (
        r["i"], r["ttft"], dpsec, r["tok"], r["total"]))
last_ttft = tt[-1]
print("\n聚合prefill吞吐: (prompt_tokens需从网关账本取, 先给时间量级)")
print("  发车→最后一路首token: %.1fs" % last_ttft)
