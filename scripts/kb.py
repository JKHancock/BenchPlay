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
    args = parser.parse_args()
    {"query": cmd_query, "upsert": cmd_upsert}[args.cmd](args)
