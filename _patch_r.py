p = 'scripts/report_gen4.py'
src = open(p, encoding='utf-8').read().replace('\r\n', '\n')
old1 = '''    return [
        c(m.get("requests_success"), "{:,.0f}"),
        c(m.get("requests_failed"), "{:,.0f}"),
        c(m.get("prompt_tokens"), "{:,.0f}"),
        c(m.get("gen_tokens"), "{:,.0f}"),
        prefix,
        c(h.get("ttft_p99_server_s"), "{:.2f}"),
        c(h.get("tpot_p99_server_s"), "{:.3f}"),
        c(h.get("itl_p99_server_s"), "{:.3f}"),
        c(h.get("queue_p99_server_s"), "{:.2f}"),
    ]'''
new1 = '''    cum = "\u2020" if m.get("latency_cum_fallback") else ""
    return [
        c(m.get("requests_success"), "{:,.0f}"),
        c(m.get("requests_failed"), "{:,.0f}"),
        c(m.get("prompt_tokens"), "{:,.0f}"),
        c(m.get("gen_tokens"), "{:,.0f}"),
        prefix,
        c(h.get("ttft_p99_server_s"), "{:.2f}") + cum,
        c(h.get("tpot_p99_server_s"), "{:.3f}") + cum,
        c(h.get("itl_p99_server_s"), "{:.3f}") + cum,
        c(h.get("queue_p99_server_s"), "{:.2f}") + cum,
    ]'''
assert old1 in src, "vcols anchor"
src = src.replace(old1, new1)
i = src.find('def _emit_vllm')
assert i > 0
seg = src[i:i+900]
anchor = 'L.append("**" + title'
assert anchor in seg, "title anchor"
new_seg = seg.replace(anchor,
    '_cumf = any((sc.get("vllm_metrics") or {}).get("counters", {}).get(ph, {}).get("latency_cum_fallback") for ph in prefixes)\n'
    '        L.append(("**" + title + ("\uff08\u2020\u5ef6\u8fdf\u5217\u4e3a\u670d\u52a1\u542f\u52a8\u4ee5\u6765\u7d2f\u8ba1\u53e3\u5f84\u2014\u2014\u65e7\u5feb\u7167\u672a\u5b58\u76f4\u65b9\u56fe\u6876\uff1b\u65b0\u7535\u6c60\u8d77\u4e3a\u6bb5\u5185\u771f\u503c\uff09" if _cumf else ""))', 1)
src = src[:i] + new_seg + src[i+900:]
open(p, 'w', encoding='utf-8', newline='\n').write(src)
print('renderer patched')
