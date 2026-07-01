/**
 * 真实信号产出：把 repairLoop 的 tsc gate 结果转成 per-候选 success/failure，
 * 追加写到 outcomes 文件(jsonl)。platform 下次启动读入喂给信任飞轮(reinforce)。
 *
 * 为什么可信：信号来自全项目 tsc 类型诊断(gate)，不是"被 pick"或 agent 自觉。
 * 归因规则：某 pick/adapt 候选落盘的文件里若有 tsc 错误 → 该候选 failure；否则 success。
 *
 * 解耦：client 不知道 ~/.loom 语义。outcomes 路径由 LOOM_OUTCOMES_PATH 指定
 * (platform 设同一路径)，未设则跳过(物化仍正常，只是不产信号)。
 */
import { appendFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { AssemblyPlan } from "./contracts.js";
import type { CandidateMeta } from "./loadCandidates.js";
import type { GateResult } from "./gate.js";

export interface Outcome {
  ref: string;
  seam_id: string;
  success: boolean;
  /** 该候选文件上的 tsc 错误数(0=通过) */
  error_count: number;
  /** 信号来源，便于 platform 侧审计 */
  source: "client-gate";
}

/**
 * 从 gate 结果 + plan + 候选映射算出每个被 pick/adapt 候选的 success/failure。
 * 归因：候选的 registry_item.files[].target 若命中 finalGate.diagnostics[].file → failure。
 */
export function computeOutcomes(
  plan: AssemblyPlan,
  candidates: Map<string, Map<string, CandidateMeta>>,
  finalGate: GateResult,
): Outcome[] {
  // 有错误的文件 → 错误数
  const errCountByFile = new Map<string, number>();
  for (const d of finalGate.diagnostics) {
    const f = normFile(d.file);
    errCountByFile.set(f, (errCountByFile.get(f) ?? 0) + 1);
  }
  const outcomes: Outcome[] = [];

  for (const seam of plan.seams) {
    // 只对真正落了候选代码的决策产信号(pick/adapt 有 ref)；generate/skip 不是"复用候选"
    if ((seam.action !== "pick" && seam.action !== "adapt") || !seam.ref) continue;
    const meta = candidates.get(seam.seam_id)?.get(seam.ref);
    if (!meta) continue;

    // 该候选落盘的目标文件上的 tsc 错误总数
    const targets = meta.registry_item.files.map((f) => normFile(f.target));
    const errCount = targets.reduce((n, t) => n + (errCountByFile.get(t) ?? 0), 0);
    outcomes.push({
      ref: seam.ref,
      seam_id: seam.seam_id,
      success: errCount === 0,
      error_count: errCount,
      source: "client-gate",
    });
  }
  return outcomes;
}

/** 追加写 outcomes 到 jsonl。路径来自 LOOM_OUTCOMES_PATH，未设则跳过(返回 false)。 */
export function emitOutcomes(outcomes: Outcome[], outcomesPath?: string): boolean {
  const path = outcomesPath ?? process.env.LOOM_OUTCOMES_PATH;
  if (!path || outcomes.length === 0) return false;
  mkdirSync(dirname(path), { recursive: true });
  const lines = outcomes.map((o) => JSON.stringify(o)).join("\n") + "\n";
  appendFileSync(path, lines, "utf-8");
  return true;
}

function normFile(f: string): string {
  return f.replace(/\\/g, "/").replace(/^\.?\//, "");
}
