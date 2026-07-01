/**
 * computeOutcomes 归因单测：验证 barrel 共享文件 / generate 撞名不误判。
 * 用法(cwd=client)：node node_modules/tsx/dist/cli.mjs scripts/t_outcomes_attribution.ts
 *
 * 纯逻辑测试(不跑物化)：构造假 plan/candidates/gate 喂 computeOutcomes，断言归因正确。
 */
import { computeOutcomes } from "../src/outcomes.js";
import type { GateResult } from "../src/gate.js";

const fails: string[] = [];
function check(name: string, cond: boolean, extra = "") {
  console.log(`  ${cond ? "✓" : "✗"} ${name}${extra ? "  " + extra : ""}`);
  if (!cond) fails.push(name);
}

// 假候选：ref → 落盘文件。用 as any 绕过完整 RegistryItem 结构(只需 files[].target)。
function cand(seam: string, ref: string, targets: string[]) {
  return [seam, new Map([[ref, { registry_item: { files: targets.map((t) => ({ target: t })) } } as any]])] as const;
}

function run() {
  console.log("== computeOutcomes 归因单测 ==");

  // 场景1：两个候选独占各自文件，一个有错一个没错
  {
    const candidates = new Map<string, Map<string, any>>([
      cand("ui.data_table", "good-table", ["src/components/table.tsx"]),
      cand("ui.form", "bad-form", ["src/components/form.tsx"]),
    ]);
    const plan: any = { seams: [
      { seam_id: "ui.data_table", action: "pick", ref: "good-table" },
      { seam_id: "ui.form", action: "pick", ref: "bad-form" },
    ]};
    const gate: GateResult = {
      errorCount: 1,
      diagnostics: [{ file: "src/components/form.tsx", line: 1, column: 1, code: 2322, message: "x", category: "error" }],
      fingerprints: [],
    };
    const out = computeOutcomes(plan, candidates as any, gate);
    const good = out.find((o) => o.ref === "good-table")!;
    const bad = out.find((o) => o.ref === "bad-form")!;
    check("独占文件无错 → success", good.success === true);
    check("独占文件有错 → failure", bad.success === false && bad.error_count === 1);
  }

  // 场景2：barrel 共享文件(两候选都写 root.ts)有错 → 都不误判 failure
  {
    const candidates = new Map<string, Map<string, any>>([
      cand("auth.a", "oauth-a", ["src/providers/a.ts", "src/server/root.ts"]),
      cand("auth.b", "oauth-b", ["src/providers/b.ts", "src/server/root.ts"]),
    ]);
    const plan: any = { seams: [
      { seam_id: "auth.a", action: "pick", ref: "oauth-a" },
      { seam_id: "auth.b", action: "pick", ref: "oauth-b" },
    ]};
    // 错误只在共享的 root.ts 上，各自独占文件无错
    const gate: GateResult = {
      errorCount: 1,
      diagnostics: [{ file: "src/server/root.ts", line: 1, column: 1, code: 2322, message: "x", category: "error" }],
      fingerprints: [],
    };
    const out = computeOutcomes(plan, candidates as any, gate);
    check("barrel 共享文件错误不归给候选A", out.find((o) => o.ref === "oauth-a")!.success === true);
    check("barrel 共享文件错误不归给候选B", out.find((o) => o.ref === "oauth-b")!.success === true);
    check("共享文件被记为 skipped", out.every((o) => o.shared_files_skipped === 1));
  }

  // 场景3：generate 与 pick 撞同名文件 → 该文件错误不归给 pick
  {
    const candidates = new Map<string, Map<string, any>>([
      cand("ui.x", "pick-x", ["src/x.tsx"]),
    ]);
    const plan: any = { seams: [
      { seam_id: "ui.x", action: "pick", ref: "pick-x" },
      { seam_id: "ui.gen", action: "generate", generated_file: "src/x.tsx" },  // 撞名
    ]};
    const gate: GateResult = {
      errorCount: 1,
      diagnostics: [{ file: "src/x.tsx", line: 1, column: 1, code: 2322, message: "x", category: "error" }],
      fingerprints: [],
    };
    const out = computeOutcomes(plan, candidates as any, gate);
    check("generate 撞名 → 错误不归给 pick 候选", out.find((o) => o.ref === "pick-x")!.success === true);
  }

  console.log(`\n=== ${fails.length ? "FAIL: " + fails.join(", ") : "PASS"} ===`);
  process.exit(fails.length ? 1 : 0);
}

run();
