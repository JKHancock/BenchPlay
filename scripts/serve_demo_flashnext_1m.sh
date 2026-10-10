#!/usr/bin/env bash
# Flash-Next 演示服务(1M x 3 路 + EP2): 与 t20261005-flashnext-1m-ep2 档案配置一致; 在 500K 口径上改四处——
#   max-model-len 524288->1048576, YaRN factor 2.0->4.0(原生262144x4=1M), max-num-seqs 8->3
# 注意: KV池随 max-model-len 的画像行为待实测(见DS的1.39M/0.91M前车之鉴), 启动后从日志读真实池大小
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
nohup vllm serve /root/.cache/huggingface/Qwen3.8-Flash-Next-NVFP4 \
  --tensor-parallel-size 2 --distributed-executor-backend ray --enable-expert-parallel \
  --speculative-config '{"method":"qwen4_exp_mtp","num_speculative_tokens":2}' \
  --hf-overrides '{"text_config":{"max_position_embeddings":1048576,"rope_scaling":{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":262144}}}' \
  --kernel-config '{"enable_flashinfer_autotune":false}' \
  --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3 \
  --served-model-name flash-next --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 --max-model-len 1048576 \
  --max-num-seqs 3 --max-num-batched-tokens 8192 --enable-chunked-prefill --enable-prefix-caching \
  > /root/vllm.log 2>&1 &
echo LAUNCHED
EOS
echo "serve 已发起(1M×3 口径), 就绪预计 ~7min; 日志: ssh $U@$H 'docker exec vllm-node tail -f /root/vllm.log'"
