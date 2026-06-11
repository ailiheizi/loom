/**
 * T9 arm 参数化 runner。
 * 用法（cwd=client）：
 *   node node_modules/tsx/dist/cli.mjs scripts/t9_runner.ts --arm assembly   [--select]
 *   node node_modules/tsx/dist/cli.mjs scripts/t9_runner.ts --arm from_zero
 *
 * assembly 臂：读 idea/core/candidates + 已有 assembly-plan.json（--select 则现跑 run_select.py）
 *   → repairLoop（选择期 token 经 plan.budget 注入 disclosure/prior）→ .work/metrics-assembly.json
 * from_zero 臂：generateFromZero → 同构 synthetic 候选库 + plan
 *   → repairLoop（生成 token 注入 prior，disclosure=0）→ .work/metrics-from_zero.json
 *
 * repairLoop 保持 arm-agnostic：arm 语义（哪段 token 算披露）由本 runner 显式注入。
 * 副作用隔离在 .work/。
 */
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { AssemblyPlan, CoreManifest } from "../src/contracts.js";
import { loadCandidates } from "../src/loadCandidates.js";
import { repairLoop } from "../src/repair.js";
import { generateFromZero } from "../src/fromZero.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..", "..");

function arg(name: string, def?: string): string | undefined {
  const i = process.argv.indexOf(name);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith("--") ? process.argv[i + 1] : (process.argv.includes(name) ? "true" : def);
}

const armRaw = arg("--arm", "assembly");
const arm = armRaw === "true" ? "assembly" : armRaw!;
const ideaPath = arg("--idea", resolve(root, "ideas/saas-admin-with-google-auth.json"))!;
const doSelect = process.argv.includes("--select");

const core = CoreManifest.parse(JSON.parse(readFileSync(resolve(root, "core/loom.core.json"), "utf-8")));
const idea = JSON.parse(readFileSync(ideaPath, "utf-8"));

console.log(`=== T9 runner arm=${arm} idea=${idea.idea_id} ===`);

if (arm === "assembly") {
  // 选择阶段：现跑或读已有 plan
  if (doSelect) {
    console.log("[t9] 现跑 run_select.py…");
    const r = spawnSync("python", ["run_select.py"], { cwd: resolve(root, "platform"), encoding: "utf-8" });
    if (r.status !== 0) {
      console.error("run_select.py 失败：", r.stderr?.slice(0, 400));
      process.exit(1);
    }
  }
  const plan = AssemblyPlan.parse(JSON.parse(readFileSync(resolve(root, ".work/assembly-plan.json"), "utf-8")));
  const candidates = loadCandidates(resolve(root, "candidates"));
  // 选择期 token 经 plan.budget 跨语言桥注入（disclosure + prior 同源）
  const selIn = plan.budget.input_tok;
  const selOut = plan.budget.output_tok;
  console.log(`[t9] 选择期 token: in=${selIn} out=${selOut}（并入 total，单列 disclosure）`);

  const res = await repairLoop({
    plan,
    candidates,
    coreSeams: core.seams,
    baseDir: resolve(root, "core/t3-base"),
    outDir: resolve(root, ".work/t9-assembly"),
    metricsDir: resolve(root, ".work"),
    arm: "assembly",
    maxRounds: 3,
    priorInputTok: selIn,
    priorOutputTok: selOut,
    disclosureInputTok: selIn,
    disclosureOutputTok: selOut,
  });
  printMetrics(res.metrics);
} else if (arm === "from_zero") {
  console.log("[t9] 从零生成 4 seam → 同构 synthetic 候选库…");
  const fz = await generateFromZero(idea, core.seams as never, resolve(root, ".work/from_zero/candidates"));
  for (const n of fz.notes) console.log("  " + n);
  console.log(`[t9] 从零生成 token: in=${fz.input_tok} out=${fz.output_tok}`);
  const candidates = loadCandidates(fz.candidatesDir);

  const res = await repairLoop({
    plan: fz.plan,
    candidates,
    coreSeams: core.seams,
    baseDir: resolve(root, "core/t3-base"),
    outDir: resolve(root, ".work/from_zero-assembly"),
    metricsDir: resolve(root, ".work"),
    arm: "from_zero",
    maxRounds: 3,
    priorInputTok: fz.input_tok,
    priorOutputTok: fz.output_tok,
    disclosureInputTok: 0, // 从零臂无披露/选择期
    disclosureOutputTok: 0,
  });
  printMetrics(res.metrics);
} else {
  console.error(`未知 arm: ${arm}（支持 assembly | from_zero）`);
  process.exit(1);
}

function printMetrics(m: { arm: string; total_input_tok: number; total_output_tok: number; disclosure_input_tok: number; converged: boolean; final_error_count: number; write_own_ratio: number; rounds: unknown[] }) {
  console.log("\n=== 指标 ===");
  console.log(`arm=${m.arm} converged=${m.converged} final_error=${m.final_error_count}`);
  console.log(`total_input=${m.total_input_tok}（含 disclosure=${m.disclosure_input_tok}）total_output=${m.total_output_tok}`);
  console.log(`write_own_ratio=${m.write_own_ratio} rounds=${m.rounds.length}`);
  console.log("→ 两臂都跑完后，cd ../platform && python run_compare.py 出 h*");
}
