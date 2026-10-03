#!/usr/bin/env bash
# 只读探测(十项). 门禁: 全部只读, 任一命令失败输出 absent 标记而非中断(异构常态).
# 用法: bash probe.sh <host> <user> [key_path] [models_root]
set -u
HOST="${1:?用法: probe.sh <host> <user> [key] [models_root]}"
USER_="${2:?缺少 user}"
KEY="${3:-$HOME/.ssh/benchplaybook_ed25519}"
MODELS_ROOT="${4:-\$HOME/.cache/huggingface}"

KEYFLAG=""
[ -f "$KEY" ] && KEYFLAG="-i $KEY"
SSH="ssh $KEYFLAG -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"

run() { name="$1"; shift; out=$($SSH "$USER_@$HOST" "$*" 2>&1); code=$?;
  if [ $code -eq 0 ]; then tag=OK; else tag=ABSENT; fi
  printf '### %s [%s]\n%s\n' "$name" "$tag" "$out"; }

run kernel  "uname -srm"
run os      "cat /etc/os-release"
run gpu     "nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader"
run docker  "docker version --format '{{.Server.Version}}'"
run images  "docker images --format '{{.Repository}}:{{.Tag}}|{{.Size}}'"
run models  "find $MODELS_ROOT -maxdepth 2 -mindepth 1 -type d -printf '%P\n' 2>/dev/null"
run disks   "df -h"
run nics    "ip -j addr"
run cpu     "nproc"
run memory  "free -h | awk 'NR==2{print \$2}'"
# 启发式识别项(机器换了 IP 也能被认出; 无硬主键, 由 agent 做相似度判断)
run identity-hostname "hostname"
run identity-model    "cat /proc/device-tree/model 2>/dev/null || echo n/a"   # ARM 设备树机型
run identity-macs     "ip -j link | grep -oE '([0-9a-f]{2}:){5}[0-9a-f]{2}' | sort -u"
run identity-disks    "lsblk -dp -o NAME,SIZE,SERIAL 2>/dev/null"
