#!/usr/bin/env python3
"""model_profile.py — 阶段 M0 模型调研器(任何 serve 之前必跑).

产出 models/<name>.profile.json: 模型能干什么/怎么伺服/坑在哪, 三源交叉:
  ① config.json     — 架构/上下文/rope形态/量化/多模态
  ② safetensors索引 — 权重实证(MTP层/视觉塔/专家结构, 精确权重量GB)
  ③ 模板与词表      — 工具调用标记/聊天模板
教训依据: 2026-09-30 两次翻车 — config无mtp键≠无MTP(权重里有19个);
         rope形态(mrope/partial)决定外拓配方; 方法名是vLLM版本耦合的需容器内核对.

用法: python model_profile.py <model_dir> [--container-check vllm-node]
      (container-check 会在容器内只读grep方法注册表, 需ssh; 不传则跳过③')
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MTP_FAMILY_HINTS = {
    "qwen3_5": "qwen3_5_mtp", "qwen3_next": "qwen3_next_mtp",
    "qwen4_exp": "qwen4_exp_mtp", "deepseek": "deepseek_mtp",
    "glm4": "glm4_moe_mtp", "ernie": "ernie_mtp",
}
TOOL_TEMPLATE_MARKERS = ("<tool_call>", "tool_call", "<tools>", "function_call")


def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def profile_model_dir(d):
    d = Path(d)
    cfg = load_json(d / "config.json")
    tc = cfg.get("text_config") if isinstance(cfg.get("text_config"), dict) else {}
    get = lambda k, default=None: cfg.get(k, tc.get(k, default))  # noqa: E731

    # ---- 权重实证(safetensors index) ----
    weights, total_bytes = {}, 0
    idx_file = d / "model.safetensors.index.json"
    if idx_file.exists():
        idx = load_json(idx_file)
        wmap = idx.get("weight_map", {})
        for name in wmap:
            weights[name] = True
        meta = idx.get("metadata", {})
        total_bytes = int(meta.get("total_size", 0))
    mtp_ws = [n for n in weights if re.search(r"(^|\.)(mtp|nextn|draft)\.", n.lower())]
    mtp_layers = sorted(set(int(m.group(1)) for n in mtp_ws
                            for m in [re.search(r"layers\.(\d+)", n)] if m))
    vision_ws = [n for n in weights if re.search(r"visual|vision|tower", n, re.I)]
    expert_ws = [n for n in weights if "experts" in n.lower()]

    # ---- 聊天模板/工具标记 ----
    template = ""
    for cand in ("tokenizer_config.json", "chat_template.jinja", "chat_template.json"):
        p = d / cand
        if p.exists():
            template += p.read_text(encoding="utf-8", errors="ignore")
    tool_markers = [m for m in TOOL_TEMPLATE_MARKERS if m in template]

    # ---- 上下文与rope形态 ----
    rope = get("rope_scaling") or get("rope_parameters") or {}
    native_ctx = get("max_position_embeddings")
    mrope = bool(rope.get("mrope_section") or getattr(tc or cfg, "get", lambda *a: None)("mrope_section"))
    arch = cfg.get("architectures", ["?"])
    model_type = cfg.get("model_type", "?")

    # ---- MTP 能力判定(权重实证优先, config声明次之) ----
    mtp_declared = get("num_nextn_predict_layers") or get("num_mtp_layers")
    mtp_capability = {
        "has_mtp_weights": len(mtp_ws) > 0,
        "mtp_weight_count": len(mtp_ws),
        "mtp_layer_indices": mtp_layers,
        "config_declared_layers": mtp_declared,
        "suggested_method": next((v for k, v in MTP_FAMILY_HINTS.items()
                                  if k in model_type), None),
        # 单层MTP可递归起草k>1(2026-09-30实测: k=2接受率75.2%, 官方warning提示k>1接受率会降)
        "k_suggestion": (2 if len(mtp_layers) == 1 else max(1, len(mtp_layers)))
                        if mtp_ws or mtp_declared else 0,
        "k_note": "单层=递归起草,k=2实测可用; k越大接受率越低, 1与2都应实测对比",
    }

    prof = {
        "model_dir": str(d), "model_type": model_type, "architectures": arch,
        "quant": cfg.get("quantization_config", {}).get("quant_method") or
                 cfg.get("quant_method") or "unknown",
        "params": {"layers": get("num_hidden_layers"),
                   "experts": get("num_experts"),
                   "attention_heads": get("num_attention_heads"),
                   "kv_heads": get("num_key_value_heads"),
                   "expert_weights_present": len(expert_ws)},
        "weights": {"total_gb": round(total_bytes / 1e9, 2),
                    "vision_tower": len(vision_ws) > 0},
        "context": {"native_max_position": native_ctx,
                    "rope": rope, "is_mrope_hybrid": mrope,
                    "extend_recipe_hint": (
                        "hf-overrides嵌套text_config, 直接写目标max_position_embeddings"
                        "(vLLM 0.30 yarn设计上不乘factor), rope_scaling需带原mrope/partial字段"
                        if mrope or rope else None)},
        "mtp": mtp_capability,
        "tool_calling": {"template_markers": tool_markers,
                         # 教训(2026-09-30): 有<tool_call>标记≠hermes — Qwen3.5系吐XML语法
                         # (<function=name><parameter=k>v), 需qwen3_xml. parser必须探针实测:
                         # serve后发一条required请求看finish_reason=tool_calls, 再发auto请求
                         # 看原始content里的调用语法形态, 二者对上才算parser正确
                         "parser_hint": "qwen3_xml" if "qwen" in model_type and tool_markers
                                        else ("hermes" if tool_markers else None),
                         "parser_must_probe": bool(tool_markers)},
        "multimodal": {"image_token": cfg.get("image_token_id") is not None},
        "recorded_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }
    return prof


def container_check(prof, host, container, user="syspetro"):
    """③' 容器内只读核对: MTP方法注册表 + 工具parser注册名(与模型建议交叉)."""
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
           "-o", "ConnectTimeout=10", f"{user}@{host}"]
    out = {"mtp_method_registered": None, "tool_parsers": []}
    try:
        r = subprocess.run(ssh + [f"docker exec {container} bash -c "
                                  "'grep -h \"\\\"\" "
                                  "/usr/local/lib/python3.12/dist-packages/vllm/config/speculative.py "
                                  "| grep -oE \\\"^[ ]*\\\"[a-z0-9_]+\\\",\\\" | tr -d \\\" ,\\\"'"],
                           capture_output=True, text=True, timeout=30)
        methods = [x for x in r.stdout.splitlines() if x.endswith("_mtp") or x == "mtp"]
        out["mtp_method_registered"] = prof["mtp"]["suggested_method"] in methods
        out["mtp_methods_seen"] = methods
    except Exception as e:
        out["error"] = str(e)[:120]
    try:
        r = subprocess.run(ssh + [f"docker exec {container} ls "
                                  "/usr/local/lib/python3.12/dist-packages/vllm/tool_parsers/"],
                           capture_output=True, text=True, timeout=30)
        out["tool_parsers"] = sorted(re.sub(r"_tool_parser.py$", "", x)
                                     for x in r.stdout.split() if x.endswith(".py"))
    except Exception as e:
        out["error2"] = str(e)[:120]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model_dir")
    ap.add_argument("--out", default=None)
    ap.add_argument("--container-check", default=None,
                    help="host[:container] 容器内只读方法核对, 如 192.168.199.129:vllm-node")
    args = ap.parse_args()
    prof = profile_model_dir(args.model_dir)
    if args.container_check:
        host, _, cont = args.container_check.partition(":")
        prof["container_check"] = container_check(prof, host, cont or "vllm-node")
    out = args.out or (Path(args.model_dir).name + ".profile.json")
    Path(out).write_text(json.dumps(prof, ensure_ascii=False, indent=1), encoding="utf-8")
    # 结论行: 供 Agent 阶段生成器直接消费
    m = prof["mtp"]
    print("M0 profile →", out)
    print("  MTP: %s (weights=%d, layers=%s, method=%s, k=%s)" % (
        "YES" if m["has_mtp_weights"] else "no", m["mtp_weight_count"],
        m["mtp_layer_indices"], m["suggested_method"], m["k_suggestion"]))
    print("  ctx native=%s mrope=%s | quant=%s | weights=%.1fGB | tools=%s→%s" % (
        prof["context"]["native_max_position"], prof["context"]["is_mrope_hybrid"],
        prof["quant"], prof["weights"]["total_gb"],
        prof["tool_calling"]["template_markers"] or "无", prof["tool_calling"]["parser_hint"]))


if __name__ == "__main__":
    main()
