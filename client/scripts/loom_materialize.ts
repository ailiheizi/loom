/**
 * Loom client 物化入口（供 loom_assemble.sh / skill 调用）。
 * 纯确定性：读 plan → materialize → 确定性 fixer（prisma model/env）→ gate → 有界修复。
 * 零 LLM（修复轮若需 AI override 才调，pick/adapt 全 0-error 时不触发）。
 *
 * 环境变量：
 *   LOOM_PLAN  assembly-plan JSON 路径（必需）
 *   LOOM_OUT   物化输出目录（必需）
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { AssemblyPlan, CoreManifest } from "../src/contracts.js";
import { loadCandidates } from "../src/loadCandidates.js";
import { repairLoop } from "../src/repair.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..", "..");

const planPath = process.env.LOOM_PLAN;
const outDir = process.env.LOOM_OUT;
if (!planPath || !outDir) {
  console.error("缺 LOOM_PLAN / LOOM_OUT 环境变量");
  process.exit(1);
}

const core = CoreManifest.parse(JSON.parse(readFileSync(resolve(root, "core/loom.core.json"), "utf-8")));
const plan = AssemblyPlan.parse(JSON.parse(readFileSync(planPath, "utf-8")));
const candidates = loadCandidates(resolve(root, "candidates"));

console.log(`[materialize] idea=${plan.idea_id} seams=${plan.seams.length} → ${outDir}`);

const res = await repairLoop({
  plan,
  candidates,
  coreSeams: core.seams,
  baseDir: resolve(root, "core/t3-base"),
  outDir,
  metricsDir: resolve(root, ".work"),
  arm: "assembly",
  maxRounds: 3,
  priorInputTok: plan.budget.input_tok,
  priorOutputTok: plan.budget.output_tok,
  disclosureInputTok: plan.budget.input_tok,
});

console.log(`[materialize] converged=${res.metrics.converged} final_error=${res.metrics.final_error_count}`);
console.log("[materialize] 装配层:");
for (const layer of res.layers) {
  console.log(`  ${layer.label}: ${layer.files.join(", ")}`);
}
if (!res.metrics.converged) {
  console.error(`[materialize] ⚠ 未完全收敛（${res.metrics.final_error_count} error），starter 可能需手工补修`);
  process.exit(2);
}
