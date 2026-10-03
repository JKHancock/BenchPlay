# -*- coding: utf-8 -*-
"""BenchPlaybook 三库浏览器(Streamlit, 本地零并发诉求).
任务回放实时刷新: st.fragment(run_every=2s). 启动:
  streamlit run viewer/app.py --server.port 8501 --server.headless true
"""
import json
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
TASKS = ROOT / "tasks"
sys.path.insert(0, str(ROOT / "scripts"))
import kb  # noqa: E402  (Qdrant 客户端, 集合 kb_playbook)

st.set_page_config(page_title="BenchPlaybook", page_icon="🛠", layout="wide")


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def read_events(task_dir):
    file = task_dir / "events.jsonl"
    if not file.exists():
        return []
    out = []
    for line in file.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def list_tasks():
    tasks = []
    if TASKS.exists():
        for d in sorted(TASKS.iterdir(), reverse=True):
            meta = read_json(d / "task.json")
            if meta:
                run = read_json(d / "run.json", {}) or {}
                tasks.append({
                    "id": meta["Id"], "name": meta["Name"], "dir": d,
                    "status": run.get("Status") or meta.get("Status", "running"),
                    "created": meta.get("CreatedAt", ""),
                    "in_tok": run.get("InputTokens"), "out_tok": run.get("OutputTokens"),
                })
    return tasks


BADGE = {"completed": "✅", "failed": "🔴", "running": "🔵"}


def block_title(key):
    if key == "director":
        return "🎯 主控 Director"
    if key == "report":
        return "📄 报告 ReportAgent"
    if key.startswith("bootstrap-"):
        return f"🛠 引导 BootstrapAgent · {key[len('bootstrap-'):]}"
    return key


def render_turn(turn):
    with st.container(border=True):
        st.caption(f"{str(turn.get('Ts', ''))[11:19]} · 第 {turn.get('Round')} 轮")
        reasoning = turn.get("Reasoning") or ""
        if reasoning:
            with st.expander("💭 思考"):
                st.markdown(reasoning)
        for call in turn.get("Calls", []):
            card = st.container(border=True)
            card.markdown(f"🔧 **{call.get('Name')}**(`{str(call.get('Arguments', ''))[:120]}`)")
            with card.expander("结果"):
                st.code(str(call.get("Result", ""))[:4000], language=None)
        answer = turn.get("Answer") or ""
        if answer:
            st.info(answer)


@st.fragment(run_every=2)
def render_task_detail(task):
    d = task["dir"]
    st.subheader(f"{task['name']} · {BADGE.get(task['status'], '')} {task['status']}")
    col1, col2, col3, col4 = st.columns(4)
    col1.caption(f"任务 {task['id']}")
    col2.caption(f"创建 {str(task['created'])[:19]}")
    col3.metric("入 tokens", task["in_tok"] if task["in_tok"] is not None else "—")
    col4.metric("出 tokens", task["out_tok"] if task["out_tok"] is not None else "—")

    tdir = d / "transcripts"
    if tdir.exists():
        order = {"director": 0}
        files = sorted(tdir.glob("*.json"),
                       key=lambda f: (0 if f.stem == "director" else 1 if f.stem.startswith("bootstrap-") else 2, f.name))
        for f in files:
            turns = read_json(f, []) or []
            with st.expander(f"{block_title(f.stem)}（{len(turns)} 轮）", expanded=True):
                for t in turns:
                    render_turn(t)
    else:
        st.info("尚无转录（任务未产生档案）")

    events = read_events(d)
    if events:
        with st.expander(f"原始事件流（{len(events)} 条）"):
            for e in reversed(events[-60:]):
                color = {"error": "🔴", "gate": "🟠", "kb": "🟢"}.get(e.get("Level"), "⚪")
                st.markdown(f"`{str(e.get('Ts', ''))[11:19]}` {color} **{e.get('Source', '')}** "
                            f"`{e.get('Machine', '')[:20]}` {str(e.get('Message', ''))[:200]}")


def render_profiles(task):
    pdir = task["dir"] / "profiles"
    if not pdir.exists():
        st.info("尚无机器档案")
        return
    for f in sorted(pdir.glob("*.json")):
        p = read_json(f) or {}
        with st.expander(f"🖥 {p.get('Host', f.stem)}（机型 {p.get('DeclaredModel') or '—'}）", expanded=True):
            if p.get("Summary"):
                st.markdown(f"> {p['Summary']}")
            cols = st.columns(4)
            fields = [("OS", "Os"), ("架构", "Arch"), ("内核", "Kernel"), ("CPU", "Cpu"),
                      ("内存", "Memory"), ("GPU", "Gpu"), ("驱动", "Driver"), ("Docker", "DockerVersion")]
            for i, (label, key) in enumerate(fields):
                cols[i % 4].metric(label, p.get(key) or "—")
            st.markdown(f"**镜像** ({len(p.get('Images', []))}): " + "; ".join(p.get("Images", [])[:6]))
            st.markdown(f"**模型** ({len(p.get('Models', []))}): " + "; ".join(p.get("Models", [])[:8]))
            ev = p.get("Evidence") or {}
            with st.expander(f"证据（{len(ev)} 项）"):
                for k, v in ev.items():
                    st.markdown(f"`{k}` ← `{v.get('Command', '')[:80]}`")
                    st.caption(str(v.get("Excerpt", ""))[:160])


def page_experience():
    st.subheader("经验库")
    edir = ROOT / "experience"
    idx = edir / "INDEX.md"
    if idx.exists():
        st.markdown(idx.read_text(encoding="utf-8"))
    for f in sorted(edir.glob("*.md")):
        if f.name == "INDEX.md":
            continue
        with st.expander(f"📒 {f.name}"):
            st.markdown(f.read_text(encoding="utf-8"))


@st.cache_resource
def get_embedder():
    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    from fastembed import TextEmbedding
    model = TextEmbedding(model_name=kb.MODEL)
    return lambda texts: [v.tolist() for v in model.embed(texts)]


def page_kb():
    st.subheader("知识库（kb_playbook）")
    q = st.text_input("语义检索（中英皆可）", placeholder="例如: worker 建连被拒绝")
    tag = st.text_input("标签过滤（可选）", placeholder="例如: cluster")
    top = st.slider("返回条数", 1, 10, 5)
    if st.button("查询", type="primary") and q.strip():
        embed = get_embedder()
        vector = embed([q])[0]
        body = {"vector": vector, "limit": top, "with_payload": True}
        if tag.strip():
            body["filter"] = {"must": [{"key": "tags", "match": {"value": tag.strip()}}]}
        try:
            result = kb.http("POST", f"/collections/{kb.COLLECTION}/points/search", body)
            hits = result.get("result", [])
            if not hits:
                st.info("无匹配")
            for p in hits:
                pl = p.get("payload", {})
                tags = "/".join(pl.get("tags", []))
                fix = f" | 修复: {pl['fix']}" if pl.get("fix") else ""
                st.markdown(f"**[{tags}]**{fix} (hits={pl.get('hits', 0)}, score={p['score']:.3f})")
                st.caption(pl.get("content", ""))
        except Exception as exc:  # noqa: BLE001
            st.error(f"查询失败: {exc}\n（Qdrant 未启动? BenchPilot/tools/qdrant/qdrant.exe）")
    st.caption("浏览器版: http://127.0.0.1:6333/dashboard")


def main():
    st.title("🛠 BenchPlaybook")
    tasks = list_tasks()
    with st.sidebar:
        st.header("任务")
        if not tasks:
            st.info("tasks/ 为空——先跑一个任务")
        options = {f"{BADGE.get(t['status'], '')} {t['name'][:24]} · {t['id'][1:]}": t for t in tasks}
        choice = st.radio("选择任务", list(options.keys()), label_visibility="collapsed") if options else None
        task = options.get(choice)
        st.divider()
        st.caption(f"知识库: Qdrant `{kb.COLLECTION}`（与 MAF 版隔离）\n\n机器状态: machines/*.json")

    if task is None:
        st.stop()

    page = st.tabs(["任务回放", "机器档案", "报告", "经验库", "知识库"])
    with page[0]:
        render_task_detail(task)
    with page[1]:
        render_profiles(task)
    with page[2]:
        report = task["dir"] / "report.md"
        st.markdown(report.read_text(encoding="utf-8") if report.exists() else "尚无报告")
    with page[3]:
        page_experience()
    with page[4]:
        page_kb()


main()
