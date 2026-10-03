#!/usr/bin/env bash
# 矩阵补采(schema v3, 报告契约"每行=多套件能力+多档性能+vLLM指标"):
#   每组合: [TP2时先组网] serve → verify → 指标@idle → Track1(1/8/32档) → 指标@perf
#           → Track2(gsm8k/mmlu/arc, n=200) → 指标@cap
# 产物: tasks/t20260930-matrix-full/raw/<tag>/...
set -u
BP=/d/CSharpProject/BenchPlaybook
CLI=/d/CSharpProject/Vllm_Benchmark
PY=$CLI/python/.venv/Scripts/python.exe
OUT=$BP/tasks/t20260930-matrix-full/raw
H=192.168.199.129; H2=192.168.199.134; U=syspetro
API=http://$H:8000/v1
mkdir -p "$OUT"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$OUT/progress.log"; }

snap() { # snap <tag> <name> — /metrics 解析快照
  "$PY" - "$API" "$OUT/$1/metrics_$2.json" <<'EOF' || log "$1 metrics_$2 FAIL"
import sys; sys.path.insert(0, 'D:/CSharpProject/Vllm_Benchmark')
from bench.common import snapshot
snapshot(sys.argv[1], sys.argv[2])
EOF
}

combo() { # tp model active_gb serve_needed
  local tp=$1 model=$2 active_gb=$3 serve=$4
  local tag="TP${tp}-$(echo "$model" | cut -d- -f1)"
  local bw=273; [ "$tp" -gt 1 ] && bw=546
  mkdir -p "$OUT/$tag"
  if [ "$serve" = "1" ]; then
    if [ "$tp" -gt 1 ]; then
      bash $BP/scripts/cluster.sh $H $H2 $U >> "$OUT/$tag/cluster.log" 2>&1 \
        || { log "$tag ray组网FAIL"; echo "$tag CLUSTER-FAIL" >> "$OUT/failures.log"; return 1; }
    fi
    if ! bash $BP/scripts/serve.sh $H $U "$model" "" 40960 "$tp" > "$OUT/$tag/serve.log" 2>&1; then
      log "$tag serve失败→重启ray重试一次"
      bash $BP/scripts/cluster.sh $H $H2 $U >> "$OUT/$tag/cluster.log" 2>&1
      bash $BP/scripts/serve.sh $H $U "$model" "" 40960 "$tp" >> "$OUT/$tag/serve.log" 2>&1 \
        || { log "$tag SERVE-FAIL"; echo "$tag SERVE-FAIL" >> "$OUT/failures.log"; return 1; }
    fi
  fi
  bash $BP/scripts/verify.sh $H > "$OUT/$tag/verify.log" 2>&1 \
    || { log "$tag VERIFY-FAIL"; echo "$tag VERIFY-FAIL" >> "$OUT/failures.log"; return 1; }
  snap "$tag" idle
  log "$tag Track1 开始(bw=$bw active=$active_gb GB)"
  (cd $CLI && "$PY" -m bench.track1 --api-base "$API" --model bench \
     --levels 1,8,32 --num-prompts 8,32,48 \
     --weights-active-gb "$active_gb" --bw-gbps "$bw" \
     --out "$OUT/$tag/perf.json" --evidence-dir "$OUT/$tag" \
     > "$OUT/$tag/track1.log" 2>&1) \
    || { log "$tag TRACK1-FAIL"; echo "$tag TRACK1-FAIL" >> "$OUT/failures.log"; }
  snap "$tag" perf
  log "$tag Track2 开始(gsm8k/mmlu/arc n=200)"
  (cd $CLI && "$PY" -m bench.track2 --api-base "$API" --model bench \
     --suites gsm8k,mmlu,arc --n 200 --concurrency 8 --request-timeout-s 480 \
     --gsm8k-max-tokens 1024 \
     --out "$OUT/$tag/cap.json" --evidence-dir "$OUT/$tag" \
     > "$OUT/$tag/track2.log" 2>&1) \
    || { log "$tag TRACK2-FAIL"; echo "$tag TRACK2-FAIL" >> "$OUT/failures.log"; }
  snap "$tag" cap
  log "$tag DONE"
}

# 执行顺序按现场状态优化: 当前 129 在跑 27B-TP1 → 先测它(免 serve);
# 之后 TP2 两次(ray 已组网连测两个), 最后 TP1.
combo 1 Qwen3.8-27B-NVFP4 15.5 0
combo 2 Qwen3.8-27B-NVFP4 15.5 1
combo 2 Qwen3.6-35B-A3B-NVFP4-Fast 1.7 1
combo 1 Qwen3.6-35B-A3B-NVFP4-Fast 1.7 1
log "ALL-DONE"
