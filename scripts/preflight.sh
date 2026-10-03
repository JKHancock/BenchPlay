#!/usr/bin/env bash
# 预检(整洁度盘点, 只读): 容器/端口/GPU 进程/运行时僵尸. 空输出=[CLEAN], 有内容=[DIRTY]+计数.
# 清理决策属于 agent(基于本输出与知识库); 本脚本不执行任何写操作.
# 用法: bash preflight.sh <host> <user> [key_path]
set -u
HOST="${1:?用法: preflight.sh <host> <user> [key]}"
USER_="${2:?缺少 user}"
KEY="${3:-$HOME/.ssh/benchplaybook_ed25519}"
KEYFLAG="-i $KEY"
[ -f "$KEY" ] || KEYFLAG=""
SSH="ssh $KEYFLAG -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"

# 段: 名称 命令 —— 输出为空=CLEAN, 非空=DIRTY(输出计数与内容)
section() { name="$1"; shift; out=$($SSH "$USER_@$HOST" "$*" 2>&1); code=$?;
  if [ -z "$out" ]; then tag=CLEAN; n=0;  # 输出为空即无发现(grep 无匹配退出码非 0 也算 CLEAN)
  else tag=DIRTY; n=$(printf '%s\n' "$out" | grep -c . || true); fi
  printf '### %s [%s] (%s 项)\n%s\n' "$name" "$tag" "$n" "$(printf '%s\n' "$out" | head -25)"; }

section containers "docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null"
section port8000  "ss -ltn 2>/dev/null | grep ':8000 '"
section gpu_procs "nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>/dev/null"
# ray 僵尸 = 容器内未被收割的尸体(Z 状态): 不占端口/GPU, 不可杀, 不阻塞部署 → 信息项
zn=$($SSH "$USER_@$HOST" "ps -eo stat,comm 2>/dev/null | awk '\$1 ~ /^Z/ && \$2 ~ /^ray/' | wc -l" 2>/dev/null)
printf '### ray_zombies [INFO] (%s 项, 容器未收割尸体, 无端口/GPU 不阻塞; 根治=重启容器)\n' "${zn:-0}"
section ray_procs "ps -eo pid,stat,comm 2>/dev/null | awk '\$2 !~ /^Z/ && \$3 ~ /^(raylet|gcs_server|ray::)/'"
section vllm_procs "pgrep -af '[v]llm|[o]penai.api_server' 2>/dev/null | head -10"
section model_lock "ls ~/.cache/huggingface/*.lock ~/.cache/huggingface/**/*.incomplete 2>/dev/null | head -5"
