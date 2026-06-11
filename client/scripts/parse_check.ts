/** 契约对拍：TS 侧 zod parse 各 fixture，与 Python 侧验证同一批 JSON。 */
import { AssemblyPlan, CoreManifest } from "../src/contracts.js";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..", "..");

const plan = AssemblyPlan.parse(
  JSON.parse(readFileSync(resolve(root, "fixtures/assembly-plan.sample.json"), "utf-8")),
);
console.log(
  `TS AssemblyPlan OK: ${plan.seams.length} decisions, write_own=${plan.seams.filter((s) => s.action === "generate").length}`,
);

const core = CoreManifest.parse(
  JSON.parse(readFileSync(resolve(root, "core/loom.core.json"), "utf-8")),
);
console.log(`TS CoreManifest OK: ${core.core_id}@${core.core_version}, ${core.seams.length} seams`);
