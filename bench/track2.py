# -*- coding: utf-8 -*-
"""Track2 能力评测(替代 C# llm-bench 经 lm_eval 的 Track2, 三套件原生实现).

- gsm8k  : 数学推理, 数值答案抽取(#### N 优先, 兜底取最后数字);
- mmlu   : 57学科知识选择题(按学科分层抽样);
- arc    : ARC-Challenge 科普推理选择题;
统一口径: 0-shot, 关闭思考链(enable_thinking=false), temperature=0,
固定种子抽样(跨行可比), 并发加速. 0-shot 分数低于官方 few-shot 属预期,
横向对比看相对差.

用法:
  python -m bench.track2 --api-base http://192.168.199.129:8000/v1 \
      --model bench --suites gsm8k,mmlu,arc --n 200 --concurrency 8 \
      --data-dir ../data/cap --out cap.json --evidence-dir ev/
扩展四套(加载/校验在 track2_extra, 数据已在 data/cap):
  math500(竞赛数学, 开思考链=公开榜口径, 全500题) / cmmlu / ceval(中文知识选择)
  / ifeval(可编程指令遵循, 严格口径=全部指令通过才算对)
"""
import argparse
import json
import os
import re
import random
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from .common import Client, stdout_utf8, UTF8JSON
from .track2_extra import (load_math500, check_math500, load_cmmlu,
                           load_ceval, load_ifeval, check_ifeval)

HF = "https://hf-mirror.com/datasets"
SUITES = {
    "gsm8k": {
        "url": HF + "/openai/gsm8k/resolve/main/main/test-00000-of-00001.parquet",
        "file": "gsm8k_test.parquet",
    },
    "mmlu": {
        "url": HF + "/cais/mmlu/resolve/main/all/test-00000-of-00001.parquet",
        "file": "mmlu_test.parquet",
    },
    "arc": {
        "url": HF + "/allenai/ai2_arc/resolve/main/ARC-Challenge/test-00000-of-00001.parquet",
        "file": "arc_challenge_test.parquet",
    },
    "hellaswag": {
        # test split 无标签, 用 validation(10042条, label 0-3)
        "url": HF + "/Rowan/hellaswag/resolve/main/data/validation-00000-of-00001.parquet",
        "file": "hellaswag_validation.parquet",
    },
    "winogrande": {
        # xl 配置 validation(1263条): sentence含_, option1/2, answer "1"/"2"
        "url": HF + "/allenai/winogrande/resolve/main/winogrande_xl/validation-00000-of-00001.parquet",
        "file": "winogrande_xl_validation.parquet",
    },
    "truthfulqa": {
        # mc1 多选题(validation 817条): mc1_targets{choices,labels}
        "url": HF + "/truthfulqa/truthful_qa/resolve/main/multiple_choice/validation-00000-of-00001.parquet",
        "file": "truthfulqa_mc1.parquet",
    },
    "openbookqa": {
        "url": HF + "/allenai/openbookqa/resolve/main/main/test-00000-of-00001.parquet",
        "file": "openbookqa_test.parquet",
    },
    "race": {
        # 高中阅读理解 high validation(1021条): article/question/options/answer
        "url": HF + "/ehovy/race/resolve/main/high/validation-00000-of-00001.parquet",
        "file": "race_high_validation.parquet",
    },
}

EXTRA_SUITES = {"math500", "cmmlu", "ceval", "ifeval"}


def ensure_dataset(data_dir, suite):
    import pyarrow.parquet as pq
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, SUITES[suite]["file"])
    if not os.path.exists(path):
        url = SUITES[suite]["url"]
        print("  下载 %s ..." % url)
        r = requests.get(url, timeout=300, stream=True)
        r.raise_for_status()
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        os.replace(tmp, path)
        print("  已存 %s (%.1f MB)" % (path, os.path.getsize(path) / 1e6))
    # 读入即校验可解析(DLP密文/截断文件在这里暴露)
    return [dict(x) for x in pq.read_table(path).to_pylist()]


def norm_num(s):
    if s is None:
        return None
    s = str(s).replace(",", "").replace("$", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


def extract_gsm8k(text, gold):
    """gold: 标准答案里 #### 后的数字串. 返回 (对不对, 抽到的数字串)."""
    if not text:
        return False, None
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    m = re.findall(r"####\s*\$?(-?[\d,]+(?:\.\d+)?)", t)
    got = m[-1] if m else None
    if got is None:
        nums = re.findall(r"-?\d[\d,]*(?:\.\d+)?", t)
        got = nums[-1] if nums else None
    if got is None:
        return False, None
    g = norm_num(gold)
    v = norm_num(got)
    return (g is not None and v is not None and abs(v - g) < 1e-4), got


LETTERS = ["A", "B", "C", "D", "E"]


def extract_letter(text, gold_letter):
    if not text:
        return False, None
    t = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    m = re.search(r"\b([A-E])\b", t) or re.match(r"^([A-E])[).:\s]?", t)
    got = m.group(1) if m else None
    return (got is not None and got == gold_letter), got


def build_mc_question(item):
    """mmlu/arc 通用选择题构造; 返回 (messages, gold_letter).

    gold 兼容三种形态: 字母(A-D)/数字下标(int 0-3)/标签键(answerKey "1"-"4").
    (实测坑: mmlu all 配置的 answer 是 int 0-3, 且 0 是 falsy —
     用 `a or b or c` 链会把 answer=0 吞成空串, 必须显式判 None.)
    """
    q = item.get("question") or ""
    if "choices" in item and isinstance(item["choices"], dict):
        texts = list(item["choices"]["text"])
        labels = list(item["choices"].get("label") or LETTERS[: len(texts)])
    else:
        texts = list(item["choices"] or [])
        labels = LETTERS[: len(texts)]
    raw = item.get("answerKey")
    if raw is None or raw == "":
        raw = item.get("answer")
    gold = None
    if isinstance(raw, int) and 0 <= raw < len(LETTERS):
        gold = LETTERS[raw]
    elif isinstance(raw, str):
        if raw in LETTERS:
            gold = raw
        elif raw.isdigit() and int(raw) < len(LETTERS):
            gold = LETTERS[int(raw)]
        elif labels and raw in labels:
            gold = LETTERS[labels.index(raw)]
    lines = ["Question: %s" % q.strip(), ""]
    for lab, tx in zip(labels, texts):
        lab_n = lab if lab in LETTERS else (
            LETTERS[int(lab)] if str(lab).isdigit() and int(lab) < len(LETTERS) else lab)
        lines.append("%s. %s" % (lab_n, str(tx).strip()))
    lines += ["", "Answer with ONLY the letter (%s) of the correct option." %
              "/".join(LETTERS[: len(texts)])]
    return [{"role": "user", "content": "\n".join(lines)}], gold


def build_hellaswag(item):
    """ctx + 4 endings, label int 0-3 → A-D."""
    q = (item.get("ctx") or "").strip()
    ends = list(item["endings"])
    gold = LETTERS[int(item["label"])] if str(item["label"]).lstrip("-").isdigit() else None
    lines = ["Context: %s" % q, "", "Which ending is the most plausible continuation?"]
    for lab, tx in zip(LETTERS[: len(ends)], ends):
        lines.append("%s. %s" % (lab, str(tx).strip()))
    lines += ["", "Answer with ONLY the letter (%s)." % "/".join(LETTERS[: len(ends)])]
    return [{"role": "user", "content": "\n".join(lines)}], gold


def build_winogrande(item):
    """sentence 含 _ 空位, option1/2, answer "1"/"2" → A/B."""
    s = (item.get("sentence") or "").strip()
    o1, o2 = item.get("option1"), item.get("option2")
    a = str(item.get("answer") or "")
    gold = {"1": "A", "2": "B"}.get(a)
    lines = ["Sentence (with a blank _): %s" % s, "",
             "Which option correctly fills the blank _?",
             "A. %s" % o1, "B. %s" % o2,
             "", "Answer with ONLY the letter (A/B)."]
    return [{"role": "user", "content": "\n".join(lines)}], gold


def build_truthfulqa(item):
    t = item.get("mc1_targets") or {}
    ch, lb = list(t.get("choices") or []), list(t.get("labels") or [])
    if not ch or 1 not in lb:
        return None, None
    gold = LETTERS[lb.index(1)]
    lines = ["Question: %s" % (item.get("question") or "")]
    for L, tx in zip(LETTERS, ch):
        lines.append("%s. %s" % (L, str(tx).strip()))
    lines += ["", "Answer with ONLY the letter."]
    return [{"role": "user", "content": "\n".join(lines)}], gold


def build_openbookqa(item):
    e = dict(item)
    e["question"] = item.get("question_stem") or item.get("question")
    return build_mc_question(e)


def build_race(item):
    opts = list(item.get("options") or [])
    gold = (item.get("answer") or "").strip()
    if len(opts) != 4 or gold not in LETTERS[:4]:
        return None, None
    lines = ["Passage: %s" % (item.get("article") or "").strip()[:6000],
             "", "Question: %s" % (item.get("question") or "").strip()]
    for L, tx in zip(LETTERS, opts):
        lines.append("%s. %s" % (L, str(tx).strip()))
    lines += ["", "Answer with ONLY the letter."]
    return [{"role": "user", "content": "\n".join(lines)}], gold


def build_gsm8k(item):
    q = item["question"]
    gold = item["answer"].split("####")[-1].strip()
    content = (q + "\n\nReason step by step concisely, then give the final "
               'numeric answer on the last line as "#### <integer>".')
    return [{"role": "user", "content": content}], gold


def run_suite(client, suite, rows, n, conc, seed, max_tokens, evidence_dir,
              timeout_s):
    rng = random.Random(seed)
    if len(rows) > n:
        if suite == "mmlu":
            # 按学科分层: 覆盖尽量多的 subject
            by_subj = {}
            for r in rows:
                by_subj.setdefault(r.get("subject") or "?", []).append(r)
            sample = []
            subj_names = sorted(by_subj)
            rng.shuffle(subj_names)
            i = 0
            while len(sample) < n:
                s = subj_names[i % len(subj_names)]
                cand = by_subj[s]
                if cand:
                    sample.append(cand.pop(rng.randrange(len(cand))))
                i += 1
        else:
            sample = rng.sample(rows, n)
    else:
        sample = list(rows)

    tasks = []
    for idx, item in enumerate(sample):
        if suite == "gsm8k":
            msg, gold = build_gsm8k(item)
        elif suite == "hellaswag":
            msg, gold = build_hellaswag(item)
        elif suite == "winogrande":
            msg, gold = build_winogrande(item)
        elif suite == "truthfulqa":
            msg, gold = build_truthfulqa(item)
        elif suite == "openbookqa":
            msg, gold = build_openbookqa(item)
        elif suite == "race":
            msg, gold = build_race(item)
        else:
            msg, gold = build_mc_question(item)
        if gold is None:
            continue
        tasks.append((idx, msg, gold))
    print("  %s: 抽样 %d 条(有效 %d, 并发 %d, max_tokens %d)" % (
        suite, len(sample), len(tasks), conc, max_tokens))

    results = [None] * len(sample)  # 按原始抽样下标存(跳过无效gold留None)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=conc) as ex:
        # 能力评测要答案全文做抽取(流式统计职责在 Track1), 走非流式
        futs = [ex.submit(full_one, client, t, max_tokens, timeout_s)
                for t in tasks]
        for f in futs:
            idx, gold, text, ok, err, comp = f.result()
            if suite == "gsm8k":
                correct, got = extract_gsm8k(text, gold) if ok else (False, None)
            else:
                correct, got = extract_letter(text, gold) if ok else (False, None)
            results[idx] = {"correct": correct, "gold": str(gold), "got": got,
                            "finish_err": None if ok else err,
                            "completion_tokens": comp}
    dur = time.time() - t0
    done = [r for r in results if r is not None]
    n_ok = [r for r in done if r["finish_err"] is None]
    correct = len([r for r in done if r["correct"]])
    avg_comp = (sum(r["completion_tokens"] or 0 for r in n_ok) / len(n_ok)
                if n_ok else None)
    summary = {
        "suite": suite, "n": len(done),
        "acc": round(correct / len(done), 4) if done else None,
        "correct": correct,
        "requests_failed": len(done) - len(n_ok),
        "avg_completion_tokens": round(avg_comp, 1) if avg_comp else None,
        "mode": "0-shot,no-think,temp=0",
        "duration_s": round(dur, 1),
    }
    if evidence_dir:
        os.makedirs(evidence_dir, exist_ok=True)
        with open(os.path.join(evidence_dir, "%s_items.jsonl" % suite), "w",
                  encoding="utf-8") as f:
            for i, r in enumerate(results):
                if r:
                    f.write(json.dumps({"i": i, **r}, ensure_ascii=False) + "\n")
    print("  %s: acc=%s (%d/%d) 失败请求=%d 平均输出=%s tokens 用时=%.0fs" % (
        suite, summary["acc"], correct, len(done), summary["requests_failed"],
        summary["avg_completion_tokens"], dur))
    return summary


def run_extra_suite(client, suite, n, conc, evidence_dir, timeout_s,
                    math500_max_tokens, ifeval_max_tokens, mc_max_tokens):
    """扩展四套: 统一 temp=0; math500 开思考链(公开榜口径), 其余关思考链."""
    think = suite == "math500"
    if suite == "math500":
        rows = load_math500(500)  # 全集仅 500 条, 不抽样
        mt = math500_max_tokens
        tasks = [(i, msg, gold) for i, (msg, gold, _t) in enumerate(rows)]
    elif suite == "cmmlu":
        rows = load_cmmlu(n)
        mt = mc_max_tokens
        tasks = [(i, msg, gold) for i, (msg, gold, _t) in enumerate(rows)]
    elif suite == "ceval":
        rows = load_ceval(n)
        mt = mc_max_tokens
        tasks = [(i, msg, gold) for i, (msg, gold, _t) in enumerate(rows)]
    else:  # ifeval: 第三位存整条原始数据(打分要 instruction_id_list/kwargs)
        rows = load_ifeval(n)
        mt = ifeval_max_tokens
        tasks = [(i, [{"role": "user", "content": it["prompt"]}], it)
                 for i, (it, _ids, _t) in enumerate(rows)]
    mode = "0-shot,%s,temp=0" % ("think" if think else "no-think")
    print("  %s: %d 条(并发 %d, max_tokens %d, %s)" % (suite, len(tasks), conc, mt, mode))

    results = [None] * len(tasks)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=conc) as ex:
        futs = [ex.submit(full_one, client, t, mt, timeout_s, think) for t in tasks]
        for f in futs:
            idx, gold, text, ok, err, comp = f.result()
            if suite == "ifeval":
                it = gold
                if ok:
                    body = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
                    p, tot = check_ifeval(body, it["instruction_id_list"], it["kwargs"])
                else:
                    p, tot = 0, len(it["instruction_id_list"])
                results[idx] = {"correct": p == tot, "instr_pass": p,
                                "instr_total": tot,
                                "gold": ";".join(it["instruction_id_list"]),
                                "got": None,
                                "finish_err": None if ok else err,
                                "completion_tokens": comp}
            elif suite == "math500":
                correct = check_math500(text, gold) if ok else False
                results[idx] = {"correct": correct, "gold": str(gold), "got": None,
                                "finish_err": None if ok else err,
                                "completion_tokens": comp}
            else:
                correct, got = extract_letter(text, gold) if ok else (False, None)
                results[idx] = {"correct": correct, "gold": str(gold), "got": got,
                                "finish_err": None if ok else err,
                                "completion_tokens": comp}
    dur = time.time() - t0
    done = [r for r in results if r is not None]
    n_ok = [r for r in done if r["finish_err"] is None]
    correct = len([r for r in done if r["correct"]])
    instr_p = sum(r["instr_pass"] for r in done if "instr_pass" in r)
    instr_t = sum(r["instr_total"] for r in done if "instr_total" in r)
    avg_comp = (sum(r["completion_tokens"] or 0 for r in n_ok) / len(n_ok)
                if n_ok else None)
    summary = {
        "suite": suite, "n": len(done),
        "acc": round(correct / len(done), 4) if done else None,
        "correct": correct,
        "requests_failed": len(done) - len(n_ok),
        "avg_completion_tokens": round(avg_comp, 1) if avg_comp else None,
        "mode": mode,
        "duration_s": round(dur, 1),
    }
    if suite == "ifeval" and instr_t:
        summary["instr_acc"] = round(instr_p / instr_t, 4)
    if evidence_dir:
        os.makedirs(evidence_dir, exist_ok=True)
        with open(os.path.join(evidence_dir, "%s_items.jsonl" % suite), "w",
                  encoding="utf-8") as f:
            for i, r in enumerate(results):
                if r:
                    f.write(json.dumps({"i": i, **r}, ensure_ascii=False) + "\n")
    print("  %s: acc=%s (%d/%d) 失败请求=%d 平均输出=%s tokens 用时=%.0fs" % (
        suite, summary["acc"], correct, len(done), summary["requests_failed"],
        summary["avg_completion_tokens"], dur))
    return summary


def full_one(client, task, max_tokens, timeout_s, think=False):
    """非流式拿全文(能力评测要文本抽答案, 流式统计交给 Track1)."""
    idx, msg, gold = task
    body = {"model": client.model, "messages": msg, "max_tokens": max_tokens,
            "temperature": 0.0,
            "chat_template_kwargs": {"enable_thinking": think}}
    last_err = None
    for _ in range(2):  # 网络错重试1次
        try:
            r = client.s.post(client.base + "/chat/completions", json=body,
                              timeout=timeout_s)
            r.raise_for_status()
            d = r.json()
            if d.get("error"):
                return idx, gold, "", False, str(d["error"])[:200], 0
            ch = d["choices"][0]
            txt = ch["message"].get("content") or ""
            if ch["message"].get("reasoning_content"):
                txt = ch["message"]["reasoning_content"] + "\n" + txt
            comp = (d.get("usage") or {}).get("completion_tokens", 0)
            return idx, gold, txt, True, None, comp
        except Exception as e:
            last_err = "%s: %s" % (type(e).__name__, str(e)[:150])
            time.sleep(1)
    return idx, gold, "", False, last_err, 0


def main():
    stdout_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-base", required=True)
    ap.add_argument("--model", default="bench")
    ap.add_argument("--suites", default="gsm8k,mmlu,arc")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20260930)
    ap.add_argument("--gsm8k-max-tokens", type=int, default=1024)
    ap.add_argument("--mc-max-tokens", type=int, default=32)
    ap.add_argument("--math500-max-tokens", type=int, default=8192)
    ap.add_argument("--ifeval-max-tokens", type=int, default=1024)
    ap.add_argument("--request-timeout-s", type=int, default=300)
    ap.add_argument("--data-dir", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cap"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--evidence-dir", default=None)
    args = ap.parse_args()

    client = Client(args.api_base, args.model, timeout_s=args.request_timeout_s)
    summaries = {}
    for suite in [s.strip() for s in args.suites.split(",") if s.strip()]:
        if suite in EXTRA_SUITES:
            summaries[suite] = run_extra_suite(
                client, suite, args.n, args.concurrency, args.evidence_dir,
                args.request_timeout_s, args.math500_max_tokens,
                args.ifeval_max_tokens, args.mc_max_tokens)
            continue
        rows = ensure_dataset(args.data_dir, suite)
        mt = args.gsm8k_max_tokens if suite == "gsm8k" else args.mc_max_tokens
        summaries[suite] = run_suite(
            client, suite, rows, args.n, args.concurrency, args.seed + 7,
            mt, args.evidence_dir,
            max(args.request_timeout_s, int(mt * 3)))
    out = {"track": "track2", "api_base": args.api_base, "model": args.model,
           "params": {"n_per_suite": args.n, "concurrency": args.concurrency,
                      "seed": args.seed, "mode": "0-shot,no-think,temp=0",
                      "gsm8k_max_tokens": args.gsm8k_max_tokens,
                      "mc_max_tokens": args.mc_max_tokens},
           "suites": summaries}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, **UTF8JSON)
    bad = [s for s, d in summaries.items() if not d["n"] or d["requests_failed"] > d["n"] * 0.05]
    if bad:
        print("FAIL Track2 套件异常: %s" % bad)
        raise SystemExit(1)
    print("PASS Track2 完成: %s" % {s: d["acc"] for s, d in summaries.items()})


if __name__ == "__main__":
    main()
