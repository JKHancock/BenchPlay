#!/usr/bin/env python3
"""报告生成器 v3(契约 REPORT-SPEC.md): rows.jsonl(schema v3) → 完整 markdown.

v3 相比 v2: 每行=多档并发性能(c1/c8/c32) + 三套件能力(gsm8k/mmlu/arc)
+ vLLM服务端指标(性能段/能力段差值, 含服务端分位数) + 屋顶线利用率
+ 确定性结论(规则推导, 非人工撰写).
用法: python report_gen.py <rows.jsonl> [out.md]"""
import json
import sys
from pathlib import Path


def cell(v, fmt="{:.1f}"):
    if v is None:
        return "—"
    try:
        return fmt.format(v) if isinstance(v, (int, float)) else str(v)
    except Exception:
        return str(v)


def pm(d):
    if not isinstance(d, dict) or d.get("p50") is None:
        return "—"
    return f"{d['p50']:.0f}/{d['p90']:.0f}/{d['p99']:.0f}"


def pm1(d):
    if not isinstance(d, dict) or d.get("p50") is None:
        return "—"
    return f"{d['p50']:.1f}/{d['p90']:.1f}/{d['p99']:.1f}"


def label(r):
    p = r.get("params", {})
    return f"{p.get('model', '?')}·TP{p.get('tp', '?')}"


def machine_line(m):
    return (f"| {m.get('hostname', '—')} | {m.get('role', '—')} | {m.get('mgmt_ip', '—')} | "
            f"{m.get('data_ip', '—')} | {m.get('os', '—')} | {m.get('kernel', '—')} | {m.get('gpu', '—')} "
            f"+ drv {m.get('driver', '—')} | {m.get('cpu', '—')}核/{m.get('memory', '—')} | "
            f"Docker {m.get('docker', '—')} | {m.get('image_digest', '—')[:19]} | {m.get('nvme_serial', '—')} |")


def cap_pair(cap, suite):
    return cap.get(suite) or {}


def px(d, fmt="%.0f"):
    return "—" if not isinstance(d, dict) or d.get("p50") is None else fmt % d["p50"]


def px99(d, fmt="%.0f"):
    return "—" if not isinstance(d, dict) or d.get("p99") is None else fmt % d["p99"]


def main():
    rows = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()]
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(sys.argv[1]).with_suffix(".md")
    L = ["# 条件组合完整数据报告（契约 v3 渲染）", "",
         f"**生成**: 确定性渲染自 `{Path(sys.argv[1]).name}`（{len(rows)} 行）| 缺格 = —(未采集)", ""]

    fp = rows[0].get("fingerprint") if rows else None
    if fp:
        L += [f"**适用指纹**: vllm镜像 `{fp.get('vllm_image', '—')}` 驱动 `{fp.get('driver', '—')}` "
              f"GPU `{fp.get('gpu', '—')}`（{fp.get('recorded_at', '—')}），环境漂移即整体失效", ""]

    # 一、主表(一行一运行: 参数紧凑 + c1性能 + 三套件能力)
    L += ["## 一、主表（一行一运行：参数 · 单流性能 · 能力三套件）", "",
          "| # | 模型 | 架构/量化 | TP | 集群 | max-len | seqs | cp/pc | "
          "c1 TTFT p50/90/99 ms | c1 TPOT p50/90/99 ms | c1 出流 tok/s | gsm8k | mmlu | arc |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        p = r.get("params", {})
        cl = r.get("cluster", {})
        lv = (r.get("perf", {}) or {}).get("levels", {})
        c1 = lv.get("c1", {})
        cap = r.get("capability", {}) or {}
        L.append(
            f"| {i} | {p.get('model', '—')} | {p.get('arch', '—')}/{p.get('quant', '—')} | "
            f"{p.get('tp', '—')} | {cl.get('mode', '—')} | {p.get('max_model_len', '—')} | "
            f"{p.get('max_num_seqs', '—')} | "
            f"{p.get('chunked_prefill') and 'cp' or '—'}/{p.get('prefix_caching') and 'pc' or '—'} | "
            f"{pm(c1.get('ttft_ms'))} | {pm1(c1.get('tpot_ms'))} | {cell(c1.get('output_tok_s'))} | "
            + " | ".join(cell((cap.get(s) or {}).get("acc"), "{:.3f}") for s in ("gsm8k", "mmlu", "arc"))
            + " |")
    L.append("")

    # 二、多档并发性能
    L += ["## 二、多档并发性能（c1 / c8 / c32，random-512入/256出/ignore_eos/temp=0）", ""]
    any_levels = any((r.get("perf", {}) or {}).get("levels") for r in rows)
    if any_levels:
        L += ["| 组合 | 档 | n | TTFT p50/p99 ms | TPOT p50/p99 ms | 出流 tok/s | 总吞吐 tok/s | QPS | 成/败 | 平均输出tok |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            lv = (r.get("perf", {}) or {}).get("levels", {})
            for k in ("c1", "c8", "c32"):
                v = lv.get(k)
                if not v:
                    continue
                L.append(
                    f"| {label(r)} | {k[1:]} | {v.get('num_prompts', '—')} | "
                    f"{px(v.get('ttft_ms'))}/{px99(v.get('ttft_ms'))} | "
                    f"{px(v.get('tpot_ms'), '%.1f')}/{px99(v.get('tpot_ms'), '%.1f')} | "
                    f"{cell(v.get('output_tok_s'))} | {cell(v.get('total_tok_s'), '{:.0f}')} | "
                    f"{cell(v.get('qps'), '{:.2f}')} | {v.get('completed', '—')}/{v.get('failed', '—')} | "
                    f"{cell(v.get('avg_completion_tokens'), '{:.0f}')} |")
        L.append("")
        # 屋顶线
        L += ["### 屋顶线常识检查（单流解码上限 ≈ 带宽 ÷ 激活权重）", "",
              "| 组合 | 上限 tok/s | c1 实测 | 利用率 | 警告 |", "|---|---|---|---|---|"]
        for r in rows:
            rl = r.get("roofline") or {}
            L.append(f"| {label(r)} | {cell(rl.get('ceiling_tok_s'), '{:.0f}')} | "
                     f"{cell(rl.get('c1_output_tok_s'))} | {cell(rl.get('utilization'), '{:.0%}')} | "
                     f"{rl.get('warning') or '—'} |")
        L.append("")
    else:
        L += ["（未采集多档数据）", ""]

    # 三、模型能力(多套件)
    cp = (rows[0].get("capability_params", {}) if rows else {}) or {}
    L += ["## 三、模型能力（统一口径：0-shot · 关思考链 · temp=0 · 每套件 n=%s · 并发%s）" % (
              cp.get("n_per_suite", "—"), cp.get("concurrency", "—")), "",
          "| 组合 | gsm8k acc | 对/ n | 平均输出tok | mmlu acc | 对/ n | arc acc | 对/ n | 失败请求 |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        cap = r.get("capability", {}) or {}
        g, mm, a = cap.get("gsm8k") or {}, cap.get("mmlu") or {}, cap.get("arc") or {}
        fails = sum((x or {}).get("requests_failed", 0) for x in (g, mm, a))
        L.append(
            f"| {label(r)} | {cell(g.get('acc'), '{:.3f}')} | {g.get('correct', '—')}/{g.get('n', '—')} | "
            f"{cell(g.get('avg_completion_tokens'), '{:.0f}')} | "
            f"{cell(mm.get('acc'), '{:.3f}')} | {mm.get('correct', '—')}/{mm.get('n', '—')} | "
            f"{cell(a.get('acc'), '{:.3f}')} | {a.get('correct', '—')}/{a.get('n', '—')} | {fails} |")
    L += ["",
          "*注: 0-shot 关思考链口径低于官方 few-shot 属预期, 看横向相对差; "
          "选择题要求仅输出字母(平均输出≈2 tok), 数学题自由推理(平均输出≈250 tok)。*", ""]

    # 四、vLLM 服务端指标(分段差值)
    L += ["## 四、vLLM 服务端指标（性能段=idle→Track1后, 能力段=Track1→Track2后, 计数器差值）", "",
          "| 组合 | 段 | 成功(stop+len) | 失败(abort+err) | prompt tok | gen tok | 前缀命中q/h | TTFT p99(服务端) | TPOT p99(服务端) | ITL p99 | 排队 p99 |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        vm = r.get("vllm_metrics", {}) or {}
        for seg in ("perf", "cap"):
            m = vm.get(seg) or {}
            q, h = m.get("prefix_queries"), m.get("prefix_hits")
            hr = f"{cell(q, '{:,.0f}')}/{cell(h, '{:,.0f}')}" if q is not None else "—"
            L.append(
                f"| {label(r)} | {seg} | {cell(m.get('requests_success'), '{:,.0f}')} | "
                f"{cell(m.get('requests_failed'), '{:,.0f}')} | "
                f"{cell(m.get('prompt_tokens'), '{:,.0f}')} | {cell(m.get('gen_tokens'), '{:,.0f}')} | {hr} | "
                f"{cell(m.get('ttft_p99_server_s'), '{:.3f}')} | "
                f"{cell(m.get('tpot_p99_server_s'), '{:.3f}')} | "
                f"{cell(m.get('itl_p99_server_s'), '{:.3f}')} | "
                f"{cell(m.get('queue_p99_server_s'), '{:.3f}')} |")
    L += ["",
          "### KV 缓存容量与最大可并发倍数（启动日志 kv_cache_utils 实测行）", "",
          "| 组合 | KV 容量(tokens) | 最大并发×(40,960/请求) | 来源 |", "|---|---|---|---|"]
    for r in rows:
        c = (r.get("vllm_metrics", {}) or {}).get("capacity") or {}
        L.append(f"| {label(r)} | {cell(c.get('kv_capacity_tokens'), '{:,.0f}')} | "
                 f"{cell(c.get('max_concurrency_x'), '{:.1f}')} | {c.get('kv_source', '—')} |")
    L += ["",
          "*注: 前缀命中 0 属预期——random 数据集与各题独立问句无共享前缀块; "
          "KV/running 为相位后 gauge(已回落), 负载中峰值采样自 v3.1 起为采集义务。*", ""]

    # 五、每机器运行环境 + 集群拓扑
    L += ["## 五、每机器运行环境与集群拓扑", ""]
    for i, r in enumerate(rows, 1):
        cl = r.get("cluster", {})
        L.append(f"### r{i} · {cl.get('mode', '—')}"
                 + (f"（head={cl.get('head')} workers={','.join(cl.get('workers', []))} "
                    f"数据面={cl.get('data_plane')} 网卡={cl.get('iface')} ray={cl.get('ray')}）"
                    if cl.get("mode") != "single-node" else "（无集群, 单机服务）"))
        L.append("")
        L.append("| 主机名 | 角色 | 管理口 | 数据口 | OS | 内核 | GPU/驱动 | CPU/内存 | Docker | 镜像 | NVMe序列 |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for m in r.get("machines", []):
            L.append(machine_line(m))
        L.append("")

    # 六、vLLM 完整启动参数
    L += ["## 六、vLLM 完整启动参数（逐 flag 原文 + 启动环境变量 + 就绪耗时）", ""]
    for i, r in enumerate(rows, 1):
        args = " ".join(r.get("vllm_args", [])) or "—(未采集)"
        env = json.dumps(r.get("launch_env", {}), ensure_ascii=False)
        srs = r.get("serve_ready_s")
        L.append(f"- **r{i}** `{args}`")
        L.append(f"  - launch_env: `{env}` · serve就绪耗时: "
                 f"{'%ds' % srs if srs else '—'}")
        note = (r.get("notes") or "").strip()
        if note:
            L.append(f"  - ⚠备注: {note}")
    L.append("")

    # 七、确定性结论(规则推导)
    L += ["## 七、确定性结论（由数据规则推导，非人工撰写）", ""]
    try:
        ok = [r for r in rows
              if (r.get("perf", {}).get("levels", {}).get("c1", {}).get("output_tok_s"))]
        if ok:
            # 延迟最优 = c1 TPOT p50 最小; 吞吐最高 = c1 出流最大
            fast = min(ok, key=lambda r: r["perf"]["levels"]["c1"]["tpot_ms"]["p50"])
            best = max(ok, key=lambda r: r["perf"]["levels"]["c1"]["output_tok_s"])
            L.append(f"- **单流延迟最优**: {label(fast)} —— c1 TPOT p50 "
                     f"{fast['perf']['levels']['c1']['tpot_ms']['p50']:.1f} ms，"
                     f"出流 {fast['perf']['levels']['c1']['output_tok_s']:.1f} tok/s")
            L.append(f"- **单流吞吐最高**: {label(best)} —— {best['perf']['levels']['c1']['output_tok_s']:.1f} tok/s"
                     f"（TP{best['params'].get('tp')}，{best['params'].get('arch', '')}架构）")
        caps = [r for r in rows
                if all((r.get("capability", {}) or {}).get(s, {}).get("acc") is not None
                       for s in ("gsm8k", "mmlu", "arc"))]
        if caps:
            def avg_cap(r):
                return sum(r["capability"][s]["acc"] for s in ("gsm8k", "mmlu", "arc")) / 3
            bc = max(caps, key=avg_cap)
            L.append(f"- **能力最佳**: {label(bc)} —— 三套件均分 {avg_cap(bc):.3f} "
                     f"（gsm8k {bc['capability']['gsm8k']['acc']:.3f} / "
                     f"mmlu {bc['capability']['mmlu']['acc']:.3f} / arc {bc['capability']['arc']['acc']:.3f}）")
        c32 = [r for r in rows if r.get("perf", {}).get("levels", {}).get("c32", {}).get("output_tok_s")]
        if c32:
            bt = max(c32, key=lambda r: r["perf"]["levels"]["c32"]["output_tok_s"])
            L.append(f"- **高并发吞吐最高**: {label(bt)} —— c32 出流 "
                     f"{bt['perf']['levels']['c32']['output_tok_s']:.0f} tok/s，"
                     f"QPS {bt['perf']['levels']['c32'].get('qps', 0):.2f}")
        L.append("")
    except Exception as e:
        L += [f"（结论推导异常: {e}）", ""]

    L += ["---",
          "*本报告由契约 v3 渲染；仅适用指纹匹配环境，版本变更即失效。*"]
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"PASS 报告已生成: {out} ({len(rows)} 行)")


if __name__ == "__main__":
    main()
