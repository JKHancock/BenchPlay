#!/usr/bin/env bash
# 抢救电池: EP2 serve已在跑(清场加载跳过), 直测 w1-w6+探针+soak+12套件+Track3+BFCL
# 场景: TP2+MTP(k2)+YaRN4x→1M+qwen3_xml工具+8路+batched8192, 关FlashInfer自调优(防死锁)
# 电池: w1-w6+探针+Track2十二套件(新增 MATH-500/CMMLU/CEval/IFEval)+Track3+BFCL
# 输出: tasks/t20260930-flashnext-c12/raw/FlashNext-TP2-1M (同参数复测, 替换报告数据)
set -u
BP=/d/CSharpProject/BenchPlaybook
CLI=/d/CSharpProject/BenchPlaybook
PY=$CLI/.venv/Scripts/python.exe
OUTBASE=$BP/tasks/t20261005-flashnext-1m-ep2/raw
H=192.168.199.129; H2=192.168.199.134; U=syspetro; API=http://$H:8000/v1
SSHOPT="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"
tag=FlashNext-TP2-1M-ep2
OUT=$OUTBASE/$tag

bash $BP/scripts/verify.sh $H 1 > "$OUT/verify.log" 2>&1 || { log "VERIFY-FAIL"; cat "$OUT/verify.log"; exit 1; }
log "四关全过, 电池开始"
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
  (cd $CLI && "$PY" -m bench.track1 --api-base "$API" --model flash-next \
     --workload $w --weights-active-gb 4.0 --bw-gbps 546 --request-timeout-s 900 \
     --out "$OUT/$w.json" --evidence-dir "$OUT" > "$OUT/$w.log" 2>&1) || log "$w FAIL"
  snap "api" "metrics_${w}_b.json"
done
log "probes 开始"
snap "api" "metrics_probe_a.json"
(cd $CLI && "$PY" -m bench.probes --api-base "$API" \
   --out "$OUT/probes.json" > "$OUT/probes.log" 2>&1) || log "probes FAIL"
snap "api" "metrics_probe_b.json"
log "soak 开始(3路 x 500K)"
(cd $CLI && "$PY" -m bench.soak --api-base "$API" --model flash-next \n   --sessions 3 --chunk-tokens 20000 --target-context 524288 --max-tokens 512 \n   --request-timeout-s 1200 --out "$OUT/soak.json" --evidence-dir "$OUT" > "$OUT/soak.log" 2>&1) || log "soak FAIL"
log "Track2 十二套件开始"
snap "api" "metrics_cap_a.json"
(cd $CLI && "$PY" -m bench.track2 --api-base "$API" --model flash-next \
   --suites gsm8k,mmlu,arc,hellaswag,winogrande,truthfulqa,openbookqa,race,math500,cmmlu,ceval,ifeval \
   --n 200 --concurrency 8 --request-timeout-s 900 --gsm8k-max-tokens 1024 \
   --math500-max-tokens 8192 --ifeval-max-tokens 1024 \
   --out "$OUT/cap.json" --evidence-dir "$OUT" > "$OUT/track2.log" 2>&1) || log "track2 FAIL"
snap "api" "metrics_cap_b.json"
log "Track3+BFCL 开始"
snap "api" "metrics_agent_a.json"
(cd $CLI && "$PY" -m bench.track3_agent --api-base "$API" --model flash-next \
   --out "$OUT/agent.json" > "$OUT/track3.log" 2>&1) || log "track3 FAIL"
(cd $CLI && "$PY" -m bench.bfcl --api-base "$API" --model flash-next \
   --n 100 --out "$OUT/bfcl.json" > "$OUT/bfcl.log" 2>&1) || log "bfcl FAIL"
snap "api" "metrics_agent_b.json"
ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c \"pkill -f 'nvidia-smi --query-gpu=utilization.gpu,memory.used' 2>/dev/null; true\"; docker exec vllm-node cat /tmp/hostsample.log 2>/dev/null | tail -3000; docker exec vllm-node bash -c 'rm -f /tmp/hostsample.log'" 2>/dev/null > "$OUT/host_head.log"
log "DONE(全流程电池完成)"

# 失败传播: 任何步骤 FAIL 必须让电池退出非零(2026-10-05 事故: soak FAIL 被吞, 电池假绿)
if grep -q " FAIL" "$OUTBASE/progress.log"; then log "电池含FAIL标记, 判失败"; exit 1; fi
