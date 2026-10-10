import json, urllib.request, time, threading, os, random, sys

URL = "http://127.0.0.1:3000/v1/chat/completions"
TOK = open(os.path.expanduser("~/gb10/secrets/newapi-token.txt")).read().strip()
TAG = sys.argv[1] if len(sys.argv) > 1 else "?"

def post_stream(body):
    req = urllib.request.Request(URL, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + TOK)
    return urllib.request.urlopen(req, json.dumps(body).encode(), timeout=600)

WORDS = ["量子计算", "引力波", "神经网络", "基因编辑", "超导材料", "暗物质", "区块链", "自动驾驶",
         "核聚变", "光合作用", "板块运动", "免疫系统", "芯片制程", "航天轨道", "深海生态", "气候变化"]

def big_prompt(seed):
    r = random.Random(seed)
    parts = ["【注入%d独有%d】参考资料:" % (seed, r.randrange(10**9))]
    n = 0
    while n < 38000:
        s = "%d. %s与%s在%s尺度上呈现%d量级的耦合。" % (
            len(parts), r.choice(WORDS), r.choice(WORDS), r.choice(WORDS), r.randrange(10**6))
        parts.append(s); n += len(s)
    parts.append("用50字总结。")
    return "".join(parts)

T0 = time.time()
INJECT_AT = T0 + 12
timelines = {i: [] for i in range(4)}
big_res = {}
stop_at = [None]

def steady(i):
    body = {"model": "qwen3.8-27b",
            "messages": [{"role": "user", "content": "【稳态%d】从1慢慢数到3000,每行一个数字" % i}],
            "max_tokens": 3500, "stream": True}
    try:
        for line in post_stream(body):
            line = line.decode().strip()
            if not line.startswith("data: ") or line == "data: [DONE]": continue
            ch = json.loads(line[6:]).get("choices")
            if not ch: continue
            if ch[0].get("delta", {}).get("content"):
                timelines[i].append((time.time(), len(timelines[i]) + 1))
            if stop_at[0] and time.time() > stop_at[0]: break
    except Exception:
        pass

def big(seed):
    t0 = time.time()
    body = {"model": "qwen3.8-27b",
            "messages": [{"role": "user", "content": big_prompt(seed)}],
            "max_tokens": 100, "stream": True}
    ttft = None; n = 0
    try:
        for line in post_stream(body):
            line = line.decode().strip()
            if not line.startswith("data: ") or line == "data: [DONE]": continue
            ch = json.loads(line[6:]).get("choices")
            if not ch: continue
            if ch[0].get("delta", {}).get("content"):
                if ttft is None: ttft = time.time() - t0
                n += 1
    except Exception as e:
        print("big err", str(e)[:60])
    big_res.update({"ttft": ttft, "tok": n, "start": t0, "end": time.time()})

ths = [threading.Thread(target=steady, args=(i,), daemon=True) for i in range(4)]
for t in ths: t.start()
while time.time() < INJECT_AT: time.sleep(0.2)
tb = threading.Thread(target=big, args=(int(time.time()),), daemon=True); tb.start(); tb.join()
stop_at[0] = time.time() + 8
for t in ths: t.join(timeout=20)

bs, be = big_res["start"], big_res["end"]
def tps_in(tl, a, b):
    na = len([1 for t, _ in tl if t <= a]); nb = len([1 for t, _ in tl if t <= b])
    return (nb - na) / max(0.5, b - a)
base = sum(tps_in(timelines[i], T0, T0 + 10) for i in range(4))
during = sum(tps_in(timelines[i], bs + 0.5, be) for i in range(4))
tail = sum(tps_in(timelines[i], be + 1, be + 7) for i in range(4))
print("[%s] 注入TTFT=%.1fs | 聚合decode: 基线=%.0f 期间=%.0f(%.0f%%) 恢复=%.0f tok/s" % (
    TAG, big_res["ttft"] or -1, base, during, 100*during/max(1,base), tail))
