# -*- coding: utf-8 -*-
"""一次性补丁: agent_metrics 真数值入汇编+渲染直出. 用后即删."""
import ast

# --- build_doc.py: 场景行装配 agent_metrics ---
P1 = 'scripts/build_doc.py'
s = open(P1, encoding='utf-8').read()
anchor = '        cap_suites = []'
assert anchor in s
inject = '''        # 智能体评测真数值直出(不再引用证据目录)
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
        cap_suites = []'''
s = s.replace(anchor, inject, 1)
anchor2 = '"capability_scores": {"suites": cap_suites},'
assert anchor2 in s
s = s.replace(anchor2, anchor2 + '\n            "agent_metrics": agent_metrics,', 1)
open(P1, 'w', encoding='utf-8').write(s)
ast.parse(s)

# --- report_gen4.py: Benchmark三 渲染 bfcl 直出 ---
P2 = 'scripts/report_gen4.py'
r = open(P2, encoding='utf-8').read()
old = '''            a4 = m.get("reasoning_ab")
            if a4:
                ton, toff = a4.get("thinking_on", {}), a4.get("thinking_off", {})
                L.append(f"- 思考链开/关对比：开 {ton.get('wall_ms', '—')}ms/"
                         f"{ton.get('completion_tokens', '—')}tok · "
                         f"关 {toff.get('wall_ms', '—')}ms/"
                         f"{toff.get('completion_tokens', '—')}tok")
        else:
            L.append("（智能体评测原始结果见证据目录 agent.json / bfcl.json；本场景汇编字段待接入）")'''
new = '''            a4 = m.get("reasoning_ab")
            if a4:
                ton, toff = a4.get("thinking_on", {}), a4.get("thinking_off", {})
                L.append(f"- 思考链开/关对比：开 {ton.get('wall_ms', '—')}ms/"
                         f"{ton.get('completion_tokens', '—')}tok · "
                         f"关 {toff.get('wall_ms', '—')}ms/"
                         f"{toff.get('completion_tokens', '—')}tok")
            bf = ag.get("bfcl") or {}
            if bf.get("irrelevance") is not None or bf.get("simple") is not None:
                L.append(f"- BFCL 函数调用：无关克制(该拒调时拒调) {c(bf.get('irrelevance'), '{:.3f}')} · "
                         f"结构分(下界口径) {c(bf.get('simple'), '{:.3f}')} · "
                         f"循环时延 {c(min([l.get('e2e_ms') or 9e9 for l in (agd_loops or [])], default=None), '{:.2f}') if False else ''}")
                L.append(f"  （工具选择满分=1.0 表示含不调用克制全部正确；结构分为无官方真值的保守下界）")
        else:
            L.append("（本场景未采集智能体评测）")'''
assert old in r
r = r.replace(old, new, 1)
open(P2, 'w', encoding='utf-8').write(r)
ast.parse(r)
print('both patched')
