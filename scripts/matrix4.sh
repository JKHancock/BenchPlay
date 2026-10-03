#!/usr/bin/env bash
# v4 全矩阵: 4场景全电池(cell4), 执行顺序按现场状态优化.
# TP2-Qwen3.6 沿用关自调优口径(已验证: 跨会话自调优确定性死亡).
set -u
BP=/d/CSharpProject/BenchPlaybook
NOK='--kernel-config {"enable_flashinfer_autotune":false}'

bash $BP/scripts/cell4.sh 2 Qwen3.8-27B-NVFP4 15.5 TP2-Qwen3.8 ""
bash $BP/scripts/cell4.sh 2 Qwen3.6-35B-A3B-NVFP4-Fast 1.7 TP2-Qwen3.6 "$NOK"
bash $BP/scripts/cell4.sh 1 Qwen3.6-35B-A3B-NVFP4-Fast 1.7 TP1-Qwen3.6 ""
bash $BP/scripts/cell4.sh 1 Qwen3.8-27B-NVFP4 15.5 TP1-Qwen3.8 ""
echo "[$(date +%H:%M:%S)] ALL-DONE-V4" | tee -a $BP/tasks/t20260930-matrix-full/raw4/progress.log
