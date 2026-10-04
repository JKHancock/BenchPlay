#!/usr/bin/env python3
"""知识库客户端(Qdrant kb 集合): 向量召回 + 标签过滤; 幂等 upsert(hits++).
用法:
  python kb.py query "gloo 连接被拒绝" [--tag cluster] [--top 5]
  python kb.py upsert --content "..." [--fix "..."] [--tags cluster,ray] [--provenance t...]
依赖: fastembed(Vllm_Benchmark venv 已装, 模型已缓存, 离线可用); HF_ENDPOINT 默认 hf-mirror.
"""
import argparse
import json
import os
import urllib.request

QDRANT = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
# 与 MAF/C# 实现(BenchPilot)完全隔离: 各用各的集合, 互不读写
COLLECTION = os.environ.get("KB_COLLECTION", "kb_playbook")
MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def stable_hash(text: str) -> int:
    h = 2166136261
    for c in text:
        h = ((h ^ ord(c)) * 16777619) & 0xFFFFFFFF
    return h


def embed(texts):
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    from fastembed import TextEmbedding
    embedder = TextEmbedding(model_name=MODEL)
    return [v.tolist() for v in embedder.embed(texts)]


def http(method, path, body=None):
    req = urllib.request.Request(
        QDRANT + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def ensure_collection(dim):
    try:
        http("GET", f"/collections/{COLLECTION}")
    except urllib.error.HTTPError:
        http("PUT", f"/collections/{COLLECTION}",
             {"vectors": {"size": dim, "distance": "Cosine"}})


def cmd_query(args):
    vector = embed([args.text])[0]
    body = {"vector": vector, "limit": args.top + 10, "with_payload": True}
    if args.tag:
        body["filter"] = {"must": [{"key": "tags", "match": {"value": args.tag}}]}
    result = http("POST", f"/collections/{COLLECTION}/points/search", body)
    for p in result["result"][:args.top]:
        pl = p["payload"]
        tags = "/".join(pl.get("tags", []))
        fix = f" | 修复: {pl['fix']}" if pl.get("fix") else ""
        print(f"[{tags}]{fix} {pl['content']} (hits={pl.get('hits', 0)}, score={p['score']:.3f})")


def cmd_upsert(args):
    ensure_collection(len(embed(["dim"])[0]))
    pid = stable_hash(args.content[:64])
    try:
        existing = http("POST", f"/collections/{COLLECTION}/points",
                        {"ids": [pid], "with_payload": True})["result"]
        hits = (existing[0]["payload"].get("hits", 0) + 1) if existing else 0
    except Exception:
        hits = 0
    vector = embed([args.content])[0]
    http("PUT", f"/collections/{COLLECTION}/points?wait=true", {"points": [{
        "id": pid, "vector": vector,
        "payload": {"content": args.content, "fix": args.fix or "",
                    "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
                    "provenance": args.provenance or "", "hits": hits}}]})
    print(f"PASS upsert (id={pid}, hits={hits})")


def cmd_export(args):
    """全量导出(不含向量, 向量可由 content 重嵌): archive/kb_snapshot.jsonl 进 git."""
    import json
    pts, offset = [], None
    while True:
        body = {"limit": 256, "with_payload": True}
        if offset is not None:
            body["offset"] = offset
        r = http("POST", f"/collections/{COLLECTION}/points/scroll", body)["result"]
        pts += [{"id": p["id"], "payload": p["payload"]} for p in r.get("points", [])]
        offset = r.get("next_page_offset")
        if offset is None:
            break
    out = args.out or "archive/kb_snapshot.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for p in pts:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"PASS export {len(pts)} 条 -> {out}")


def cmd_rebuild(args):
    """从快照重建 Qdrant 集合(重嵌向量, 保留 hits; 幂等)."""
    import json
    from pathlib import Path
    src = Path(getattr(args, "infile", None) or "archive/kb_snapshot.jsonl")
    rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
    ensure_collection(len(embed(["dim"])[0]))
    for i in range(0, len(rows), 64):
        chunk = rows[i:i + 64]
        vecs = embed([r["payload"]["content"] for r in chunk])
        http("PUT", f"/collections/{COLLECTION}/points?wait=true", {"points": [
            {"id": r["id"], "vector": v, "payload": r["payload"]}
            for r, v in zip(chunk, vecs)]})
    print(f"PASS rebuild {len(rows)} 条 (源 {src})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("query")
    q.add_argument("text")
    q.add_argument("--tag")
    q.add_argument("--top", type=int, default=5)
    u = sub.add_parser("upsert")
    u.add_argument("--content", required=True)
    u.add_argument("--fix")
    u.add_argument("--tags", default="")
    u.add_argument("--provenance")
    e = sub.add_parser("export")
    e.add_argument("--out", default=None)
    rb = sub.add_parser("rebuild")
    rb.add_argument("--infile", default=None)
    args = parser.parse_args()
    {"query": cmd_query, "upsert": cmd_upsert,
     "export": cmd_export, "rebuild": cmd_rebuild}[args.cmd](args)
