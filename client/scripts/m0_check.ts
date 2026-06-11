/**
 * M0 验证 driver：手工 plan → 物化 → 闸门，验证物化引擎通路。
 * 用法：tsx scripts/m0_check.ts
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { AssemblyPlan, CoreManifest } from "../src/contracts.js";
import { loadCandidates } from "../src/loadCandidates.js";
import { materialize } from "../src/materialize.js";
import { injectEnv } from "../src/injectEnv.js";
import { gate } from "../src/gate.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..", "..");

const core = CoreManifest.parse(JSON.parse(readFileSync(resolve(root, "core/loom.core.json"), "utf-8")));
const candidates = loadCandidates(resolve(root, "candidates"));

// M0 最小 plan：只 pick google-oauth（最干净路径，预期 0 error）
const plan = AssemblyPlan.parse({
  idea_id: "m0-smoke",
  core_ref: "create-t3-app@7.39.x",
  seams: [
    { seam_id: "auth.oauth_provider", action: "pick", ref: "google-oauth", confidence: 1, why: "m0 smoke" },
  ],
});

console.log("=== 物化 ===");
const result = materialize({
  plan,
  candidates,
  coreSeams: core.seams,
  baseDir: resolve(root, "core/t3-base"),
  outDir: resolve(root, ".work/m0-smoke"),
});
for (const c of result.changes) console.log(`  [${c.kind}] ${c.target}${c.detail ? " — " + c.detail : ""}`);
console.log(`  deps: ${JSON.stringify(result.deps)}`);
console.log(`  envVars: ${JSON.stringify(result.envVars)}`);
console.log(`  requiresPrismaModels: ${JSON.stringify(result.requiresPrismaModels)}`);

console.log("=== envVars 注入 ===");
const envR = injectEnv(result.outDir, result.envVars);
console.log(`  injected: ${JSON.stringify(envR.injected)}, skipped: ${JSON.stringify(envR.skipped)}`);

console.log("=== 闸门 ===");
const g = gate(result.outDir);
console.log(`  errorCount: ${g.errorCount}`);
for (const d of g.diagnostics.slice(0, 15)) {
  console.log(`  TS${d.code} ${d.file}:${d.line}:${d.column} ${d.message}`);
}
console.log(`  fingerprints: ${JSON.stringify(g.fingerprints)}`);
