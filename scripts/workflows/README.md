# 编排工作流模板(随库资产)

ZCode 直接以 CreateWorkflow 的 `path` 提交本目录下的 .dwf.ts 即可运行;
Claude Code / Codex / OpenCode 按 docs/AGENT-BINDING.md §并行加速 第0条的
监工模式(独立监工 workflow + 子智能体周期跑 foreman.sh, 只诊断不动手)
用各自原语翻译等价拓扑——门禁语义不得弱化。

- 电池监工.dwf.ts: 长电池运行期 15min 周期巡检(foreman.sh 分级退出码),
  异常派子智能体诊断上报, 见 DONE 撤岗; 轮次上限 40。

- 全流程电池.dwf.ts (v3): **监工自动必带**——电池 world.run 与监工循环并发,
  电池结束监工自然收束; 含归因回跳(≤2轮)/汇编/渲染/入库/独立复核全链。
  用法: 复制→改 CONFIG 5 项→提交; 监工不再需要单独拉起。
