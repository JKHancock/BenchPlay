#!/usr/bin/env bash
# 环境指纹: 数据点/知识条目的防漂移锚. 输出一行 JSON.
# 用法: envfingerprint.sh <head_host> [user] [key]
set -u
HOST="${1:?用法: envfingerprint.sh <host> [user] [key]}"
USER_="${2:-syspetro}"
KEY="${3:-}"
KEYFLAG="-i $KEY"; [ -n "$KEY" ] && [ -f "$KEY" ] || KEYFLAG=""
SSH="ssh -n $KEYFLAG -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"
C=vllm-node

vllm_v=$($SSH "$USER_@$HOST" "docker exec $C python3 -c 'import vllm; print(vllm.__version__)'" 2>/dev/null | head -1)
img=$($SSH "$USER_@$HOST" "docker inspect $C -f '{{.Image}}'" 2>/dev/null | cut -c8-19)
drv_gpu=$($SSH "$USER_@$HOST" "nvidia-smi --query-gpu=driver_version,name,power.limit --format=csv,noheader" 2>/dev/null | head -1)
drv=$(echo "$drv_gpu" | cut -d, -f1 | tr -d ' ')
gpu=$(echo "$drv_gpu" | cut -d, -f2 | tr -d ' ')
pwr=$(echo "$drv_gpu" | cut -d, -f3 | tr -d ' ')
numa=$($SSH "$USER_@$HOST" "lscpu | grep 'NUMA node(s)' | awk '{print \$NF}'" 2>/dev/null)
ts=$(date '+%Y-%m-%dT%H:%M:%S')

cat <<EOF
{"vllm":"${vllm_v:-?}","image":"sha256:${img:-?}","driver":"${drv:-?}","gpu":"${gpu:-?}","power_limit":"${pwr:-?}","numa_nodes":"${numa:-?}","recorded_at":"$ts"}
EOF
