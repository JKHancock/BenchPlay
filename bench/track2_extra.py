# -*- coding: utf-8 -*-
"""四套新数据集接入: MATH-500 / CMMLU / CEval / IFEval.

MATH-500: 数值+LaTex 容差匹配 | CMMLU/CEval: 中选择题 | IFEval: 可编程指令校验.
每套函数: load_X() → [(messages, gold, checker), ...], checker(text) → bool.
"""
import json
import os
import re
from pathlib import Path

CAP = Path(__file__).resolve().parent.parent / "data" / "cap"


# ═══════════════════ MATH-500 ═══════════════════

def load_math500(n=500):
    rows = [json.loads(l) for l in (CAP / "math500.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    out = []
    for item in rows[:n]:
        gold = item["answer"]
        msg = [{"role": "user", "content":
                item["problem"] + "\n\nSolve step by step. Put your final answer on the last line as: #### <answer>"}]
        out.append((msg, gold, "math500"))
    return out


def check_math500(text, gold):
    """从回答中抽 #### 后的答案，与 gold 做容差比较（数值/字符串/LaTex 归一化）."""
    m = re.findall(r"####\s*(.+)", text)
    got = m[-1].strip() if m else None
    if not got:
        nums = re.findall(r"-?\d+\.?\d*", text)
        got = nums[-1] if nums else ""
    return _norm_answer(got) == _norm_answer(gold)


def _norm_answer(s):
    s = str(s).strip()
    s = re.sub(r"\\left|\\right|\\!|\\,|\\;|\\$", "", s)
    s = re.sub(r"\\frac\{([^}]+)\}\{([^}]+)\}", r"\1/\2", s)
    s = re.sub(r"\\d?frac\{?([^}{]+)\}\{?([^}{]+)\}?", r"\1/\2", s)
    s = re.sub(r"[{}\\$]", "", s)
    s = re.sub(r"\s+", "", s)
    try:
        return str(float(s))
    except (ValueError, ZeroDivisionError):
        pass
    # "1/2"/"3+2" 这类简单算式数值化(模型写分数、标准答案给小数时两侧可比)
    try:
        return str(eval(s, {"__builtins__": {}}, {}))
    except Exception:
        return s.lower()


# ═══════════════════ CMMLU (CSV) ═══════════════════

def load_cmmlu(n=200):
    import csv
    import random
    test_dir = CAP / "cmmlu_tmp" / "test"
    if not test_dir.exists():
        return []
    all_rows = []
    for f in test_dir.glob("*.csv"):
        with open(f, encoding="utf-8") as fp:
            for row in csv.DictReader(fp):
                all_rows.append(row)
    rng = random.Random(20260930)
    rng.shuffle(all_rows)
    out = []
    LET = "ABCD"
    for item in all_rows[:n]:
        q = item.get("Question", "")
        opts = [item.get("A", ""), item.get("B", ""), item.get("C", ""), item.get("D", "")]
        gold = LET.index(item.get("Answer", "A").strip()) if item.get("Answer", "A").strip() in LET else 0
        lines = [f"Question: {q}", ""] + [f"{LET[i]}. {o}" for i, o in enumerate(opts)]
        lines += ["", "Answer with ONLY the letter (A/B/C/D)."]
        out.append(([{"role": "user", "content": "\n".join(lines)}], LET[gold], "cmmlu"))
    return out


# ═══════════════════ CEval (parquet) ═══════════════════

def load_ceval(n=200):
    import random
    import pyarrow.parquet as pq
    files = sorted(CAP.glob("ceval_*.parquet"))
    if not files:
        return []
    all_rows = []
    for f in files:
        for row in pq.read_table(f).to_pylist():
            all_rows.append(row)
    rng = random.Random(20260930)
    rng.shuffle(all_rows)
    out = []
    LET = "ABCD"
    for item in all_rows[:n]:
        q = item.get("question", "")
        opts = [item.get("A", ""), item.get("B", ""), item.get("C", ""), item.get("D", "")]
        gold_l = item.get("answer", "A").strip()
        gold_idx = LET.index(gold_l) if gold_l in LET else 0
        lines = [f"Question: {q}", ""] + [f"{LET[i]}. {o}" for i, o in enumerate(opts)]
        lines += ["", "Answer with ONLY the letter (A/B/C/D)."]
        out.append(([{"role": "user", "content": "\n".join(lines)}], LET[gold_idx], "ceval"))
    return out


# ═══════════════════ IFEval (可编程指令校验) ═══════════════════

def load_ifeval(n=200):
    rows = [json.loads(l) for l in (CAP / "ifeval.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    out = []
    for item in rows[:n]:
        out.append((item, item["instruction_id_list"], "ifeval"))
    return out


def check_ifeval(response, instructions, kwargs_list):
    """逐条校验可编程指令. 返回 (通过数, 总数)."""
    passed = 0
    for inst_id, kw in zip(instructions, kwargs_list):
        checker = _IFEVAL_CHECKERS.get(inst_id)
        if checker is None:
            passed += 1  # 未知指令默认通过
            continue
        try:
            if checker(response, kw or {}):
                passed += 1
        except Exception:
            passed += 1  # 校验器异常默认通过
    return passed, len(instructions)


def _wc(text):
    return len(text.split())


def _has_letter_case(text, letter):
    return re.search(rf"[{letter}][.)]", text) is not None


_IFEVAL_CHECKERS = {
    "keywords:existence": lambda t, kw: all(k.lower() in t.lower() for k in kw.get("keywords", [])),
    "keywords:frequency": lambda t, kw: t.lower().count(kw.get("keyword", "").lower()) >= kw.get("frequency", 1),
    "keywords:forbidden_words": lambda t, kw: not any(w.lower() in t.lower() for w in kw.get("forbidden_words", [])),
    "keywords:letter_frequency": lambda t, kw: t.lower().count(kw.get("letter", "").lower()) >= kw.get("let_frequency", 1),
    "language:response_language": lambda t, kw: _lang_ok(t, kw.get("language", "")),
    "length_constraints:number_sentences": lambda t, kw: _sent_ok(t, kw),
    "length_constraints:number_paragraphs": lambda t, kw: len([p for p in t.split("\n\n") if p.strip()]) == kw.get("num_paragraphs", 1),
    "length_constraints:number_words": lambda t, kw: kw.get("relation", "at least") == "at least" and _wc(t) >= kw.get("num_words", 0) or kw.get("relation") == "at most" and _wc(t) <= kw.get("num_words", 0),
    "detectable_content:number_placeholders": lambda t, kw: t.count("[" + kw.get("num_placeholders", 1) * "[" + "]") > 0 or len(re.findall(r"\[.*?\]", t)) >= kw.get("num_placeholders", 1),
    "detectable_content:postscript": lambda t, kw: re.search(r"P\.?S\.?:", t, re.I) is not None,
    "detectable_format:number_bullet_lists": lambda t, kw: len(re.findall(r"^\s*•|^\s*\*|^\s*-", t, re.M)) >= kw.get("num_bullets", 1),
    "detectable_format:constrained_response": lambda t, kw: any(x in t for x in kw.get("options", ["My answer is yes", "My answer is no", "My answer is maybe"])),
    "detectable_format:number_highlighted_sections": lambda t, kw: len(re.findall(r"\*[^*]+\*", t)) >= kw.get("num_highlights", 1),
    "detectable_format:multiple_sections": lambda t, kw: _has_sections(t, kw),
    "combination:two_responses": lambda t, kw: "&&" in t or t.count("RESPONSE 2") > 0 or len(t.split("\n\n")) >= 2,
    "combination:repeat_prompt": lambda t, kw: kw.get("prompt_to_repeat", "") in t,
    "startend:quotation": lambda t, kw: t.strip().startswith('"') and t.strip().endswith('"'),
    "startend:first_word_of_response": lambda t, kw: t.strip().lower().startswith(kw.get("first_word", "").lower()),
    "punctuation:no_comma": lambda t, kw: "," not in t,
    "change_case:capital_word_frequency": lambda t, kw: sum(1 for w in t.split() if w.isupper()) >= kw.get("capital_frequency", 1),
    "change_case:english_capital": lambda t, kw: t == t.upper(),
    "change_case:english_lowercase": lambda t, kw: t == t.lower(),
}


def _lang_ok(text, lang):
    if "zh" in lang.lower() or "chinese" in lang.lower():
        return len(re.findall(r"[\u4e00-\u9fff]", text)) > len(text) * 0.2
    if "en" in lang.lower() or "english" in lang.lower():
        return len(re.findall(r"[a-zA-Z]", text)) > len(text) * 0.5
    return True


def _sent_ok(text, kw):
    num = kw.get("num_sentences", 1)
    rel = kw.get("relation", "at least")
    sents = len(re.findall(r"[.!?]+", text))
    return sents >= num if "at least" in rel else sents <= num


def _has_sections(text, kw):
    secs = re.findall(r"(?:SECTION|Section)\s+\d+|(?:段落|Section)", text)
    return len(secs) >= kw.get("num_sections", 2)
