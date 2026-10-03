# os-network 经验条目(自动拆分自gb10.md)

## workflow/自动化执行环境里裸 "bash" 解析到 WSL2 → Windows 路径全不认
- 阶段: 清点(探测) | 现象: 双机(129/134)同一报错 `/bin/bash: D:/CSharpProject/BenchPlaybook/scripts/probe.sh: No such file or directory`
- 真因(实测): ZCode 动态 workflow 的 `world.run("bash",...)` 解析到 **WSL2 bash**
  (`uname -a` = microsoft-standard-WSL2)——它不认 `D:/...` 与 `/d/...`，且其 `$HOME`
  (/home/...) 没有 SSH 密钥。初版误诊为"脚本被投递到远端执行"，实测纠正为本地 WSL。
- 修复: `world.run` 的 bash 一律用 **Git Bash 完整路径字面量**
  `C:/Program Files/Git/bin/bash.exe` + **MSYS 风格路径** `/d/CSharpProject/...`；
  shell 内建命令(mkdir 等)走 `bash.exe -c`（Windows 无独立 mkdir.exe，直接 spawn 报 ENOENT）。
- 副作用: WSL 下 `mkdir 'D:/...'` 会在 cwd 造出字面量 `D:` 垃圾目录，需清理。
- 来源: t20261001-iter1 | 命中: 2（初版误诊 + 实测纠正）

## 运行结果的 verified/notCovered 必须从证据推导
- 阶段: 报告 | 现象: 迭代1首版脚本把 `verified` 写成硬编码("退出码均为 0")，与真实失败矛盾
- 结论: 编排者(主 agent)同样受不变式#4约束——verified 只能来自真实退出码/落盘证据，
  汇报字段应从结果对象推导(如成功数统计)，不许手写结论性字符串。
- 来源: t20261001-iter1 | 命中: 1

## GB10 管理 IP 走 WiFi DHCP(不保证稳定, 属风险推断非实测)——跨任务识别钉 hostname/MAC/NVMe 序列号
- 阶段: 清点(探测) | 现象: 双机管理 IP 均来自 WiFi wlP9s9 的 DHCP 动态租约(129 剩约 75994s, 134 租期 74445s), 租约更替 IP 即漂
- 结论/修复: 档案已录稳定指纹——hostname(gx10-9f5c/gx10-9c05)、MAC 族(30:c5:99:3d:9f:5c..62 / 30:c5:99:3d:9c:05..0b)、NVMe 序列号(511250619080002301/…2242); 后续任务按指纹识别机器, 不按 IP; 要稳定管理入口可做 DHCP 预约
- 来源: t20261001-iter1 | 命中: 2 (双机)

## ssh 吃掉 while-read 循环 stdin 造成假阳性: 循环内调 ssh 必加 -n; 复核必须固化成门禁, 只记证据防不住下一次
- 阶段: 分发 | 现象: distribute.sh 旧版在 while read 循环体内裸调 ssh, ssh 默认消费 stdin 把循环待读的文件列表吃光——循环静默提前结束, 退出码 0 照样 echo PASS, 远端仅落 16K 目录壳(allOk=true 假阳性, 迭代2 双机中招)
- 结论/修复: ① 循环体内每条 ssh 加 `-n`(不读 stdin), 文件列表用 `done < <(find ...)` 进程替换供给(distribute.sh:15,26,49); ② 更普适: 工具回传 PASS 只是证据, 复核(逐文件 sha256/文件数/du -sb 体积)必须做成脚本退出码门禁——FAIL exit 1 才能在当次拦截假阳性, "报告里记疑点"只能事后补救; 迭代2 的 du 对账因只是任务级证据, 16K 存根靠人读报告才发现, iter2b 重跑(修复 -n + 三重门禁)4/4 PASS 并经报告员 SSH 独立复核字节级一致
- 来源: t20261001-iter2 → t20261001-iter2b | 命中: 2 (iter2 双机假阳性, iter2b 修复验证)

## 双机 SSH 密钥面不对称(129 认引导密钥, 134 只认 nvsync.key); KEYFLAG 未加引号遇含空格路径即断
- 阶段: 连接(全阶段前置) | 现象: 报告员复检 129 用 ~/.ssh/benchpilot_ed25519 成功, 同法 134 报 `Permission denied (publickey,password)`;
  134 只接受 NVIDIA Sync config(~/.ssh/config Include)所载 nvsync.key, 其路径含空格; clean.sh/preflight.sh 的 `KEYFLAG="-i $KEY"` 未加引号,
  传含空格路径按词断裂(`Identity file … not accessible` + hostname 解析错误)
- 结论/修复: ① 每台机器先 BatchMode 试钥匙再跑批量任务, 单机成功不外推到另一台; ② 134 补装 benchpilot 公钥统一密钥面;
  ③ 脚本 KEYFLAG 改加引号或数组传参
- 来源: t20261001-iter3 | 命中: 2 (134 拒引导密钥 + 空格路径断裂)

## 探测脚本"空输出"语义 = 无发现而非失败: 判定与退出码语义必须分离(grep 无匹配 exit 1 曾误判 DIRTY)
- 阶段: 预检/工具设计 | 现象: 3b 双机 port8000 [DIRTY](0 项)——section() 把退出码非 0 也判脏, grep 无匹配 exit 1,
  实质无监听; 探测器把"没有发现"报成"发现异常"是最危险的误报方向(每次都要人工直连复核)
- 修复: preflight.sh:15-16 改为空输出即 CLEAN(退出码仅用于区分"命令失败"与"真无输出"); 3c 终验 port8000 双机
  CLEAN(0 项), 同一检测对象标签由 DIRTY 翻 CLEAN=修复生效的直接证据
- 普适: 只读探测器的输出语义按"空=无发现"设计; 读结果时 [DIRTY](0 项)应先怀疑误报再下结论(与上方 iter3 条目互证,
  本条为修复落盘+终验闭环记录)
- 来源: t20261001-iter3 → t20261001-iter3b → t20261001-iter3c | 命中: 3 (iter3/3b 双机误报 + 3c 修复终验)

## 快速档只跑 Track1 的取舍: 配置 track2.enabled=true 时 CLI 默认 --track both 仍会起 lm_eval, 封装不传开关则"失败"≠"跳过"
- 阶段: 基准(分档) | 现象: 快速档(并发1×8)定位是验握手与量级, 但 gx10-dual.yaml `track2.enabled: true` 且
  bench.sh 未传 `--track`(bench.sh:13-14, CLI 默认 both, RunCommand.cs:68-70)→ 快速档也起 lm_eval,
  首跑即撞 6 数据集(MMLU-Pro/humaneval 等)重下载, 必产 no-score 告警(DD §9 记 failed)且拖长尾部
- 结论/修复: ① 分档=快速档显式 `--track perf`, Track2 留完整档(数据集全量落 HF cache 后再跑, 配合上条
  HF_ENDPOINT); ② 语义纪律: 封装脚本不传开关时, Track2 是「试了但失败」而非「跳过」——告警行如实入档,
  勿把告警吞成绿; bench.sh 的 Track1 门禁只读 phases(bench.sh:22-35)所以 Track2 失败不拦 PASS, 属预期,
  但读结果时要分清两通道各自的判定
- 来源: t20261001-iter5 | 命中: 1 (bench.sh 快速档首跑)

## 管理面 WiFi 瞬断会废掉整个性能档 — 档内失败条目自动补跑
- 阶段: 测试 | 现象: TP1-27B c1 档 8 条中 7 条 ConnectionError(Max retries exceeded), 同一脚本几分钟后 c8/c32 全过——管理面(192.168.199.x/OTA WiFi)瞬断, 与服务端无关
- 修复: bench/track1 档内失败条目补跑(最多2轮, 只补失败条目, 好样本不受污染), phase 记 retried 数; 客户端重试 3 次指数退避
- 教训: 基准客户端的重试语义要区分"网络失败"(可补跑)与"模型输出异常"(不可重试否则污染)
- 来源: t20260930-matrix-full | 命中: 1
