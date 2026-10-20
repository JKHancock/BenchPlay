#!/usr/bin/env bash
# gpt-oss-120b NVFP4 绑定【2026-10-20 放弃, verdict=deferred】
# 根因链: ①shanjiaz/gpt-oss-120b-nvfp4-modelopt 张量命名与 vllm0.30 GptOss NVFP4 加载器不兼容
#   (KeyError: layers.0.mlp.experts.w2_bias; worker秒崩, ray ActorHandleNotFound 只是次生症状);
# ②官方 openai/gpt-oss-120b(MXFP4) 大分片经 hf-mirror 强制 xet 通道且令牌401/普通通道超限, 下载不可达;
# ③新运维栈容器=服务本体(PID1), 流程的 pkill+exec 模式需先做容器形态适配(本轮已适配, DS 已按原样恢复).
# 重启条件: vLLM 升级修复 NVFP4 命名 / OpenAI 官方发布 NVFP4 版 / xet 镜像通道修复.
# 权重: shanjiaz/gpt-oss-120b-nvfp4-modelopt (ModelOpt NVFP4, compressed-tensors, W4A4 g16)
# 拓扑: 新 worker gx10-9c05=192.168.199.198(旧134退役); 容器已由运维栈改名回 vllm-node
# 口径: 原生128K上下文, max-num-seqs 8, 无MTP(gpt-oss无草稿头), served-name=bench(电池约定)
set -u
H=192.168.199.129; H2=192.168.199.198; U=syspetro
SSHOPT="-o BatchMode=yes -o StrictHostKeyChecking=no -o ConnectTimeout=10"

# 单机TP1: 不依赖双机集群(2026-10-20跨节点ray会话不稳止损)
for n in $H; do
  ssh -n $SSHOPT $U@$n "docker exec vllm-node bash -c \"pkill -f '[v]llm serve' 2>/dev/null; true\"" 2>/dev/null
done
sleep 8
ssh $SSHOPT $U@$H "docker exec -i vllm-node bash -s" <<'EOS'
export HF_ENDPOINT=https://hf-mirror.com RAY_memory_monitor_refresh_ms=0
export GLOO_SOCKET_IFNAME=enp1s0f1np1 NCCL_SOCKET_IFNAME=enp1s0f1np1
nohup vllm serve /root/.cache/huggingface/gpt-oss-120b-nvfp4 \
  --tensor-parallel-size 1 \
  --kernel-config '{"enable_flashinfer_autotune":false}' \
  --served-model-name bench --host 0.0.0.0 --port 8000 \
  --gpu-memory-utilization 0.85 --max-model-len 131072 \
  --max-num-seqs 8 --max-num-batched-tokens 8192 --enable-chunked-prefill --enable-prefix-caching \
  > /root/vllm.log 2>&1 &
echo LAUNCHED
EOS
echo "serve 已发起(gpt-oss-120b NVFP4, 128K×8), 就绪预计 ~6min; 日志: ssh $U@$H 'docker exec vllm-node tail -f /root/vllm.log'"
