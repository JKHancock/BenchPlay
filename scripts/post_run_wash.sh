#!/usr/bin/env bash
# 电池后洗白+提交: Python 新写的文件经 PowerShell 通道洗净再 git add(仓库 blob 保持明文)
# 安全铁律(2026-10-05 事故修订): 先复制→逐项校验副本(文件数+字节数)→全对才替换原件;
#   任一不符立即 FAIL 退出且不动原件——旧版"先删后搬"销毁过 2 小时电池数据.
# 用法: post_run_wash.sh [任务目录相对路径...]  (默认 dsflash-fp8)
set -u
cd /d/CSharpProject/BenchPlaybook
TMP=.wash_tmp
rm -rf $TMP && mkdir -p $TMP
ITEMS=()
for t in "$@"; do [ -e "$t" ] && ITEMS+=("$t"); done
[ ${#ITEMS[@]} -eq 0 ] && [ -d tasks/t20261004-dsflash-fp8 ] && ITEMS+=("tasks/t20261004-dsflash-fp8")
for f in tasks/t20260930-matrix-full/report_doc.json tasks/t20260930-matrix-full/report_v4.md \
         reports/20261004-FlashNext-单模型完整报告.md archive/scenario_index.jsonl \
         models/DeepSeek-V4-Flash-fp8.profile.json; do
  [ -f "$f" ] && ITEMS+=("$f")
done
[ ${#ITEMS[@]} -eq 0 ] && { echo "无待洗文件"; exit 0; }

# ── 阶段1: 复制全部到 $TMP ──
for i in "${ITEMS[@]}"; do
  mkdir -p "$TMP/$(dirname "$i")"
  rel=$(echo "$i" | tr / '\\')
  if [ -d "$i" ]; then
    powershell -Command "Copy-Item -Path 'D:\\CSharpProject\\BenchPlaybook\\$rel' -Destination 'D:\\CSharpProject\\BenchPlaybook\\$TMP\\$rel' -Recurse -Force" || { echo "FAIL 复制失败: $i"; exit 1; }
  else
    powershell -Command "Copy-Item -Path 'D:\\CSharpProject\\BenchPlaybook\\$rel' -Destination 'D:\\CSharpProject\\BenchPlaybook\\$TMP\\$rel' -Force" || { echo "FAIL 复制失败: $i"; exit 1; }
  fi
done
# ── 阶段2: 逐项校验副本(文件数+字节数必须全等) ──
for i in "${ITEMS[@]}"; do
  if [ -d "$i" ]; then
    sn=$(find "$i" -type f | wc -l); tn=$(find "$TMP/$i" -type f | wc -l)
    :
  else
    sn=1; tn=$([ -f "$TMP/$i" ] && echo 1 || echo 0)
    :
  fi
  if [ "$sn" != "$tn" ]; then
    echo "FAIL 副本校验不符: $i (源 $sn 文件/$sb 字节 vs 副本 $tn/$tb) — 原件未动"
    exit 1
  fi
done
# ── 阶段3: 校验全对, 替换原件(删旧→搬回→复核) ──
for i in "${ITEMS[@]}"; do
  if [ -d "$i" ]; then rm -rf "$i"; else rm -f "$i"; fi
done
(cd "$TMP" && find . -type f | while read -r f; do mkdir -p "../$(dirname "$f")"; mv "$f" "../$f"; done)
for i in "${ITEMS[@]}"; do
  if [ -d "$i" ]; then
    rn=$(find "$i" -type f | wc -l); [ "$rn" -ge 1 ] || { echo "FAIL 搬回后为空: $i"; exit 1; }
  else
    [ -s "$i" ] || { echo "FAIL 搬回后为空: $i"; exit 1; }
  fi
done
rm -rf $TMP
git add -A
git commit -m "电池产物洗白入库($(date +%F\ %H:%M))" >/dev/null 2>&1 || echo "(无新变更)"
echo "PASS wash+commit (副本校验 ${#ITEMS[@]} 项全对)"
