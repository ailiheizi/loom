/**
 * T8 压测 driver — 场景 B（震荡止损）。
 * 用 generic-crud-factory：它的 barrel register 是 `project: createCrudRouter(ctx.db.project),`，
 * 注册进 root.ts 顶层那里没有 ctx → TS2304/TS2552。错误落在 root.ts（override 黑名单），
 * AI 不可达 → 两轮不改善 → thrash 提前止损 → converged=false。
 *
 * 用法（cwd=client）：node node_modules/tsx/dist/cli.mjs scripts/t8_dirty_thrash.ts
 * 副作用隔离在 .work/dirty-thrash-assembly。
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

// 手工 plan：pick generic-crud-factory（barrel register 用了顶层不存在的 ctx）
const plan = AssemblyPlan.parse({
  idea_id: "dirty-thrash",
  core_ref: "create-t3-app@7.39.x",
  seams: [
    { seam_id: "data.crud_resource", action: "pick", ref: "generic-crud-factory", confidence: 0.5, why: "压测震荡止损：错误落黑名单文件 root.ts，AI 不可达" },
  ],
});

console.log("=== T8 压测 场景B（震荡止损）===");
const res = await repairLoop({
  plan,
  candidates,
  coreSeams: core.seams,
  baseDir: resolve(root, "core/t3-base"),
  outDir: resolve(root, ".work/dirty-thrash-assembly"),
  metricsDir: resolve(root, ".work"),
  arm: "dirty-thrash",
  maxRounds: 3,
});

console.log("\n=== 指标 ===");
const m = res.metrics;
console.log(`converged=${m.converged} final_error_count=${m.final_error_count}`);
console.log(`rounds 数=${m.rounds.length}`);
for (const r of m.rounds) {
  console.log(`  round ${r.round_index}: errors=${r.error_count} in=${r.input_tok} out=${r.output_tok} auto_fixed=${r.auto_fixed} fp=${JSON.stringify(r.error_fingerprints)}`);
}
console.log("\n判定：", !m.converged && m.final_error_count > 0 ? "✓ 正确止损（未假装收敛，错误落黑名单 AI 不可达）" : "✗ 预期之外");
