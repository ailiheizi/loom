/**
 * 物化引擎：把 AssemblyPlan + 候选物化进一份 t3-base 副本。
 *
 * 策略（文件级拼装，绝不做 AST 行级合并）：
 * - pick : 候选 files[] 整文件落盘到 target；按 barrel_snippet 在锚点处 append import/register。
 * - adapt: 同 pick，额外把 adapter 说明落成一个 TODO adapter 文件（M1 简化，真正胶水由后续修复轮补）。
 * - generate: 用 plan 里 AI 写的 generated 内容落盘（由 select 阶段填充 generatedContent）。
 * - skip : 不动。
 *
 * barrel append 用文本锚点插入：锚点是注释 `// <loom-anchor:xxx>`，
 * 在锚点行之前插入片段，幂等（已存在则跳过，对应 Hygen 的 skip_if）。
 */
import { cpSync, readFileSync, writeFileSync, mkdirSync, existsSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import type { AssemblyPlan } from "./contracts.js";
import type { CandidateMeta } from "./loadCandidates.js";

export interface MaterializeInput {
  plan: AssemblyPlan;
  /** seamId -> ref -> 候选 */
  candidates: Map<string, Map<string, CandidateMeta>>;
  /** loom.core.json 的 seams，用于查锚点 */
  coreSeams: Array<{
    seam_id: string;
    barrel: { file: string; anchor_register: string | null; anchor_import: string | null; op: string };
  }>;
  /** 冻结的 base 目录 */
  baseDir: string;
  /** 物化输出目录（会先清空再从 base 复制） */
  outDir: string;
  /** generate 决策的 AI 产物内容：seamId -> 文件内容 */
  generatedContent?: Map<string, string>;
}

export interface FileChange {
  kind: "file-add" | "barrel-append" | "barrel-skip(exist)";
  target: string;
  detail?: string;
}

export interface MaterializeResult {
  outDir: string;
  changes: FileChange[];
  /** 合并去重后的 npm 依赖 */
  deps: Array<{ name: string; version: string }>;
  /** 需要注入 env.js 的环境变量名 */
  envVars: string[];
  /** 需要追加的 prisma model（来自候选 requires_prisma_model 标记，M1 暴露的真实接缝） */
  requiresPrismaModels: string[];
}

/** 在指定文件的锚点行之前插入 snippet（幂等）。 */
function appendAtAnchor(filePath: string, anchor: string, snippet: string): "appended" | "exists" | "no-anchor" {
  const content = readFileSync(filePath, "utf-8");
  if (content.includes(snippet.trim())) return "exists";
  const idx = content.indexOf(anchor);
  if (idx === -1) return "no-anchor";
  // 找到锚点所在行的行首，在该行前插入（保持锚点缩进）
  const lineStart = content.lastIndexOf("\n", idx) + 1;
  const indent = content.slice(lineStart, idx);
  const insertion = `${indent}${snippet.trim()}\n`;
  const next = content.slice(0, lineStart) + insertion + content.slice(lineStart);
  writeFileSync(filePath, next, "utf-8");
  return "appended";
}

export function materialize(input: MaterializeInput): MaterializeResult {
  const { plan, candidates, coreSeams, baseDir, outDir, generatedContent } = input;

  // 1. 从 base 复制出干净副本
  if (existsSync(outDir)) rmSync(outDir, { recursive: true, force: true });
  cpSync(baseDir, outDir, { recursive: true });

  const changes: FileChange[] = [];
  const deps: Array<{ name: string; version: string }> = [];
  const envVars = new Set<string>();
  const requiresPrismaModels: string[] = [];
  const seamById = new Map(coreSeams.map((s) => [s.seam_id, s]));

  for (const decision of plan.seams) {
    const seam = seamById.get(decision.seam_id);

    if (decision.action === "skip") continue;

    if (decision.action === "generate") {
      const content = generatedContent?.get(decision.seam_id);
      const target = decision.generated_file;
      if (content && target) {
        const abs = join(outDir, target);
        mkdirSync(dirname(abs), { recursive: true });
        writeFileSync(abs, content, "utf-8");
        changes.push({ kind: "file-add", target, detail: "generate(AI 自写)" });
      } else {
        changes.push({ kind: "file-add", target: target ?? "?", detail: "generate 缺内容(待 select 填充)" });
      }
      continue;
    }

    // pick / adapt：落候选文件 + barrel append
    if (!decision.ref) continue;
    const meta = candidates.get(decision.seam_id)?.get(decision.ref);
    if (!meta) {
      changes.push({ kind: "file-add", target: decision.ref, detail: "候选未找到!" });
      continue;
    }

    // 落盘候选 files[]
    for (const f of meta.registry_item.files) {
      const srcAbs = join(meta.dir, f.path);
      const dstAbs = join(outDir, f.target);
      mkdirSync(dirname(dstAbs), { recursive: true });
      writeFileSync(dstAbs, readFileSync(srcAbs, "utf-8"), "utf-8");
      changes.push({ kind: "file-add", target: f.target });
    }

    // 收集依赖 / env / prisma model
    for (const pkg of meta.registry_item.meta_loom.ext_pkgs) {
      deps.push({ name: pkg.name, version: pkg.version });
    }
    for (const dep of meta.registry_item.dependencies) {
      const at = dep.lastIndexOf("@");
      if (at > 0) deps.push({ name: dep.slice(0, at), version: dep.slice(at + 1) });
    }
    for (const ev of Object.keys(meta.registry_item.env_vars)) envVars.add(ev);
    const prismaModel = (meta.registry_item.meta_loom as Record<string, unknown>).requires_prisma_model;
    if (typeof prismaModel === "string") requiresPrismaModels.push(prismaModel);

    // barrel append（仅当 seam 有接入口锚点且候选给了片段）
    if (seam && meta.barrel_snippet) {
      const barrelAbs = join(outDir, seam.barrel.file);
      if (meta.barrel_snippet.import && seam.barrel.anchor_import && existsSync(barrelAbs)) {
        const r = appendAtAnchor(barrelAbs, seam.barrel.anchor_import, meta.barrel_snippet.import);
        changes.push({ kind: r === "exists" ? "barrel-skip(exist)" : "barrel-append", target: seam.barrel.file, detail: `import (${r})` });
      }
      if (meta.barrel_snippet.register && seam.barrel.anchor_register && existsSync(barrelAbs)) {
        const r = appendAtAnchor(barrelAbs, seam.barrel.anchor_register, meta.barrel_snippet.register);
        changes.push({ kind: r === "exists" ? "barrel-skip(exist)" : "barrel-append", target: seam.barrel.file, detail: `register (${r})` });
      }
    }
  }

  // 依赖去重
  const seen = new Set<string>();
  const dedupDeps = deps.filter((d) => {
    const k = `${d.name}@${d.version}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });

  return {
    outDir,
    changes,
    deps: dedupDeps,
    envVars: [...envVars],
    requiresPrismaModels,
  };
}
