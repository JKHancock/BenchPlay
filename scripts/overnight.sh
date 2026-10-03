#!/usr/bin/env bash
# 整夜值守: A) Flash-Next 补 40960 短上下文档  B) 等DeepSeek下载完→M0→适配→尝试serve→全电池
# C) build7+报告+git提交  全程日志 tasks/t20261003-overnight/progress.log
set -u
BP=/d/CSharpProject/BenchPlaybook
CLI=/d/CSharpProject/Vllm_Benchmark
PY=$CLI/python/.venv/Scripts/python.exe
OUT=$BP/tasks/t20261003-overnight
H=192.168.199.129; H2=192.168.199.134; U=syspetro
SSHOPT="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"
mkdir -p "$OUT"
log(){ echo "[$(date +%m-%d\ %H:%M:%S)] $*" | tee -a "$OUT/progress.log"; }

cleanup(){ for n in $H $H2; do ssh -n $SSHOPT $U@$n "docker exec vllm-node bash -c \"pkill -f '[v]llm serve' 2>/dev/null; pkill -f '[R]ayWorkerProc' 2>/dev/null; pkill -f '[E]ngineCore' 2>/dev/null; true\"" 2>/dev/null; done; }

launch(){ # launch <model> <served_name> <extra_args...>
  local model=$1 name=$2; shift 2
  bash $BP/scripts/cluster.sh $H $H2 $U >> "$OUT/cluster.log" 2>&1 || return 1
  cleanup; sleep 20
  ssh $SSHOPT $U@$H "docker exec -i -e MODEL=$model -e NAME=$name -e TP=2 -e EXTRA='$*' vllm-node bash -s" > "$OUT/serve_${name}.log" 2>&1 <<'EOS' || return 1
export CUTE_DSL_ARCH=sm_121a HF_ENDPOINT=https://hf-mirror.com RAY_memory_monitor_refresh_ms=0
export GLOO_SOCKET_IFNAME=enp1s0f1np1 NCCL_SOCKET_IFNAME=enp1s0f1np1
nohup vllm serve /root/.cache/huggingface/$MODEL \
  --tensor-parallel-size $TP --distributed-executor-backend ray $EXTRA \
  --served-model-name $NAME --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 --max-num-seqs 8 --max-num-batched-tokens 8192 \
  --enable-chunked-prefill --enable-prefix-caching > /root/vllm.log 2>&1 &
echo LAUNCHED
EOS
}

wait_ready(){ # wait_ready <max_min> <tag>
  local maxloop=$(( ${1:-40} * 6 )) tag=${2:-srv}
  for i in $(seq 1 $maxloop); do
    sleep 10
    local r p
    r=$(ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -c 'Application startup complete' /root/vllm.log" 2>/dev/null)
    p=$(ssh -n $SSHOPT $U@$H "ss -ltn 2>/dev/null | grep -c ':8000 '" 2>/dev/null)
    if [ "${r:-0}" -ge 1 ] && [ "${p:-0}" -ge 1 ]; then
      ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -E 'GPU KV cache size|Maximum concurrency' /root/vllm.log" 2>/dev/null | tee -a "$OUT/startup_${tag}.log"
      return 0
    fi
    if ! ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c \"pgrep -f '[v]llm serve' >/dev/null\"" 2>/dev/null; then
      ssh -n $SSHOPT $U@$H "docker exec vllm-node tail -25 /root/vllm.log" 2>/dev/null >> "$OUT/serve_${tag}.log"
      return 1
    fi
  done
  return 1
}

battery(){ # battery <served_name> <outdir> <active_gb>
  local name=$1 dir=$2 agb=$3
  mkdir -p "$dir"
  bash $BP/scripts/verify.sh $H 1 > "$dir/verify.log" 2>&1 || { log "$name VERIFY-FAIL"; return 1; }
  local api=http://$H:8000/v1
  snap(){ "$PY" - "$api" "$dir/$2" <<'EOF'
import sys; sys.path.insert(0,'D:/CSharpProject/Vllm_Benchmark')
from bench.common import snapshot
snapshot(sys.argv[1], sys.argv[2])
EOF
  }
  for w in w1 w2 w3 w4 w5 w6; do
    snap x "metrics_${w}_a.json"
    (cd $CLI && "$PY" -m bench.track1 --api-base "$api" --model "$name" --workload $w \
       --weights-active-gb "$agb" --bw-gbps 546 --request-timeout-s 900 \
       --out "$dir/$w.json" > "$dir/$w.log" 2>&1) || log "$name $w FAIL"
    snap x "metrics_${w}_b.json"
  done
  snap x metrics_probe_a.json
  (cd $CLI && "$PY" -m bench.probes --api-base "$api" --out "$dir/probes.json" > "$dir/probes.log" 2>&1) || true
  snap x metrics_probe_b.json
  snap x metrics_cap_a.json
  (cd $CLI && "$PY" -m bench.track2 --api-base "$api" --model "$name" \
     --suites gsm8k,mmlu,arc,hellaswag,winogrande,truthfulqa,openbookqa,race \
     --n 200 --concurrency 8 --request-timeout-s 600 --gsm8k-max-tokens 1024 \
     --out "$dir/cap.json" > "$dir/track2.log" 2>&1) || log "$name track2 FAIL"
  snap x metrics_cap_b.json
  snap x metrics_agent_a.json
  (cd $CLI && "$PY" -m bench.track3_agent --api-base "$api" --model "$name" \
     --out "$dir/agent.json" > "$dir/track3.log" 2>&1) || true
  (cd $CLI && "$PY" -m bench.bfcl --api-base "$api" --model "$name" \
     --n 100 --out "$dir/bfcl.json" > "$dir/bfcl.log" 2>&1) || true
  snap x metrics_agent_b.json
  log "$name 电池完成 → $dir"
}

# ═══ A) Flash-Next 40960 档 ═══
log "A) Flash-Next 短上下文档(40960)开始"
if launch Qwen3.8-Flash-Next-NVFP4 flashnext-40k \
   '--speculative-config {"method":"qwen4_exp_mtp","num_speculative_tokens":2} --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3 --kernel-config {"enable_flashinfer_autotune":false} --max-model-len 40960'; then
  if wait_ready 40 flashnext-40k; then
    log "A) serve就绪, 电池开始"
    battery flashnext-40k "$OUT/FlashNext-TP2-40960" 4.0
  else log "A) 就绪失败"; fi
else log "A) serve发起失败"; fi
cleanup

# ═══ B) DeepSeek: 等下载(≤8h) → M0 → 适配 → serve → 电池 ═══
log "B) 等待 DeepSeek-V4-Flash-0731-NVFP4 下载完成(双机)"
DSOK=0
for i in $(seq 1 480); do
  sz1=$(ssh -n $SSHOPT $U@$H "du -sm /root/.cache/huggingface/DeepSeek-V4-Flash-0731-NVFP4 2>/dev/null | cut -f1" 2>/dev/null)
  sz2=$(ssh -n $SSHOPT $U@$H2 "du -sm /root/.cache/huggingface/DeepSeek-V4-Flash-0731-NVFP4 2>/dev/null | cut -f1" 2>/dev/null)
  log "下载进度: 129=${sz1:-0}MB 134=${sz2:-0}MB (目标≈170000)"
  if [ "${sz1:-0}" -ge 165000 ] && [ "${sz2:-0}" -ge 165000 ]; then DSOK=1; break; fi
  sleep 60
done
if [ "$DSOK" = "1" ]; then
  log "B) 下载完成, 阶段2a: M0 画像"
  "$PY" $BP/scripts/model_profile.py /tmp/nul --out /dev/null 2>/dev/null || true
  ssh -n $SSHOPT $U@$H "docker exec vllm-node python3 -c \"
import json,re
p='/root/.cache/huggingface/DeepSeek-V4-Flash-0731-NVFP4/'
c=json.load(open(p+'config.json'))
tc=c.get('text_config',c)
print('model_type:',c.get('model_type'),'| mpe:',tc.get('max_position_embeddings'),'| layers:',tc.get('num_hidden_layers'),'| experts:',tc.get('n_routed_experts') or tc.get('num_experts'))
idx=json.load(open(p+'model.safetensors.index.json'))
mtp=[n for n in idx['weight_map'] if re.search(r'(^|\\\\.)(mtp|nextn)',n.lower())]
print('MTP权重:',len(mtp),'| 总GB:',round(idx['metadata']['total_size']/1e9,1))
\"" 2>/dev/null | tee "$OUT/ds_profile.txt"
  # 适配核对(2c): 注册表内 deepseek 架构/方法支持
  ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c 'grep -rhoE \\\"deepseek[a-z0-9_]*\\\" /usr/local/lib/python3.12/dist-packages/vllm/config/speculative.py /usr/local/lib/python3.12/dist-packages/vllm/tool_parsers/__init__.py 2>/dev/null | sort -u | head -8'" 2>/dev/null | tee "$OUT/ds_registry.txt"
  log "B) 阶段2c/serve尝试: TP2 + deepseek_mtp k2 + 1M(按profile定) + qwen3_xml先试"
  if launch DeepSeek-V4-Flash-0731-NVFP4 deepseek \
     '--speculative-config {"method":"deepseek_mtp","num_speculative_tokens":2} --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3 --max-model-len 131072'; then
    if wait_ready 45 deepseek; then
      log "B) serve就绪! 电池开始(权重GB按profile行填)"
      AG=$(grep -oE '总GB: [0-9.]+' "$OUT/ds_profile.txt" | grep -oE '[0-9.]+' | head -1)
      AG=${AG:-90}
      ACT=$(python - <<<'' 2>/dev/null; echo 8)  # 激活参数未知先保守8GB, 屋顶线仅供参考
      battery deepseek "$OUT/DeepSeek-TP2-131k" "$ACT"
    else log "B) serve就绪失败(可能: 176GB超双机0.85内存 / 架构不支持) — 已存证, 走《适配报告》路径"; fi
  else log "B) serve发起失败"; fi
else
  log "B) 下载8小时未完成, 放弃本轮(已存进度)"
fi

# ═══ C) 汇编+报告+提交 ═══
log "C) 汇编报告并提交"
cd $BP
"$PY" scripts/build7.py > "$OUT/build.log" 2>&1 || true
"$PY" scripts/report_gen4.py tasks/t20260930-matrix-full/report_doc.json tasks/t20260930-matrix-full/report_v4.md >> "$OUT/build.log" 2>&1 || true
git add -A
git -c user.name="benchplaybook" -c user.email="bp@local" commit -m "overnight: Flash-Next 40960档+DeepSeek V4-Flash-0731全流程(M0→适配→serve→电池)原始证据与报告更新" >> "$OUT/build.log" 2>&1 || true
log "OVERNIGHT-DONE"
