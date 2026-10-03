#!/usr/bin/env bash
# 精准清理(进程级, 保留容器/镜像/模型): 停各容器内 vllm/ray 进程 + 宿主 ray 残留.
# 门禁: 清理后 GPU 计算进程与 8000 端口必须 CLEAN, 否则 FAIL. 幂等可重跑.
# 用法: bash clean.sh <host> <user> [key_path]
set -u
HOST="${1:?用法: clean.sh <host> <user> [key]}"
USER_="${2:?缺少 user}"
KEY="${3:-$HOME/.ssh/benchplaybook_ed25519}"
KEYFLAG="-i $KEY"
[ -f "$KEY" ] || KEYFLAG=""
SSH="ssh -n $KEYFLAG -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"

echo "-- 清理 $USER_@$HOST: 容器内 vllm/ray + 宿主 ray --"
$SSH "$USER_@$HOST" '
  for c in $(docker ps -q); do
    name=$(docker inspect -f "{{.Name}}" "$c" | tr -d /)
    docker exec "$c" pkill -f "[v]llm serve|[v]llm.entrypoints|[a]pi_server" 2>/dev/null && echo "  容器 $name: vllm 进程已停"
    docker exec "$c" bash -lc "ray stop" >/dev/null 2>&1 && echo "  容器 $name: ray stop 已执行"
    docker exec "$c" pkill -f "[r]aylet|[g]cs_server|[r]ay::" 2>/dev/null && echo "  容器 $name: ray 僵尸已清"
  done
  pkill -f "[r]aylet|[g]cs_server" 2>/dev/null && echo "  宿主 ray 残留已停"
  sleep 4'
[ $? -ne 0 ] && { echo "FAIL 清理命令执行失败"; exit 1; }

# 门禁: GPU 计算进程 + 8000 端口
gpu=$($SSH "$USER_@$HOST" "nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null")
port=$($SSH "$USER_@$HOST" "ss -ltn 2>/dev/null | grep ':8000 '")
code=0
if [ -n "$gpu" ]; then echo "FAIL GPU 仍被占用: $gpu"; code=1; else echo "  GPU 计算进程: CLEAN"; fi
if [ -n "$port" ]; then echo "FAIL 8000 端口仍被监听"; code=1; else echo "  8000 端口: CLEAN"; fi
$SSH "$USER_@$HOST" "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null" | sed 's/^/  显存: /'
[ $code -eq 0 ] && echo "PASS $USER_@$HOST 精准清理完成(容器与数据保留)"
exit $code
