#!/usr/bin/env bash
# 模型分发: 逐文件 本地sha256 -> scp -> 远端sha256sum 三段门禁; 已存在同哈希跳过(增量续传).
# 不变式: 远端路径必须绝对化(~ 在 scp 目标里不展开; 历史事故: 整体写入字面量 ~/ 目录).
# 用法: bash distribute.sh <host> <user> <model_dir_local> [remote_root]
set -euo pipefail
HOST="${1:?用法: distribute.sh <host> <user> <本地模型目录> [远端根]}"
USER_="${2:?缺少 user}"
LOCAL_DIR="${3:?缺少本地模型目录}"
ROOT="${4:-.cache/huggingface}"
KEY="${KEY:-$HOME/.ssh/benchplaybook_ed25519}"
KEYFLAG="-i $KEY"
[ -f "$KEY" ] || KEYFLAG=""  # 密钥不存在时回退默认密钥(如 134 未引导专用密钥)
MODEL=$(basename "$LOCAL_DIR")

SSH="ssh -n $KEYFLAG -o BatchMode=yes -o StrictHostKeyChecking=no"  # -n: 防止 ssh 吃掉 while-read 循环的 stdin(实测饿死循环的坑)
SCP="scp $KEYFLAG -o StrictHostKeyChecking=no -o ConnectTimeout=15"

# 不变式#6: 先解析绝对 HOME
REMOTE_HOME=$($SSH "$USER_@$HOST" 'echo $HOME')
case "$REMOTE_HOME" in /*) ;; *) echo "FAIL 无法解析远端 HOME: '$REMOTE_HOME'"; exit 1;; esac
ROOT=${ROOT/#\~\//$REMOTE_HOME\/}          # ~/xxx -> /home/u/xxx
TARGET="$REMOTE_HOME/${ROOT#/}/$MODEL"     # 强制绝对

uploaded=0; skipped=0; bytes=0
cd "$LOCAL_DIR"
while IFS= read -r -d '' file; do
  rel=${file//\\/\/}
  remote_path="$TARGET/${rel}"
  local_hash=$(sha256sum "$file" | awk '{print toupper($1)}')
  size=$(stat -c%s "$file")
  # 增量: 已存在且大小同 -> 比对哈希, 一致则跳过
  if remote_size=$($SSH "$USER_@$HOST" "stat -c%s '$remote_path' 2>/dev/null" || true); then
    if [ "${remote_size:-0}" = "$size" ]; then
      remote_hash=$($SSH "$USER_@$HOST" "sha256sum '$remote_path'" | awk '{print toupper($1)}')
      if [ "$remote_hash" = "$local_hash" ]; then
        skipped=$((skipped+1)); echo "skip  $rel (哈希一致)"; continue
      fi
    fi
  fi
  $SSH "$USER_@$HOST" "mkdir -p '$(dirname "$remote_path")'"
  echo "put   $rel ($((size / 1024 / 1024))MB)"
  $SCP "$file" "$USER_@$HOST:$remote_path"
  remote_hash=$($SSH "$USER_@$HOST" "sha256sum '$remote_path'" | awk '{print toupper($1)}')
  if [ "$remote_hash" != "$local_hash" ]; then
    echo "FAIL sha256 门禁: $rel 本地 ${local_hash:0:12}.. 远端 ${remote_hash:0:12}.."
    exit 1
  fi
  uploaded=$((uploaded+1)); bytes=$((bytes+size)); echo "ok    $rel"
done < <(find . -type f -print0)

# 收尾门禁: 远端文件数必须与本地一致(防部分传输假阳性)
remote_n=$($SSH "$USER_@$HOST" "find '$TARGET' -type f 2>/dev/null | wc -l")
local_n=$(find . -type f | wc -l)
if [ "$remote_n" != "$local_n" ]; then
  echo "FAIL 文件数门禁: 本地 $local_n 远端 ${remote_n:-0}"
  exit 1
fi
echo "PASS $MODEL -> $USER_@$HOST:$TARGET (传 $uploaded 跳过 $skipped, $((bytes / 1024 / 1024 / 1024))GB, 文件数 $local_n 一致)"
