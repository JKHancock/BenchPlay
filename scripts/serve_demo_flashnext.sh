#!/usr/bin/env bash
# Flash-Next 演示服务(产品口径: 500K x 3 路 SLA)
# 依据 t20260930-flashnext-c12 实测: KV池1,919,532 tok, 3x500K=1.57M 留8%余量;
#   4x500K=2.10M 超池8.5% 不可承诺. 单流46 tok/s, c8 goodput 95.8%.
# 与基准配置的差异: 仅 max-model-len 1M->500K(YaRN因子同步降为2.0), 其余全同 cell7.
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
  --tensor-parallel-size 2 --distributed-executor-backend ray \
  --speculative-config '{"method":"qwen4_exp_mtp","num_speculative_tokens":2}' \
  --hf-overrides '{"text_config":{"max_position_embeddings":524288,"rope_scaling":{"rope_type":"yarn","factor":2.0,"original_max_position_embeddings":262144}}}' \
  --kernel-config '{"enable_flashinfer_autotune":false}' \
  --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3 \
  --served-model-name flash-next --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 --max-model-len 524288 \
  --max-num-seqs 8 --max-num-batched-tokens 8192 --enable-chunked-prefill --enable-prefix-caching \
  > /root/vllm.log 2>&1 &
echo LAUNCHED
EOS
echo "serve 已发起, 就绪预计 ~7min(150s加载+图捕获), 日志: ssh $U@$H 'docker exec vllm-node tail -f /root/vllm.log'"
