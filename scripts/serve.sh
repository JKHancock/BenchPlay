#!/usr/bin/env bash
# vLLM 服务起动(TP 可选; TP>1 仅 head 容器发起, worker 经 ray 自动调度) + 就绪门禁.
# 门禁: 日志出现 "Application startup complete" 且 8000 端口监听(≤900s 轮询).
# 用法: serve.sh <head_host> <user> <model_name> [key] [max_model_len] [tp] [extra_flags]
set -u
HOST="${1:?用法: serve.sh <host> <user> <model_name> [key] [max_model_len] [tp] [extra_flags]}"
USER_="${2:?缺少 user}"
MODEL="${3:?缺少 model_name}"
KEY="${4:-}"
MAXLEN="${5:-40960}"
TP="${6:-2}"
EXTRA="${7:-}"
KEYFLAG="-i $KEY"; [ -n "$KEY" ] && [ -f "$KEY" ] || KEYFLAG=""
SSH="ssh -n $KEYFLAG -o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"
C=vllm-node

# awk 状态机: 持有 192.168.100.x 的接口(grep -B 上下文会跨块误抓 lo, 实测翻车)
IFACE=$($SSH "$USER_@$HOST" "ip -4 addr" 2>/dev/null | awk '/^[0-9]+: /{gsub(/:/,"",$2); iface=$2} /inet 192\.168\.100\./{print iface; exit}')
[ -z "$IFACE" ] || [ "$IFACE" = "lo" ] && { echo "FAIL QSFP 网卡探测异常: '$IFACE'"; exit 1; }
echo "  通信钉定网卡: $IFACE (192.168.100.0/24)  [宿主探测, host 网络视图=容器]"

# 清场(幂等): 旧 serve + ray worker + 引擎核 全杀, 然后等 GPU 计算进程归零(≤180s)
# (实测教训: 只杀 vllm serve 不够, worker 叫 ray::RayWorkerProc, 显存不释放则新实例加载卡死)
$SSH "$USER_@$HOST" "docker exec $C bash -c \"pkill -f '[v]llm serve' 2>/dev/null; pkill -f '[R]ayWorkerProc' 2>/dev/null; pkill -f '[E]ngineCore' 2>/dev/null; true\""
for i in $(seq 1 36); do
  g=$($SSH "$USER_@$HOST" "nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null" | grep -c .)
  [ "${g:-0}" -eq 0 ] && break
  sleep 5
done
g=$($SSH "$USER_@$HOST" "nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null" | grep -c .)
if [ "${g:-0}" -ne 0 ]; then
  echo "FAIL 清场后 GPU 仍被占用($g 个计算进程), 先跑 clean.sh 再试"
  exit 1
fi
echo "  清场完成: GPU 计算进程归零"

DIST=""
[ "$TP" -gt 1 ] && DIST="--distributed-executor-backend ray"
$SSH "$USER_@$HOST" "docker exec -d $C bash -c '
export CUTE_DSL_ARCH=sm_121a HF_ENDPOINT=https://hf-mirror.com RAY_memory_monitor_refresh_ms=0
export GLOO_SOCKET_IFNAME=$IFACE NCCL_SOCKET_IFNAME=$IFACE
nohup vllm serve /root/.cache/huggingface/$MODEL \
  --tensor-parallel-size $TP $DIST $EXTRA \
  --served-model-name bench --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 --max-model-len $MAXLEN \
  --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching \
  > /root/vllm.log 2>&1'" || { echo "FAIL serve 启动命令失败"; exit 1; }
echo "  vllm serve 已发起(TP$TP/$MODEL/max-len=$MAXLEN), 等待就绪..."

for i in $(seq 1 360); do
  sleep 10
  ready=$($SSH "$USER_@$HOST" "docker exec $C grep -c 'Application startup complete' /root/vllm.log 2>/dev/null" 2>/dev/null)
  port=$($SSH "$USER_@$HOST" "ss -ltn 2>/dev/null | grep -c ':8000 '")
  if [ "${ready:-0}" -ge 1 ] && [ "${port:-0}" -ge 1 ]; then
    echo "PASS vLLM 就绪 (http://$HOST:8000, 耗时约 $((i*10))s)"
    # 启动容量两行必须入档案(实测坑: vllm.log 每次serve覆盖, 不落档即永久丢失)
    $SSH "$USER_@$HOST" "docker exec $C grep -E 'GPU KV cache size|Maximum concurrency' /root/vllm.log" 2>/dev/null | sed 's/^/  /'
    exit 0
  fi
  # 启动即崩检测
  if $SSH "$USER_@$HOST" "docker exec $C bash -c \"pgrep -f '[v]llm serve' >/dev/null\"" 2>/dev/null; then :; else
    echo "FAIL vllm serve 进程已退出, 日志尾部:"; $SSH "$USER_@$HOST" "docker exec $C tail -25 /root/vllm.log" 2>/dev/null; exit 1
  fi
  # 15 分钟仍未就绪: 若 FlashInfer 自调优活跃(MoE 模型首次加载的一次性成本)则延长门禁至 60 分钟
  if [ $i -eq 90 ]; then
    if $SSH "$USER_@$HOST" "docker exec $C grep -qE 'Autotun|Tuning' /root/vllm.log" 2>/dev/null; then
      echo "  首次 FlashInfer 自调优进行中(MoE 内核一次性调优, 结果入缓存), 门禁延长至 60 分钟"
    else
      break
    fi
  fi
done
echo "FAIL 就绪超时(900s), 日志尾部:"
$SSH "$USER_@$HOST" "docker exec $C tail -25 /root/vllm.log" 2>/dev/null
exit 1
