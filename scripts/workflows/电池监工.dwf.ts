// 电池监工工作流: 子智能体周期巡检正在运行的电池, 直到完成/异常上报.
// 与电池工作流(dwfrun-646b2035)并发运行, 独立互不干预; 电池自身的归因回跳归电池工作流.
const BASH = "C:/Program Files/Git/bin/bash.exe";

interface Diagnosis {
  /** 异常定位: 服务死亡/电池失败标记/疑似卡死/误报 */
  stage: string;
  /** 一句话根因(带证据行) */
  root_cause: string;
  /** true=需要人决策 */
  needs_user: boolean;
}
interface WatchReport {
  conclusion: string;
  findings: { where: string; what: string; evidence: string; severity: "low" | "medium" | "high" }[];
  verified: string[];
  notCovered: string[];
}

phase("周期巡检电池（每15分钟）");
const foreman = agent("电池监工", {
  system:
    "你看护 GPU 集群上正在运行的基准测试电池(当前: DeepSeek FP8, 由另一个动态工作流管理)." +
    "判定一律以 foreman.sh 的退出码与输出为准; 你只诊断和上报, 严禁修改集群状态/重启服务/杀进程——" +
    "电池工作流有自己的归因回跳, 重复干预会造成双控制器打架." +
    "读证据定位: progress.log / 场景目录下各 *.log / ssh -o BatchMode=yes syspetro@192.168.199.129 \"docker exec vllm-node tail -30 /root/vllm.log\"." +
    "判不了就明说判不了, 不要猜.",
});

let cycles = 0;
let healthyCycles = 0;
const findings: WatchReport["findings"] = [];
let concluded = "监工轮次耗尽前电池未结束";

for (let cycle = 1; cycle <= 40; cycle++) {
  const chk = await world.run("C:/Program Files/Git/bin/bash.exe", ["-c", "bash /d/CSharpProject/BenchPlaybook/scripts/foreman.sh"], { timeoutMs: 300000 });
  cycles = cycle;
  const batteryGone = chk.stdout.includes("无进行中的电池");
  if (batteryGone) {
    concluded = "电池已完成(监工检测到无进行中电池), 撤岗";
    break;
  }
  if (chk.exitCode === 4) {
    const diag = await foreman.ask<Diagnosis>(
      "巡检异常(FOREMAN exit 4):\n" + chk.stdout + "\n按证据归因(只诊断不动手), 返回 stage/root_cause/needs_user。",
    );
    findings.push({
      where: "tasks/t20261004-dsflash-fp8/raw",
      what: "第" + cycle + "轮巡检异常: " + diag.stage + " — " + diag.root_cause,
      evidence: chk.stdout.split("\n").slice(0, 4).join(" | "),
      severity: diag.needs_user ? "high" : "medium",
    });
    report({ cycle: cycle, 状态: "异常", 结论: diag.root_cause, 需人工: diag.needs_user });
    if (diag.needs_user) { concluded = "发现需人工决策的异常, 监工提前撤岗上报"; break; }
  } else if (chk.exitCode === 3) {
    report({ cycle: cycle, 状态: "观察", 详情: (chk.stdout.split("\n")[1] ?? "").slice(0, 80) });
  } else {
    healthyCycles += 1;
    log("[监工] 第" + cycle + "轮健康: " + ((chk.stdout.split("\n")[2] ?? chk.stdout.split("\n")[0] ?? "").slice(0, 60)));
  }
  await world.run("C:/Program Files/Git/bin/bash.exe", ["-c", "sleep 900"], { timeoutMs: 960000 });
}

return {
  conclusion: concluded + "; 巡检 " + cycles + " 轮(健康 " + healthyCycles + " 轮), 异常 " + findings.length + " 条",
  findings: findings,
  verified: ["每轮判定均来自 foreman.sh 真实退出码与双采样指标"],
  notCovered: ["电池内部各测试的质量判定归电池工作流, 监工只看活性与失败标记"],
} satisfies WatchReport;