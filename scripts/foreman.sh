#!/usr/bin/env bash
# 电池监工(foreman): 电池运行期间的定期健康巡检, 输出中文摘要, 退出码即分级.
# 用法: foreman.sh [task_raw_dir]   (默认自动定位最新的未完成电池)
# 分级: exit 0=健康 / 3=观察(WARN) / 4=异常(FAIL, 需归因)
# 设计要点: progress.log 只记阶段开始(math500 可 legitimately 90min 无新行),
#           所以活性判定用服务端双采样(running/generation 计数 60s 内有变化即活),
#           而不是只看日志时间戳.
set -u
BP=/d/CSharpProject/BenchPlaybook
H=192.168.199.129
SSHOPT="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"
DIR="${1:-}"
if [ -z "$DIR" ]; then
  for d in $(ls -dt $BP/tasks/t*/raw 2>/dev/null); do
    if [ -f "$d/progress.log" ] && ! tail -1 "$d/progress.log" 2>/dev/null | grep -q "DONE"; then DIR="$d"; break; fi
  done
fi
[ -z "$DIR" ] && { echo "[监工] 无进行中的电池"; exit 0; }
echo "[监工] 目标: $DIR"
code=0
tail5=$(tail -5 "$DIR/progress.log" 2>/dev/null)
last_line=$(tail -1 "$DIR/progress.log" 2>/dev/null)
# 1) 显式 FAIL 标记
if echo "$tail5" | grep -qE "FAIL|未归零|超时"; then
  echo "[FAIL] progress.log 含失败标记:"; echo "$tail5" | tail -3; exit 4
fi
# 2) 服务存活(电池未完但 8000 无监听)
p=$(ssh -n $SSHOPT syspetro@$H "ss -ltn 2>/dev/null | grep -c ':8000 '" 2>/dev/null || echo 0)
if [ "${p:-0}" -lt 1 ]; then
  echo "[FAIL] 电池未完成但 8000 端口无监听(服务死了)"; exit 4
fi
# 3) 双采样活性(60s 间隔)
m1=$(curl -s -m 8 "http://$H:8000/metrics" 2>/dev/null | grep -E "^(vllm:num_requests_running|vllm:generation_tokens_total)" | awk '{print $2}' | tr '\n' ',')
sleep 60
m2=$(curl -s -m 8 "http://$H:8000/metrics" 2>/dev/null | grep -E "^(vllm:num_requests_running|vllm:generation_tokens_total)" | awk '{print $2}' | tr '\n' ',')
if [ "$m1" != "$m2" ]; then
  echo "[健康] 服务端活性正常(60s 指标有变化): $m1 -> $m2"
  echo "[健康] 当前阶段: $last_line"
  exit 0
fi
# 冻结: 判定是否在长思考套件容忍窗内(距最后阶段开始 <100min)
age_min=$(( ( $(date +%s) - $(stat -c %Y "$DIR/progress.log" 2>/dev/null || echo 0) ) / 60 ))
if [ "$age_min" -lt 100 ]; then
  echo "[WARN] 指标 60s 冻结但阶段开始仅 ${age_min} 分钟前(可能在长套件排队/思考) — 观察: $last_line"
  exit 3
fi
echo "[FAIL] 指标冻结且阶段开始已 ${age_min} 分钟 — 疑似卡死: $last_line"
exit 4
