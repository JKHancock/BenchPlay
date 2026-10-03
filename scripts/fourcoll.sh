#!/usr/bin/env bash
# 四指标集合采集(当前演示服务): vllm / perf / capability / agent, 三时点+段间快照.
set -u
BP=/d/CSharpProject/BenchPlaybook
CLI=/d/CSharpProject/Vllm_Benchmark
PY=$CLI/python/.venv/Scripts/python.exe
OUT=$BP/tasks/t20260930-demo-4col/raw
H=192.168.199.129; API=http://$H:8000/v1; MODEL=qwen3.6-35b-a3b
mkdir -p "$OUT"
log(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$OUT/progress.log"; }
snap(){ "$PY" - "$API" "$OUT/$1" <<'EOF'
import sys; sys.path.insert(0, 'D:/CSharpProject/Vllm_Benchmark')
from bench.common import snapshot
snapshot(sys.argv[1], sys.argv[2])
EOF
}

log "idle快照"
snap metrics_idle.json

log "Track1 性能(w1: c1/c8/c32)"
(cd $CLI && "$PY" -m bench.track1 --api-base "$API" --model "$MODEL" \
  --workload w1 --weights-active-gb 1.7 --bw-gbps 546 \
  --out "$OUT/perf_w1.json" --evidence-dir "$OUT" > "$OUT/track1.log" 2>&1) \
  || log "track1 FAIL"
snap metrics_perf.json

log "Track2 能力(5套件 n=200)"
(cd $CLI && "$PY" -m bench.track2 --api-base "$API" --model "$MODEL" \
  --suites gsm8k,mmlu,arc,hellaswag,winogrande --n 200 --concurrency 8 \
  --request-timeout-s 480 --gsm8k-max-tokens 1024 \
  --out "$OUT/cap.json" --evidence-dir "$OUT" > "$OUT/track2.log" 2>&1) \
  || log "track2 FAIL"
snap metrics_cap.json

log "Track3 智能体 + reasoning A/B"
(cd $CLI && "$PY" -m bench.track3_agent --api-base "$API" --model "$MODEL" \
  --out "$OUT/agent.json" > "$OUT/track3.log" 2>&1) || log "track3 FAIL(见日志)"
"$PY" - "$API" > "$OUT/reasoning_ab.json" <<'EOF'
import sys, json, time, requests
sys.path.insert(0, 'D:/CSharpProject/Vllm_Benchmark')
api = sys.argv[1].rstrip("/")
S = {"type": "function", "function": {"name": "get_weather",
     "description": "查城市天气", "parameters": {"type": "object",
     "properties": {"city": {"type": "string"}}, "required": ["city"]}}}
out = {}
for mode in (False, True):
    body = {"model": "qwen3.6-35b-a3b",
            "messages": [{"role": "user", "content": "上海天气如何?"}],
            "tools": [S], "tool_choice": "auto", "max_tokens": 2048,
            "chat_template_kwargs": {"enable_thinking": mode}}
    t0 = time.time()
    r = requests.post(api + "/chat/completions", json=body, timeout=180).json()
    ms = (time.time() - t0) * 1000
    ch = r["choices"][0]
    u = r.get("usage", {})
    out["thinking_on" if mode else "thinking_off"] = {
        "called": bool(ch["message"].get("tool_calls")),
        "wall_ms": round(ms, 0),
        "completion_tokens": u.get("completion_tokens"),
        "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
    }
print(json.dumps(out, ensure_ascii=False, indent=1))
EOF
snap metrics_agent.json
log "ALL-DONE"
