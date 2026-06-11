/**
 * T8 验证 driver：读真实 assembly-plan → 跑有界修复循环 → 打印指标。
 * 用法（cwd=client）：node node_modules/tsx/dist/cli.mjs scripts/t8_repair.ts
 *
 * 副作用范围：只在 .work/t8-assembly（物化输出目录）跑 prisma generate / pnpm add，
 * 不碰任何源码或 base。
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
const candidates = loadCandidates(resolve(root, "candidates"));
const plan = AssemblyPlan.parse(JSON.parse(readFileSync(resolve(root, ".work/assembly-plan.json"), "utf-8")));

console.log("=== T8 有界修复循环 ===");
console.log(`idea=${plan.idea_id} seams=${plan.seams.length}`);

const res = await repairLoop({
  plan,
  candidates,
  coreSeams: core.seams,
  baseDir: resolve(root, "core/t3-base"),
  outDir: resolve(root, ".work/t8-assembly"),
  metricsDir: resolve(root, ".work"),
  arm: "loom-full",
  maxRounds: 3,
});

console.log("\n=== 指标 ===");
const m = res.metrics;
console.log(`converged=${m.converged} final_error_count=${m.final_error_count}`);
console.log(`total_input=${m.total_input_tok} total_output=${m.total_output_tok} retry_input(ΔRepair)=${m.retry_input_tok}`);
console.log(`write_own_ratio=${m.write_own_ratio} fix_diff_lines=${m.fix_diff_lines}`);
console.log("rounds:");
for (const r of m.rounds) {
  console.log(
    `  round ${r.round_index}: errors=${r.error_count} in=${r.input_tok} out=${r.output_tok} auto_fixed=${r.auto_fixed} fp=${JSON.stringify(r.error_fingerprints)}`,
  );
}
