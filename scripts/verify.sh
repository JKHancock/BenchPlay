#!/usr/bin/env bash
# URL 四关验证(从操作机直连, 与部署侧零耦合): 身份/功能/可观测/[智能体].
# 关4 由用途驱动: 用法 verify.sh <host> [expect_tools=0|1]
#   agent用途传 1 → 工具调用回环为 FAIL 级门禁; 默认 0 → 提示级
# (2026-09-30 事故新增关4: 智能体服务漏配 --enable-auto-tool-choice/--tool-call-parser,
#  对话三关全绿但 agent 客户端首 call 即 400 — 验收契约必须含目标用途的真实调用形态)
set -u
HOST="${1:?用法: verify.sh <host> [expect_tools]}"
EXPECT_TOOLS="${2:-0}"
BASE="http://$HOST:8000"
code=0

# 关1 身份: /v1/models 非空且取首个模型名(服务名不再硬编码 bench)
models=$(curl -s -m 10 "$BASE/v1/models")
mid=$(printf '%s' "$models" | grep -oE '"id":"[^"]+"' | head -1 | cut -d'"' -f4)
if [ -n "$mid" ]; then
  echo "  关1 身份: ✓ /v1/models 含 $mid"
else
  echo "FAIL 关1 身份: /v1/models 无模型 → $models"; code=1
fi

# 关2 功能: 对话冒烟(良构补全即通过; 推理型模型思考耗 token, 答案仅作信息展示)
resp=$(curl -s -m 120 -X POST "$BASE/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$mid\",\"messages\":[{\"role\":\"user\",\"content\":\"What is 1+1? Answer with the number only.\"}],\"max_tokens\":2000}")
if printf '%s' "$resp" | grep -q '"chatcmpl-' && printf '%s' "$resp" | grep -q '"finish_reason"'; then
  echo "  关2 功能: ✓ 对话冒烟通过"
else
  echo "FAIL 关2 功能: 冒烟异常 → $(printf '%s' "$resp" | head -c 300)"; code=1
fi

# 关3 可观测: /metrics 有 vllm: 指标族
n=$(curl -s -m 10 "$BASE/metrics" | grep -c '^vllm:')
if [ "${n:-0}" -ge 10 ]; then
  echo "  关3 可观测: ✓ /metrics 含 $n 个 vllm: 指标"
else
  echo "FAIL 关3 可观测: vllm: 指标仅 ${n:-0} 个"; code=1
fi

# 关4 智能体(用途驱动): 工具调用回环
tcode=$(curl -s -m 60 -o /tmp/verify_tool.json -w "%{http_code}" -X POST "$BASE/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$mid\",\"messages\":[{\"role\":\"user\",\"content\":\"weather in Beijing? use the tool\"}],\"tools\":[{\"type\":\"function\",\"function\":{\"name\":\"get_weather\",\"parameters\":{\"type\":\"object\",\"properties\":{\"city\":{\"type\":\"string\"}},\"required\":[\"city\"]}}}],\"tool_choice\":\"auto\",\"max_tokens\":1024,\"chat_template_kwargs\":{\"enable_thinking\":false}}")
if [ "$tcode" = "200" ] && grep -q '"tool_calls"' /tmp/verify_tool.json 2>/dev/null; then
  echo "  关4 智能体: ✓ 工具调用回环通(model=$mid)"
elif [ "$EXPECT_TOOLS" = "1" ]; then
  echo "FAIL 关4 智能体: agent用途但回环 http=$tcode (需 --enable-auto-tool-choice + --tool-call-parser)"; code=1
else
  echo "  关4 智能体: △ 未启用工具调用(用途=chat 可接受; agent 用途须传 expect_tools=1 并配parser)"
fi

[ $code -eq 0 ] && echo "PASS URL 四关全过: $BASE"
exit $code
