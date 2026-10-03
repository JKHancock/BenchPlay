#!/usr/bin/env bash
# v4 单场景全电池: cluster(TP2) → 双节点清场 → serve(stdin脚本,可带extra flag)
#   → verify → 主机采样起 → 逐工作负载(w1-w6+probes, 每负载前后指标快照)
#   → 能力5套件 → 主机采样收
# 用法: cell4.sh <tp> <model> <active_gb> <tag> [extra_json_flag]
set -u
BP=/d/CSharpProject/BenchPlaybook
CLI=/d/CSharpProject/Vllm_Benchmark
PY=$CLI/python/.venv/Scripts/python.exe
OUTBASE=$BP/tasks/t20260930-matrix-full/raw4
H=192.168.199.129; H2=192.168.199.134; U=syspetro; API=http://$H:8000/v1
SSHOPT="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"

tp=$1; model=$2; active_gb=$3; tag=$4; extra="${5:-}"
OUT=$OUTBASE/$tag
mkdir -p "$OUT"
log(){ echo "[$(date +%H:%M:%S)] $tag $*" | tee -a "$OUTBASE/progress.log"; }
bw=273; [ "$tp" -gt 1 ] && bw=546

# ---- serve (统一 stdin 通道, extra flag 原样嵌入) ----
if [ "$tp" -gt 1 ]; then
  bash $BP/scripts/cluster.sh $H $H2 $U > "$OUT/cluster.log" 2>&1 || { log "ray FAIL"; exit 1; }
fi
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
  [ "$g" -eq 0 ] && break; sleep 5
done
[ "$g" -ne 0 ] && { log "GPU未归零($g)"; exit 1; }

DIST=""; [ "$tp" -gt 1 ] && DIST="--distributed-executor-backend ray"
# 引号地狱对策(实测两次翻车): 参数经 docker -e 传环境变量, 脚本走引号heredoc —
# env 展开只做分词不做引号剥离, JSON 双引号原样到达 vllm argv
ssh $SSHOPT $U@$H "docker exec -i -e MODEL='$model' -e TP=$tp -e DIST='$DIST' -e 'EXTRA_ARGS=$extra' vllm-node bash -s" > "$OUT/serve.log" 2>&1 <<'EOS' || { log "serve发起失败"; exit 1; }
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
log "serve已发起(TP$tp extra=${extra:-none}), 等就绪..."
# TP2+MoE 且无 extra(即开自调优)时给60分钟, 其余15分钟
MAXLOOP=90
if [ "$tp" -gt 1 ] && [ -z "$extra" ] && [[ "$model" == *A3B* ]]; then MAXLOOP=360; fi
ready=0
for i in $(seq 1 $MAXLOOP); do
  sleep 10
  r=$(ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -c 'Application startup complete' /root/vllm.log" 2>/dev/null)
  p=$(ssh -n $SSHOPT $U@$H "ss -ltn 2>/dev/null | grep -c ':8000 '" 2>/dev/null)
  if [ "${r:-0}" -ge 1 ] && [ "${p:-0}" -ge 1 ]; then
    log "serve就绪(约$((i*10))s)"
    ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -E 'GPU KV cache size|Maximum concurrency' /root/vllm.log" 2>/dev/null | tee "$OUT/startup.log"
    ready=1; break
  fi
  if ! ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c \"pgrep -f '[v]llm serve' >/dev/null\"" 2>/dev/null; then
    log "serve进程退出"; ssh -n $SSHOPT $U@$H "docker exec vllm-node tail -25 /root/vllm.log" >> "$OUT/serve.log" 2>/dev/null; exit 1
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

# ---- 主机负载中采样(两节点, 电池全程) ----
hsstart(){ ssh -n $SSHOPT $U@$1 "docker exec -d vllm-node bash -c 'while true; do nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >> /tmp/hostsample.log 2>&1; sleep 3; done'" 2>/dev/null; }
hsstop(){ ssh -n $SSHOPT $U@$1 "docker exec vllm-node bash -c \"pkill -f 'nvidia-smi --query-gpu=utilization.gpu,memory.used' 2>/dev/null; true\"; docker exec vllm-node cat /tmp/hostsample.log 2>/dev/null | tail -2000; docker exec vllm-node bash -c 'rm -f /tmp/hostsample.log'" 2>/dev/null > "$OUT/host_$2.log"; }
hsstart $H; [ "$tp" -gt 1 ] && hsstart $H2

# ---- 逐工作负载: 快照→跑→快照 ----
for w in w1 w2 w3 w4 w5 w6; do
  log "$w 开始"
  snap "api" "metrics_${w}_a.json"
  (cd $CLI && "$PY" -m bench.track1 --api-base "$API" --workload $w \
     --weights-active-gb "$active_gb" --bw-gbps "$bw" --request-timeout-s 600 \
     --out "$OUT/$w.json" --evidence-dir "$OUT" > "$OUT/$w.log" 2>&1) \
    || log "$w FAIL(见$w.log)"
  snap "api" "metrics_${w}_b.json"
done

log "probes 开始"
snap "api" "metrics_probe_a.json"
(cd $CLI && "$PY" -m bench.probes --api-base "$API" \
   --out "$OUT/probes.json" > "$OUT/probes.log" 2>&1) || log "probes FAIL"
snap "api" "metrics_probe_b.json"

log "track2 开始(5套件 n=200)"
snap "api" "metrics_cap_a.json"
(cd $CLI && "$PY" -m bench.track2 --api-base "$API" \
   --suites gsm8k,mmlu,arc,hellaswag,winogrande --n 200 --concurrency 8 \
   --request-timeout-s 480 --gsm8k-max-tokens 1024 \
   --out "$OUT/cap.json" --evidence-dir "$OUT" > "$OUT/cap.log" 2>&1) \
  || log "track2 FAIL"
snap "api" "metrics_cap_b.json"

hsstop $H head; [ "$tp" -gt 1 ] && hsstop $H2 worker
log "DONE"
