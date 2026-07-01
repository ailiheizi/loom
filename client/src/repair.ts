/**
 * T8 有界修复循环。
 *
 * 设计（用户已拍板的三个决策）：
 *  1. 循环架构：round-0 唯一一次 materialize（注入 generate 内容）；之后所有修复
 *     **就地改 outDir + 只重跑 gate()，绝不重物化**——否则修复会被 cpSync 擦除。
 *  2. 白名单命令：仅允许在 outDir 跑 `prisma generate` 与 `pnpm add <包>`，严禁其他命令
 *     （尤其 migrate / db push，那些需要真库）。
 *  3. generate 依赖策略：允许 AI 调库（配合 pnpm add），但 prompt 优先无依赖方案。
 *
 * 处置的 FATAL（详见 docs/T8-doubt-register.md）：
 *  - A2a：requires_prisma_model 被 zod LoomMeta 剥离 → materialize.requiresPrismaModels 恒空。
 *         这里直读原始 meta.json 绕过，不依赖 materialize 的派生值。
 *  - A2b/c/d：base 无 Project model；这里用内置模板 append 到 prisma-models 锚点，再跑 generate。
 *  - A3：report 接缝 generate 无内容；generateContents 锁客户端方向 + 浏览器原生导出。
 *  - A4：每轮产 RepairRound（round_index=0=初始 gate，0 修复 token），写 .work/metrics-<arm>.json。
 *  - A5：override prompt 禁 as any/@ts-ignore/删逻辑；本地 rejectIfDegraded 兜底丢弃。
 *  - A6：收敛=fingerprint 集严格收窄 OR error_count 严格下降；都不改善判 thrash。
 *
 * 关键陷阱：
 *  - #1 base 有 postinstall: prisma generate → pnpm add 会顺带 generate。固定顺序：
 *       先 append schema → 有 deps 则 pnpm add（顺带 generate）→ 否则显式 prisma generate。
 *  - #3 barrel 文件（root.ts/config.ts/env.js/schema.prisma）整文件 override 会丢锚点且不可逆，
 *       列入黑名单，只由确定性 fixer 处理。
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { spawnSync } from "node:child_process";
import { complete, extractCode } from "./llm.js";
import { gate, type GateResult } from "./gate.js";
import { materialize, type MaterializeInput } from "./materialize.js";
import { injectEnv } from "./injectEnv.js";
import { computeOutcomes, emitOutcomes } from "./outcomes.js";
import type { CandidateMeta } from "./loadCandidates.js";
import { AssemblyMetrics, type AssemblyPlan, type Diagnostic, type RepairRound } from "./contracts.js";

// ─────────────────────────────────────────────────────────────────────────────
// 配置与结果
// ─────────────────────────────────────────────────────────────────────────────

export interface RepairConfig {
  plan: AssemblyPlan;
  candidates: Map<string, Map<string, CandidateMeta>>;
  coreSeams: MaterializeInput["coreSeams"];
  baseDir: string;
  outDir: string;
  arm: string;
  /** 修复轮硬上限，默认 3 */
  maxRounds?: number;
  /** 错误 span 上下文行数，默认 12 */
  spanContext?: number;
  /** 指标输出目录（写 metrics-<arm>.json），默认 outDir 的同级 .work */
  metricsDir?: string;
  /** 选择期/前置阶段已消耗的 input token，seed 进 total（arm 语义由 runner 注入，repairLoop 保持 arm-agnostic） */
  priorInputTok?: number;
  /** 选择期/前置阶段已消耗的 output token，seed 进 total */
  priorOutputTok?: number;
  /** 其中属于"披露/选择期"的 input，单列进 disclosure_input_tok（不含 generate/repair） */
  disclosureInputTok?: number;
  /** 其中属于"披露/选择期"的 output，单列进 disclosure_output_tok */
  disclosureOutputTok?: number;
  /**
   * 修复模式（LLM 翻转开关，agent-native 设计）：
   *  - "llm"（默认）：gate 失败时 client 侧调 LLM 跑有界修复轮（全自动 shell 路径用）。
   *  - "none"：不调任何 LLM。gate 失败即停在 round-0，残留诊断经 RepairResult.unresolved 回传，
   *    交给宿主 agent（client 侧的 Claude）修。MCP/agent-native 路径用这个，server 侧零 LLM。
   */
  repairMode?: "llm" | "none";
}

export interface RepairResult {
  metrics: AssemblyMetrics;
  finalGate: GateResult;
  outDir: string;
  /** 分层提交用：每层涉及的文件相对路径（picked=pick落盘+barrel, generated=generate内容, deterministic=prisma/env, repair-round-N=该轮override）。 */
  layers: { label: string; files: string[] }[];
  /** repairMode="none" 且未收敛时，未解决的诊断（供宿主 agent 接手修）。 */
  unresolved?: GateResult["diagnostics"];
}

/**
 * barrel / 锚点宿主文件黑名单（#3）：整文件 AI override 会丢失 loom 锚点与已 append 内容，
 * 且循环不重物化 = 永久丢失。这些文件只能由确定性 fixer 改。
 */
const OVERRIDE_BLACKLIST = [
  "src/server/api/root.ts",
  "src/server/auth/config.ts",
  "src/env.js",
  "prisma/schema.prisma",
];

function isBlacklisted(file: string): boolean {
  const norm = file.replace(/\\/g, "/");
  return OVERRIDE_BLACKLIST.some((b) => norm === b || norm.endsWith("/" + b));
}

// ─────────────────────────────────────────────────────────────────────────────
// 白名单命令执行器（#10：严格只留 generate + add）
// ─────────────────────────────────────────────────────────────────────────────

export type WhitelistCmd = { kind: "prisma-generate" } | { kind: "pnpm-add"; pkgs: string[] };

export interface CmdResult {
  ok: boolean;
  code: number | null;
  stdout: string;
  stderr: string;
}

const PKG_NAME_RE = /^[@a-z0-9._/-]+(@[\w.\-^~*x]+)?$/i;

/** 在 outDir 跑白名单命令。失败不抛（#9），由调用方记日志 + round 标记。 */
export function runWhitelisted(outDir: string, cmd: WhitelistCmd, timeoutMs?: number): CmdResult {
  const isWin = process.platform === "win32";
  let bin: string;
  let args: string[];
  let defaultTimeout: number;

  if (cmd.kind === "prisma-generate") {
    bin = join(outDir, "node_modules", ".bin", isWin ? "prisma.CMD" : "prisma");
    args = ["generate"];
    defaultTimeout = 120_000;
  } else if (cmd.kind === "pnpm-add") {
    for (const p of cmd.pkgs) {
      if (!PKG_NAME_RE.test(p)) {
        return { ok: false, code: null, stdout: "", stderr: `非法包名(拒绝执行): ${p}` };
      }
    }
    bin = isWin ? "pnpm.CMD" : "pnpm";
    args = ["add", ...cmd.pkgs];
    defaultTimeout = 180_000;
  } else {
    return { ok: false, code: null, stdout: "", stderr: "命令不在白名单" };
  }

  const r = spawnSync(bin, args, {
    cwd: outDir,
    timeout: timeoutMs ?? defaultTimeout,
    encoding: "utf-8",
    shell: isWin, // Windows 下 .CMD 需要 shell
    windowsHide: true,
  });
  return { ok: r.status === 0, code: r.status, stdout: r.stdout ?? "", stderr: r.stderr ?? "" };
}

// ─────────────────────────────────────────────────────────────────────────────
// 确定性 prisma model 修复（A2a/b/c）
// ─────────────────────────────────────────────────────────────────────────────

/**
 * 直读原始 meta.json 拿 requires_prisma_model（绕过 A2a：zod LoomMeta 会 strip 该字段）。
 * 与 loadCandidates 的 zod 解析路径平行，故意不经过它。
 */
function readRawPrismaModel(candDir: string): string | null {
  const metaPath = join(candDir, "meta.json");
  if (!existsSync(metaPath)) return null;
  try {
    const raw = JSON.parse(readFileSync(metaPath, "utf-8"));
    const v = raw?.registry_item?.meta_loom?.requires_prisma_model;
    return typeof v === "string" && v.trim() ? v.trim() : null;
  } catch {
    return null;
  }
}

/** 从 plan 的 pick/adapt 决策派生需要的 prisma model 名（去重）。 */
export function derivePrismaModels(
  plan: AssemblyPlan,
  candidates: Map<string, Map<string, CandidateMeta>>,
): string[] {
  const models = new Set<string>();
  for (const d of plan.seams) {
    // pick 和 adapt 都落候选文件、都可能需要 prisma model（adapt 只是额外加胶水）
    if ((d.action !== "pick" && d.action !== "adapt") || !d.ref) continue;
    const meta = candidates.get(d.seam_id)?.get(d.ref);
    if (!meta) continue;
    const m = readRawPrismaModel(meta.dir);
    if (m) models.add(m);
  }
  return [...models];
}

/**
 * 内置 model 体模板。与 project.ts 实际用法精确对齐（id/name/description?/createdAt），
 * **无 relation 必填列**——否则 create({name,description}) 会因缺字段再报错。
 */
function prismaModelBody(name: string): string {
  return [
    `model ${name} {`,
    `    id          String   @id @default(cuid())`,
    `    name        String`,
    `    description String?`,
    `    createdAt   DateTime @default(now())`,
    `    updatedAt   DateTime @updatedAt`,
    ``,
    `    @@index([name])`,
    `}`,
  ].join("\n");
}

const PRISMA_ANCHOR = "// <loom-anchor:prisma-models>";

/**
 * 在 schema.prisma 的 prisma-models 锚点前插入 model 体（幂等）。
 * 与 materialize.appendAtAnchor 语义对齐——若 materialize 改动锚点逻辑需同步此处。
 */
export function applyPrismaModels(
  outDir: string,
  models: string[],
): { appended: string[]; alreadyPresent: string[] } {
  const appended: string[] = [];
  const alreadyPresent: string[] = [];
  if (models.length === 0) return { appended, alreadyPresent };

  const schemaPath = join(outDir, "prisma/schema.prisma");
  if (!existsSync(schemaPath)) return { appended, alreadyPresent };

  let content = readFileSync(schemaPath, "utf-8");
  for (const name of models) {
    if (new RegExp(`\\bmodel\\s+${name}\\b`).test(content)) {
      alreadyPresent.push(name);
      continue;
    }
    const idx = content.indexOf(PRISMA_ANCHOR);
    const body = prismaModelBody(name) + "\n\n";
    if (idx === -1) {
      // 锚点缺失：append 到文件尾（兜底）
      content = content + "\n" + body;
    } else {
      const lineStart = content.lastIndexOf("\n", idx) + 1;
      content = content.slice(0, lineStart) + body + content.slice(lineStart);
    }
    appended.push(name);
  }
  writeFileSync(schemaPath, content, "utf-8");
  return { appended, alreadyPresent };
}

// ─────────────────────────────────────────────────────────────────────────────
// generate 接缝内容生成（A3）
// ─────────────────────────────────────────────────────────────────────────────

const GENERATE_SYS = [
  "你是资深 TypeScript/Next.js(App Router, React 19) 工程师。",
  "为给定接缝生成一个完整、可直接编译通过的源文件。",
  "硬约束：",
  "1. 只输出该文件的完整内容，包在单个 ``` 代码块里，不要解释。",
  "2. 环境**无法安装任何 npm 包**：禁止引入 xlsx/exceljs/papaparse/date-fns 等任何第三方库。日期用 Intl/toISOString，导出用浏览器原生 Blob + URL.createObjectURL 实现 CSV 下载。",
  "3. 禁止 `as any`、`@ts-ignore`、`@ts-expect-error`、空函数体占位。所有类型必须真实成立。",
  "4. 严格按给定的文件路径、签名与复用类型实现，不要重定义已存在的类型。",
].join("\n");

/** 为每个 action=generate 的接缝调 AI 产文件内容。唯一一次 LLM 产物，喂给 round-0 materialize。 */
export async function generateContents(
  plan: AssemblyPlan,
): Promise<{ contents: Map<string, string>; input_tok: number; output_tok: number; notes: string[] }> {
  const contents = new Map<string, string>();
  const notes: string[] = [];
  let input_tok = 0;
  let output_tok = 0;

  for (const d of plan.seams) {
    if (d.action !== "generate") continue;
    const target = d.generated_file;
    if (!target) {
      notes.push(`接缝 ${d.seam_id} 是 generate 但缺 generated_file，跳过`);
      continue;
    }

    // A3 路径矛盾处置：plan 的 generated_file 是客户端组件路径（materialize 只认它），
    // 与 core seam 的 server 规格冲突。有意以 plan 为准，锁死客户端方向，记日志。
    const isClient = target.includes("_components") || target.endsWith(".tsx");
    if (isClient) {
      notes.push(
        `接缝 ${d.seam_id}: 有意偏离 core seam(server Buffer 规格)，按 plan.generated_file 实现为客户端组件 ${target}`,
      );
    }

    const userMsg = [
      `接缝 ID: ${d.seam_id}`,
      `目标文件路径: ${target}`,
      `选择理由: ${d.why}`,
      ``,
      `实现要求：`,
      isClient
        ? [
            `- 这是一个 Next.js App Router 客户端组件，文件首行必须是 "use client"。`,
            `- 导出一个 React 组件 ExportButton，props: { columns: { key: string; header: string }[]; rows: Record<string, unknown>[] }`,
            `  （与 src/app/_components/data-table.tsx 的 DataTable 列/行形状一致，直接复用同形状，不要 import 它的类型）。`,
            `- 点击按钮时，把 rows 按 columns 顺序导出为 CSV 文本，用 Blob + URL.createObjectURL 触发浏览器下载。`,
            `- 处理逗号/引号/换行的 CSV 转义。零外部依赖。`,
          ].join("\n")
        : [
            `- 实现 core seam 规定的能力，自包含、可直接编译通过。`,
            `- 项目约定（必须遵守，否则编译失败）：`,
            `  · 模块别名一律用 "~/"（如 ~/server/db、~/server/api/trpc），**禁止 "@/"**。`,
            `  · 需要数据库时 import { db } from "~/server/db"（Prisma 单例）；tRPC 用 import { createTRPCRouter, protectedProcedure } from "~/server/api/trpc"。`,
            `  · **不要 import Prisma 命名空间**（不写 import { Prisma } from "@prisma/client"）；用 TS 原生类型自定义形状。`,
            `  · 禁止引入任何新 npm 包（环境不能装包）；只用项目已有依赖 + 浏览器/Node 原生 API。`,
            `  · 输出必须是语法完整的 TS 文件（括号/注释闭合），禁止 as any/@ts-ignore。`,
          ].join("\n"),
    ].join("\n");

    const { text, usage } = await complete(GENERATE_SYS, userMsg, 8192);
    input_tok += usage.input_tok;
    output_tok += usage.output_tok;
    const code = extractCode(text);
    if (!fenceComplete(text) || rejectIfDegraded(code) || !looksLikeCode(code)) {
      notes.push(`接缝 ${d.seam_id}: 生成内容被拒（截断或含退化标记），留空待修复轮处理`);
      continue;
    }
    contents.set(d.seam_id, code);
  }

  return { contents, input_tok, output_tok, notes };
}

// ─────────────────────────────────────────────────────────────────────────────
// 修复轮：错误聚合 + override 守门
// ─────────────────────────────────────────────────────────────────────────────

export interface FileErrorGroup {
  file: string;
  codes: number[];
  messages: string[];
  snippet: string;
  firstLine: number;
}

/** 按文件聚合诊断，取覆盖所有错误行的 ±span 行 span 片段（带行号）。 */
export function aggregateByFile(diags: Diagnostic[], outDir: string, span: number): FileErrorGroup[] {
  const byFile = new Map<string, Diagnostic[]>();
  for (const d of diags) {
    if (d.file === "(global)") continue;
    if (!byFile.has(d.file)) byFile.set(d.file, []);
    byFile.get(d.file)!.push(d);
  }

  const groups: FileErrorGroup[] = [];
  for (const [file, ds] of byFile) {
    const abs = join(outDir, file);
    if (!existsSync(abs)) continue;
    const lines = readFileSync(abs, "utf-8").split("\n");
    const errLines = ds.map((d) => d.line).filter((n) => n > 0);
    const lo = Math.max(1, Math.min(...errLines) - span);
    const hi = Math.min(lines.length, Math.max(...errLines) + span);
    const snippet = lines
      .slice(lo - 1, hi)
      .map((l, i) => `${lo + i} | ${l}`)
      .join("\n");
    groups.push({
      file,
      codes: ds.map((d) => d.code),
      messages: ds.map((d) => `TS${d.code} @${d.line}:${d.column} ${d.message}`),
      snippet,
      firstLine: lo,
    });
  }
  return groups;
}

/** 代码块 fence 是否完整闭合（#7：防整文件 override 截断写坏）。 */
function fenceComplete(text: string): boolean {
  const fences = (text.match(/```/g) ?? []).length;
  return fences >= 2; // 至少一对开闭
}

/** 退化标记守门（A5）：含 as any / @ts-ignore / @ts-expect-error 则拒绝。 */
function rejectIfDegraded(code: string): boolean {
  return /\bas\s+any\b|@ts-ignore|@ts-expect-error/.test(code);
}

/**
 * 噪声守门：AI 有时把 agentic 行动描述（read_file:、I'll、让我…）当文件内容塞进 fence。
 * 校验首个非空行是合法 TS 文件起始（import/export/注释/use client/类型声明等）。
 * 拦不住所有情况，但能挡住明显非源码的回复，防止写坏文件后修复轮发散。
 */
function looksLikeCode(code: string): boolean {
  const firstLine = code.split("\n").map((l) => l.trim()).find((l) => l.length > 0) ?? "";
  if (/^(read_file|write_file|I'?ll|let me|here'?s|我|让我|首先|step\b)/i.test(firstLine)) return false;
  return /^(import|export|"use client"|'use client'|\/\/|\/\*|\*|type|interface|const|function|class|async|@|\{|\}|package|model|generator|datasource)/.test(
    firstLine,
  );
}

/** 行级 diff 行数（新增+删除的近似：对称差的行数）。 */
function countDiffLines(oldText: string, newText: string): number {
  const a = new Set(oldText.split("\n"));
  const b = new Set(newText.split("\n"));
  let n = 0;
  for (const l of a) if (!b.has(l)) n++;
  for (const l of b) if (!a.has(l)) n++;
  return n;
}

const REPAIR_SYS = [
  "你是资深 TypeScript 工程师，正在修复一个 Next.js(App Router) + tRPC v11 + Prisma + NextAuth v5 项目的类型错误。",
  "给你一个文件的错误列表与上下文片段，你要输出**整个文件**的修正版本。",
  "硬约束：",
  "1. 只输出该文件完整内容，包在单个 ``` 代码块里，不要解释。",
  "2. 禁止 `as any`、`@ts-ignore`、`@ts-expect-error`、删除业务逻辑、把函数体改空来消除错误。必须真正修复类型。",
  "3. 不要改动文件里与错误无关的部分；保留所有 import 与导出签名。",
  "4. 环境**不能安装任何新 npm 包**。若错误是 TS2307(找不到模块/缺依赖)，不要保留该 import——改用项目已有依赖或浏览器/Node 原生 API 重写（如日期格式化用 Intl/toISOString，导出用 Blob+URL.createObjectURL），彻底移除对缺失包的引用。",
].join("\n");

function buildFilePrompt(grp: FileErrorGroup): string {
  return [
    `文件: ${grp.file}`,
    `错误:`,
    ...grp.messages.map((m) => `  - ${m}`),
    ``,
    `上下文片段（行号 | 内容）:`,
    grp.snippet,
    ``,
    `请输出修正后的完整文件内容。`,
  ].join("\n");
}

/** 从一段源码里提取 import 的第三方包名（用于判断是否需要 pnpm add）。 */
function extractBarePackages(code: string): string[] {
  const pkgs = new Set<string>();
  const re = /(?:import|from|require\()\s*['"]([^'".][^'"]*)['"]/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(code))) {
    const spec = m[1];
    if (spec.startsWith(".") || spec.startsWith("~") || spec.startsWith("@/") || spec.startsWith("node:")) continue;
    // 取包名（@scope/pkg 或 pkg），剥掉子路径
    const parts = spec.split("/");
    const name = spec.startsWith("@") ? parts.slice(0, 2).join("/") : parts[0];
    pkgs.add(name);
  }
  return [...pkgs];
}

// 已在 base 里的依赖（不需要 pnpm add）
const KNOWN_DEPS = new Set([
  "react", "react-dom", "next", "next-auth", "zod", "superjson", "server-only",
  "@prisma/client", "@auth/prisma-adapter", "@t3-oss/env-nextjs",
  "@trpc/client", "@trpc/server", "@trpc/react-query", "@tanstack/react-query",
]);

// ─────────────────────────────────────────────────────────────────────────────
// 指标持久化（A4）
// ─────────────────────────────────────────────────────────────────────────────

function persistMetrics(metricsDir: string, arm: string, metrics: AssemblyMetrics): string {
  mkdirSync(metricsDir, { recursive: true });
  // 文件名带 idea_id，避免多想法铺宽时互相覆盖（M2）
  const out = join(metricsDir, `metrics-${arm}-${metrics.idea_id}.json`);
  // 写前 zod 校验形状合法
  const validated = AssemblyMetrics.parse(metrics);
  writeFileSync(out, JSON.stringify(validated, null, 2), "utf-8");
  return out;
}

// ─────────────────────────────────────────────────────────────────────────────
// 主循环
// ─────────────────────────────────────────────────────────────────────────────

export async function repairLoop(cfg: RepairConfig): Promise<RepairResult> {
  const maxRounds = cfg.maxRounds ?? 3;
  const span = cfg.spanContext ?? 12;
  const metricsDir = cfg.metricsDir ?? join(dirname(cfg.outDir), ".work");

  const rounds: RepairRound[] = [];
  let totalInput = cfg.priorInputTok ?? 0;
  let totalOutput = cfg.priorOutputTok ?? 0;
  let retryInput = 0;
  let diffLines = 0;

  const log = (msg: string) => console.log(`[repair] ${msg}`);

  // ── A. generate 内容（唯一一次 LLM 产物 → materialize）
  log("生成 generate 接缝内容…");
  const gen = await generateContents(cfg.plan);
  totalInput += gen.input_tok;
  totalOutput += gen.output_tok;
  for (const n of gen.notes) log("  " + n);

  // ── B. round-0 物化（唯一一次 materialize，注入 generate 内容）
  log("round-0 物化…");
  const mat = materialize({
    plan: cfg.plan,
    candidates: cfg.candidates,
    coreSeams: cfg.coreSeams,
    baseDir: cfg.baseDir,
    outDir: cfg.outDir,
    generatedContent: gen.contents,
  });
  log(`  物化 ${mat.changes.length} 项变更, deps=${JSON.stringify(mat.deps)}, env=${JSON.stringify(mat.envVars)}`);

  // ── C. 确定性 pre-AI fixers（就地改，不重物化）
  const models = derivePrismaModels(cfg.plan, cfg.candidates);
  const pm = applyPrismaModels(cfg.outDir, models);
  if (pm.appended.length) log(`  prisma model append: ${pm.appended.join(", ")}`);
  if (pm.alreadyPresent.length) log(`  prisma model 已存在: ${pm.alreadyPresent.join(", ")}`);

  const envR = injectEnv(cfg.outDir, mat.envVars);
  if (envR.injected.length) log(`  env 注入: ${envR.injected.join(", ")}`);

  // 依赖策略（已改为强约束无依赖）：pnpm add 在 cpSync 物化出的 outDir 里结构性跑不通
  //（node_modules 符号链接到 base 的 .pnpm 虚拟 store，复制后 pnpm 拒绝 add）。
  // 故不装包：若候选声明了 deps，只告警（缺口会留在 gate 里促使换无依赖写法）；
  // schema 改了就显式 prisma generate（它不装包，不受虚拟 store 问题影响）。
  const planDeps = mat.deps.map((d) => `${d.name}@${d.version}`);
  if (planDeps.length > 0) {
    log(`  ⚠ 候选声明了依赖 ${planDeps.join(" ")}，但已禁用 pnpm add（强约束无依赖）。缺口将体现在 gate。`);
  }
  if (pm.appended.length > 0) {
    log(`  prisma generate（schema 已改，重生成 client 类型）`);
    const r = runWhitelisted(cfg.outDir, { kind: "prisma-generate" });
    if (!r.ok) log(`  ⚠ prisma generate 失败(code=${r.code}): ${r.stderr.slice(0, 200)}`);
  }

  // 分层收集（T12 分层 commit 用）：从 materialize changes 分出 picked / generated
  const layers: { label: string; files: string[] }[] = [];
  const pickedFiles = new Set<string>();
  const generatedFiles = new Set<string>();
  for (const ch of mat.changes) {
    if (ch.kind === "barrel-append") continue; // barrel 宿主归 deterministic（锚点宿主文件）
    if (ch.detail && ch.detail.includes("generate")) generatedFiles.add(ch.target);
    else if (ch.kind === "file-add") pickedFiles.add(ch.target);
  }
  if (pickedFiles.size) layers.push({ label: "picked", files: [...pickedFiles] });
  if (generatedFiles.size) layers.push({ label: "generated", files: [...generatedFiles] });
  // 确定性层：prisma schema（若 append 了 model）+ env.js/.env（若注入）+ barrel 宿主
  const detFiles = new Set<string>();
  if (pm.appended.length) detFiles.add("prisma/schema.prisma");
  if (envR.injected.length) { detFiles.add("src/env.js"); detFiles.add(".env"); }
  for (const ch of mat.changes) if (ch.kind === "barrel-append") detFiles.add(ch.target);
  if (detFiles.size) layers.push({ label: "deterministic", files: [...detFiles] });

  // ── D. round-0 初始 gate（修复 token 必须 0）
  let g = gate(cfg.outDir);
  rounds.push({
    round_index: 0,
    error_count: g.errorCount,
    error_fingerprints: g.fingerprints,
    input_tok: 0,
    output_tok: 0,
    auto_fixed: 0,
  });
  log(`round-0 gate: errorCount=${g.errorCount}, fingerprints=${JSON.stringify(g.fingerprints)}`);

  let converged = g.errorCount === 0;

  // ── E. 修复轮 1..maxRounds
  // repairMode="none"：不调 LLM，gate 失败即停，残留诊断回传给宿主 agent 修（LLM 翻转）。
  const repairMode = cfg.repairMode ?? "llm";
  if (!converged && repairMode === "none") {
    log(`repairMode=none：gate 残留 ${g.errorCount} 错，不调 LLM，交回宿主 agent 修复`);
  }
  if (!converged && repairMode !== "none") {
    let prevFp = new Set(g.fingerprints);
    let prevCount = g.errorCount;

    for (let round = 1; round <= maxRounds; round++) {
      const groups = aggregateByFile(g.diagnostics, cfg.outDir, span);
      let roundIn = 0;
      let roundOut = 0;
      let autoFixed = 0;
      const touchedPkgs = new Set<string>();
      const roundFiles = new Set<string>();

      for (const grp of groups) {
        if (isBlacklisted(grp.file)) {
          log(`  round ${round}: 跳过黑名单文件 ${grp.file}（只由确定性 fixer 处理）`);
          continue;
        }
        const { text, usage } = await complete(REPAIR_SYS, buildFilePrompt(grp), 8192);
        roundIn += usage.input_tok;
        roundOut += usage.output_tok;
        const code = extractCode(text);
        if (!fenceComplete(text)) {
          log(`  round ${round}: ${grp.file} 回复 fence 不完整，丢弃`);
          continue;
        }
        if (rejectIfDegraded(code)) {
          log(`  round ${round}: ${grp.file} 含退化标记(as any/@ts-ignore)，丢弃`);
          continue;
        }
        if (!looksLikeCode(code)) {
          log(`  round ${round}: ${grp.file} 回复非源码（疑似行动描述/噪声），丢弃`);
          continue;
        }
        const abs = join(cfg.outDir, grp.file);
        const oldText = readFileSync(abs, "utf-8");
        diffLines += countDiffLines(oldText, code);
        writeFileSync(abs, code, "utf-8");
        roundFiles.add(grp.file);
        autoFixed += grp.codes.length;
        for (const p of extractBarePackages(code)) {
          if (!KNOWN_DEPS.has(p)) touchedPkgs.add(p);
        }
      }

      // AI 引入新包：已禁用 pnpm add（强约束无依赖）。不装包，只告警——
      // import 缺包的 TS2307 会留在 gate 里，促使下一轮 AI 换无依赖写法。
      if (touchedPkgs.size > 0) {
        log(`  round ${round}: AI 引入新包 ${[...touchedPkgs].join(" ")}，但已禁用装包。缺口留在 gate 促使换原生写法。`);
      }

      // 只重跑 gate，绝不重物化
      if (roundFiles.size) layers.push({ label: `repair-round-${round}`, files: [...roundFiles] });
      g = gate(cfg.outDir);
      retryInput += roundIn;
      totalInput += roundIn;
      totalOutput += roundOut;
      rounds.push({
        round_index: round,
        error_count: g.errorCount,
        error_fingerprints: g.fingerprints,
        input_tok: roundIn,
        output_tok: roundOut,
        auto_fixed: autoFixed,
      });
      log(`  round ${round} gate: errorCount=${g.errorCount}, fingerprints=${JSON.stringify(g.fingerprints)}`);

      if (g.errorCount === 0) {
        converged = true;
        break;
      }

      // A6 收敛判据：fingerprint 集严格收窄 OR error_count 严格下降
      const curFp = new Set(g.fingerprints);
      const fpNarrowed = curFp.size < prevFp.size && [...curFp].every((f) => prevFp.has(f));
      const countDropped = g.errorCount < prevCount;
      if (!fpNarrowed && !countDropped) {
        log(`  round ${round}: 指纹未收窄且错误数未降 → 判定 thrash，提前止损`);
        break;
      }
      prevFp = curFp;
      prevCount = g.errorCount;
    }
  }

  // ── 收尾指标
  const totalDecisions = cfg.plan.seams.filter((s) => s.action !== "skip").length;
  const writeOwn = cfg.plan.seams.filter((s) => s.action === "generate").length;
  const metrics: AssemblyMetrics = AssemblyMetrics.parse({
    arm: cfg.arm,
    idea_id: cfg.plan.idea_id,
    total_input_tok: totalInput,
    total_output_tok: totalOutput,
    retry_input_tok: retryInput,
    disclosure_input_tok: cfg.disclosureInputTok ?? 0,
    disclosure_output_tok: cfg.disclosureOutputTok ?? 0,
    rounds,
    converged,
    final_error_count: g.errorCount,
    write_own_ratio: totalDecisions > 0 ? writeOwn / totalDecisions : 0,
    fix_diff_lines: diffLines,
  });

  const metricsPath = persistMetrics(metricsDir, cfg.arm, metrics);
  log(`converged=${converged} final_error=${g.errorCount} 指标写入 ${metricsPath}`);

  // 真实信号：把本次 gate 结果转成 per-候选 success/failure 写 outcomes 文件，
  // platform 下次启动消费驱动飞轮(不依赖 agent 主动回报)。LOOM_OUTCOMES_PATH 未设则跳过。
  try {
    const outcomes = computeOutcomes(cfg.plan, cfg.candidates, g);
    if (emitOutcomes(outcomes)) {
      log(`真实信号已产出：${outcomes.length} 个候选(success=${outcomes.filter((o) => o.success).length})`);
    }
  } catch (e) {
    log(`产出真实信号失败(不影响物化): ${e instanceof Error ? e.message : String(e)}`);
  }

  return {
    metrics,
    finalGate: g,
    outDir: cfg.outDir,
    layers,
    unresolved: converged ? undefined : g.diagnostics,
  };
}
