# process-governance 经验条目(自动拆分自gb10.md)

## 分发 allOk=true ≠ 权重落盘完整: 完成判定必须加远端 du/文件数对账, 16K 目录=骨架存根
- 阶段: 分发 | 现象: 双机分发 allOk=true, 但 du 复核 Qwen3.8-27B-NVFP4 在 129/134 均 16K,
  134 的 Qwen3.6-35B-A3B-NVFP4-Fast 仅 16K(同模型在 129 实测 20G)——16K 连一个权重分片都容不下, 判目录骨架/存根
- 结论/修复: 工具退出码只证明命令成功; 完成判定改为「allOk ∧ 远端 du -sh/文件数 ≥ 量级下限」双条件
  (35B 级 NVFP4 ≈ 20G 量级可作下限参照); 疑似存根目录先重跑分发, 勿直接起服;
  另 129 存在小写 qwen3.8-nvfp4 疑似重复目录(未测体积, 真权重错放假设未验证)
- 来源: t20261001-iter2 | 命中: 3 (129 Qwen3.8-27B + 134 Qwen3.8-27B + 134 Qwen3.6)

## 数据集陷阱: HF parquet 的 answer 字段形态不一, falsy-zero 会吞掉 answer=0
- 现象: mmlu(all 配置)的 answer 是 int 0-3 而非字母; `a or b or c` 链在 answer=0(选项A)时返回空串 → 23% 条目(3222/14042)被判无效 gold
- 修复: 显式 `is None` 判断 + 三形态兼容(字母/int下标/answerKey标签); arc 的 answerKey 是 "A"-"D" 或 "1"-"4" 混存
- 来源: t20260930-matrix-full | 命中: 1
