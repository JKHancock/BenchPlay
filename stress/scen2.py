import json, urllib.request, time, threading, os, random

URL = "http://127.0.0.1:3000/v1/chat/completions"
TOK = open(os.path.expanduser("~/gb10/secrets/newapi-token.txt")).read().strip()

def post_stream(body):
    req = urllib.request.Request(URL, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + TOK)
    return urllib.request.urlopen(req, json.dumps(body).encode(), timeout=600)

WORDS = ["量子计算", "引力波", "神经网络", "基因编辑", "超导材料", "暗物质", "区块链", "自动驾驶",
         "核聚变", "光合作用", "板块运动", "免疫系统", "芯片制程", "航天轨道", "深海生态", "气候变化"]

def big_prompt(seed=777):
    r = random.Random(seed)
    parts = ["【注入独有%d】参考资料:" % r.randrange(10**9)]
    n = 0
    while n < 46000:
        s = "%d. %s与%s在%s尺度上呈现%d量级的耦合。" % (
            len(parts), r.choice(WORDS), r.choice(WORDS), r.choice(WORDS), r.randrange(10**6))
        parts.append(s); n += len(s)
    parts.append("用50字总结。")
    return "".join(parts)

T0 = time.time()
INJECT_AT = T0 + 20
timelines = {i: [] for i in range(4)}     # (unix_ts, 累计token)
big_res = {}
stop_at = [None]

def steady(i):
    body = {"model": "qwen3.8-27b",
            "messages": [{"role": "user", "content": "【稳态%d】从1慢慢数到3000,每行一个数字,不要解释" % i}],
            "max_tokens": 3500, "stream": True}
    try:
        for line in post_stream(body):
            line = line.decode().strip()
            if not line.startswith("data: ") or line == "data: [DONE]": continue
            ch = json.loads(line[6:]).get("choices")
            if not ch: continue
            d = ch[0].get("delta", {})
            if d.get("content"):
                timelines[i].append((time.time(), len(timelines[i]) + 1))
            if stop_at[0] and time.time() > stop_at[0]: break
    except Exception:
        pass

def big():
    t0 = time.time()
    body = {"model": "qwen3.8-27b",
            "messages": [{"role": "user", "content": big_prompt()}],
            "max_tokens": 120, "stream": True}
    ttft = None; n = 0
    try:
        for line in post_stream(body):
            line = line.decode().strip()
            if not line.startswith("data: ") or line == "data: [DONE]": continue
            ch = json.loads(line[6:]).get("choices")
            if not ch: continue
            d = ch[0].get("delta", {})
            if d.get("content"):
                if ttft is None: ttft = time.time() - t0
                n += 1
    except Exception as e:
        print("big err", str(e)[:60])
    big_res.update({"ttft": ttft, "tok": n, "dur": time.time() - t0,
                    "start": t0, "end": time.time()})

ths = [threading.Thread(target=steady, args=(i,), daemon=True) for i in range(4)]
for t in ths: t.start()
while time.time() < INJECT_AT: time.sleep(0.3)
print("T+20s 注入大prompt(46K字符)")
big_res["start"] = time.time()
tb = threading.Thread(target=big, daemon=True); tb.start(); tb.join()
stop_at[0] = time.time() + 12
for t in ths: t.join(timeout=30)

print("窗口 unix=%d..%d" % (T0, time.time()))
print("注入prefill: TTFT=%.1fs 解码%d tok 总%.1fs" % (big_res.get("ttft") or -1, big_res.get("tok", 0), big_res.get("dur") or -1))
bs, be = big_res["start"], big_res["end"]

def tps_in(tl, a, b):
    ka = [t for t, _ in tl if t <= a]
    kb = [t for t, _ in tl if t <= b]
    na = len(ka); nb = len(kb)
    return (nb - na) / max(0.5, b - a)

print("\n稳态流各窗口TPS:")
for i in range(4):
    tl = timelines[i]
    base = tps_in(tl, T0, T0 + 18)
    during = tps_in(tl, bs + 0.5, be)
    tail = tps_in(tl, be + 1, be + 10)
    print("  稳态%d: 基线=%5.1f  prefill期间=%5.1f  恢复后=%5.1f  (总token=%d)" % (
        i, base, during, tail, len(tl)))
agg_b = sum(tps_in(timelines[i], T0, T0 + 18) for i in range(4))
agg_d = sum(tps_in(timelines[i], bs + 0.5, be) for i in range(4))
agg_t = sum(tps_in(timelines[i], be + 1, be + 10) for i in range(4))
print("  聚合:  基线=%5.1f  prefill期间=%5.1f  恢复后=%5.1f tok/s" % (agg_b, agg_d, agg_t))
