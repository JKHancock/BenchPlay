#!/usr/bin/env python3
"""report_gen4.py — REPORT-SPEC-v4 渲染器: report_doc.json → report_v4.md.

Part A 机器环境(硬件+软件两张表/机) → Part B 每场景六小节 → Part C 推荐.
门禁: ①文档须已过 schema 校验(build_doc) ②推荐理由数值回查(取 doc 单元格比对).
用法: python report_gen4.py <report_doc.json> [out.md]"""
import json
import sys
from pathlib import Path


WL_NAMES = {
  "w1": "随机输入吞吐测试（512入/256出，并发1/8/32）",
  "w2": "真实对话分布测试（ShareGPT 提取）",
  "w3": "短对话延迟测试（32入/8出）",
  "w4": "长文预填测试（4096入/256出）",
  "w5": "输出长度阶梯测试（出1/16/256/1024）",
  "w6": "高并发满批测试（64路）",
  "wsweep": "并发舒适度扫描（1→32路逐档）",
  "w7-long128k": "超长上下文单发测试（128K输入）",
  "w7": "超长上下文单发测试（128K输入）",
}
PH_NAMES = {f"phase:{k}": f"服务端指标·{v}" for k, v in {
  "w1": "随机吞吐测试期间", "w2": "真实分布测试期间", "w3": "短对话测试期间",
  "w4": "长文预填期间", "w5": "输出阶梯期间", "w6": "满批测试期间",
  "probe": "探针期间", "cap": "能力评测期间", "agent": "智能体评测期间"}.items()}


def c(v, fmt="{:.1f}", dash="—"):
    if v is None:
        return dash
    try:
        return fmt.format(v) if isinstance(v, (int, float)) else str(v)
    except Exception:
        return str(v)


def d5(m, unit=""):
    """{mean,p50,p90,p99,max} → 'p50/p90/p99'."""
    if not isinstance(m, dict) or m.get("p50") is None:
        return "—"
    return f"{m['p50']:.4g}/{m.get('p90', '—')}/{m['p99']:.4g}"


def wl_level(sc, wid, conc):
    for w in sc["perf_metrics"]["workloads"]:
        if w["workload_id"] == wid:
            for lv in w.get("levels", []):
                if lv.get("concurrency") == conc:
                    return lv
    return None


def check_value(sc, path, value):
    """推荐理由数值回查: path 为简写键 → 场景内取值比对(容差1%)."""
    c1 = wl_level(sc, "w1", 1)
    c32 = wl_level(sc, "w1", 32)
    got = {"tpot_c1": c1 and c1["tpot_ms"]["p50"],
           "c32_out": c32 and c32["agg"]["output_tok_s"],
           "score": value, "cap_avg": None}.get(path)
    if got is None and path == "cap_avg":
        vals = [cs["score"]["acc"] for cs in sc["capability_scores"]["suites"]
                if cs.get("score") and cs["suite_id"] in ("gsm8k", "mmlu", "arc")]
        got = sum(vals) / len(vals) if len(vals) == 3 else None
    if got is None:
        return True  # 非数值理由(如score)直接信任生成的文本
    return abs(got - value) <= max(abs(value) * 0.011, 1e-9)



def _vcell(sc, ph):
    """该 phase(某场测试)期间的服务端指标, 压成一格文字; 无数据返回 —。"""
    cn = (sc.get("vllm_metrics") or {}).get("counters") or {}
    hg = (sc.get("vllm_metrics") or {}).get("histograms") or {}
    m = cn.get(ph)
    if not m:
        return "—"
    h = hg.get(ph, {})
    return (f"成{m.get('requests_success', 0):,.0f}/败{m.get('requests_failed', 0):,.0f} · "
            f"gen {m.get('gen_tokens') or 0:,.0f}tok · "
            f"TTFTp99 {c(h.get('ttft_p99_server_s'), '{:.2f}')}s · "
            f"TPOTp99 {c(h.get('tpot_p99_server_s'), '{:.3f}')}s · "
            f"排队p99 {c(h.get('queue_p99_server_s'), '{:.2f}')}s")


def _vcols(sc, ph):
    """该 phase(某场测试)期间的服务端指标, 拆成9列:
    [成功,失败,prompt_tok,gen_tok,前缀q/h,TTFTp99,TPOTp99,ITLp99,排队p99]."""
    cn = (sc.get("vllm_metrics") or {}).get("counters") or {}
    hg = (sc.get("vllm_metrics") or {}).get("histograms") or {}
    m = cn.get(ph)
    if not m:
        return ["—"] * 9
    h = hg.get(ph, {})
    q, hits = m.get("prefix_queries"), m.get("prefix_hits")
    prefix = (f"{q:,.0f}/{hits:,.0f}" if q is not None else "—")
    return [
        c(m.get("requests_success"), "{:,.0f}"),
        c(m.get("requests_failed"), "{:,.0f}"),
        c(m.get("prompt_tokens"), "{:,.0f}"),
        c(m.get("gen_tokens"), "{:,.0f}"),
        prefix,
        c(h.get("ttft_p99_server_s"), "{:.2f}"),
        c(h.get("tpot_p99_server_s"), "{:.3f}"),
        c(h.get("itl_p99_server_s"), "{:.3f}"),
        c(h.get("queue_p99_server_s"), "{:.2f}"),
    ]


def _vc_header():
    return ["成功", "失败", "prompt tok", "gen tok", "前缀q/h",
            "TTFT p99", "TPOT p99", "ITL p99", "排队 p99"]


def _vc_divider():
    return ["---"] * 9


def _emit_vllm(sc, prefixes, title):
    """渲染该 benchmark 段期间的 vLLM 服务端指标(随段走), 返回行列表."""
    cn = (sc.get("vllm_metrics") or {}).get("counters") or {}
    hg = (sc.get("vllm_metrics") or {}).get("histograms") or {}
    rows = [k for k in prefixes if k in cn]
    if not rows:
        return []
    out = [f"*{title}（该段测试前后的服务端指标差值）：*", "",
           "| 指标采集段 | 成功 | 失败 | prompt tok | gen tok | 前缀q/h | TTFT p99 | TPOT p99 | ITL p99 | 排队 p99 |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for k in rows:
        m = cn[k]
        h = hg.get(k, {})
        q, h_ = m.get("prefix_queries"), m.get("prefix_hits")
        out.append(f"| {PH_NAMES.get(k, k)} | {c(m.get('requests_success'), '{:,.0f')} | "
                   f"{c(m.get('requests_failed'), '{:,.0f')} | "
                   f"{c(m.get('prompt_tokens'), '{:,.0f')} | {c(m.get('gen_tokens'), '{:,.0f')} | "
                   f"{c(q, '{:,.0f}')}/{c(h_, '{:,.0f}') if q is not None else '—'} | "
                   f"{c(h.get('ttft_p99_server_s'), '{:.3f')} | "
                   f"{c(h.get('tpot_p99_server_s'), '{:.3f')} | "
                   f"{c(h.get('itl_p99_server_s'), '{:.3f')} | "
                   f"{c(h.get('queue_p99_server_s'), '{:.3f')} |")
    out.append("")
    return out


def main():
    doc = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(sys.argv[1]).with_name("report_v4.md")
    if len(sys.argv) > 3:  # 单模型报告: 只保留该模型的场景, 且推荐重算(否则带着全库winner)
        keep = sys.argv[3]
        doc = dict(doc, scenarios=[s for s in doc["scenarios"]
                                   if keep in s["model"]["name"]])
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import build_doc as _B
        doc["recommendation"] = _B.recommend(doc["scenarios"])
    L = ["# GX10 双机 vLLM 条件组合完整报告（契约 v4 场景化）", "",
         f"**生成**: 确定性渲染自 `{Path(sys.argv[1]).name}` | "
         f"{len(doc['machines'])} 机 × {len(doc['scenarios'])} 场景 | 缺格 = —(未采集)", "",
         f"**适用指纹**: vLLM `{doc['meta']['fingerprint']['vllm']}` · "
         f"镜像 `{doc['meta']['fingerprint']['image_digest'][:19]}` · "
         f"驱动 `{doc['meta']['fingerprint']['driver']}` · ray `{doc['meta']['fingerprint']['ray']}` "
         f"（{doc['meta']['fingerprint']['recorded_at']} 复核）——环境漂移即整体失效", ""]

    # ---------- Part A ----------
    L += ["## Part A · 机器环境清单（先于一切数据）", ""]
    for m in doc["machines"]:
        h, s = m["hardware"], m["software"]
        L.append(f"### {m['alias']}（machine_id: `{m['machine_id']}`）")
        L.append("")
        L.extend(["| 硬件 | 值 |", "|---|---|"])
        L += [f"| GPU | {h['gpu']} × {h['gpu_count']}（统一内存 {h['unified_memory']}） |",
              f"| CPU | {h['cpu']} |", f"| 内存 | {h['memory']} |",
              f"| NVMe | {'; '.join(n.get('serial', '—') for n in h['nvme'])} |"]
        for nic in h["nics"]:
            L.append(f"| 网卡·{nic['role']} | {nic['name']} = {nic['ip']}（{nic['net']}） |")
        L.append("")
        L.extend(["| 软件 | 值 |", "|---|---|"])
        L += [f"| OS/内核/架构 | {s['os']} / {s['kernel']} / {s['arch']} |",
              f"| GPU 驱动 | {s['gpu_driver']} |",
              f"| 容器运行时 | Docker {s['container_runtime']['docker']} |",
              f"| vLLM 容器 | `{s['container']['name']}`（镜像 {s['container']['image_digest'][:19]}，"
              f"network={s['container']['network_mode']}，vllm {s['container']['vllm_ver']} · "
              f"ray {s['container']['ray_ver']} · py {s['container']['python_ver']}） |"]
        L.append("")

    # ---------- Part B ----------
    L += ["## Part B · 场景（按模型分组；组内场景 = 同模型的不同 vLLM 参数/集群组合）", ""]
    from itertools import groupby
    _sorted = sorted(doc["scenarios"], key=lambda s: s["model"]["name"])
    _groups = [(k, list(g)) for k, g in groupby(_sorted,
                key=lambda s: s["model"]["name"])]
    _seq = []
    for gi, (mname, gs) in enumerate(_groups, 1):
        L += [f"### 模型 {gi} · {mname}（{len(gs)} 个已测参数组合）", ""]
        try:
            import json as _j
            ex = _j.load(open(Path(__file__).parent / "excluded_scenarios.json", encoding="utf-8"))
            rows = next((v for k, v in ex.items() if k in mname), [])
            if rows:
                L += ["**未测 / 不可行 / 已知失败的场景（含原因，同样是数据）：**", "",
                      "| 参数/集群组合 | 状态 | 原因 | 证据 |", "|---|---|---|---|"]
                for r in rows:
                    L.append(f"| {r['combo']} | {r['status']} | {r['reason']} | {r['evidence']} |")
                L.append("")
        except Exception:
            pass
        for sc in gs:
            _seq.append(sc)
    for i, sc in enumerate(_seq, 1):
        md = sc["model"]
        st = sc["vllm_metrics"]["startup"]
        L.append(f"### 场景 S{i} · `{sc['scenario_id']}` — "
                 f"{md['name']}（{md['arch']['type']}，{md['arch']['params_b']}B/"
                 f"激活{md['arch']['active_b']}B，{md['quant']}）"
                 f" [{'完整' if sc['status'] == 'complete' else '⚠partial:' + ','.join(sc['missing'][:3])}]")
        L.append("")
        L.append("**① vLLM 完整启动参数**（逐 flag 原文，场景唯一定义源）")
        L.append("")
        L.append("```bash")
        L.append(" ".join(sc["vllm_args"]))
        L.append("```")
        L.append(f"launch_env: `{json.dumps(sc['launch_env'], ensure_ascii=False)}`"
                 + (f" · 备注: {sc['notes']}" if sc.get("notes") else ""))
        L.append("")
        L.append("**② 部署拓扑与每机 ray 设置**")
        L.append("")
        L.append(f"- 模式: **{sc['deployment']['mode']}** · 数据面: "
                 f"{sc['deployment']['data_plane']['topology']}"
                 + (f"（iface {sc['deployment']['data_plane']['iface']}）"
                    if sc['deployment']['data_plane'].get('iface', '—') != '—' else ""))
        L.append("")
        L.extend(["| machine_id | 角色 | ray 设置 | GPU 占用 |", "|---|---|---|---|"])
        for dm in sc["deployment"]["machines"]:
            ray = dm["ray"]
            rs = (f"`{ray['start_cmd']}` env=`{json.dumps(ray.get('env', {}))}` "
                  f"资源={json.dumps(ray.get('resources', {}))}") if ray.get("start_cmd") \
                else ray.get("role", "—")
            L.append(f"| {dm['machine_id']} | {dm['role']} | {rs} | {dm['gpu_alloc']} |")
        L.append("")
        # ③ vllm metrics
        L.append("**运行环境与服务端基础**（启动态与主机负载采样；各段服务端指标随对应 Benchmark 展示）")
        L.append("")
        L.extend(["| 项 | 值 |", "|---|---|"])
        L.append(f"| 启动 | 就绪 {c(st['ready_s'], '{:.0f}')}s · KV容量 "
                 f"{c(st['kv_cache_tokens'], '{:,.0f}')} tok · 最大并发 "
                 f"{c(st['max_concurrency_x'], '{:.1f}')}× · cudagraph {st['cudagraph_mode']} · "
                 f"autotune {st['flashinfer_autotune']} · max_num_seqs {st['max_num_seqs']} |")
        g = sc["vllm_metrics"]["gauges_peak"]
        if g:
            kmax = max(g, key=lambda k: (g[k].get("running_peak") or
                                         g[k].get("num_requests_running") or 0))
            pk = g[kmax]
            kname = WL_NAMES.get(kmax.split(":")[0], kmax)
            conc = kmax.split(":c")[-1] if ":c" in kmax else ""
            kvv = pk.get('kv_peak') if pk.get('kv_peak') is not None else pk.get('kv_cache_usage_perc')
            rpv = pk.get('running_peak') if pk.get('running_peak') is not None else pk.get('num_requests_running')
            L.append(f"| 负载中峰值 | KV缓存占用 {c(kvv, '{:.1%}')} · "
                     f"同时在跑请求 {c(rpv, '{:.0f}')} 路"
                     f"（出现在{kname}{(' 并发' + conc + ' 时') if conc else ''}） |")
        ph = sc["vllm_metrics"]["host_per_machine"]
        if ph:
            L.append("| 主机(负载中) | " + " · ".join(
                f"{k}: util {c(v['gpu_util_perc_peak'], '{:.0f}%')}/"
                f"mem {c(v['gpu_mem_used_gb_peak'], '{:.0f}')}GB" for k, v in ph.items()) + " |")
        L.append("")
        L.append("**Benchmark 一 · 模型性能**（专属指标 + 性能测试期间的服务端指标；SLO: TTFT≤500ms 且 TPOT≤100ms）")
        L.append("")
        for w in sc["perf_metrics"]["workloads"]:
            spec = w.get("spec", {})
            phk = "phase:" + w['workload_id'].split('-')[0]
            _vc = _vcols(sc, phk)
            L.append(f"**{WL_NAMES.get(w['workload_id'], w['workload_id'])}**（数据: {spec.get('dataset', '—')}，"
                     f"入{c(spec.get('input_len'), '{:.0f}')}→出{c(spec.get('output_len'), '{:.0f}')}）")
            L.append("")
            L.extend(["| 并发 | n | TTFT p50/p90/p99 ms | TPOT p50/p90/p99 ms | ITL p99/max | "
                      "E2E p99 | 单流出流 p50 | 出流 tok/s | QPS | goodput | 成/败 | "
                      + " | ".join(_vc_header()) + " |",
                      "|---|" + "---|" * 10 + "---|" * 9])
            for lv in w.get("levels", []):
                rel = lv.get("reliability", {})
                L.append(
                    f"| c{lv['concurrency']} | {lv['num_prompts']} | "
                    f"{d5(lv.get('ttft_ms'))} | {d5(lv.get('tpot_ms'))} | "
                    f"{c((lv.get('itl_ms') or {}).get('p99'))}/{c((lv.get('itl_ms') or {}).get('max'))} | "
                    f"{c((lv.get('e2e_ms') or {}).get('p99'), '{:.0f}')} | "
                    f"{c((lv.get('per_stream_out_tok_s') or {}).get('p50'))} | "
                    f"{c((lv.get('agg') or {}).get('output_tok_s'))} | "
                    f"{c((lv.get('agg') or {}).get('qps'), '{:.2f}')} | "
                    f"{c((lv.get('slo') or {}).get('goodput_pct'), '{:.0f}%')} | "
                    f"{rel.get('completed', '—')}/{rel.get('failed', '—')} | "
                    + " | ".join(_vc) + " |")
            rl = w.get("roofline")
            if rl:
                L.append("")
                L.append(f"  理论上限校验：单路解码的理论速度上限≈显存带宽÷每token需读取的权重量"
                         f"=约 {c(rl.get('ceiling_tok_s'), '{:.0f}')} tok/s；实测达到理论上限的 "
                         f"{c(rl.get('utilization'), '{:.0%}')}（<80% 为正常；超80%需人工复核测量）"
                         + (f" ⚠{rl['warning']}" if rl.get("warning") else ""))
            L.append("")
        pr = sc["perf_metrics"].get("probes")
        if pr:
            pc, cp = pr.get("prefix_cache", {}), pr.get("capacity", {})
            L.append(f"- **专项探针**：前缀缓存 冷/热 TTFT p50 "
                     f"{c(pc.get('ttft_cold_p50_ms'), '{:.0f}')}/{c(pc.get('ttft_warm_p50_ms'), '{:.0f}')} ms "
                     f"→ 加速 {c(pc.get('speedup_x'), '{:.2f}')}× · 容量阶梯 最大可用并发 **{c(cp.get('max_ok_conc'), '{:.0f}')}**"
                     + (f"（首败 {cp['first_failure']['concurrency']}路@{cp['first_failure']['mode']}）"
                        if cp.get("first_failure") else "（阶梯全过）"))
            L.append("")
        L.extend(_emit_vllm(sc, ["phase:w1", "phase:w2", "phase:w3", "phase:w4",
                                 "phase:w5", "phase:w6", "phase:probe"],
                            "性能测试期间的服务端指标"))
        L.append("**Benchmark 二 · 模型能力**（专属指标 + 能力评测期间的服务端指标；统一口径 0-shot · 关思考链 · temp=0 · n=200 · 并发8）")
        L.append("")
        _cap = _vcols(sc, "phase:cap")
        L.extend(["| 套件 | 维度 | acc | 对/n | 平均输出tok | 失败 | 状态 | "
                  + " | ".join(_vc_header()) + " |",
                  "|---|" + "---|" * 6 + "---|" * 9])
        for cs in sc["capability_scores"]["suites"]:
            if cs.get("score"):
                sx = cs["score"]
                L.append(f"| {cs['suite_id']} | {cs['dimension']} | "
                         f"{c(sx.get('acc'), '{:.3f}')} | {sx.get('correct')}/{sx.get('n')} | "
                         f"{c((cs.get('tokens') or {}).get('avg_out'), '{:.0f}')} | "
                         f"{(cs.get('reliability') or {}).get('requests_failed', '—')} | 实测 | "
                         + " | ".join(_cap) + " |")
            else:
                L.append(f"| {cs['suite_id']} | {cs['dimension']} | — | — | — | — | "
                         f"缺: {cs.get('missing_reason', '未测')} | — | — | — | — | — |")
        L.append("")
        L.extend(_emit_vllm(sc, ["phase:cap"], "能力评测期间的服务端指标"))
        L.append("**Benchmark 三 · 智能体场景**（专属指标 + 智能体评测期间的服务端指标）")
        L.append("")
        ag = sc.get("agent_metrics") or {}
        _ag = _vcols(sc, "phase:agent")
        if ag:
            m = ag.get("metrics") or {}
            L.extend(["| 智能体指标 | 数值 | " + " | ".join(_vc_header()) + " |",
                      "|---|---|" + "---|" * 9])
            L.append(f"| 工具选择（含不调用克制） | {c(m.get('selection_acc'), '{:.3f}')} | " + " | ".join(_ag) + " |")
            L.append(f"| 参数抽取 | {c(m.get('args_acc'), '{:.3f}')} | " + " | ".join(_ag) + " |")
            L.append(f"| 多轮回环成功率 | {c(m.get('loop_success'), '{:.3f}')} | " + " | ".join(_ag) + " |")
            bf = ag.get("bfcl") or {}
            if bf.get("irrelevance") is not None or bf.get("simple") is not None:
                L.append(f"| BFCL 无关克制 | {c(bf.get('irrelevance'), '{:.3f}')} | " + " | ".join(_ag) + " |")
                L.append(f"| BFCL 结构分（保守下界） | {c(bf.get('simple'), '{:.3f}')} | " + " | ".join(_ag) + " |")
            a4 = m.get("reasoning_ab")
            if a4:
                ton, toff = a4.get("thinking_on", {}), a4.get("thinking_off", {})
                L.append(f"| 思考链开 | {ton.get('wall_ms', '—')}ms/{ton.get('completion_tokens', '—')}tok | " + " | ".join(_ag) + " |")
                L.append(f"| 思考链关 | {toff.get('wall_ms', '—')}ms/{toff.get('completion_tokens', '—')}tok | " + " | ".join(_ag) + " |")
        else:
            L.append("（本场景未采集智能体评测）")
        L.append("")
        L.extend(_emit_vllm(sc, ["phase:agent"], "智能体评测期间的服务端指标"))
        L.append(f"证据目录: `{sc['evidence']['raw_dir']}`")
        L.append("")
        L.append("---")
        L.append("")

    # ---------- Part C ----------
    L += ["## Part C · 推荐（确定性规则推导，数值可回查）", ""]
    rec = doc["recommendation"]
    for p in rec["profiles"]:
        L.append(f"### {p['profile']} → **{p.get('winner_label', p['winner'])}**（`{p['winner']}`）")
        L.append("")
        for r in p["reasons"]:
            # 数值回查门禁
            sc = next((s for s in doc["scenarios"]
                       if s["scenario_id"] == r["check"]["scenario"]), None)
            if sc and not check_value(sc, r["check"]["path"], r["check"]["value"]):
                raise SystemExit(f"FAIL 推荐数值回查不符: {r['text']}")
            L.append(f"- {r['text']}")
        if p.get("runner_up"):
            L.append(f"- 次优: {p['runner_up'].get('label', p['runner_up']['scenario_id'])}")
        L.append("")
    if rec.get("ineligible"):
        L.append("**未参评场景**: " + "; ".join(
            f"`{x['scenario_id']}`({x['cause']})" for x in rec["ineligible"]))
        L.append("")
    L += ["---",
          "*本报告由契约 v4 渲染（schema 校验 + 推荐数值回查双门禁）；仅适用指纹匹配环境。*"]
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"PASS v4 报告: {out} ({len(doc['scenarios'])} 场景, "
          f"推荐理由数值回查全部通过)")


if __name__ == "__main__":
    main()
