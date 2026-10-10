#!/usr/bin/env bash
# make_cell.sh — cell 生成器: 绑定文件(bindings/*.env) + 模板(scripts/cell_template.sh) → cell脚本
# 用法: bash scripts/make_cell.sh bindings/<name>.env
# 门禁: ①必填键校验 ②生成物中残留@@TOKEN@@即失败(防半生成/漏绑定)
#       ③bash -n 语法校验  ④拒绝覆盖已存在目标(防意外重写历史cell)
# 纪律: cell 是生成物, 改参数=改绑定重新生成; 禁止手改生成物本身
set -u
# bash>=5.2 的 patsub_replacement 默认开: 替换串里的&会被展开成模式文本(sed语义),
# 块值含 &&/2>&1 必中招 → 本脚本要的是纯字面量替换, 显式关闭(2026-10-06 实测复现)
shopt -u patsub_replacement 2>/dev/null || true
BP=/d/CSharpProject/BenchPlaybook
TPL=$BP/scripts/cell_template.sh
BIND=$1
[ -f "$BIND" ] || { echo "绑定文件不存在: $BIND"; exit 1; }
[ -f "$TPL" ] || { echo "模板不存在: $TPL"; exit 1; }

# 绑定键白名单: 模板里的全部 @@TOKEN@@(单值键)
KEYS=(HEADER TASK_ID TAG LOAD_HINT MODEL_DIR DISTRIB_FLAG TP EP_FLAG MTP_FLAG KERNEL_FLAG \
      EXTRA_ARGS PARSER MODEL_NAME MEM_UTIL MAX_LEN MAX_SEQS BATCHED T1_TIMEOUT WLOADS \
      THINK_PROBE_DESC THINK_PROBE_BLOCK SOAK_DESC SOAK_BLOCK CAP_BLOCK AGENT_BLOCK)

# 绑定文件是 bash 可源文件; 多行块(THINK_PROBE_BLOCK/SOAK_BLOCK)用引号跨行写
# shellcheck disable=SC1090
source "$BIND"

MISS=0
for k in "${KEYS[@]}"; do
  v=${!k-}
  if [ -z "$v" ] && [ "$k" != "EXTRA_ARGS" ] && [ "$k" != "EP_FLAG" ] && \
     [ "$k" != "MTP_FLAG" ] && [ "$k" != "KERNEL_FLAG" ] && [ "$k" != "THINK_PROBE_BLOCK" ] && \
     [ "$k" != "SOAK_BLOCK" ] && [ "$k" != "CAP_BLOCK" ] && [ "$k" != "AGENT_BLOCK" ]; then
    echo "缺必填键: $k"; MISS=1
  fi
done
[ "$MISS" -ne 0 ] && exit 1
# TASK_ID/TAG 命名纪律: task=tYYYYMMDD-*, tag=[A-Za-z0-9-]+
[[ "$TASK_ID" =~ ^t[0-9]{8}-[a-z0-9-]+$ ]] || { echo "TASK_ID 不合规范(tYYYYMMDD-xxx): $TASK_ID"; exit 1; }
[[ "$TAG" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "TAG 含非法字符: $TAG"; exit 1; }

NAME=$(basename "$BIND" .env)
OUT=$BP/scripts/cell_${NAME}.sh
[ -f "$OUT" ] && { echo "目标已存在, 拒绝覆盖(重生成请先删): $OUT"; exit 1; }

# 替换循环: 纯bash字符串替换, 值含引号/JSON/换行均按字面量落入
while IFS= read -r line; do
  for k in "${KEYS[@]}"; do
    line=${line//@@${k}@@/${!k-}}
  done
  printf '%s\n' "$line"
done < "$TPL" > "$OUT"

# 门禁②: 残留token检测
if grep -n '@@[A-Z_]*@@' "$OUT" >/dev/null 2>&1; then
  echo "生成物残留未替换token:"; grep -n '@@[A-Z_]*@@' "$OUT"; rm -f "$OUT"; exit 1
fi
# 门禁③: 语法校验
bash -n "$OUT" || { echo "生成物语法错误, 已删除"; rm -f "$OUT"; exit 1; }

echo "生成: $OUT"
echo "  场景: $TAG  → tasks/$TASK_ID/raw/$TAG"
echo "  模型: $MODEL_NAME ($MODEL_DIR)  MTP: ${MTP_FLAG:-off}  EP: ${EP_FLAG:-off}"
echo "  上下文: $MAX_LEN × ${MAX_SEQS}路  batched: $BATCHED  mem-util: $MEM_UTIL"
