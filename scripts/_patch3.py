# -*- coding: utf-8 -*-
"""一次性补丁: 三大benchmark表合并专属列+vLLM列(每行直带). 用后即删."""
import ast

P = 'scripts/report_gen4.py'
src = open(P, encoding='utf-8').read()

# 1) 通用: 单元格式化某 phase 的 vLLM 指标(紧凑一格)
helper = '''

def _vcell(sc, ph):
    """该 phase 期间的服务端指标, 压成一格文字; 无数据返回 —。"""
    cn = (sc.get("vllm_metrics") or {}).get("counters") or {}
    hg = (sc.get("vllm_metrics") or {}).get("histograms") or {}
    m = cn.get(ph)
    if not m:
        return "—"
    h = hg.get(ph, {})
    q, h_ = m.get("prefix_queries"), m.get("prefix_hits")
    return (f"成{m.get('requests_success', 0):,.0f}/败{m.get('requests_failed', 0):,.0f} · "
            f"gen {m.get('gen_tokens') or 0:,.0f}tok · "
            f"服务端TTFTp99 {c(h.get('ttft_p99_server_s'), '{:.2f}')}s · "
            f"TPOTp99 {c(h.get('tpot_p99_server_s'), '{:.3f}')}s · "
            f"排队p99 {c(h.get('queue_p99_server_s'), '{:.2f}')}s")

'''
src = src.replace('\ndef _emit_vllm(', helper + '\ndef _emit_vllm(', 1)

# 2) 性能表: 每行尾加"该测试期间的服务端指标"列
old_p = '''            L.extend(["| 并发 | n | TTFT p50/p90/p99 ms | TPOT p50/p90/p99 ms | ITL p99/max | "
                      "E2E p99 | 单流出流 p50 | 出流 tok/s | QPS | goodput | 成/败 |",
                      "|---|---|---|---|---|---|---|---|---|---|---|---|"])'''
new_p = '''            phk = "phase:" + w['workload_id'].split('-')[0]
            vc = _vcell(sc, phk)
            L.extend(["| 并发 | n | TTFT p50/p90/p99 ms | TPOT p50/p90/p99 ms | ITL p99/max | "
                      "E2E p99 | 单流出流 p50 | 出流 tok/s | QPS | goodput | 成/败 | 该测试期间的服务端指标 |",
                      "|---|---|---|---|---|---|---|---|---|---|---|---|"])'''
assert old_p in src
src = src.replace(old_p, new_p, 1)
old_row = '''                    f"{rel.get('completed', '—')}/{rel.get('failed', '—')} |")'''
new_row = '''                    f"{rel.get('completed', '—')}/{rel.get('failed', '—')} | {vc} |")'''
assert old_row in src
src = src.replace(old_row, new_row, 1)

# 3) 能力表: 每行尾加 vLLM 列(phase:cap)
old_c = '''        L.extend(["| 套件 | 维度 | acc | 对/n | 平均输出tok | 失败 | 状态 |",
                  "|---|---|---|---|---|---|---|"])'''
new_c = '''        vc_cap = _vcell(sc, "phase:cap")
        L.extend(["| 套件 | 维度 | acc | 对/n | 平均输出tok | 失败 | 状态 | 能力评测期间的服务端指标 |",
                  "|---|---|---|---|---|---|---|---|"])'''
assert old_c in src
src = src.replace(old_c, new_c, 1)
src = src.replace('''                         f"缺: {cs.get('missing_reason', '未测')} |")''',
                  '''                         f"缺: {cs.get('missing_reason', '未测')} | {'—' if not cs.get('score') else vc_cap} |")''', 1)
src = src.replace('''                         f"{(cs.get('reliability') or {}).get('requests_failed', '—')} | 实测 |")''',
                  '''                         f"{(cs.get('reliability') or {}).get('requests_failed', '—')} | 实测 | {vc_cap} |")''', 1)

# 4) 智能体: 列表改表格, 每行带 vLLM 列(phase:agent)
old_a = '''        ag = sc.get("agent_metrics") or {}
        if ag:
            m = ag.get("metrics") or {}
            L.append(f"- 工具选择 {c(m.get('selection_acc'), '{:.3f}')} · "
                     f"参数抽取 {c(m.get('args_acc'), '{:.3f}')} · "
                     f"循环成功率 {c(m.get('loop_success'), '{:.3f')}")'''
new_a = '''        ag = sc.get("agent_metrics") or {}
        vc_ag = _vcell(sc, "phase:agent")
        if ag:
            m = ag.get("metrics") or {}
            L.extend(["| 指标 | 数值 | 智能体评测期间的服务端指标 |", "|---|---|---|"])
            L.append(f"| 工具选择（含克制） | {c(m.get('selection_acc'), '{:.3f}')} | {vc_ag} |")
            L.append(f"| 参数抽取 | {c(m.get('args_acc'), '{:.3f}')} | {vc_ag} |")
            L.append(f"| 多轮回环成功率 | {c(m.get('loop_success'), '{:.3f')} | {vc_ag} |")
            bf = ag.get("bfcl") or {}
            if bf.get("irrelevance") is not None or bf.get("simple") is not None:
                L.append(f"| BFCL 无关克制 | {c(bf.get('irrelevance'), '{:.3f}')} | {vc_ag} |")
                L.append(f"| BFCL 结构分（保守下界） | {c(bf.get('simple'), '{:.3f}')} | {vc_ag} |")
            L.append("")'''
assert old_a in src
src = src.replace(old_a, new_a, 1)

# 5) 删除三处独立 _emit_vllm 调用(已并入行)
for call in ['        L.extend(_emit_vllm(sc, ["phase:w1", "phase:w2", "phase:w3", "phase:w4",\n                                 "phase:w5", "phase:w6", "phase:probe"],\n                            "性能测试期间的服务端指标"))',
             '        L.extend(_emit_vllm(sc, ["phase:cap"], "能力评测期间的服务端指标"))',
             '        L.extend(_emit_vllm(sc, ["phase:agent"], "智能体评测期间的服务端指标"))']:
    src = src.replace(call, '        L.append("")')

open(P, 'w', encoding='utf-8').write(src)
ast.parse(src)
print('merged-columns OK')
