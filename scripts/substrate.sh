#!/usr/bin/env bash
# 底座校验(只读): vllm-node 容器存在且含 GB10 六必备 flag + ray 版本 + 模型可见.
# 门禁: 任一项缺失 → FAIL(附修复提示). 用法: substrate.sh <host> <user> [key] <model_name>
set -u
HOST="${1:?用法: substrate.sh <host> <user> [key] <model_name>}"
USER_="${2:?缺少 user}"
KEY="${3:-}"; MODEL="${4:?缺少 model_name}"
[ -z "$MODEL" ] && { echo "缺少 model_name"; exit 2; }
KEYFLAG="-i $KEY"; [ -n "$KEY" ] && [ -f "$KEY" ] || KEYFLAG=""
SSH="ssh -n $KEYFLAG -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"
C=vllm-node
code=0
fail() { echo "FAIL $1"; code=1; }
ok()   { echo "  ok: $1"; }

ins=$($SSH "$USER_@$HOST" "docker inspect $C 2>/dev/null" ) || true
[ -z "$ins" ] && { echo "FAIL 容器 $C 不存在(创建: 见 docs/PIPELINE.md 底座节 6-flag)"; exit 1; }
running=$(printf '%s' "$ins" | grep -o '"Running": true' | head -1)
[ -n "$running" ] && ok "容器运行中" || fail "容器未运行"

chk() { # chk <desc> <grep-pattern>
  if printf '%s' "$ins" | grep -q "$2"; then ok "$1"; else fail "$1 (缺: $2)"; fi; }
chk "IPC=host"          '"IpcMode": "host"'
chk "Network=host"      '"NetworkMode": "host"'
chk "GPU all"           '"Count": -1'
chk "/dev/infiniband"   '/dev/infiniband'
chk "IPC_LOCK"          'IPC_LOCK'
chk "memlock=-1"        '"Name": "memlock"'

rayv=$($SSH "$USER_@$HOST" "docker exec $C python3 -c 'import ray; print(ray.__version__)' 2>/dev/null")
if [ "$rayv" = "2.44.0" ]; then ok "ray==2.44.0"; else fail "ray 版本 '$rayv' != 2.44.0"; fi

if $SSH "$USER_@$HOST" "docker exec $C test -d /root/.cache/huggingface/$MODEL" 2>/dev/null; then
  ok "模型在容器内可见: /root/.cache/huggingface/$MODEL"
else
  fail "容器内未见模型 $MODEL(检查宿主挂载 ~/.cache/huggingface)"
fi

[ $code -eq 0 ] && echo "PASS 底座校验通过 $USER_@$HOST (容器 $C)"
exit $code
