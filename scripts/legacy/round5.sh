#!/usr/bin/env bash
# 第五轮 TP2-35B: 关 FlashInfer 自调优(--kernel-config)绕开确定性33分钟自调优死亡.
# 流程: ray双节点重启 → 双节点清场等GPU归零 → serve脚本经stdin入容器(绕三层引号)
#       → 就绪门禁(15min) → verify → 三时点指标 → Track1 → Track2
set -u
BP=/d/CSharpProject/BenchPlaybook
CLI=/d/CSharpProject/Vllm_Benchmark
PY=$CLI/python/.venv/Scripts/python.exe
OUT=$BP/tasks/t20260930-matrix-full/raw/TP2-Qwen3.6
H=192.168.199.129; H2=192.168.199.134; U=syspetro; API=http://$H:8000/v1
mkdir -p "$OUT"
log(){ echo "[$(date +%H:%M:%S)] TP2-Qwen3.6-round5 $*" | tee -a $BP/tasks/t20260930-matrix-full/raw/progress.log; }
SSHOPT="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"

log "开始: ray重启..."
bash $BP/scripts/cluster.sh $H $H2 $U > "$OUT/cluster5.log" 2>&1 || { log "ray组网FAIL"; exit 1; }

for n in $H $H2; do
  ssh -n $SSHOPT $U@$n "docker exec vllm-node bash -c \"pkill -f '[v]llm serve' 2>/dev/null; pkill -f '[R]ayWorkerProc' 2>/dev/null; pkill -f '[E]ngineCore' 2>/dev/null; true\"" 2>/dev/null
done
g=99
for i in $(seq 1 36); do
  g=0
  for n in $H $H2; do
    c=$(ssh -n $SSHOPT $U@$n "nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null" | grep -c .)
    g=$((g + ${c:-0}))
  done
  [ "$g" -eq 0 ] && break
  sleep 5
done
[ "$g" -ne 0 ] && { log "GPU未归零($g进程)"; exit 1; }
log "双节点清场完成, serve发起(关自调优)..."

ssh $SSHOPT $U@$H "docker exec -i vllm-node bash -s" > "$OUT/serve5.log" 2>&1 <<'EOS' || { log "serve发起失败"; exit 1; }
export CUTE_DSL_ARCH=sm_121a HF_ENDPOINT=https://hf-mirror.com RAY_memory_monitor_refresh_ms=0
export GLOO_SOCKET_IFNAME=enp1s0f1np1 NCCL_SOCKET_IFNAME=enp1s0f1np1
nohup vllm serve /root/.cache/huggingface/Qwen3.6-35B-A3B-NVFP4-Fast \
  --tensor-parallel-size 2 --distributed-executor-backend ray \
  --kernel-config '{"enable_flashinfer_autotune": false}' \
  --served-model-name bench --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 --max-model-len 40960 \
  --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching \
  > /root/vllm.log 2>&1 &
echo LAUNCHED
EOS

ready=0
for i in $(seq 1 90); do
  sleep 10
  r=$(ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -c 'Application startup complete' /root/vllm.log" 2>/dev/null)
  p=$(ssh -n $SSHOPT $U@$H "ss -ltn 2>/dev/null | grep -c ':8000 '" 2>/dev/null)
  if [ "${r:-0}" -ge 1 ] && [ "${p:-0}" -ge 1 ]; then
    log "serve就绪(约$((i*10))s, 关自调优口径)"; ready=1; break
  fi
  if ! ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c \"pgrep -f '[v]llm serve' >/dev/null\"" 2>/dev/null; then
    log "serve进程退出, 日志尾部已存 serve5.log"
    ssh -n $SSHOPT $U@$H "docker exec vllm-node tail -25 /root/vllm.log" >> "$OUT/serve5.log" 2>/dev/null
    exit 1
  fi
done
[ "$ready" -ne 1 ] && { log "就绪超时(900s)"; exit 1; }

bash $BP/scripts/verify.sh $H > "$OUT/verify.log" 2>&1 || { log "VERIFY-FAIL"; exit 1; }
snap(){ "$PY" - "$API" "$OUT/metrics_$1.json" <<'EOF' || log "metrics_$1 FAIL"
import sys; sys.path.insert(0, 'D:/CSharpProject/Vllm_Benchmark')
from bench.common import snapshot
snapshot(sys.argv[1], sys.argv[2])
EOF
}
snap idle
(cd $CLI && "$PY" -m bench.track1 --api-base "$API" --model bench \
   --levels 1,8,32 --num-prompts 8,32,48 \
   --weights-active-gb 1.7 --bw-gbps 546 \
   --out "$OUT/perf.json" --evidence-dir "$OUT" > "$OUT/track1.log" 2>&1) || log "TRACK1-FAIL"
snap perf
(cd $CLI && "$PY" -m bench.track2 --api-base "$API" --model bench \
   --suites gsm8k,mmlu,arc --n 200 --concurrency 8 --request-timeout-s 480 \
   --gsm8k-max-tokens 1024 \
   --out "$OUT/cap.json" --evidence-dir "$OUT" > "$OUT/track2.log" 2>&1) || log "TRACK2-FAIL"
snap cap
log "DONE(round5)"
