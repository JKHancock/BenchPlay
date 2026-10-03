#!/usr/bin/env bash
# 目标场景: TP2+EP2+投机解码(ngram,2tok)+YaRN4x+1M上下文 (模型无MTP头, ngram为可行替代).
# 电池: 舒适度扫描 wsweep(c1..c32) + 真实分布扫描 w2s + 128K长文探针 w7 + gsm8k验证.
set -u
BP=/d/CSharpProject/BenchPlaybook
CLI=/d/CSharpProject/Vllm_Benchmark
PY=$CLI/python/.venv/Scripts/python.exe
OUTBASE=$BP/tasks/t20260930-matrix-full/raw4
H=192.168.199.129; H2=192.168.199.134; U=syspetro; API=http://$H:8000/v1
SSHOPT="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"
tag=TP2EP2MTP-1M-Qwen3.6
OUT=$OUTBASE/$tag
mkdir -p "$OUT"
log(){ echo "[$(date +%H:%M:%S)] $tag $*" | tee -a "$OUTBASE/progress.log"; }

bash $BP/scripts/cluster.sh $H $H2 $U > "$OUT/cluster.log" 2>&1 || { log "ray FAIL"; exit 1; }
for n in $H $H2; do
  ssh -n $SSHOPT $U@$n "docker exec vllm-node bash -c \"pkill -f '[v]llm serve' 2>/dev/null; pkill -f '[R]ayWorkerProc' 2>/dev/null; pkill -f '[E]ngineCore' 2>/dev/null; true\"" 2>/dev/null
done
sleep 10
ssh $SSHOPT $U@$H "docker exec -i -e MODEL=Qwen3.6-35B-A3B-NVFP4-Fast -e TP=2 vllm-node bash -s" > "$OUT/serve.log" 2>&1 <<'EOS' || { log "serve发起失败"; exit 1; }
export CUTE_DSL_ARCH=sm_121a HF_ENDPOINT=https://hf-mirror.com RAY_memory_monitor_refresh_ms=0
export GLOO_SOCKET_IFNAME=enp1s0f1np1 NCCL_SOCKET_IFNAME=enp1s0f1np1
nohup vllm serve /root/.cache/huggingface/$MODEL \
  --tensor-parallel-size $TP --distributed-executor-backend ray \
  --enable-expert-parallel \
  --speculative-config '{"method":"qwen3_5_mtp","num_speculative_tokens":2}' \
  --hf-overrides '{"text_config":{"max_position_embeddings":1048576,"rope_scaling":{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":262144,"mrope_interleaved":true,"mrope_section":[11,11,10],"partial_rotary_factor":0.25,"rope_theta":10000000}}}' \
  --kernel-config '{"enable_flashinfer_autotune":false}' \
  --served-model-name bench --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 --max-model-len 1048576 \
  --max-num-seqs 64 --enable-chunked-prefill --enable-prefix-caching \
  > /root/vllm.log 2>&1 &
echo LAUNCHED
EOS
log "serve已发起(EP+qwen3_5_mtp-k2+yarn4x+1M), 等就绪..."
ready=0
for i in $(seq 1 120); do
  sleep 10
  r=$(ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -c 'Application startup complete' /root/vllm.log" 2>/dev/null)
  p=$(ssh -n $SSHOPT $U@$H "ss -ltn 2>/dev/null | grep -c ':8000 '" 2>/dev/null)
  if [ "${r:-0}" -ge 1 ] && [ "${p:-0}" -ge 1 ]; then
    log "serve就绪(约$((i*10))s)"
    ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -E 'GPU KV cache size|Maximum concurrency' /root/vllm.log" 2>/dev/null > "$OUT/startup.log"
    ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -iE 'spec|draft|accept|yarn|rope' /root/vllm.log | head -6" 2>/dev/null | tee "$OUT/spec_info.log"
    ready=1; break
  fi
  if ! ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c \"pgrep -f '[v]llm serve' >/dev/null\"" 2>/dev/null; then
    log "serve进程退出, 尾部:"
    ssh -n $SSHOPT $U@$H "docker exec vllm-node tail -30 /root/vllm.log" 2>/dev/null | tee -a "$OUT/serve.log"
    exit 1
  fi
done
[ "$ready" -ne 1 ] && { log "就绪超时"; exit 1; }
bash $BP/scripts/verify.sh $H > "$OUT/verify.log" 2>&1 || { log "VERIFY-FAIL"; exit 1; }
snap(){ "$PY" - "$API" "$OUT/$2" <<'EOF'
import sys; sys.path.insert(0, 'D:/CSharpProject/Vllm_Benchmark')
from bench.common import snapshot
snapshot(sys.argv[1], sys.argv[2])
EOF
}
ssh -n $SSHOPT $U@$H "docker exec -d vllm-node bash -c 'while true; do nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >> /tmp/hostsample.log 2>&1; sleep 3; done'" 2>/dev/null

for w in wsweep w2s w7-long128k; do
  log "$w 开始"
  snap "api" "metrics_${w}_a.json"
  (cd $CLI && "$PY" -m bench.track1 --api-base "$API" --workload $w \
     --weights-active-gb 1.7 --bw-gbps 546 --request-timeout-s 900 \
     --out "$OUT/$w.json" --evidence-dir "$OUT" > "$OUT/$w.log" 2>&1) \
    || log "$w FAIL(见$w.log)"
  snap "api" "metrics_${w}_b.json"
done
log "probes 开始"
snap "api" "metrics_probe_a.json"
(cd $CLI && "$PY" -m bench.probes --api-base "$API" \
   --out "$OUT/probes.json" > "$OUT/probes.log" 2>&1) || log "probes FAIL"
snap "api" "metrics_probe_b.json"
log "gsm8k验证开始(n=200)"
snap "api" "metrics_cap_a.json"
(cd $CLI && "$PY" -m bench.track2 --api-base "$API" \
   --suites gsm8k --n 200 --concurrency 8 --request-timeout-s 480 \
   --gsm8k-max-tokens 1024 \
   --out "$OUT/cap.json" --evidence-dir "$OUT" > "$OUT/cap.log" 2>&1) || log "cap FAIL"
snap "api" "metrics_cap_b.json"
ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c \"pkill -f 'nvidia-smi --query-gpu=utilization.gpu,memory.used' 2>/dev/null; true\"; docker exec vllm-node cat /tmp/hostsample.log 2>/dev/null | tail -2000; docker exec vllm-node bash -c 'rm -f /tmp/hostsample.log'" 2>/dev/null > "$OUT/host_head.log"
log "DONE"
