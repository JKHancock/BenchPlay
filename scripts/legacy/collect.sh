#!/usr/bin/env bash
# 补采单元格(报告规格驱动): 逐组合 服务→metrics快照(负载前后)→Track1→能力(3.6)
# 产物落 tasks/t20261001-full-report/raw/{tag}/..., 完成后由 merge 重建 rows.jsonl
set -u
BP=/d/CSharpProject/BenchPlaybook
CLI=/d/CSharpProject/Vllm_Benchmark
OUT=$BP/tasks/t20261001-full-report/raw
H=192.168.199.129
mkdir -p "$OUT"

run_combo() { # tp model cap
  tp=$1; model=$2; cap=$3
  tag="TP${tp}-$(echo "$model" | cut -d- -f1)"
  mkdir -p "$OUT/$tag"
  echo "[$(date +%H:%M:%S)] $tag serve..." >> "$OUT/progress.log"
  if ! bash $BP/scripts/serve.sh $H syspetro "$model" "" 40960 "$tp" > "$OUT/$tag/serve.log" 2>&1; then
    echo "[$(date +%H:%M:%S)] $tag serve重试(ray重启)..." >> "$OUT/progress.log"
    bash $BP/scripts/cluster.sh $H 192.168.199.134 syspetro >> "$OUT/$tag/cluster.log" 2>&1
    bash $BP/scripts/serve.sh $H syspetro "$model" "" 40960 "$tp" >> "$OUT/$tag/serve.log" 2>&1 \
      || { echo "$tag SERVE-FAIL" >> "$OUT/failures.log"; return; }
  fi
  bash $BP/scripts/verify.sh $H > "$OUT/$tag/verify.log" 2>&1 || { echo "$tag VERIFY-FAIL" >> "$OUT/failures.log"; return; }
  curl -s -m 10 "http://$H:8000/metrics" | grep -v '^#' > "$OUT/$tag/metrics_idle.txt"
  bash $BP/scripts/bench.sh 1 8 > "$OUT/$tag/bench.log" 2>&1
  [ $? -ne 0 ] && echo "$tag BENCH-FAIL" >> "$OUT/failures.log"
  curl -s -m 10 "http://$H:8000/metrics" | grep -v '^#' > "$OUT/$tag/metrics_loaded.txt"
  if [ "$cap" = "cap" ]; then
    echo "[$(date +%H:%M:%S)] $tag gsm8k..." >> "$OUT/progress.log"
    (cd $CLI && HF_ENDPOINT=https://hf-mirror.com dotnet run --project src/LocalLlmBench.Cli -- \
       run -c configs/cap-gsm8k.yaml --track capability > "$OUT/$tag/cap.log" 2>&1)
    dir=$(ls -1dt $CLI/results/2026*-* | head -1)
    cp "$dir/capability_result.json" "$OUT/$tag/capability_result.json" 2>/dev/null \
      || echo "$tag CAP-FAIL" >> "$OUT/failures.log"
  fi
  echo "$tag DONE" >> "$OUT/progress.log"
}

run_combo 2 Qwen3.6-35B-A3B-NVFP4-Fast cap
run_combo 1 Qwen3.6-35B-A3B-NVFP4-Fast cap
run_combo 2 Qwen3.8-27B-NVFP4 nocap
run_combo 1 Qwen3.8-27B-NVFP4 nocap
echo "ALL-DONE" >> "$OUT/progress.log"
