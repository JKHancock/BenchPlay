# GB10 压力测试工具集

目标机: `syspetro@192.168.199.129`（经 newapi 网关 `127.0.0.1:3000/v1` 施压,令牌在 `~/gb10/secrets/newapi-token.txt`）。
所有脚本纯 python3 标准库,scp 到目标机直接跑,无需安装依赖。

| 脚本 | 用途 | 关键实测结论(2026-10-09/10, qwen3.6-35b-a3b / qwen3.8-27b) |
|---|---|---|
| `loadtest.py` | 阶梯并发压测(1→4→8→16→32, 每档45s),测吞吐/延迟分位 | 27B稠密: 单流~18tok/s,聚合天花板130tok/s(LPDDR5x带宽约束),16并发是甜点位;超并发只涨延迟 |
| `scen1.py` | 16路同时冷启满上下文(每路~21K token唯一prompt),测TTFT楼梯/聚合prefill | TTFT呈9.1s/级的完美楼梯(chunked prefill预算串行),聚合prefill~2,318tok/s;先完成预填的路在其余路预填期间解码被压到1.5tok/s |
| `scen2.py` | 稳态解码+注入1路大prefill,量化"prefill压decode"凹坑 | 4路稳态42tok/s→注入期间15tok/s(↓64%)→prefill结束瞬时恢复;chunked prefill不会杀死decode但挤压约2/3 |
| `probe.py` | 同scen2的轻量探针(带标签参数),用于参数扫频 | max_num_batched_tokens扫频:4096/8192(默认)/16384/32768 → 默认8192双指标最优,16384反而恶化40%,32768起不来;GB10上不要动此参数 |
| `overnight.py` | 通宵harness(计划HOURS小时):循环混合负载(稳态长解码/冷预填/工具调用/12路短并发/断流演练) | 11h无人值守:91周期4962请求0失败,738万tokens,抢占0,GPU峰值75°C/67.8W,MTP长跑接受率78.3% |
| `overnight_watchdog.sh` | harness看门狗(进程死拉起/日志15min不涨判僵死重启/5min心跳) | 两个血的教训:①pgrep -f自匹配会让守护永不启动——必须用pidfile+kill -0;②看门狗不认识"任务完成"会把按计划退出的harness复活——需停止契约 |

## 用法速查

```bash
scp stress/*.py syspetro@192.168.199.129:/tmp/
ssh syspetro@192.168.199.129
python3 /tmp/loadtest.py        # 阶梯并发
python3 /tmp/scen1.py           # 16路冷启满上下文
python3 /tmp/probe.py 标签名     # prefill-vs-decode探针(扫频时改vllm.exp.yml重建)
nohup python3 ~/gb10/overnight.py >/dev/null 2>&1 &   # 通宵(改脚本内HOURS)
```

## 注意

- 压测前确认 vllm 在跑: `curl -s http://127.0.0.1:8000/v1/models`
- 修改并发路数 = 改脚本顶部常量;模型名同理(当前 qwen3.6-35b-a3b)
- 探针类脚本若配合 `max_num_batched_tokens` 扫频: 改 `~/gb10/vllm.exp.yml` 后 `docker compose -f vllm.exp.yml up -d`(compose的command是参数列表,一行一个参数,别塞同一项)
- 对账口径: harness账(Python累计) / Prometheus(11h窗口increase) / newapi账本(logs表) 三方应一致,差<1%
