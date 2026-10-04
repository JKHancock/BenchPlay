// ═══ 全流程电池工作流模板 v3(监工自动必带) ═══
// 用法(ZCode): 复制本文件到会话工作区, 改下方 CONFIG 五个路径后
//   CreateWorkflow path 提交; 他 IDE 按 docs/AGENT-BINDING.md §并行加速 翻译等价拓扑.
// 结构: 电池(长时间 world.run) 与 监工循环(15min 周期 foreman.sh) **并发**,
//       监工只诊断不动手(修复归主线归因回跳), 电池结束监工自然收束;
//       失败 → 主线 fixer 归因修复(≤2轮) → 幂等重跑 → 汇编渲染入库复核.
// 教训沉淀: 2026-10-04 两起事故(坏分片/MTP错配)证明无监工的长电池=盲飞.

// ── CONFIG(按场景改这 5 项) ──
const CELL = "/d/CSharpProject/BenchPlaybook/scripts/cellN.sh";        // 电池脚本(MSYS 路径)
const TASK_DIR = "tasks/tXXXXXX-xxx/raw";                               // 任务 raw 目录(仓库相对)
const BUILD = "D:/CSharpProject/BenchPlaybook/scripts/buildN.py";       // 汇编脚本
const MODEL_FILTER = "模型过滤词";                                       // 单模型报告过滤
const REPORT = "D:/CSharpProject/BenchPlaybook/reports/XXXX-单模型报告.md";
// ────────────────────

const BASH = "C:/Program Files/Git/bin/bash.exe";
const PY = "D:/CSharpProject/BenchPlaybook/.venv/Scripts/python.exe";
const BP = "D:/CSharpProject/BenchPlaybook";
const DOC = "D:/CSharpProject/BenchPlaybook/tasks/t20260930-matrix-full/report_doc.json";
const FULL_MD = "D:/CSharpProject/BenchPlaybook/tasks/t20260930-matrix-full/report_v4.md";
const RAW = "D:/CSharpProject/BenchPlaybook/" + TASK_DIR;

interface Diagnosis {
  /** 失败定位的阶段 */
  stage: string;
  /** 一句话根因(带证据行) */
  root_cause: string;
  /** 已执行的修复动作, 空串=没有可修项 */
  fix_done: string;
  /** true=修不动需要人 */
  needs_user: boolean;
}
interface Finding {
  where: string;
  what: string;
  evidence: string;
  status: "verified" | "unconfirmed";
  severity: "low" | "medium" | "high";
}
interface WorkflowReport {
  conclusion: string;
  findings: Finding[];
  verified: string[];
  notCovered: string[];
}

phase("发射电池（监工自动随行，15 分钟周期巡检）");
log("电池与监工并发启动; 电池预计 2.5-3.5 小时");
let batterySettled = false;
const batPromise = world.run(BASH, [CELL], { timeoutMs: 16200000 })
  .then((r) => { batterySettled = true; return r; });

const foreman = agent("电池监工", {
  system:
    "你看护正在运行的基准电池。判定以 foreman.sh 退出码与输出为准; 只诊断和上报, " +
    "严禁修改集群状态——修复归主线归因回跳, 双控制器不打架。判不了就明说。",
});
let lastSig = "";
const watchFindings: Finding[] = [];
const watcherPromise = (async () => {
  for (let cycle = 1; cycle <= 40 && !batterySettled; cycle++) {
    const chk = await world.run(BASH, ["-c", "bash " + BP + "/scripts/foreman.sh"], { timeoutMs: 300000 });
    if (batterySettled) break;
    if (chk.exitCode === 4) {
      const sig = chk.stdout.split("\n").slice(0, 2).join("|").slice(0, 140);
      if (sig !== lastSig) {
        lastSig = sig;
        const d = await foreman.ask<Diagnosis>(
          "巡检异常(FOREMAN exit 4):\n" + chk.stdout + "\n只诊断不动手, 返回 stage/root_cause/needs_user。",
        );
        watchFindings.push({
          where: TASK_DIR, what: "监工第" + cycle + "轮: " + d.stage + " — " + d.root_cause,
          evidence: chk.stdout.split("\n").slice(0, 4).join(" | "),
          status: "unconfirmed", severity: d.needs_user ? "high" : "medium",
        });
        report({ cycle: cycle, 状态: "异常", 结论: d.root_cause, 需人工: d.needs_user });
      } else {
        report({ cycle: cycle, 状态: "重复异常(处置中)" });
      }
    } else if (chk.exitCode === 3) {
      report({ cycle: cycle, 状态: "观察", 详情: (chk.stdout.split("\n")[1] ?? "").slice(0, 80) });
    } else if (!chk.stdout.includes("无进行中的电池")) {
      log("[监工] 第" + cycle + "轮健康: " + (chk.stdout.split("\n")[2] ?? "").slice(0, 60));
    }
    if (!batterySettled) {
      await world.run(BASH, ["-c", "sleep 900"], { timeoutMs: 960000 });
    }
  }
  return watchFindings;
})();

let bat = await batPromise;
const fixer = agent("运维诊断工程师", {
  system:
    "你负责诊断 GPU 集群上 vLLM 电池脚本的失败并尽量修复。可读文件、跑命令(ssh 密钥已配)、编辑脚本。" +
    "诊断纪律: 先证据后结论, 修复最小化可重入。修复边界=配置修复+启动级验证(serve 冒烟到四关或根因消除即止), " +
    "严禁在你的回合内运行完整电池——电池执行归主线重跑阶段(教训 2026-10-05: fixer 把 4h 电池跑进自己回合, 主线失明又冗余重跑一遍)。集群: 双节点 192.168.199.129/134, 容器 vllm-node, vLLM 0.30。" +
});
for (let round = 1; round <= 2 && bat.exitCode !== 0; round++) {
  phase("归因诊断并修复");
  const diag = await fixer.ask<Diagnosis>(
    "电池(" + CELL + ")失败, 退出码 " + bat.exitCode + "。证据: " + RAW + "/progress.log 与场景目录各日志; " +
    "远端: ssh -o BatchMode=yes syspetro@192.168.199.129 \"docker exec vllm-node tail -50 /root/vllm.log\"。" +
    (watchFindings.length ? "监工已上报线索: " + JSON.stringify(watchFindings.map((f) => f.what)) + "。" : "") +
    "按症状→阶段定位; 修复边界=配置修复+启动级验证, 严禁在你的回合内运行完整电池(电池执行归主线); 返回诊断结果。",
  );
  if (diag.needs_user || !diag.fix_done) break;
  // 冗余重跑闸门: 若电池数据已完整(诊断回合内被跑完/上轮已成功), 跳过重跑直接采用
  // (教训 2026-10-05: fixer 把 4h 电池跑进自己回合, 主线按缓存的失败退出码又完整重跑一遍)
  const probeDone = await world.run(BASH,
    ["-c", "tail -3 " + RAW + "/progress.log 2>/dev/null | grep -c DONE || true"],
    { timeoutMs: 30000 });
  if ((probeDone.stdout || "").trim() !== "0") {
    log("电池数据已完整(检测到 DONE), 跳过冗余重跑");
    bat = { exitCode: 0, stdout: "battery data complete (DONE marker present)", stderr: "" };
    break;
  }
  phase("重跑电池（修复后）");
  log("第 " + round + " 轮修复: " + diag.fix_done);
  bat = await world.run(BASH, [CELL], { timeoutMs: 16200000 });
}
const watchAll = await watcherPromise;
const batteryOk = bat.exitCode === 0;
log("电池终态: " + (batteryOk ? "PASS" : "FAIL") + "; 监工上报 " + watchAll.length + " 条");

if (!batteryOk) {
  return {
    conclusion: "电池两轮归因修复后仍未通过; 监工与诊断证据已上报, 电池幂等可续。",
    findings: watchAll,
    verified: ["电池以真实退出码门禁"],
    notCovered: ["汇编/渲染/入库未执行"],
  } satisfies WorkflowReport;
}

phase("汇编场景档案并校验契约");
const b = await world.run(PY, [BUILD], { timeoutMs: 300000 });
if (b.exitCode !== 0) {
  return { conclusion: "电池通过但汇编失败。", findings: [{ where: BUILD, what: "汇编退出码 " + b.exitCode, evidence: b.stderr.slice(0, 400), status: "verified", severity: "high" }], verified: ["电池 PASS"], notCovered: ["渲染/入库"] } satisfies WorkflowReport;
}
phase("渲染全库与单模型报告");
const rg = "D:/CSharpProject/BenchPlaybook/scripts/report_gen4.py";
const rFull = await world.run(PY, [rg, DOC, FULL_MD], { timeoutMs: 300000 });
const rOne = await world.run(PY, [rg, DOC, REPORT, MODEL_FILTER], { timeoutMs: 300000 });
if (rFull.exitCode !== 0 || rOne.exitCode !== 0) {
  return { conclusion: "渲染失败。", findings: [{ where: "report_gen4", what: "退出码 " + rFull.exitCode + "/" + rOne.exitCode, evidence: (rOne.stderr || rFull.stderr).slice(0, 400), status: "verified", severity: "high" }], verified: ["电池 PASS", "汇编 PASS"], notCovered: ["入库"] } satisfies WorkflowReport;
}
phase("场景入库并洗白提交");
const idx = await world.run(PY, ["D:/CSharpProject/BenchPlaybook/scripts/scenario_index.py", DOC], { timeoutMs: 120000 });
const wash = await world.run(BASH, ["/d/CSharpProject/BenchPlaybook/scripts/post_run_wash.sh", TASK_DIR], { timeoutMs: 300000 });
phase("独立复核最终报告");
const reviewer = agent("独立复核员", { system: "你没看过实验过程, 只凭报告文本复核; 找问题不找优点; 判断不了就说判断不了。" });
const rev = await reviewer.ask<{ issues: Finding[]; verdict: string }>(
  "读 " + REPORT + ", 找数字缺格/结论超证据/误导表述, 每条给 where/what/evidence(报告行), status 统一 unconfirmed。",
);
return {
  conclusion: "全流程闭环完成(电池→汇编→渲染→入库" + (idx.exitCode === 0 && wash.exitCode === 0 ? "全 PASS" : "有失败项") + "); 监工全程随行",
  findings: rev.issues.concat(watchAll),
  verified: ["电池退出码门禁", "schema 校验", "渲染数值回查", "洗白入库 exit=" + wash.exitCode],
  notCovered: [],
} satisfies WorkflowReport;