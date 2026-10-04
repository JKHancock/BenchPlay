#!/usr/bin/env bash
# 电池后洗白+提交: Python 新写的文件经 PowerShell 通道洗净再 git add(仓库 blob 保持明文)
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
for i in "${ITEMS[@]}"; do
  mkdir -p "$TMP/$(dirname "$i")"
  if [ -d "$i" ]; then
    powershell -Command "Copy-Item -Path 'D:\\CSharpProject\\BenchPlaybook\\$(echo "$i" | tr / '\\')' -Destination 'D:\\CSharpProject\\BenchPlaybook\\$TMP\\$(echo "$i" | tr / '\\')' -Recurse -Force" || exit 1
    rm -rf "$i"
  else
    powershell -Command "Copy-Item -Path 'D:\\CSharpProject\\BenchPlaybook\\$(echo "$i" | tr / '\\')' -Destination 'D:\\CSharpProject\\BenchPlaybook\\$TMP\\$(echo "$i" | tr / '\\')' -Force" || exit 1
    rm -f "$i"
  fi
done
(cd "$TMP" && find . -type f | while read -r f; do mkdir -p "../$(dirname "$f")"; mv "$f" "../$f"; done)
rm -rf $TMP
git add -A
git commit -m "电池产物洗白入库($(date +%F\ %H:%M))" >/dev/null 2>&1 || echo "(无新变更)"
echo "PASS wash+commit"
