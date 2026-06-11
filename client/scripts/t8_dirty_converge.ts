/**
 * T8 压测 driver — 场景 A（修复轮收敛）。
 * 用脏候选 dirty-crud（含自包含 TS2322，正解明确，落非黑名单文件）压测：
 * round-0 gate 应报错 → round-1 AI 整文件 override 修好 → converged=true，rounds≥2。
 *
 * 用法（cwd=client）：node node_modules/tsx/dist/cli.mjs scripts/t8_dirty_converge.ts
 * 副作用隔离在 .work/dirty-assembly。
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { AssemblyPlan, CoreManifest } from "../src/contracts.js";
import { loadCandidates } from "../src/loadCandidates.js";
import { repairLoop } from "../src/repair.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..", "..");

const core = CoreManifest.parse(JSON.parse(readFileSync(resolve(root, "core/loom.core.json"), "utf-8")));
// 从脏候选库加载（隔离，不碰真实 candidates/）
const candidates = loadCandidates(resolve(root, ".work/dirty/candidates"));

// 手工 plan：只 pick dirty-crud（含可修 TS2322）
const plan = AssemblyPlan.parse({
  idea_id: "dirty-converge",
  core_ref: "create-t3-app@7.39.x",
  seams: [
    { seam_id: "data.crud_resource", action: "pick", ref: "dirty-crud", confidence: 0.5, why: "压测修复轮：含自包含 TS2322" },
  ],
});

console.log("=== T8 压测 场景A（修复轮收敛）===");
const res = await repairLoop({
  plan,
  candidates,
  coreSeams: core.seams,
  baseDir: resolve(root, "core/t3-base"),
  outDir: resolve(root, ".work/dirty-assembly"),
  metricsDir: resolve(root, ".work"),
  arm: "dirty-converge",
  maxRounds: 3,
});

console.log("\n=== 指标 ===");
const m = res.metrics;
console.log(`converged=${m.converged} final_error_count=${m.final_error_count}`);
console.log(`retry_input(ΔRepair)=${m.retry_input_tok} fix_diff_lines=${m.fix_diff_lines}`);
console.log(`rounds 数=${m.rounds.length}（>1 表示修复轮真跑了）`);
for (const r of m.rounds) {
  console.log(`  round ${r.round_index}: errors=${r.error_count} in=${r.input_tok} out=${r.output_tok} auto_fixed=${r.auto_fixed} fp=${JSON.stringify(r.error_fingerprints)}`);
}
console.log("\n判定：", m.converged && m.rounds.length > 1 ? "✓ 修复轮真跑并收敛" : (m.rounds.length <= 1 ? "✗ 修复轮没跑（round-0 就 0 error）" : "✗ 未收敛"));
