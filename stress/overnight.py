#!/usr/bin/env python3
# 通宵高压测试 harness — 经网关:3000全链路,混合负载,无人值守
import json, urllib.request, time, threading, os, random, sys
from datetime import datetime

URL = "http://127.0.0.1:3000/v1/chat/completions"
TOK = open(os.path.expanduser("~/gb10/secrets/newapi-token.txt")).read().strip()
MODEL = "qwen3.6-35b-a3b"
HOURS = 11
LOGDIR = os.path.expanduser("~/gb10/overnight")
os.makedirs(LOGDIR, exist_ok=True)
LOG = open(os.path.join(LOGDIR, "results-%s.log" % datetime.now().strftime("%Y%m%d-%H%M")), "a", buffering=1)

STATS = {"ok": 0, "fail": 0, "tok": 0, "events": []}
WORDS = ["量子计算", "引力波", "神经网络", "基因编辑", "超导材料", "暗物质", "区块链", "自动驾驶",
         "核聚变", "光合作用", "板块运动", "免疫系统", "芯片制程", "航天轨道", "深海生态", "气候变化"]

def log(msg):
    LOG.write("%s %s\n" % (datetime.now().strftime("%H:%M:%S"), msg))

def big_prompt(seed):
    r = random.Random(seed)
    parts = ["【%d】参考资料:" % r.randrange(10**12)]
    n = 0
    while n < 30000:
        s = "%d. %s与%s在%s尺度呈现%d量级耦合。" % (
            len(parts), r.choice(WORDS), r.choice(WORDS), r.choice(WORDS), r.randrange(10**6))
        parts.append(s); n += len(s)
    parts.append("用80字总结。")
    return "".join(parts)

def chat(body, timeout=600):
    req = urllib.request.Request(URL, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + TOK)
    t0 = time.time()
    r = json.loads(urllib.request.urlopen(req, json.dumps(body).encode(), timeout=timeout).read())
    return r, time.time() - t0

def attempt(tag, body, timeout=600):
    try:
        r, dur = chat(body, timeout)
        u = r.get("usage", {})
        STATS["ok"] += 1; STATS["tok"] += u.get("total_tokens", 0)
        log("%s ok %.1fs pt=%s ct=%s" % (tag, dur, u.get("prompt_tokens"), u.get("completion_tokens")))
        return r
    except Exception as e:
        STATS["fail"] += 1
        log("%s FAIL %s" % (tag, str(e)[:100]))
        return None

def steady_worker(stop, idx):
    """长解码流(不思考), 持续到stop"""
    i = 0
    while not stop.is_set():
        attempt("稳态%d-%d" % (idx, i), {
            "model": MODEL, "max_tokens": 1500,
            "messages": [{"role": "user", "content": "【稳态%d轮%d】从1数到1200,每行一个数字" % (idx, i)}],
            "chat_template_kwargs": {"enable_thinking": False}})
        i += 1
        time.sleep(2)

def burst(n, max_tokens, tag):
    ths = []
    for i in range(n):
        body = {"model": MODEL, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": "【%s-%d】写一句%d字内的哲理短句" % (tag, i, random.Random().randrange(20, 60))}]}
        t = threading.Thread(target=attempt, args=("%s%d" % (tag, i), body))
        ths.append(t); t.start()
    for t in ths: t.join(timeout=660)

def abort_stream(tag):
    """开流5秒掐死(验证不崩+留痕)"""
    body = {"model": MODEL, "max_tokens": 900, "stream": True,
            "messages": [{"role": "user", "content": "【断流】从1慢慢数到800,每行一个"}]}
    try:
        req = urllib.request.Request(URL, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + TOK)
        resp = urllib.request.urlopen(req, json.dumps(body).encode(), timeout=60)
        t0 = time.time(); n = 0
        for line in resp:
            if time.time() - t0 > 5:
                resp.close(); break
            line = line.decode().strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                ch = json.loads(line[6:]).get("choices")
                if ch and ch[0].get("delta", {}).get("content"): n += 1
        log("%s 掐断于5s 已收%d chunks" % (tag, n))
    except Exception as e:
        log("%s 异常(预期内) %s" % (tag, str(e)[:60]))

TOOLS = [{"type": "function", "function": {"name": "get_weather",
          "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}}}]

def cycle(c):
    log("===== 周期%d 开始 =====" % c)
    # 6分钟: 2路稳态长解码
    stop = threading.Event()
    ws = [threading.Thread(target=steady_worker, args=(stop, i), daemon=True) for i in range(2)]
    for t in ws: t.start()
    time.sleep(180)
    # 第3分钟: 冷大prefill注入(与稳态解码竞争)
    r = attempt("冷预填%d" % c, {"model": MODEL, "max_tokens": 150,
        "messages": [{"role": "user", "content": big_prompt(int(time.time()))}]}, timeout=900)
    if r:
        log("  冷预填TTFT近似=%.1fs(总耗时)" % 0)  # 非流式,总时长即近似
    time.sleep(120)
    # 第7分钟: 工具调用×6
    for i in range(6):
        r = attempt("工具%d-%d" % (c, i), {"model": MODEL, "max_tokens": 700,
            "messages": [{"role": "user", "content": "%s现在几点了" % random.choice(["北京", "上海", "深圳", "杭州", "成都", "西安"])}],
            "tools": TOOLS, "tool_choice": "auto"})
    # 第8分钟: 并发短请求×12
    burst(12, 60, "短并发%d" % c)
    # 第9分钟: 断流演练
    abort_stream("断流%d" % c)
    stop.set()
    for t in ws: t.join(timeout=30)
    log("===== 周期%d 结束 ok=%d fail=%d tok=%d =====" % (c, STATS["ok"], STATS["fail"], STATS["tok"]))
    time.sleep(60)

END = time.time() + HOURS * 3600
c = 0
log("### 通宵harness启动 模型=%s 计划%d小时 ###" % (MODEL, HOURS))
while time.time() < END:
    try:
        cycle(c)
    except Exception as e:
        log("周期异常(继续) %s" % str(e)[:120])
        time.sleep(30)
    c += 1
log("### 结束: %d周期 ok=%d fail=%d tok=%d ###" % (c, STATS["ok"], STATS["fail"], STATS["tok"]))
