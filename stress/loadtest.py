import json, urllib.request, time, threading, os

URL = "http://127.0.0.1:3000/v1/chat/completions"
TOK = open(os.path.expanduser("~/gb10/secrets/newapi-token.txt")).read().strip()
BODY = {"model": "qwen3.8-27b",
        "messages": [{"role": "user", "content": "写一段约200字的科普短文,主题自选"}],
        "max_tokens": 256}

lock = threading.Lock()
done = 0; fail = 0; tok = 0; lats = []

def worker(stop_at):
    global done, fail, tok
    while time.time() < stop_at:
        req = urllib.request.Request(URL, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + TOK)
        t0 = time.time()
        try:
            r = json.loads(urllib.request.urlopen(req, json.dumps(BODY).encode(), timeout=600).read())
            lat = time.time() - t0
            with lock:
                done += 1; tok += r["usage"]["completion_tokens"]; lats.append(lat)
        except Exception:
            with lock: fail += 1

t_all = time.time()
print("压测窗口起点 unix=%d" % t_all)
for c in [1, 4, 8, 16, 32]:
    done = 0; fail = 0; tok = 0; lats = []
    t_start = time.time()
    stop_at = t_start + 45
    ths = [threading.Thread(target=worker, args=(stop_at,), daemon=True) for _ in range(c)]
    for t in ths: t.start()
    for t in ths: t.join()
    dur = time.time() - t_start
    s = sorted(lats)
    p50 = s[len(s)//2] if s else 0
    p95 = s[min(len(s)-1, int(len(s)*0.95))] if s else 0
    print("c=%-2d 完成=%-4d 失败=%-3d 吞吐=%.1f req/s  生成=%.0f tok/s  p50=%.1fs p95=%.1fs" % (
        c, done, fail, done/dur, tok/dur, p50, p95), flush=True)
    time.sleep(8)
print("压测窗口终点 unix=%d" % time.time())
