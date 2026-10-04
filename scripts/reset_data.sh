#!/usr/bin/env bash
# 数据清空(冷启动): 只动动态层, 静态资产(文档/脚本/bench/数据集)不动.
# 语义见 README §9.1 与 §10; 删除物移入 .reset_backup/<时间戳>/ 而非 rm(可反悔).
#
# 用法:
#   reset_data.sh show          只显示将清空什么, 不动手
#   reset_data.sh data          清实验记忆: tasks/ archive/ machines/ models/ reports/
#                               (经验库保留 —— 教训是跨实验资产)
#   reset_data.sh all           再加 experience/ 与 Qdrant kb_playbook 集合(全新冷启动;
#                               archive/kb_snapshot.jsonl 不删, 可 kb.py rebuild 复原知识库)
# 前置: QDRANT_URL 默认 http://127.0.0.1:6333 (仅 all 模式需要, 不通则跳过并提示)
set -u
cd "$(dirname "$0")/.."
MODE="${1:-show}"
STAMP=$(date +%Y%m%d-%H%M%S)
BK=".reset_backup/$STAMP"

DATA_DIRS="tasks archive machines models reports"
ALL_DIRS="experience"

plan(){ printf '  %s\n' "$@"; }
show(){
  echo "[show] 模式=data 将移走:"; plan $DATA_DIRS
  echo "[show] 模式=all 追加:";    plan $ALL_DIRS "Qdrant 集合 kb_playbook"
  echo "[show] 永不动: docs/ scripts/ bench/ data/ viewer/ *.md requirements.txt"
}

move_to_backup(){
  for d in "$@"; do
    if [ -e "$d" ]; then
      mkdir -p "$BK/$(dirname "$d")"
      mv "$d" "$BK/$d"
      echo "  moved: $d -> $BK/$d"
    else
      echo "  skip(不存在): $d"
    fi
  done
}

case "$MODE" in
  show) show; exit 0 ;;
  data)
    echo "[data] 实验记忆清空(备份至 $BK):"
    move_to_backup $DATA_DIRS
    mkdir -p archive
    echo "PASS 冷启动(数据层)完成 —— 经验库保留"
    ;;
  all)
    echo "[all] 全量冷启动(备份至 $BK):"
    move_to_backup $DATA_DIRS $ALL_DIRS
    mkdir -p archive experience
    # 经验库骨架重建(空文件, 保持检索入口可用)
    for f in serve-vllm os-network testing-bench process-governance INDEX; do
      [ -e "experience/$f.md" ] || printf '# %s\n(空: 全新冷启动, 条目由阶段9沉淀追加)\n' "$f" > "experience/$f.md"
    done
    BASE="${QDRANT_URL:-http://127.0.0.1:6333}"
    curl -s -m 5 -X DELETE "$BASE/collections/kb_playbook" \
      2>/dev/null | grep -q '"result"' \
      && echo "  Qdrant kb_playbook 已删(快照仍在 git, kb.py rebuild 可复原)" \
      || echo "  △ Qdrant 不可达, 跳过集合删除(如需: curl -X DELETE $BASE/collections/kb_playbook)"
    echo "PASS 冷启动(全量)完成"
    ;;
  *) echo "用法: reset_data.sh [show|data|all]"; exit 2 ;;
esac
