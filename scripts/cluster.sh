#!/usr/bin/env bash
# ray 双机组网: 容器内起 head/worker, QSFP 段自动探测(192.168.100.0/24).
# 门禁: head 容器 ray status 必须 2 NODES 且 Total GPUs=2(以 ray 自述为准). 幂等.
# 用法: cluster.sh <head_host> <worker_host> <user> [key]
set -u
HEAD="${1:?用法: cluster.sh <head> <worker> <user> [key]}"
WORKER="${2:?缺少 worker}"
USER_="${3:?缺少 user}"
KEY="${4:-}"
KEYFLAG="-i $KEY"; [ -n "$KEY" ] && [ -f "$KEY" ] || KEYFLAG=""
SSH="ssh -n $KEYFLAG -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"
C=vllm-node

qip() { # qip <host> → 192.168.100.x; 容器为 --network host, 宿主网络视图即容器视图(容器内无 ip 命令)
  $SSH "$USER_@$1" "ip -4 addr" 2>/dev/null | grep -oE 'inet 192\.168\.100\.[0-9]+' | head -1 | awk '{print $2}'; }

gate() { # ray 2.44 输出判据: Active 段两个 node_ 行 + Resources 段 0.0/2.0 GPU
  local st; st=$($SSH "$USER_@$HEAD" "docker exec $C bash -lc 'ray status'" 2>/dev/null)
  local nodes gpus
  nodes=$(printf '%s' "$st" | grep -cE '^ [0-9]+ node_')
  gpus=$(printf '%s' "$st" | grep -oE '[0-9.]+/2\.0 GPU' | head -1)
  if [ "$nodes" -ge 2 ] && [ -n "$gpus" ]; then
    echo "PASS ray 双机集群就绪 (Active=$nodes, GPU $gpus)"; return 0
  fi
  return 1
}

# 幂等: 已是 2 节点 2 GPU 直接 PASS
if gate; then exit 0; fi

HIP=$(qip "$HEAD"); WIP=$(qip "$WORKER")
[ -z "$HIP" ] || [ -z "$WIP" ] && { echo "FAIL QSFP(192.168.100.0/24) 地址探测失败: head=$HIP worker=$WIP"; exit 1; }
echo "  数据面: head $HIP ↔ worker $WIP"

$SSH "$USER_@$HEAD" "docker exec $C bash -c 'RAY_memory_monitor_refresh_ms=0 ray stop >/dev/null 2>&1; RAY_memory_monitor_refresh_ms=0 nohup ray start --head --port=6379 --node-ip-address=$HIP >/root/ray.log 2>&1'" || { echo "FAIL head ray start"; exit 1; }
sleep 3
$SSH "$USER_@$WORKER" "docker exec $C bash -c 'RAY_memory_monitor_refresh_ms=0 ray stop >/dev/null 2>&1; RAY_memory_monitor_refresh_ms=0 nohup ray start --address=$HIP:6379 --node-ip-address=$WIP >/root/ray.log 2>&1'" || { echo "FAIL worker ray start"; exit 1; }
sleep 5

st=$($SSH "$USER_@$HEAD" "docker exec $C bash -lc 'ray status'" 2>/dev/null)
echo "$st" | sed -n '1,10p'
if gate; then
  echo "  (head $HIP)"
  exit 0
else
  echo "FAIL ray status 未达 2 节点/2 GPU(输出见上)"
  exit 1
fi
