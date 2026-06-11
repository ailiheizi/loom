/**
 * T12 单命令端到端驱动 + 产物分层 git commit。
 * 用法（cwd=client）：
 *   node node_modules/tsx/dist/cli.mjs scripts/t12_e2e.ts [--select]
 *
 * 一条命令串起：组装臂（选择→物化→修复）+ 从零臂（从零生成→物化→修复），各产 metrics；
 * 对组装臂产物做 git init + 分层 commit（picked/generated/deterministic/repair-round-N），
 * 体现可追溯的装配历史；最后调 run_compare.py 出双臂对照 + h*。
 *
 * 副作用：.work/ 下读写 + 对 .work/t12-assembly 做 git init/commit（独立仓，不碰 Loom 源码）。
 */
import { readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve, join } from "node:path";
import { AssemblyPlan, CoreManifest } from "../src/contracts.js";
import { loadCandidates } from "../src/loadCandidates.js";
import { repairLoop, type RepairResult } from "../src/repair.js";
import { generateFromZero } from "../src/fromZero.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..", "..");
const doSelect = process.argv.includes("--select");

const core = CoreManifest.parse(JSON.parse(readFileSync(resolve(root, "core/loom.core.json"), "utf-8")));
const ideaPath = resolve(root, "ideas/saas-admin-with-google-auth.json");
const idea = JSON.parse(readFileSync(ideaPath, "utf-8"));

function git(cwd: string, args: string[]): boolean {
  const r = spawnSync("git", args, { cwd, encoding: "utf-8" });
  if (r.status !== 0 && !(args[0] === "commit" && /nothing to commit/.test(r.stdout ?? ""))) {
    console.log(`  ⚠ git ${args.slice(0, 2).join(" ")} → ${(r.stderr || r.stdout || "").trim().slice(0, 120)}`);
    return false;
  }
  return true;
}

/** 对产物目录 git init + 按 layers 顺序分层 commit。 */
function commitLayers(outDir: string, res: RepairResult): void {
  console.log(`[t12] 产物分层 commit @ ${outDir}`);
  // 独立仓：init + 基线（base 副本，排除 .git/node_modules/.next）
  git(outDir, ["init", "-q"]);
  git(outDir, ["config", "user.email", "loom@local"]);
  git(outDir, ["config", "user.name", "Loom Assembler"]);
  // 写产物仓 .gitignore：排除 cpSync 来的巨大/生成目录，只追踪源码
  writeFileSync(
    join(outDir, ".gitignore"),
    ["node_modules/", ".next/", "generated/", "*.sqlite", ".env"].join("\n") + "\n",
    "utf-8",
  );
  // 基线 commit：先提交 base 全量（含 node_modules 会很大 → 用 .gitignore 排除）
  // 写一个最小 .gitignore（产物仓内）
  spawnSync("git", ["add", "-A"], { cwd: outDir, encoding: "utf-8" });
  git(outDir, ["commit", "-q", "-m", "base: 冻结的 create-t3-app 基线 + 全部装配产物"]);

  // 分层：在已全量提交基础上，用 layers 信息打 tag 标注每层涉及的文件（体现来源）。
  // （文件已在基线里，这里用 tag + 空 commit 记录装配历史，避免重复落盘）
  let i = 0;
  for (const layer of res.layers) {
    i++;
    const msg = `${layer.label}: ${layer.files.length} 文件 [${layer.files.slice(0, 6).join(", ")}${layer.files.length > 6 ? ", …" : ""}]`;
    git(outDir, ["commit", "-q", "--allow-empty", "-m", msg]);
    git(outDir, ["tag", `layer-${i}-${layer.label}`]);
  }
  const log = spawnSync("git", ["log", "--oneline", "--decorate"], { cwd: outDir, encoding: "utf-8" });
  console.log("  装配历史：");
  for (const line of (log.stdout ?? "").trim().split("\n")) console.log("    " + line);
}

async function runAssembly(): Promise<RepairResult> {
  console.log("\n========== 组装臂 ==========");
  if (doSelect) {
    console.log("[t12] 现跑 run_select.py…");
    const r = spawnSync("python", ["run_select.py"], { cwd: resolve(root, "platform"), encoding: "utf-8" });
    if (r.status !== 0) throw new Error("run_select.py 失败: " + r.stderr?.slice(0, 300));
  }
  const plan = AssemblyPlan.parse(JSON.parse(readFileSync(resolve(root, ".work/assembly-plan.json"), "utf-8")));
  const candidates = loadCandidates(resolve(root, "candidates"));
  const outDir = resolve(root, ".work/t12-assembly");
  const res = await repairLoop({
    plan, candidates, coreSeams: core.seams,
    baseDir: resolve(root, "core/t3-base"), outDir,
    metricsDir: resolve(root, ".work"), arm: "assembly", maxRounds: 3,
    priorInputTok: plan.budget.input_tok, priorOutputTok: plan.budget.output_tok,
    disclosureInputTok: plan.budget.input_tok, disclosureOutputTok: plan.budget.output_tok,
  });
  commitLayers(outDir, res);
  return res;
}

async function runFromZero(): Promise<RepairResult> {
  console.log("\n========== 从零臂 ==========");
  const fz = await generateFromZero(idea, core.seams as never, resolve(root, ".work/from_zero/candidates"));
  for (const n of fz.notes) console.log("  " + n);
  const candidates = loadCandidates(fz.candidatesDir);
  return repairLoop({
    plan: fz.plan, candidates, coreSeams: core.seams,
    baseDir: resolve(root, "core/t3-base"), outDir: resolve(root, ".work/from_zero-assembly"),
    metricsDir: resolve(root, ".work"), arm: "from_zero", maxRounds: 3,
    priorInputTok: fz.input_tok, priorOutputTok: fz.output_tok,
    disclosureInputTok: 0, disclosureOutputTok: 0,
  });
}

console.log(`=== T12 端到端 idea=${idea.idea_id} ===`);
const asm = await runAssembly();
const fz = await runFromZero();

console.log("\n========== 双臂对照 + h* ==========");
const cmp = spawnSync("uv", ["run", "python", "run_compare.py"], { cwd: resolve(root, "platform"), encoding: "utf-8" });
console.log(cmp.stdout ?? "");
if (cmp.status !== 0) console.log("compare stderr:", cmp.stderr?.slice(0, 300));

console.log(`\n=== T12 完成 ===`);
console.log(`组装臂 converged=${asm.metrics.converged} (${asm.layers.length} 层装配历史)`);
console.log(`从零臂 converged=${fz.metrics.converged}`);
