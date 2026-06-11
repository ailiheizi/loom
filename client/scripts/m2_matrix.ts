/**
 * M2 批量 runner：对每个想法 × {assembly, from_zero, oracle} 跑 repairLoop，产 N×3 metrics。
 * 用法（cwd=client）：node node_modules/tsx/dist/cli.mjs scripts/m2_matrix.ts [--select]
 *   --select：assembly 臂现跑 run_select.py（否则读已有 .work/assembly-plan-<idea>.json）
 *
 * 三臂：
 *   assembly  = AI 选择 plan → repairLoop（disclosure=选择期 token）
 *   oracle    = 人工最优 plan（ideas/oracle/）→ repairLoop（无选择期，disclosure=0）
 *   from_zero = 从零生成同构候选 → repairLoop（无选择期）
 * 产物隔离在 .work/m2/<idea>/<arm>，metrics 写 .work/metrics-<arm>-<idea>.json。
 */
import { readFileSync, existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { AssemblyPlan, CoreManifest } from "../src/contracts.js";
import { loadCandidates } from "../src/loadCandidates.js";
import { repairLoop } from "../src/repair.js";
import { generateFromZero } from "../src/fromZero.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..", "..");
const doSelect = process.argv.includes("--select");

const IDEAS = [
  "saas-admin-with-google-auth",
  "task-tracker-with-github-auth",
  "contact-book-with-google-auth",
];

// --only <idea> 只跑指定想法（补跑/限流恢复用）
const onlyIdx = process.argv.indexOf("--only");
const ONLY = onlyIdx >= 0 ? process.argv[onlyIdx + 1] : null;
const RUN_IDEAS = ONLY ? IDEAS.filter((i) => i === ONLY) : IDEAS;

const core = CoreManifest.parse(JSON.parse(readFileSync(resolve(root, "core/loom.core.json"), "utf-8")));
const candidates = loadCandidates(resolve(root, "candidates"));
const baseDir = resolve(root, "core/t3-base");
const workDir = resolve(root, ".work");

function loadJson(p: string): any {
  return JSON.parse(readFileSync(p, "utf-8"));
}

async function runArm(ideaId: string, arm: "assembly" | "oracle" | "from_zero"): Promise<string> {
  const outDir = resolve(workDir, "m2", ideaId, arm);
  const ideaPath = resolve(root, "ideas", `${ideaId}.json`);
  const idea = loadJson(ideaPath);

  if (arm === "from_zero") {
    const fz = await generateFromZero(idea, core.seams as never, resolve(workDir, "m2", ideaId, "fz-candidates"));
    const r = await repairLoop({
      plan: fz.plan, candidates: loadCandidates(fz.candidatesDir), coreSeams: core.seams,
      baseDir, outDir, metricsDir: workDir, arm: "from_zero", maxRounds: 3,
      priorInputTok: fz.input_tok, priorOutputTok: fz.output_tok, disclosureInputTok: 0, disclosureOutputTok: 0,
    });
    return `from_zero converged=${r.metrics.converged} err=${r.metrics.final_error_count}`;
  }

  if (arm === "oracle") {
    const oraclePath = resolve(root, "ideas/oracle", `oracle-plan-${ideaId}.json`);
    const plan = AssemblyPlan.parse(loadJson(oraclePath));
    const r = await repairLoop({
      plan, candidates, coreSeams: core.seams,
      baseDir, outDir, metricsDir: workDir, arm: "oracle", maxRounds: 3,
      priorInputTok: 0, priorOutputTok: 0, disclosureInputTok: 0, disclosureOutputTok: 0,
    });
    return `oracle converged=${r.metrics.converged} err=${r.metrics.final_error_count}`;
  }

  // assembly：需要 AI 选择 plan
  const planPath = resolve(workDir, `assembly-plan-${ideaId}.json`);
  if (doSelect || !existsSync(planPath)) {
    console.log(`  [select] run_select.py ${ideaId}…`);
    // 用 uv run（全局 python 的 pydantic/anthropic 版本冲突，platform/.venv 才完整）
    const sr = spawnSync("uv", ["run", "python", "run_select.py", ideaPath], { cwd: resolve(root, "platform"), encoding: "utf-8" });
    if (sr.status !== 0) throw new Error(`run_select 失败 (${ideaId}): ${(sr.stderr || sr.stdout || "").slice(0, 300)}`);
  }
  const plan = AssemblyPlan.parse(loadJson(planPath));
  const r = await repairLoop({
    plan, candidates, coreSeams: core.seams,
    baseDir, outDir, metricsDir: workDir, arm: "assembly", maxRounds: 3,
    priorInputTok: plan.budget.input_tok, priorOutputTok: plan.budget.output_tok,
    disclosureInputTok: plan.budget.input_tok, disclosureOutputTok: plan.budget.output_tok,
  });
  return `assembly converged=${r.metrics.converged} err=${r.metrics.final_error_count} write_own=${r.metrics.write_own_ratio}`;
}

console.log(`=== M2 矩阵：${RUN_IDEAS.length} 想法 × 3 臂 ===`);
for (const ideaId of RUN_IDEAS) {
  console.log(`\n## 想法: ${ideaId}`);
  for (const arm of ["assembly", "oracle", "from_zero"] as const) {
    try {
      const summary = await runArm(ideaId, arm);
      console.log(`  ✓ ${summary}`);
    } catch (e) {
      console.log(`  ✗ ${arm} 失败: ${(e as Error).message}`);
    }
  }
}
console.log(`\n=== 矩阵跑完，cd ../platform && uv run python m2_verdict.py 出判定 ===`);
