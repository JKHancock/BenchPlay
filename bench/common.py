# -*- coding: utf-8 -*-
"""bench 公共层: HTTP/SSE 客户端, /metrics 解析, 分位数统计, JSON 落盘.

设计约束:
- 只依赖 requests + 标准库(venv 现成, 不新增安装);
- 所有输出 ASCII 键名 JSON, 中文只出现在 status 说明里(编码安全);
- 任何异常不吞: 请求失败重试 1 次, 再失败计入 failed, 由门禁拦截.
"""
import json
import re
import time
import threading
import requests

UTF8JSON = {"ensure_ascii": False, "indent": 2}


def stdout_utf8():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


class Client:
    """OpenAI 兼容客户端(chat completions, SSE 流式)."""

    def __init__(self, api_base, model, timeout_s=300, max_retries=2):
        self.base = api_base.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.s = requests.Session()

    def chat_stream(self, messages, max_tokens, temperature=0.0, seed=None,
                    ignore_eos=False, no_think=True, extra=None):
        """一次流式请求. 返回 dict: {ok, ttft_ms, tpot_ms, completion_tokens,
        prompt_tokens, wall_ms, finish, error}. 失败重试 1 次(网络/5xx)."""
        body = {
            "model": self.model, "messages": messages, "max_tokens": max_tokens,
            "temperature": temperature, "stream": True,
            "stream_options": {"include_usage": True},
        }
        if seed is not None:
            body["seed"] = seed
        if ignore_eos:
            body["ignore_eos"] = True
        if no_think:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        if extra:
            body.update(extra)
        last_err = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._one_stream(body)
            except Exception as e:  # 网络/解析异常(管理面WiFi抖动实测会发生)
                last_err = "%s: %s" % (type(e).__name__, str(e)[:200])
                time.sleep(2 * (attempt + 1))
        return {"ok": False, "error": last_err, "ttft_ms": None, "tpot_ms": None,
                "completion_tokens": 0, "prompt_tokens": 0, "wall_ms": None,
                "finish": "error"}

    def _one_stream(self, body):
        t0 = time.perf_counter()
        first_t = None
        text_len = 0
        chunk_times = []  # 每个含content块的到达时刻(ITL样本源)
        usage = None
        finish = None
        r = self.s.post(self.base + "/chat/completions", json=body,
                        stream=True, timeout=self.timeout_s)
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except Exception:
                continue
            if obj.get("error"):
                raise RuntimeError(str(obj["error"])[:200])
            if "usage" in obj and obj["usage"]:
                usage = obj["usage"]
            ch = obj.get("choices") or []
            if ch:
                d = ch[0]
                if d.get("finish_reason"):
                    finish = d["finish_reason"]
                delta = d.get("delta") or {}
                c = delta.get("content")
                if c:
                    now = time.perf_counter()
                    if first_t is None:
                        first_t = now
                    chunk_times.append(now)
                    text_len += len(c)
        t_end = time.perf_counter()
        if first_t is None:
            raise RuntimeError("no content chunk (empty stream)")
        comp = (usage or {}).get("completion_tokens")
        if comp is None:
            comp = max(1, text_len // 4)  # 无 usage 时按字符近似, 仅为兜底
        wall_ms = (t_end - t0) * 1000.0
        ttft_ms = (first_t - t0) * 1000.0
        gen_ms = (t_end - first_t) * 1000.0
        tpot_ms = gen_ms / max(1, comp - 1) if comp > 1 else None
        itl_ms = [(chunk_times[i] - chunk_times[i - 1]) * 1000.0
                  for i in range(1, len(chunk_times))]
        return {"ok": True, "ttft_ms": ttft_ms, "tpot_ms": tpot_ms,
                "itl_ms": itl_ms, "e2e_ms": wall_ms,
                "completion_tokens": comp,
                "prompt_tokens": (usage or {}).get("prompt_tokens"),
                "wall_ms": wall_ms, "finish": finish or "stop", "error": None}


def pct(sorted_vals, p):
    """线性插值分位数; 入参必须已升序."""
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return sorted_vals[0]
    k = (n - 1) * p / 100.0
    lo = int(k)
    hi = min(lo + 1, n - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def pct3(vals):
    """{p50,p90,p99} 或全 None."""
    if not vals:
        return {"p50": None, "p90": None, "p99": None}
    s = sorted(vals)
    return {"p50": pct(s, 50), "p90": pct(s, 90), "p99": pct(s, 99)}


def fetch_metrics(api_base, timeout_s=15):
    """抓 /metrics 原文并解析为 {name{labels}: value}; 只留非 _created/_bucket/_sum/_count."""
    base = api_base.rstrip("/")
    if not base.endswith(":8000"):
        base = base + ":8000" if "://" in base else base
    url = base.split("/v1")[0] + "/metrics"
    r = requests.get(url, timeout=timeout_s)
    r.raise_for_status()
    out = {}
    hist = {}  # name -> {"buckets": [(le, cum)], "count": n}
    for line in r.text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-\d.eE+]+)$", line)
        if not m:
            continue
        name, labels, val = m.group(1), m.group(2) or "", float(m.group(3))
        if name.endswith(("_created", "_sum", "_count")):
            continue
        if name.endswith("_bucket"):
            le = re.search(r'le="([^"]+)"', labels)
            if le:
                key = name[: -len("_bucket")]
                h = hist.setdefault(key, {"buckets": [], "count": 0.0, "inf": 0.0})
                le_v = le.group(1)
                if le_v == "+Inf":
                    h["inf"] = val
                else:
                    h["buckets"].append((float(le_v), val))
            continue
        out[name + labels] = val
    for k, h in hist.items():
        if h["inf"] > 0:
            out[k + "{q=0.99}"] = hist_pct(h, 99)
            out[k + "{q=0.50}"] = hist_pct(h, 50)
    return out


def hist_pct(h, p):
    """从累计桶估分位数."""
    total = h["inf"]
    target = total * p / 100.0
    prev_c, prev_le = 0.0, 0.0
    for le, c in sorted(h["buckets"]):
        if c >= target:
            if c - prev_c <= 0:
                return le
            frac = (target - prev_c) / (c - prev_c)
            return prev_le + (le - prev_le) * frac
        prev_c, prev_le = c, le
    return h["buckets"][-1][0] if h["buckets"] else None


def metrics_delta(after, before, keys):
    """关心的计数器取差值(累计型), gauge/直方图取 after 值.

    键查找两级回退: 精确(名+标签) → 按名(不同标签变体/无标签).
    (实测坑: vLLM 0.30 的 request_success_total 带 finished_reason 标签,
     直方图分位数键是我们自造的 {q=...}, 必须精确匹配.)"""
    out = {}
    for label, kind, key in keys:
        v = _lookup(after, key)
        if v is None:
            continue
        if kind == "counter":
            b = _lookup(before, key)
            out[label] = round(v - b, 3) if b is not None else None
        else:
            out[label] = round(v, 4)
    return out


def _lookup(metrics, key):
    v = metrics.get(key)
    if v is not None or "{q=" in key:
        return v
    name = key.split("{")[0]
    for k, val in metrics.items():
        if k.split("{")[0] == name:
            return val
    return None


METRIC_KEYS = [
    # (输出名, 类型, metrics 键[带标签]; vLLM 0.30 实测命名)
    ("requests_stop", "counter", 'vllm:request_success_total{engine="0",finished_reason="stop",model_name="bench"}'),
    ("requests_length", "counter", 'vllm:request_success_total{engine="0",finished_reason="length",model_name="bench"}'),
    ("requests_abort", "counter", 'vllm:request_success_total{engine="0",finished_reason="abort",model_name="bench"}'),
    ("requests_error", "counter", 'vllm:request_success_total{engine="0",finished_reason="error",model_name="bench"}'),
    ("prompt_tokens", "counter", 'vllm:prompt_tokens_total{engine="0",model_name="bench"}'),
    ("gen_tokens", "counter", 'vllm:generation_tokens_total{engine="0",model_name="bench"}'),
    ("prefix_queries", "counter", 'vllm:prefix_cache_queries_total{engine="0",model_name="bench"}'),
    ("prefix_hits", "counter", 'vllm:prefix_cache_hits_total{engine="0",model_name="bench"}'),
    ("prompt_tokens_cached", "counter", 'vllm:prompt_tokens_cached_total{engine="0",model_name="bench"}'),
    ("kv_cache_usage", "gauge_last", 'vllm:kv_cache_usage_perc{engine="0",model_name="bench"}'),
    ("gpu_cache_usage", "gauge_last", 'vllm:gpu_cache_usage_perc{engine="0",model_name="bench"}'),
    ("running_peak", "gauge_last", 'vllm:num_requests_running{engine="0",model_name="bench"}'),
    ("ttft_p99_server_s", "gauge_last", "vllm:time_to_first_token_seconds{q=0.99}"),
    ("ttft_p50_server_s", "gauge_last", "vllm:time_to_first_token_seconds{q=0.50}"),
    ("tpot_p99_server_s", "gauge_last", "vllm:request_time_per_output_token_seconds{q=0.99}"),
    ("itl_p99_server_s", "gauge_last", "vllm:inter_token_latency_seconds{q=0.99}"),
    ("queue_p99_server_s", "gauge_last", "vllm:request_queue_time_seconds{q=0.99}"),
    ("req_latency_p99_server_s", "gauge_last", "vllm:request_inference_time_seconds{q=0.99}"),
]


def snapshot(api_base, path=None):
    m = fetch_metrics(api_base)
    if path:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(m, f, **UTF8JSON)
    return m


class GaugePoller:
    """负载中后台轮询 gauge 峰值(kv/gpu_cache 占用, running 数).

    (实测坑: 相位结束后才快照 /metrics, kv_cache_usage_perc 已回落 0% —
     峰值必须负载中采样.)"""

    GAUGES = {
        "kv_peak": "vllm:kv_cache_usage_perc",
        "gpu_cache_peak": "vllm:gpu_cache_usage_perc",
        "running_peak": "vllm:num_requests_running",
    }

    def __init__(self, api_base, interval_s=2.0):
        self.url = api_base.rstrip("/").split("/v1")[0] + "/metrics"
        self.interval_s = interval_s
        self.peaks = {k: 0.0 for k in self.GAUGES}
        self.n = 0
        self._stop = threading.Event()
        self._t = None

    def _poll(self):
        import re as _re
        pat = {k: _re.compile(_re.escape(name) + r"(\{[^}]*\})?\s+([-\d.eE+]+)")
               for k, name in self.GAUGES.items()}
        while not self._stop.is_set():
            try:
                txt = requests.get(self.url, timeout=5).text
                for k, p in pat.items():
                    for m in p.finditer(txt):
                        v = float(m.group(2))
                        if v > self.peaks[k]:
                            self.peaks[k] = v
                self.n += 1
            except Exception:
                pass  # 与管理面WiFi抖动共存, 丢一轮采样无碍峰值
            self._stop.wait(self.interval_s)

    def start(self):
        self._t = threading.Thread(target=self._poll, daemon=True)
        self._t.start()
        return self

    def stop(self):
        self._stop.set()
        if self._t:
            self._t.join(timeout=10)
        out = dict(self.peaks)
        out["samples"] = self.n
        return out


class Concurrency:
    """简单线程池并发执行 fn(items) 并收集结果(保序)."""

    def __init__(self, n):
        self.n = max(1, n)
        self.lock = threading.Lock()

    def map_collect(self, items, fn, sink):
        """fn(item, idx) -> result; sink(result) 线程安全."""
        sem = threading.Semaphore(self.n)
        threads = []

        def run(it, idx):
            with sem:
                sink(fn(it, idx))

        for idx, it in enumerate(items):
            t = threading.Thread(target=run, args=(it, idx), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
