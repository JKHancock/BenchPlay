# 操作员手册（RUNBOOK）

## 发起任务

对任意 agent 说（或写成 issue 交给它）：

```
读 SKILL.md 并执行：
机器 192.168.199.129|syspetro||GB10
     192.168.199.134|syspetro|<密码>|GB10
分发模型 Qwen3.6-35B-A3B-NVFP4-Fast
完成后出报告并做经验提炼。
```

- 已引导过的机器密码留空（密钥 `~/.ssh/benchplaybook_ed25519` 直连）。
- 新机器第一次必须给密码；引导成功后该机以后都免密。

## 把新模型放进分发中心

1. 源文件若来自下载目录（如 `D:\LocalAIResources`），**先洗白**（DLP 密文直传会乱码）：
   ```powershell
   powershell -File scripts/wash.ps1 -Source "D:\LocalAIResources\<模型>" -Target "D:\ModelHub\<模型>"
   ```
   脚本逐文件 PowerShell Copy-Item（唯一实测解密通道）并校验 config.json 可解析。
2. 确认可分发：看 `D:\ModelHub\<模型>\config.json` 用文本工具直读是明文 JSON。
3. 任务里引用目录名即可。

## 常见故障与人工介入

| 症状 | 原因 | 人的动作 |
|---|---|---|
| 导入后 config.json 仍乱码 | DLP 洗白通道失效（策略变更） | 找 IT 调白名单/换下载通道重取模型 |
| 传输中断 | 网络/超时 | 直接重发任务——增量续传，已传文件自动跳过 |
| 远端出现 `~` 字面量目录 | 某 agent 没遵守不变式 #6 | 删除 `~` 目录，检查该步是否先做了 `$HOME` 绝对化 |
| 报错 `/bin/bash: D:/...: No such file or directory` | 命令在 WSL2 bash 里跑（它不认 Windows 盘符路径） | 显式用 Git Bash 完整路径 + `/d/...` MSYS 路径重跑；顺手检查 cwd 有无 `D:` 垃圾目录 |
| `spawn mkdir ENOENT` 之类 | shell 内建命令当独立 exe 直接 spawn | 走 `bash.exe -c "mkdir -p ..."` |
| 引导失败 whoami 不符 | 密码错/用户名错 | 核对凭据；连续失败看目标机 sshd 日志 |
| 阶段反复失败 | 知识库无匹配签名 | 看档案 events 定位；解决后让 agent 提炼入经验库 |

## 服务依赖

- Qdrant 需在 `127.0.0.1:6333` 运行（`BenchPilot/tools/qdrant/qdrant.exe` 可启动）。
- embedding 用 fastembed（`Vllm_Benchmark/python/.venv` 已装，模型已缓存，离线可用）。
- 目标机可达（ssh 22）。

## 安全红线

- 密码只出现在发起任务那一次，之后任何输出/文件/日志不得含密码。
- 除 authorized_keys 一行与模型目录外，目标机不接受任何写操作（除非任务明确要求部署段）。
