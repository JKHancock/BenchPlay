#!/usr/bin/env bash
# =====================================================================
# 自动生成cell — 来源: scripts/cell_template.sh + bindings/ 绑定文件
# 生成器: scripts/make_cell.sh (含未替换token检测门禁)
# 任何手改请改模板/绑定后重新生成, 禁止直接编辑生成物
# =====================================================================
# # 压力专项电池: DS-V4-Flash NVFP4 产品口径(k2基线参数)
# w13冷踩踏→w7/w8/w9超长冷prefill→w10干扰战→w11池溢出→w12马拉松
# 预计时长~60-90min; 产出: 每workload独立json + 干扰比/溢出行为/马拉松衰减画像
# 电池: w1-w6+探针+思考探针(无(压力专项跳过))+soak(无(压力专项跳过))+Track2十二套件+Track3+BFCL, 全程三时点metrics
# 输出: tasks/t20261006-ds-stress/raw/DsFlashN-TP2-1M-stress
set -u
BP=/d/CSharpProject/BenchPlaybook
CLI=/d/CSharpProject/BenchPlaybook
PY=$CLI/.venv/Scripts/python.exe
OUTBASE=$BP/tasks/t20261006-ds-stress/raw
H=192.168.199.129; H2=192.168.199.134; U=syspetro; API=http://$H:8000/v1
SSHOPT="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"
tag=DsFlashN-TP2-1M-stress
OUT=$OUTBASE/$tag
mkdir -p "$OUT"
log(){ echo "[$(date +%m-%d\ %H:%M:%S)] $tag $*" | tee -a "$OUTBASE/progress.log"; }

bash $BP/scripts/cluster.sh $H $H2 $U > "$OUT/cluster.log" 2>&1 || { log "ray FAIL"; exit 1; }
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
log "清场+ray完成, serve发起(166.9GB加载预计10-20min)..."
ssh $SSHOPT $U@$H "docker exec -i vllm-node bash -s" > "$OUT/serve.log" 2>&1 <<'EOS' || { log "serve发起失败"; exit 1; }
export CUTE_DSL_ARCH=sm_121a HF_ENDPOINT=https://hf-mirror.com RAY_memory_monitor_refresh_ms=0
export GLOO_SOCKET_IFNAME=enp1s0f1np1 NCCL_SOCKET_IFNAME=enp1s0f1np1
nohup vllm serve /root/.cache/huggingface/DeepSeek-V4-Flash-NVFP4 \
  --tensor-parallel-size 2 --distributed-executor-backend ray --enable-expert-parallel --speculative-config '{"method":"dspark","num_speculative_tokens":2}' --kernel-config '{"enable_flashinfer_autotune":false}' \
   \
  --enable-auto-tool-choice --tool-call-parser deepseek_v4 \
  --served-model-name ds-nvfp4 --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 --max-model-len 1048576 \
  --max-num-seqs 8 --max-num-batched-tokens 8192 --enable-chunked-prefill --enable-prefix-caching \
  > /root/vllm.log 2>&1 &
echo LAUNCHED
EOS
ready=0
for i in $(seq 1 300); do
  sleep 10
  r=$(ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -c 'Application startup complete' /root/vllm.log" 2>/dev/null)
  p=$(ssh -n $SSHOPT $U@$H "ss -ltn 2>/dev/null | grep -c ':8000 '" 2>/dev/null)
  if [ "${r:-0}" -ge 1 ] && [ "${p:-0}" -ge 1 ]; then
    log "serve就绪(约$((i*10))s)"
    ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -E 'GPU KV cache size|Maximum concurrency' /root/vllm.log" 2>/dev/null | tee "$OUT/startup.log"
    ready=1; break
  fi
  if ! ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c \"pgrep -f '[v]llm serve' >/dev/null\"" 2>/dev/null; then
    log "serve进程退出,尾部:"; ssh -n $SSHOPT $U@$H "docker exec vllm-node tail -25 /root/vllm.log" 2>/dev/null | tee -a "$OUT/serve.log"; exit 1
  fi
done
[ "$ready" -ne 1 ] && { log "就绪超时(50min)"; exit 1; }
bash $BP/scripts/verify.sh $H 1 > "$OUT/verify.log" 2>&1 || { log "VERIFY-FAIL"; cat "$OUT/verify.log"; exit 1; }
log "四关全过"

log "电池开始"
snap(){ "$PY" - "$API" "$OUT/$2" <<'EOF'
import sys; sys.path.insert(0, 'D:/CSharpProject/BenchPlaybook')
from bench.common import snapshot
snapshot(sys.argv[1], sys.argv[2])
EOF
}
ssh -n $SSHOPT $U@$H "docker exec -d vllm-node bash -c 'while true; do nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >> /tmp/hostsample.log 2>&1; sleep 3; done'" 2>/dev/null
for w in w13-stampede w7-long128k w8-long256k-c4 w9-long500k w10-interfere w11-overflow w12-marathon; do
  log "$w 开始"
  snap "api" "metrics_${w}_a.json"
  (cd $CLI && "$PY" -m bench.track1 --api-base "$API" --model ds-nvfp4 \
     --workload $w --weights-active-gb 6.0 --bw-gbps 546 --request-timeout-s 1800 \
     --out "$OUT/$w.json" --evidence-dir "$OUT" > "$OUT/$w.log" 2>&1) || log "$w FAIL"
  snap "api" "metrics_${w}_b.json"
done
log "probes 开始"
snap "api" "metrics_probe_a.json"
(cd $CLI && "$PY" -m bench.probes --api-base "$API" \
   --out "$OUT/probes.json" > "$OUT/probes.log" 2>&1) || log "probes FAIL"
snap "api" "metrics_probe_b.json"



ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c \"pkill -f 'nvidia-smi --query-gpu=utilization.gpu,memory.used' 2>/dev/null; true\"; docker exec vllm-node cat /tmp/hostsample.log 2>/dev/null | tail -3000; docker exec vllm-node bash -c 'rm -f /tmp/hostsample.log'" 2>/dev/null > "$OUT/host_head.log"
log "DONE(全流程电池完成)"

# 失败传播: 任何步骤 FAIL 必须让电池退出非零(2026-10-05 事故: soak FAIL 被吞, 电池假绿)
if grep -q " FAIL" "$OUTBASE/progress.log"; then log "电池含FAIL标记, 判失败"; exit 1; fi
