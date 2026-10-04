#!/usr/bin/env bash
# 测试段: 调用孪生 C# 实现(llm-bench CLI)对现网服务跑 Track1 性能基准.
# 门禁: perf_run_result.json 生成且至少一层 completed>0 failed=0 → PASS.
# 用法: bench.sh [concurrency] [num_prompts]   (默认 1 8, 快速档)
set -u
CONC="${1:-1}"; NP="${2:-8}"
CLI_DIR="/d/CSharpProject/Vllm_Benchmark"
CFG="$CLI_DIR/configs/gx10-dual.yaml"
RESULTS="$CLI_DIR/results"

# 只跑 Track1(Track2 数据集首次下载重, 由调用方显式开启)
cd "$CLI_DIR" || { echo "FAIL 找不到 CLI 目录"; exit 1; }
out=$(dotnet run --project src/LocalLlmBench.Cli -- run -c "$CFG" \
  --concurrency "$CONC" --num-prompts "$NP" 2>&1 | tail -6)
echo "$out"

dir=$(ls -1dt "$RESULTS"/2026*-* 2>/dev/null | head -1)
[ -z "$dir" ] && { echo "FAIL 未生成结果目录"; exit 1; }
perf="$dir/perf_run_result.json"
[ -f "$perf" ] || { echo "FAIL 缺 perf_run_result.json"; exit 1; }

# 门禁: 每层 completed>0 且 failed=0; 附屋顶线常识检查(实测超上限80%报⚠人工复核)
# (实测教训: 门禁退出码必须直检——ok=$(...)后 echo "$ok" || ... 测的是 echo 的退出码, 0/8全败仍PASS)
if ! "$CLI_DIR/python/.venv/Scripts/python.exe" - "$perf" <<'PY'
import json, sys, os
d = json.load(open(sys.argv[1], encoding='utf-8'))
phases = d.get('phases', [])
bad = [p for p in phases if p.get('completed', 0) <= 0 or p.get('failed', 0) > 0]
bw_gbps = float(os.environ.get('BW_GBPS', '900'))       # 显存带宽 GB/s
weights_gb = float(os.environ.get('WEIGHTS_GB', '0'))   # 权重GB, 调用方传(如 13.5)
def num(x):
    return float(x) if x is not None else 0.0
for p in phases:
    line = (f"  并发{p.get('concurrency')} x {p.get('num_prompts')}条: "
            f"TTFT_p50={num(p.get('p50_ttft_ms')):.0f}ms TTFT_p99={num(p.get('p99_ttft_ms')):.0f}ms "
            f"TPOT_p50={num(p.get('p50_tpot_ms')):.1f}ms TPOT_p99={num(p.get('p99_tpot_ms')):.1f}ms "
            f"出流={num(p.get('output_throughput')):.1f}tok/s (成{p.get('completed')}/败{p.get('failed')})")
    if weights_gb > 0 and p.get('concurrency') == 1 and p.get('output_throughput') is not None:
        ceiling = bw_gbps / weights_gb
        if num(p['output_throughput']) > ceiling * 0.8:
            line += f"  ⚠屋顶线警告: 上限≈{ceiling:.0f}tok/s, 疑似缓存命中/测量错误, 人工复核"
    print(line)
sys.exit(0 if phases and not bad else 1)
PY
then
  echo "FAIL 存在失败/空层(见上方各层统计)"
  exit 1
fi
echo "PASS Track1 基准完成, 产物: $perf"
echo "$dir" > /tmp/bench_last_dir
