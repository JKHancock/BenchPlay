#!/usr/bin/env bash
# 演示服务(27B密集版): TP2+MTP2投机+YaRN4x+1M+工具调用(qwen3_xml)+8路硬顶.
# 与3.6版差异: 无EP(密集) 无kernel-config(无MoE自调优问题) 仍带MTP权重(实测15个).
set -u
BP=/d/CSharpProject/BenchPlaybook
H=192.168.199.129; H2=192.168.199.134; U=syspetro
SSHOPT="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"

for n in $H $H2; do
  ssh -n $SSHOPT $U@$n "docker exec vllm-node bash -c \"pkill -f '[v]llm serve' 2>/dev/null; pkill -f '[R]ayWorkerProc' 2>/dev/null; pkill -f '[E]ngineCore' 2>/dev/null; true\"" 2>/dev/null
done
g=99
for i in $(seq 1 36); do
  g=0
  for n in $H $H2; do
    c=$(ssh -n $SSHOPT $U@$n "nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null" | grep -c .)
    g=$((g + ${c:-0}))
  done
  [ "$g" -eq 0 ] && break; sleep 5
done
[ "$g" -ne 0 ] && { echo "FAIL GPU未归零($g)"; exit 1; }
echo "  双节点清场完成"
bash $BP/scripts/cluster.sh $H $H2 $U > /tmp/demo_cluster.log 2>&1 || { echo "FAIL ray"; exit 1; }
echo "  ray 双机就绪"

ssh $SSHOPT $U@$H "docker exec -i -e MODEL=Qwen3.8-27B-NVFP4 -e TP=2 vllm-node bash -s" > /tmp/demo_serve27b.log 2>&1 <<'EOS' || { echo "FAIL serve发起"; exit 1; }
export CUTE_DSL_ARCH=sm_121a HF_ENDPOINT=https://hf-mirror.com RAY_memory_monitor_refresh_ms=0
export GLOO_SOCKET_IFNAME=enp1s0f1np1 NCCL_SOCKET_IFNAME=enp1s0f1np1
nohup vllm serve /root/.cache/huggingface/$MODEL \
  --tensor-parallel-size $TP --distributed-executor-backend ray \
  --speculative-config '{"method":"qwen3_5_mtp","num_speculative_tokens":2}' \
  --hf-overrides '{"text_config":{"max_position_embeddings":1048576,"rope_scaling":{"rope_type":"yarn","factor":4.0,"original_max_position_embeddings":262144}}}' \
  --enable-auto-tool-choice --tool-call-parser qwen3_xml --reasoning-parser qwen3 \
  --served-model-name qwen3.8-27b --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 --max-model-len 1048576 \
  --max-num-seqs 8 --max-num-batched-tokens 8192 --enable-chunked-prefill --enable-prefix-caching \
  > /root/vllm.log 2>&1 &
echo LAUNCHED
EOS
echo "  serve已发起(27B·TP2+MTP2+1M+工具), 等就绪..."
ready=0
for i in $(seq 1 60); do
  sleep 10
  r=$(ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -c 'Application startup complete' /root/vllm.log" 2>/dev/null)
  p=$(ssh -n $SSHOPT $U@$H "ss -ltn 2>/dev/null | grep -c ':8000 '" 2>/dev/null)
  if [ "${r:-0}" -ge 1 ] && [ "${p:-0}" -ge 1 ]; then
    echo "PASS 就绪(约$((i*10))s)"
    ssh -n $SSHOPT $U@$H "docker exec vllm-node grep -E 'GPU KV cache size|Maximum concurrency' /root/vllm.log" 2>/dev/null
    ready=1; break
  fi
  if ! ssh -n $SSHOPT $U@$H "docker exec vllm-node bash -c \"pgrep -f '[v]llm serve' >/dev/null\"" 2>/dev/null; then
    echo "FAIL serve进程退出, 尾部:"; ssh -n $SSHOPT $U@$H "docker exec vllm-node tail -20 /root/vllm.log" 2>/dev/null; exit 1
  fi
done
[ "$ready" -ne 1 ] && { echo "FAIL 就绪超时"; exit 1; }
echo "PASS 27B演示服务就绪: http://$H:8000/v1 model=qwen3.8-27b 无鉴权"
