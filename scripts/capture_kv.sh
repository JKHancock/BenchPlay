#!/usr/bin/env bash
# 补采启动两行(KV容量/最大并发×): serve→等就绪→grep落档→撤. 不跑电池.
# 用法: capture_kv.sh <tp> <model> <tag> [extra]
set -u
BP=/d/CSharpProject/BenchPlaybook
H=192.168.199.129; H2=192.168.199.134; U=syspetro
SSHOPT="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"
tp=$1; model=$2; tag=$3; extra="${4:-}"
OUT=$BP/tasks/t20260930-matrix-full/raw4/$tag
[ "$tp" -gt 1 ] && bash $BP/scripts/cluster.sh $H $H2 $U > "$OUT/cluster.log" 2>&1
for n in $H $H2; do
  ssh -n $SSHOPT $U@$n "docker exec vllm-node bash -c \"pkill -f '[v]llm serve' 2>/dev/null; pkill -f '[R]ayWorkerProc' 2>/dev/null; pkill -f '[E]ngineCore' 2>/dev/null; true\"" 2>/dev/null
done
sleep 10
DIST=""; [ "$tp" -gt 1 ] && DIST="--distributed-executor-backend ray"
ssh $SSHOPT $U@$H "docker exec -i -e MODEL='$model' -e TP=$tp -e DIST='$DIST' -e 'EXTRA_ARGS=$extra' vllm-node bash -s" > "$OUT/serve.log" 2>&1 <<'EOS'
export CUTE_DSL_ARCH=sm_121a HF_ENDPOINT=https://hf-mirror.com RAY_memory_monitor_refresh_ms=0
export GLOO_SOCKET_IFNAME=enp1s0f1np1 NCCL_SOCKET_IFNAME=enp1s0f1np1
nohup vllm serve /root/.cache/huggingface/$MODEL \
  --tensor-parallel-size $TP $DIST $EXTRA_ARGS \
  --served-model-name bench --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 --max-model-len 40960 \
  --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching \
  > /root/vllm.log 2>&1 &
echo LAUNCHED
EOS
for i in $(seq 1 60); do
  sleep 10
  r=$(ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -c 'Application startup complete' /root/vllm.log" 2>/dev/null)
  if [ "${r:-0}" -ge 1 ]; then
    sleep 3
    ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -E 'GPU KV cache size|Maximum concurrency' /root/vllm.log" 2>/dev/null > "$OUT/startup.log"
    echo "[$tag] $(cat "$OUT/startup.log" | head -1 | grep -oE 'size: [0-9,]+ tokens|concurrency.*' | head -2 | tr '\n' ' ')"
    ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c \"pkill -f '[v]llm serve'; true\"" 2>/dev/null
    echo "[$tag] KV captured, server stopped"
    exit 0
  fi
  if ! ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c \"pgrep -f '[v]llm serve' >/dev/null\"" 2>/dev/null; then
    echo "[$tag] serve died"; exit 1
  fi
done
echo "[$tag] timeout"; exit 1
