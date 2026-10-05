#!/usr/bin/env bash
# DeepSeek-V4-Flash NVFP4 演示服务(产品口径: 500K x 3 路 SLA; 保持原生 1M len 不降——降 500K 反使 KV 池缩水 35%[1.39M→0.91M],
# 注: 容器内 vllm/parser/deepseek_v4.py 已patch默认关思考(2026-10-05); 容器重建后需重打(.bak在原目录)
# 依据 t20261005-dsnvfp4-1m-ep2 实测: EP2 聚合+6~9%, soak 3x52万零抢占;
#   MTP 必须用 dspark(NVFP4 打包为 DSpark 草稿拓扑, deepseek_mtp 会 KeyError 崩溃);
#   3 路准入由 --max-num-seqs 3 控制; 容量依据 soak 实测 3×52万零抢占)
set -u
H=192.168.199.129; H2=192.168.199.134; U=syspetro
SSHOPT="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"

bash /d/CSharpProject/BenchPlaybook/scripts/cluster.sh $H $H2 $U || exit 1
for n in $H $H2; do
  ssh -n $SSHOPT $U@$n "docker exec vllm-node bash -c \"pkill -f '[v]llm serve' 2>/dev/null; true\"" 2>/dev/null
done
sleep 8
ssh $SSHOPT $U@$H "docker exec -i vllm-node bash -s" <<'EOS'
export CUTE_DSL_ARCH=sm_121a HF_ENDPOINT=https://hf-mirror.com RAY_memory_monitor_refresh_ms=0
export GLOO_SOCKET_IFNAME=enp1s0f1np1 NCCL_SOCKET_IFNAME=enp1s0f1np1
nohup vllm serve /root/.cache/huggingface/DeepSeek-V4-Flash-NVFP4 \
  --tensor-parallel-size 2 --distributed-executor-backend ray --enable-expert-parallel \
  --speculative-config '{"method":"dspark","num_speculative_tokens":2}' \
  --kernel-config '{"enable_flashinfer_autotune":false}' \
  --enable-auto-tool-choice --tool-call-parser deepseek_v4 \
  --served-model-name ds-nvfp4 --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 --max-model-len 1048576 \
  --max-num-seqs 3 --max-num-batched-tokens 8192 --enable-chunked-prefill --enable-prefix-caching \
  > /root/vllm.log 2>&1 &
echo LAUNCHED
EOS
echo "serve 已发起(500K×3 口径), 就绪预计 ~8min; 日志: ssh $U@$H 'docker exec vllm-node tail -f /root/vllm.log'"
