#!/usr/bin/env bash
# 单组合补采(矩阵失败单元格重跑): ray重启(TP2) → serve → verify → 三时点指标 → Track1 → [Track2]
# 用法: cell.sh <tp> <model> <active_gb> [nocap]
set -u
BP=/d/CSharpProject/BenchPlaybook
CLI=/d/CSharpProject/Vllm_Benchmark
PY=$CLI/python/.venv/Scripts/python.exe
OUTBASE=$BP/tasks/t20260930-matrix-full/raw
H=192.168.199.129; H2=192.168.199.134; U=syspetro
API=http://$H:8000/v1

tp=$1; model=$2; active_gb=$3; cap=${4:-cap}
tag="TP${tp}-$(echo "$model" | cut -d- -f1)"
OUT=$OUTBASE/$tag
mkdir -p "$OUT"
log() { echo "[$(date +%H:%M:%S)] $tag $*" | tee -a "$OUTBASE/progress.log"; }

snap() {
  "$PY" - "$API" "$OUT/metrics_$1.json" <<'EOF' || log "metrics_$1 FAIL"
import sys; sys.path.insert(0, 'D:/CSharpProject/Vllm_Benchmark')
from bench.common import snapshot
snapshot(sys.argv[1], sys.argv[2])
EOF
}

bw=273; [ "$tp" -gt 1 ] && bw=546
[ "$tp" -gt 1 ] && { bash $BP/scripts/cluster.sh $H $H2 $U >> "$OUT/cluster.log" 2>&1 \
  || { log "ray组网FAIL"; exit 1; }; }
if ! bash $BP/scripts/serve.sh $H $U "$model" "" 40960 "$tp" > "$OUT/serve.log" 2>&1; then
  log "serve失败→重启ray重试"
  bash $BP/scripts/cluster.sh $H $H2 $U >> "$OUT/cluster.log" 2>&1
  bash $BP/scripts/serve.sh $H $U "$model" "" 40960 "$tp" >> "$OUT/serve.log" 2>&1 \
    || { log "SERVE-FAIL"; exit 1; }
fi
bash $BP/scripts/verify.sh $H > "$OUT/verify.log" 2>&1 || { log "VERIFY-FAIL"; exit 1; }
snap idle
(cd $CLI && "$PY" -m bench.track1 --api-base "$API" --model bench \
   --levels 1,8,32 --num-prompts 8,32,48 \
   --weights-active-gb "$active_gb" --bw-gbps "$bw" \
   --out "$OUT/perf.json" --evidence-dir "$OUT" > "$OUT/track1.log" 2>&1) \
  || log "TRACK1-FAIL"
snap perf
if [ "$cap" = "cap" ]; then
  (cd $CLI && "$PY" -m bench.track2 --api-base "$API" --model bench \
     --suites gsm8k,mmlu,arc --n 200 --concurrency 8 --request-timeout-s 480 \
     --gsm8k-max-tokens 1024 \
     --out "$OUT/cap.json" --evidence-dir "$OUT" > "$OUT/track2.log" 2>&1) \
    || log "TRACK2-FAIL"
  snap cap
fi
log "DONE"
