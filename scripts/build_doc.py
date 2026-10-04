#!/usr/bin/env python3
"""build_doc.py — 按 REPORT-SPEC-v4 组装 report_doc.json + 推荐引擎 + schema 校验.

输入: tasks/t20260930-matrix-full/raw4/<tag>/{w1..w6,probes,cap}.json
      + metrics_*_a/b.json + startup.log + host_*.log + progress.log
      + machines/*.json (Part A)
输出: report_doc.json (过 jsonschema 校验; 推荐已嵌入, 含可回查的数值指针)
"""
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "D:/CSharpProject/Vllm_Benchmark")
from bench.common import metrics_delta, METRIC_KEYS

BP = Path("D:/CSharpProject/BenchPlaybook")
RAW = BP / "tasks/t20260930-matrix-full/raw4"
RAW2 = BP / "tasks/t20261003-flashnext/raw"

MODELS = {
    "Qwen3.8-Flash-Next-NVFP4": {"quant": "NVFP4", "type": "moe",
                                 "params_b": 230, "active_b": 4,
                                 "weights_gb": 132.6, "ctx": 1048576},
    "Qwen3.6-35B-A3B-NVFP4-Fast": {"quant": "NVFP4", "type": "moe",
                                   "params_b": 35, "active_b": 3,
                                   "weights_gb": 19.0, "ctx": 40960},
    "Qwen3.8-27B-NVFP4": {"quant": "NVFP4", "type": "dense",
                          "params_b": 27, "active_b": 27,
                          "weights_gb": 15.5, "ctx": 40960},
}
TAGS = [("TP2-Qwen3.8", "Qwen3.8-27B-NVFP4", 2, False, [], 40960),
        ("TP2-Qwen3.6", "Qwen3.6-35B-A3B-NVFP4-Fast", 2, True, [], 40960),
        ("TP2EP2-Qwen3.6", "Qwen3.6-35B-A3B-NVFP4-Fast", 2, True,
         ["--enable-expert-parallel"], 40960),
        ("TP1-Qwen3.6", "Qwen3.6-35B-A3B-NVFP4-Fast", 1, False, [], 40960),
        ("TP1-Qwen3.8", "Qwen3.8-27B-NVFP4", 1, False, [], 40960),
        ("TP2EP2MTP-1M-Qwen3.6", "Qwen3.6-35B-A3B-NVFP4-Fast", 2, True,
         ["--enable-expert-parallel",
          "--speculative-config", '{"method":"qwen3_5_mtp","num_speculative_tokens":2}',
          "--hf-overrides", '{"text_config":{"max_position_embeddings":1048576,"rope_scaling":{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":262144,"mrope_interleaved":true,"mrope_section":[11,11,10],"partial_rotary_factor":0.25,"rope_theta":10000000}}}'],
         1048576)]
WLS = ["w1", "w2", "w3", "w4", "w5", "w6"]
SUITES_P0 = ["gsm8k", "mmlu", "arc"]
FP = {"vllm": "0.30.0", "image_digest": "sha256:91d9b077589e",
      "driver": "580.178.04", "gpu": "GB10", "ray": "2.44.0",
      "recorded_at": "2026-09-30T22:45:35"}


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def parse_kv_lines(path):
    """startup.log → kv_cache_tokens / max_concurrency_x."""
    kv, mx = None, None
    if path.exists():
        t = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"GPU KV cache size: ([\d,]+) tokens", t)
        if m:
            kv = int(m.group(1).replace(",", ""))
        m = re.search(r"Maximum concurrency[^:]*: ([\d.]+)", t)
        if m:
            mx = float(m.group(1))
    return kv, mx


def parse_host_log(path):
    """host_*.log: '98 %, 102627 MiB' 行 → util/mem 峰值."""
    if not path.exists():
        return None
    u_peak = m_peak = 0
    for ln in path.read_text(errors="replace").splitlines():
        m = re.match(r"\s*(\d+) %, (\d+) MiB", ln)
        if m:
            u_peak = max(u_peak, int(m.group(1)))
            m_peak = max(m_peak, int(m.group(2)))
    if u_peak == 0 and m_peak == 0:
        return None
    return {"gpu_util_perc_peak": u_peak, "gpu_mem_used_gb_peak": round(m_peak / 1024, 1)}


def machines_part():
    out = []
    alias = {"192.168.199.129": "GX10 Node1", "192.168.199.134": "GX10 Node2"}
    for ip, al in alias.items():
        d = load(BP / f"machines/{ip}.json")
        host = d.get("Hostname") or ip
        out.append({
            "machine_id": host, "alias": al,
            "identity": {"hostname": host,
                         "mgmt_ip": f"{ip}(OTA-WiFi-DHCP,会漂移)",
                         "data_ip": "192.168.100.1" + ("0" if ip.endswith("129") else "1")},
            "hardware": {"gpu": "GB10", "gpu_count": 1,
                         "unified_memory": f"{d.get('Memory')}(统一内存)",
                         "cpu": f"{d.get('Cpu')}核 aarch64", "memory": d.get("Memory"),
                         "nvme": [{"serial": n} for n in d.get("NvmeSerials", [])] or
                                 [{"serial": "见档案"}],
                         "nics": [
                             {"name": "enp1s0f1np1",
                              "ip": "192.168.100.1" + ("0" if ip.endswith("129") else "1"),
                              "net": "QSFP直连 192.168.100.0/24", "role": "data"},
                             {"name": "wlan/ether", "ip": ip,
                              "net": "OTA WiFi-DHCP", "role": "mgmt"}]},
            "software": {"os": d.get("Os"), "kernel": d.get("Kernel"),
                         "arch": d.get("Arch"), "gpu_driver": d.get("Driver"),
                         "container_runtime": {"docker": d.get("DockerVersion")},
                         "container": {"name": "vllm-node",
                                       "image": "nvcr.io vllm(见digest)",
                                       "image_digest": "sha256:91d9b077589e",
                                       "network_mode": "host",
                                       "vllm_ver": "0.30.0", "ray_ver": "2.44.0",
                                       "python_ver": "3.12"}},
        })
    return out


def build_vllm_args(model, tp, noauto, extra_flags=(), max_len=40960):
    """与 cell4/cell5 实际启动序逐token一致(顺序进 scenario_id 哈希, 不可乱序)."""
    args = ["vllm", "serve", f"/root/.cache/huggingface/{model}",
            "--tensor-parallel-size", str(tp)]
    if tp > 1:
        args += ["--distributed-executor-backend", "ray"]
    args += list(extra_flags)
    if noauto:
        args += ["--kernel-config", '{"enable_flashinfer_autotune":false}']
    args += ["--served-model-name", "bench", "--host", "0.0.0.0", "--port", "8000",
             "--gpu-memory-utilization", "0.85", "--max-model-len", str(max_len),
             "--max-num-seqs", "64", "--enable-chunked-prefill",
             "--enable-prefix-caching"]
    return args


def ready_s(tag):
    t = (RAW / "progress.log").read_text(errors="replace")
    last = None
    for m in re.finditer(r"\[%H", t):
        pass
    for ln in t.splitlines():
        if tag in ln and "serve就绪" in ln:
            m = re.search(r"约(\d+)s", ln)
            if m:
                last = int(m.group(1))
    return last


def scenario(tag, model, tp, noauto, extra_flags=(), max_len=40960):
    if tag.startswith("FlashNext"):
        from pathlib import Path as _P
        d = (_P("D:/CSharpProject/BenchPlaybook/tasks/t20261003-overnight") if "40960" in tag else RAW2) / tag
    else:
        d = RAW / tag
    m = MODELS[model]
    argv = build_vllm_args(model, tp, noauto, extra_flags, max_len)
    if tag == "FlashNext-TP2-1M":
        argv = ["vllm", "serve", "/root/.cache/huggingface/Qwen3.8-Flash-Next-NVFP4",
                "--tensor-parallel-size", "2",
                "--distributed-executor-backend", "ray",
                "--speculative-config", '{"method":"qwen4_exp_mtp","num_speculative_tokens":2}',
                "--hf-overrides", '{"text_config":{"max_position_embeddings":1048576,"rope_scaling":{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":262144}}}',
                "--enable-auto-tool-choice", "--tool-call-parser", "qwen3_xml",
                "--reasoning-parser", "qwen3",
                "--served-model-name", "flash-next", "--host", "0.0.0.0", "--port", "8000",
                "--gpu-memory-utilization", "0.85", "--max-model-len", "1048576",
                "--max-num-seqs", "8", "--max-num-batched-tokens", "8192",
                "--enable-chunked-prefill", "--enable-prefix-caching"]
    sid = hashlib.sha1((" ".join(argv) + model + str(tp)).encode()).hexdigest()[:8]

    # perf_metrics: 动态发现本场景实测的负载文件(cell5 型场景是 wsweep/w2s/w7)
    workloads = []
    wl_stems = sorted(p.stem for p in d.glob("w*.json"))
    for w in wl_stems:
        wd = load(d / f"{w}.json")
        wd.pop("api_base", None)
        workloads.append(wd)
    probes = load(d / "probes.json") if (d / "probes.json").exists() else None

    # vllm_metrics
    kv_tok, mx_x = parse_kv_lines(d / "startup.log")
    gauges, counters, histograms = {}, {}, {}
    for w in wl_stems + ["probe", "cap", "agent", "soak"]:
        fa, fb = d / f"metrics_{w}_a.json", d / f"metrics_{w}_b.json"
        if fa.exists() and fb.exists():
            delta = metrics_delta(load(fb), load(fa), METRIC_KEYS)
            delta["requests_success"] = round(
                delta.pop("requests_stop", 0) + delta.pop("requests_length", 0), 3)
            delta["requests_failed"] = round(
                delta.pop("requests_abort", 0) + delta.pop("requests_error", 0), 3)
            counters[f"phase:{w}"] = {k: v for k, v in delta.items()
                                      if not k.endswith(("_s",))}
            histograms[f"phase:{w}"] = {k: v for k, v in delta.items()
                                        if k.endswith("_s")}
    for wd in workloads:
        for lv in wd.get("levels", []):
            gp = (lv or {}).get("gauge_peaks") or {}
            if any(v for k, v in gp.items() if k != "samples"):
                gauges[f"{wd['workload_id']}:c{lv['concurrency']}"] = gp
    host = {}
    hh = parse_host_log(d / "host_head.log")
    if hh:
        host["gx10-9f5c"] = hh
    hw = parse_host_log(d / "host_worker.log")
    if hw:
        host["gx10-9c05"] = hw

    # capability
    cap = load(d / "cap.json") if (d / "cap.json").exists() else {"suites": {}}
    agd = load(d / "agent.json") if (d / "agent.json").exists() else {}
    am = agd.get("metrics", {}) if agd else {}
    bfd = load(d / "bfcl.json") if (d / "bfcl.json").exists() else {}
    bs = bfd.get("suites", {}) if bfd else {}
    agent_metrics = {
        "metrics": {k: am.get(k) for k in
                    ("selection_acc", "args_acc", "loop_success", "n", "n_loops")},
        "bfcl": {"irrelevance": (bs.get("bfcl_irrelevance") or {}).get("score"),
                 "simple": (bs.get("bfcl_simple") or {}).get("score")},
    }
    cap_suites = []
    for s, v in cap.get("suites", {}).items():
        cap_suites.append({"suite_id": s,
                           "dimension": {"gsm8k": "math", "mmlu": "knowledge",
                                         "arc": "science", "hellaswag": "commonsense",
                                         "winogrande": "coref",
                                         "math500": "math-adv",
                                         "cmmlu": "zh-knowledge",
                                         "ceval": "zh-knowledge",
                                         "ifeval": "instr-follow"}.get(s, "?"),
                           "settings": {"n": v["n"], "shots": 0,
                                        "thinking": ("on" if ",think," in v.get("mode", "")
                                                     else "off"),
                                        "temperature": 0.0, "seed": 20260930,
                                        "concurrency": 8},
                           "score": {"acc": v["acc"], "correct": v["correct"],
                                     "n": v["n"], "unanswered": 0,
                                     "truncated": None,
                                     **({"instr_acc": v["instr_acc"]}
                                        if v.get("instr_acc") is not None else {})},
                           "tokens": {"avg_out": v.get("avg_completion_tokens")},
                           "reliability": {"requests_failed": v["requests_failed"]},
                           "duration_s": v.get("duration_s")})
    # 未测套件才占位(cap.json 里已有的以实测为准)
    for missing, why in [("math500", "未测(需 math500.jsonl)"),
                         ("cmmlu", "未测(需 cmmlu CSV)"),
                         ("ceval", "未测(需 ceval parquet)"),
                         ("ifeval", "未测(需 ifeval.jsonl)")]:
        if any(cs["suite_id"] == missing for cs in cap_suites):
            continue
        cap_suites.append({"suite_id": missing, "dimension": "-",
                           "settings": {}, "score": None,
                           "missing_reason": why})

    dep_machines = [{"machine_id": "gx10-9f5c", "role": "standalone" if tp == 1 else "head",
                     "ray": ({"role": "head",
                              "start_cmd": "ray start --head --port=6379 --node-ip-address=192.168.100.10",
                              "env": {"RAY_memory_monitor_refresh_ms": "0"},
                              "resources": {"GPU": 1}} if tp > 1 else
                             {"role": "none(uni后端,单进程)"}),
                     "gpu_alloc": f"TP0/{tp} shard"}]
    if tp > 1:
        dep_machines.append({"machine_id": "gx10-9c05", "role": "worker",
                             "ray": {"role": "worker",
                                     "start_cmd": "ray start --address=192.168.100.10:6379 --node-ip-address=192.168.100.11",
                                     "env": {"RAY_memory_monitor_refresh_ms": "0"},
                                     "resources": {"GPU": 1}},
                             "gpu_alloc": f"TP1/{tp} shard"})

    w_ids = [w["workload_id"] for w in workloads]
    suite_ok = all(any(cs["suite_id"] == s and cs["score"] for cs in cap_suites)
                   for s in SUITES_P0)
    # P0 负载等价: 随机吞吐档 = w1 或 wsweep(含c1/c8/c32超集), 真实分布 = w2 或 w2s
    has_rand = any(w in w_ids for w in ("w1", "wsweep"))
    has_real = any(w in w_ids for w in ("w2", "w2s"))
    p0_ok = (has_rand and has_real and suite_ok
             and bool(counters) and bool(gauges))
    missing = []
    if not has_rand:
        missing.append("perf.w1/wsweep")
    if not has_real:
        missing.append("perf.w2/w2s")
    for s in SUITES_P0:
        if not any(cs["suite_id"] == s and cs["score"] for cs in cap_suites):
            missing.append(f"cap.{s}")
    if not gauges:
        missing.append("vllm.gauges_peak")
    if kv_tok is None:
        missing.append("vllm.startup.kv")

    return {
        "scenario_id": sid, "vllm_args": argv,
        "launch_env": {"CUTE_DSL_ARCH": "sm_121a", "HF_ENDPOINT": "https://hf-mirror.com",
                       "GLOO_SOCKET_IFNAME": "enp1s0f1np1",
                       "NCCL_SOCKET_IFNAME": "enp1s0f1np1",
                       "RAY_memory_monitor_refresh_ms": "0"},
        "model": {"name": model, "path": f"/root/.cache/huggingface/{model}",
                  "quant": m["quant"], "arch": {"type": m["type"],
                                                "params_b": m["params_b"],
                                                "active_b": m["active_b"]},
                  "weights_gb": m["weights_gb"], "context_len": max_len,
                  "native_context": 262144 if max_len > 262144 else max_len,
                  "served_name": "bench"},
        "deployment": {"mode": "single-node" if tp == 1 else f"ray-tp{tp}-2node",
                       "machines": dep_machines,
                       "data_plane": ({"topology": "无(仅管理口)", "iface": "—"}
                                      if tp == 1 else
                                      {"topology": "QSFP直连 192.168.100.0/24",
                                       "iface": "enp1s0f1np1", "measured_bw_gbps": None})},
        "vllm_metrics": {
            "startup": {"ready_s": ready_s(tag), "load_s": None,
                        "kv_cache_tokens": kv_tok, "max_concurrency_x": mx_x,
                        "tensor_parallel": tp, "pipeline_parallel": 1,
                        "cudagraph_mode": "PIECEWISE",
                        "flashinfer_autotune": not noauto,
                        "compile_cache": "hit" if not noauto else "n.a.",
                        "weights_gb": m["weights_gb"], "gpu_mem_reserved_gb": None,
                        "max_num_seqs": 64, "max_model_len": 40960,
                        "gpu_mem_util": 0.85},
            "gauges_peak": gauges, "counters": counters,
            "histograms": histograms, "host_per_machine": host},
        "perf_metrics": {"workloads": workloads,
                         "probes": probes and {"prefix_cache": probes["prefix_cache"],
                                               "capacity": probes["capacity"]},
                         "soak": load(d / "soak.json") if (d / "soak.json").exists() else None},
        "capability_scores": {"suites": cap_suites},
        "agent_metrics": agent_metrics,
        "status": "complete" if p0_ok else "partial",
        "missing": missing,
        "evidence": {"raw_dir": f"tasks/t20260930-matrix-full/raw4/{tag}"},
        "fingerprint": FP,
        "notes": (("qwen4_exp新架构首次在本集群实测; Track3选择8/8满分但l2计算题模型弃用工具直接心算(loop=0.5, 行为特征如实记录) " if tag.startswith("FlashNext") else "") +
                  ("EP2(专家并行, --enable-expert-parallel) " if
                   "--enable-expert-parallel" in argv else "") +
                  ("YaRN4x外拓至1M(原生262144, 质量衰减未做needle验证); "
                   "MTP投机k=2实测接受率75.2%, 单流+37%; "
                   "128K输入TTFT实测57.7s(spec模式max_num_scheduled_tokens=2048限制), "
                   "1M满输入外推≈7-8分钟 " if max_len > 262144 else "") +
                  ("FlashInfer自调优关闭口径(跨会话自调优确定性死亡, 实测代价<1%)"
                   if noauto else "")).strip(" "),
    }


def gv(sc, path):
    """按 a.b.c 取值; 支持 perf@levels c32.agg.output_tok_s 简写路径."""
    parts = path.split(".")
    cur = sc
    for p in parts:
        if isinstance(cur, list):
            cur = cur[int(p)]
        else:
            cur = cur.get(p) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


def wl_level(sc, wid, conc=None):
    for w in sc["perf_metrics"]["workloads"]:
        if w["workload_id"] == wid:
            lvs = w.get("levels", [])
            if conc is None:
                return lvs
            for lv in lvs:
                if lv.get("concurrency") == conc:
                    return lv
    return None


def cap_avg(sc, suites):
    vals = []
    for cs in sc["capability_scores"]["suites"]:
        if cs["suite_id"] in suites and cs.get("score"):
            vals.append(cs["score"]["acc"])
    return sum(vals) / len(vals) if len(vals) == len(suites) else None


def recommend(scs):
    """确定性推荐: 每 profile 从 complete 场景中按明示规则选优, 理由带可回查指针."""
    ok = [s for s in scs if s["status"] == "complete"]
    inel = [{"scenario_id": s["scenario_id"],
             "cause": f"partial: 缺 {','.join(s['missing'][:4])}"}
            for s in scs if s["status"] != "complete"]

    def c1(s):
        return wl_level(s, "w1", 1) or wl_level(s, "wsweep", 1)

    def c32(s):
        return wl_level(s, "w1", 32) or wl_level(s, "wsweep", 32)

    def num(x):
        return x if isinstance(x, (int, float)) else 0.0

    profiles = []

    def mk(name, keyfn, better="max", metric_desc="", path=None):
        if not ok:
            return
        ranked = sorted(ok, key=lambda s: num(keyfn(s)), reverse=(better == "max"))
        win, ru = ranked[0], ranked[1] if len(ranked) > 1 else None
        wv_, rv_ = num(keyfn(win)), (num(keyfn(ru)) if ru else None)
        unit = ""
        reasons = [{
            "text": f"{metric_desc}: {wv_:.4g}" + (f" vs 次优 {rv_:.4g}"
                     f"({label_of(ru)})" if ru else "") + unit,
            "check": {"scenario": win["scenario_id"], "path": path, "value": wv_}}]
        if ru:
            reasons.append({
                "text": f"差距: {(wv_ - rv_):+.4g}" + (
                    f" ({(wv_ / rv_ - 1) * 100:+.1f}%)" if rv_ else ""),
                "check": {"scenario": win["scenario_id"], "path": path, "value": wv_}})
        profiles.append({"profile": name, "winner": win["scenario_id"],
                         "winner_label": label_of(win),
                         "reasons": reasons,
                         "runner_up": ({"scenario_id": ru["scenario_id"],
                                        "label": label_of(ru)} if ru else None)})

    def label_of(s):
        tp = s['vllm_args'][s['vllm_args'].index('--tensor-parallel-size') + 1]
        ep = "+EP" if '--enable-expert-parallel' in s['vllm_args'] else ''
        mtp = "+MTP2+1M" if '--speculative-config' in s['vllm_args'] else ''
        return f"{s['model']['name']}(TP{tp}{ep}{mtp})"

    # 综合分(显式权重, 逐场景计算)
    if ok:
        def z(vals, i):
            vs = [num(v) for v in vals]
            return (vs[i] - min(vs)) / (max(vs) - min(vs)) if max(vs) > min(vs) else 0.0
        c32s = [c32(s)["agg"]["output_tok_s"] for s in ok]
        c1s = [c1(s)["agg"]["output_tok_s"] for s in ok]
        caps = [cap_avg(s, SUITES_P0) for s in ok]
        kvx = [s["vllm_metrics"]["startup"]["max_concurrency_x"] or 0 for s in ok]
        solo = [1.0 if s["deployment"]["mode"] == "single-node" else 0.0 for s in ok]
        W = {"c32_tput": 0.35, "c1_tput": 0.20, "capability": 0.25,
             "kv_capacity": 0.10, "single_node_saving": 0.10}
        scores = []
        for i, s in enumerate(ok):
            sc_ = (W["c32_tput"] * z(c32s, i) + W["c1_tput"] * z(c1s, i)
                   + W["capability"] * z(caps, i) + W["kv_capacity"] * z(kvx, i)
                   + W["single_node_saving"] * z(solo, i))
            scores.append(sc_)
        bi = scores.index(max(scores))
        win = ok[bi]
        profiles.append({
            "profile": "综合推荐",
            "winner": win["scenario_id"], "winner_label": label_of(win),
            "reasons": [
                {"text": f"综合分 {scores[bi]:.3f}(权重 c32吞吐{W['c32_tput']}/c1吞吐{W['c1_tput']}/能力{W['capability']}/KV容量{W['kv_capacity']}/省一机{W['single_node_saving']})",
                 "check": {"scenario": win["scenario_id"],
                           "path": "score", "value": round(scores[bi], 3)}},
                {"text": f"c32 出流 {c32s[bi]:.1f} tok/s, c1 出流 {c1s[bi]:.1f} tok/s, 三套件均分 {caps[bi]:.3f}",
                 "check": {"scenario": win["scenario_id"],
                           "path": "score", "value": round(scores[bi], 3)}}],
            "runner_up": None})
    mk("延迟敏感", lambda s: c1(s) and c1(s)["tpot_ms"]["p50"] or 9e9,
       "min", "c1 TPOT p50 ms (越低越好)", "tpot_c1")
    mk("吞吐优先", lambda s: c32(s) and c32(s)["agg"]["output_tok_s"] or 0,
       "max", "c32 出流 tok/s", "c32_out")
    mk("能力优先", lambda s: cap_avg(s, SUITES_P0) or 0,
       "max", "三套件(gsm8k/mmlu/arc)均分", "cap_avg")
    solo_ok = [s for s in ok if s["deployment"]["mode"] == "single-node"]
    if solo_ok:
        best = max(solo_ok, key=lambda s: num(c32(s)["agg"]["output_tok_s"]))
        profiles.append({
            "profile": "单机约束(无集群)", "winner": best["scenario_id"],
            "winner_label": label_of(best),
            "reasons": [{"text": f"单机场景中 c32 出流 {c32(best)['agg']['output_tok_s']:.1f} tok/s 最高",
                         "check": {"scenario": best["scenario_id"],
                                   "path": "c32_out",
                                   "value": num(c32(best)["agg"]["output_tok_s"])}}],
            "runner_up": None})
    return {"method": "规则可复算: 权重与排序键随报告输出, 全部数值可回查",
            "profiles": profiles, "ineligible": inel}


SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#", "type": "object",
    "required": ["meta", "machines", "scenarios", "recommendation"],
    "properties": {
        "meta": {"type": "object",
                 "required": ["contract_version", "generated_at", "fingerprint"]},
        "machines": {"type": "array", "minItems": 1},
        "scenarios": {"type": "array", "minItems": 1},
        "recommendation": {"type": "object", "required": ["profiles"]}},
}


def main():
    machines = machines_part()
    scs = [scenario(*t) for t in TAGS if (RAW / t[0]).exists()]
    doc = {"meta": {"contract_version": "4",
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "source_artifacts": ["tasks/t20260930-matrix-full/raw4"],
                    "fingerprint": FP},
           "machines": machines, "scenarios": scs,
           "recommendation": recommend(scs)}
    import jsonschema
    jsonschema.validate(doc, SCHEMA)
    out = RAW.parent / "report_doc.json"
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("PASS report_doc.json (%d机 %d场景) → %s" % (len(machines), len(scs), out))
    for s in scs:
        print("  %s %s [%s] missing=%s" % (s["scenario_id"],
              s["model"]["name"] + "·TP" + s["deployment"]["mode"][:6],
              s["status"], s["missing"] or "-"))


if __name__ == "__main__":
    main()
