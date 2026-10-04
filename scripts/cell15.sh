#!/usr/bin/env bash
# 全流程电池: DeepSeek-V4-Flash NVFP4 (deepseek_v4, DSpark草稿: mtp.0/1/2+main_norm/main_proj+markov/confidence头)
# 场景: TP2+DSpark投机(dspark,k2)+原生1M+deepseek_v4工具parser+8路+batched8192, 关自调优
# 注意: NVFP4版草稿是DSpark拓扑, 无enorm/hnorm/e_proj/h_proj, 必须用method=dspark(deepseek_mtp仅适用FP8版)
# 电池: w1-w6+探针+Track2十二套件+soak(3x500K)+Track3+BFCL, 全程三时点metrics
# 输出: tasks/t20261005-dsnvfp4-40960-ep2/raw/DsFlashN-TP2-40960-ep2
set -u
BP=/d/CSharpProject/BenchPlaybook
CLI=/d/CSharpProject/BenchPlaybook
PY=$CLI/.venv/Scripts/python.exe
OUTBASE=$BP/tasks/t20261005-dsnvfp4-40960-ep2/raw
H=192.168.199.129; H2=192.168.199.134; U=syspetro; API=http://$H:8000/v1
SSHOPT="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"
tag=DsFlashN-TP2-40960-ep2
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
  --tensor-parallel-size 2 --distributed-executor-backend ray --enable-expert-parallel \
  --speculative-config '{"method":"dspark","num_speculative_tokens":2}' \
  --kernel-config '{"enable_flashinfer_autotune":false}' \
  --enable-auto-tool-choice --tool-call-parser deepseek_v4 \
  --served-model-name ds-nvfp4 --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 --max-model-len 40960 \
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
# 思考链形态探针: deepseek模板是否认 enable_thinking(不认则能力套件口径需修正)
"$PY" - "$API" > "$OUT/think_probe.log" 2>&1 <<'EOF'
import sys, json, requests
api = sys.argv[1] + "/chat/completions"
for flag in (False, True):
    r = requests.post(api, json={"model": "ds-nvfp4", "max_tokens": 512, "temperature": 0,
                                 "chat_template_kwargs": {"enable_thinking": flag},
                                 "messages": [{"role": "user", "content": "1+1=? 数字作答"}]}, timeout=120)
    d = r.json()["choices"][0]["message"]
    print("enable_thinking=%s -> reasoning=%s content=%s" % (flag, bool(d.get("reasoning_content")), (d.get("content") or "")[:40]))
EOF
cat "$OUT/think_probe.log"
log "电池开始"
snap(){ "$PY" - "$API" "$OUT/$2" <<'EOF'
import sys; sys.path.insert(0, 'D:/CSharpProject/BenchPlaybook')
from bench.common import snapshot
snapshot(sys.argv[1], sys.argv[2])
EOF
}
ssh -n $SSHOPT $U@$H "docker exec -d vllm-node bash -c 'while true; do nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader >> /tmp/hostsample.log 2>&1; sleep 3; done'" 2>/dev/null
for w in w1 w2 w3 w4 w5 w6; do
  log "$w 开始"
  snap "api" "metrics_${w}_a.json"
  (cd $CLI && "$PY" -m bench.track1 --api-base "$API" --model ds-nvfp4 \
     --workload $w --weights-active-gb 6.0 --bw-gbps 546 --request-timeout-s 900 \
     --out "$OUT/$w.json" --evidence-dir "$OUT" > "$OUT/$w.log" 2>&1) || log "$w FAIL"
  snap "api" "metrics_${w}_b.json"
done
log "probes 开始"
snap "api" "metrics_probe_a.json"
(cd $CLI && "$PY" -m bench.probes --api-base "$API" \
   --out "$OUT/probes.json" > "$OUT/probes.log" 2>&1) || log "probes FAIL"
snap "api" "metrics_probe_b.json"
log "soak 开始(3路 x 500K)"
(cd $CLI && "$PY" -m bench.soak --api-base "$API" --model ds-nvfp4 \
   --sessions 3 --chunk-tokens 20000 --target-context 38400 --max-tokens 512 \
   --request-timeout-s 1200 --out "$OUT/soak.json" --evidence-dir "$OUT" > "$OUT/soak.log" 2>&1) || log "soak FAIL"
log "Track2 十二套件开始"
snap "api" "metrics_cap_a.json"
(cd $CLI && "$PY" -m bench.track2 --api-base "$API" --model ds-nvfp4 \
   --suites gsm8k,mmlu,arc,hellaswag,winogrande,truthfulqa,openbookqa,race,math500,cmmlu,ceval,ifeval \
   --n 200 --concurrency 8 --request-timeout-s 900 --gsm8k-max-tokens 1024 \
   --math500-max-tokens 8192 --ifeval-max-tokens 1024 \
   --out "$OUT/cap.json" --evidence-dir "$OUT" > "$OUT/track2.log" 2>&1) || log "track2 FAIL"
snap "api" "metrics_cap_b.json"
log "Track3+BFCL 开始"
snap "api" "metrics_agent_a.json"
(cd $CLI && "$PY" -m bench.track3_agent --api-base "$API" --model ds-nvfp4 \
   --out "$OUT/agent.json" > "$OUT/track3.log" 2>&1) || log "track3 FAIL"
(cd $CLI && "$PY" -m bench.bfcl --api-base "$API" --model ds-nvfp4 \
   --n 100 --out "$OUT/bfcl.json" > "$OUT/bfcl.log" 2>&1) || log "bfcl FAIL"
snap "api" "metrics_agent_b.json"
ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c \"pkill -f 'nvidia-smi --query-gpu=utilization.gpu,memory.used' 2>/dev/null; true\"; docker exec vllm-node cat /tmp/hostsample.log 2>/dev/null | tail -3000; docker exec vllm-node bash -c 'rm -f /tmp/hostsample.log'" 2>/dev/null > "$OUT/host_head.log"
log "DONE(全流程电池完成)"
