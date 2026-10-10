#!/bin/bash
# 通宵看门狗 — harness死了拉起/僵死(日志15分钟不涨)重启/每5分钟探活留痕
LOGDIR=$HOME/gb10/overnight
WLOG=$LOGDIR/watchdog.log
mkdir -p "$LOGDIR"
while true; do
  TS=$(date "+%m-%d %H:%M:%S")
  if ! pgrep -f "[o]vernight.py" >/dev/null; then
    echo "$TS [重启] harness不在,拉起" >> "$WLOG"
    nohup python3 $HOME/gb10/overnight.py >/dev/null 2>&1 &
  else
    NEWEST=$(ls -t $LOGDIR/results-*.log 2>/dev/null | head -1)
    if [ -n "$NEWEST" ] && [ $(( $(date +%s) - $(stat -c %Y "$NEWEST") )) -gt 900 ]; then
      echo "$TS [僵死] 日志15分钟未更新,杀掉重启" >> "$WLOG"
      pkill -f "[o]vernight.py"; sleep 3
      nohup python3 $HOME/gb10/overnight.py >/dev/null 2>&1 &
    fi
  fi
  GW=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:3000/api/status || echo ERR)
  VM=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8000/v1/models || echo ERR)
  echo "$TS 探活 harness=OK 网关=$GW vllm=$VM" >> "$WLOG"
  sleep 300
done
