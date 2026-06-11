/**
 * Loom 跨语言契约 —— TS/zod 镜像。
 *
 * 与 platform/loom_contracts.py 的 Pydantic 模型同形状。
 * 字段名保持与 Python 一致（snake_case），因为跨语言边界传的是 JSON，
 * 字段名必须逐字匹配，不做 camelCase 转换。
 *
 * 验证方式：fixtures/ 下的样例 JSON 两侧都能 parse 通过即对拍成功。
 */

import { z } from "zod";

// ─────────────────────────────────────────────────────────────────────────────
// 枚举
// ─────────────────────────────────────────────────────────────────────────────

export const SeamAction = z.enum(["pick", "adapt", "generate", "skip"]);
export type SeamAction = z.infer<typeof SeamAction>;

export const Provenance = z.enum(["platform", "user", "synthesized"]);
export type Provenance = z.infer<typeof Provenance>;

export const BarrelOp = z.enum([
  "object-key-append",
  "array-append",
  "model-append",
  "file-add",
]);
export type BarrelOp = z.infer<typeof BarrelOp>;

export const FileType = z.enum([
  "registry:lib",
  "registry:component",
  "registry:hook",
  "registry:page",
  "registry:file",
  "registry:ui",
  "registry:block",
]);
export type FileType = z.infer<typeof FileType>;

// ─────────────────────────────────────────────────────────────────────────────
// Core seam 声明（loom.core.json）
// ─────────────────────────────────────────────────────────────────────────────

export const BarrelSpec = z.object({
  file: z.string(),
  anchor_import: z.string().nullable().default(null),
  anchor_register: z.string().nullable().default(null),
  op: BarrelOp,
});
export type BarrelSpec = z.infer<typeof BarrelSpec>;

export const SeamSpec = z.object({
  seam_id: z.string(),
  kind: z.string(),
  signature: z.string(),
  signature_ref: z.string().nullable().default(null),
  barrel: BarrelSpec,
  target: z.string(),
  compat_range: z.string().nullable().default(null),
  cardinality: z.string().default("one"),
  env_vars: z.array(z.string()).default([]),
});
export type SeamSpec = z.infer<typeof SeamSpec>;

export const CoreManifest = z.object({
  core_id: z.string(),
  core_version: z.string(),
  content_hash: z.string().nullable().default(null),
  language: z.string().default("typescript"),
  seams: z.array(SeamSpec).default([]),
});
export type CoreManifest = z.infer<typeof CoreManifest>;

// ─────────────────────────────────────────────────────────────────────────────
// 候选 registry item
// ─────────────────────────────────────────────────────────────────────────────

export const RegistryFile = z.object({
  path: z.string(),
  type: FileType.default("registry:lib"),
  target: z.string(),
  hash: z.string().nullable().default(null),
});
export type RegistryFile = z.infer<typeof RegistryFile>;

export const ExtPkg = z.object({
  name: z.string(),
  version: z.string(),
  license: z.string().nullable().default(null),
});
export type ExtPkg = z.infer<typeof ExtPkg>;

export const LoomMeta = z.object({
  seam_id: z.string(),
  interface_sig: z.string(),
  provenance: Provenance.default("platform"),
  health: z.number().min(0).max(1).default(1.0),
  content_hash: z.string().nullable().default(null),
  license: z.string().nullable().default(null),
  ext_pkgs: z.array(ExtPkg).default([]),
});
export type LoomMeta = z.infer<typeof LoomMeta>;

export const RegistryItem = z.object({
  name: z.string(),
  type: FileType.default("registry:lib"),
  title: z.string().nullable().default(null),
  description: z.string().nullable().default(null),
  dependencies: z.array(z.string()).default([]),
  registry_dependencies: z.array(z.string()).default([]),
  files: z.array(RegistryFile).default([]),
  css_vars: z.record(z.unknown()).default({}),
  env_vars: z.record(z.string()).default({}),
  meta_loom: LoomMeta,
});
export type RegistryItem = z.infer<typeof RegistryItem>;

// ─────────────────────────────────────────────────────────────────────────────
// 披露式展开各层
// ─────────────────────────────────────────────────────────────────────────────

export const L0Candidate = z.object({
  ref: z.string(),
  seam_id: z.string(),
  summary: z.string(),
  deps: z.array(z.string()).default([]),
  loc: z.number().int().default(0),
  health: z.number().default(1.0),
  provenance: Provenance.default("platform"),
  content_hash: z.string().nullable().default(null),
});
export type L0Candidate = z.infer<typeof L0Candidate>;

export const L1Export = z.object({
  name: z.string(),
  signature: z.string(),
  kind: z.string().default("function"),
});
export type L1Export = z.infer<typeof L1Export>;

export const L1Signature = z.object({
  ref: z.string(),
  content_hash: z.string().nullable().default(null),
  exports: z.array(L1Export).default([]),
  types: z.array(z.string()).default([]),
  imports: z.array(z.string()).default([]),
});
export type L1Signature = z.infer<typeof L1Signature>;

export const L2File = z.object({
  path: z.string(),
  content: z.string(),
  hash: z.string().nullable().default(null),
});
export type L2File = z.infer<typeof L2File>;

export const L2FullText = z.object({
  ref: z.string(),
  content_hash: z.string().nullable().default(null),
  files: z.array(L2File).default([]),
});
export type L2FullText = z.infer<typeof L2FullText>;

// ─────────────────────────────────────────────────────────────────────────────
// AssemblyPlan（AI 的唯一产物）
// ─────────────────────────────────────────────────────────────────────────────

export const SelectionDecision = z.object({
  seam_id: z.string(),
  action: SeamAction,
  ref: z.string().nullable().default(null),
  content_hash: z.string().nullable().default(null),
  adapter: z.string().nullable().default(null),
  generated_file: z.string().nullable().default(null),
  confidence: z.number().min(0).max(1).default(0.0),
  why: z.string().default(""),
});
export type SelectionDecision = z.infer<typeof SelectionDecision>;

export const TokenBudget = z.object({
  input_tok: z.number().int().default(0),
  output_tok: z.number().int().default(0),
});
export type TokenBudget = z.infer<typeof TokenBudget>;

export const AssemblyPlan = z.object({
  idea_id: z.string(),
  core_ref: z.string(),
  seams: z.array(SelectionDecision).default([]),
  synthesized: z.array(z.string()).default([]),
  budget: TokenBudget.default({ input_tok: 0, output_tok: 0 }),
});
export type AssemblyPlan = z.infer<typeof AssemblyPlan>;

// ─────────────────────────────────────────────────────────────────────────────
// 物化两件套
// ─────────────────────────────────────────────────────────────────────────────

export const ManifestFile = z.object({
  target: z.string(),
  source: z.string(),
  op: BarrelOp.default("file-add"),
});
export type ManifestFile = z.infer<typeof ManifestFile>;

export const BarrelMutation = z.object({
  file: z.string(),
  anchor: z.string(),
  op: BarrelOp,
  snippet: z.string(),
});
export type BarrelMutation = z.infer<typeof BarrelMutation>;

export const Manifest = z.object({
  core_ref: z.string(),
  files: z.array(ManifestFile).default([]),
  barrel_ops: z.array(BarrelMutation).default([]),
  deps: z.array(ExtPkg).default([]),
  env_vars: z.array(z.string()).default([]),
});
export type Manifest = z.infer<typeof Manifest>;

export const Lockfile = z.object({
  root: z.string().nullable().default(null),
  entries: z.record(z.string()).default({}),
});
export type Lockfile = z.infer<typeof Lockfile>;

// ─────────────────────────────────────────────────────────────────────────────
// 闸门诊断 + 指标
// ─────────────────────────────────────────────────────────────────────────────

export const Diagnostic = z.object({
  file: z.string(),
  line: z.number().int(),
  column: z.number().int(),
  code: z.number().int(),
  message: z.string(),
  category: z.string().default("error"),
});
export type Diagnostic = z.infer<typeof Diagnostic>;

export const RepairRound = z.object({
  round_index: z.number().int(),
  error_count: z.number().int(),
  error_fingerprints: z.array(z.string()).default([]),
  input_tok: z.number().int().default(0),
  output_tok: z.number().int().default(0),
  auto_fixed: z.number().int().default(0),
});
export type RepairRound = z.infer<typeof RepairRound>;

export const AssemblyMetrics = z.object({
  arm: z.string(),
  idea_id: z.string(),
  total_input_tok: z.number().int().default(0),
  total_output_tok: z.number().int().default(0),
  retry_input_tok: z.number().int().default(0),
  disclosure_input_tok: z.number().int().default(0),
  disclosure_output_tok: z.number().int().default(0),
  rounds: z.array(RepairRound).default([]),
  converged: z.boolean().default(false),
  final_error_count: z.number().int().default(0),
  write_own_ratio: z.number().default(0.0),
  fix_diff_lines: z.number().int().nullable().default(null),
  extend_diff_lines: z.number().int().nullable().default(null),
  total_delivered_lines: z.number().int().nullable().default(null),
});
export type AssemblyMetrics = z.infer<typeof AssemblyMetrics>;

// ─────────────────────────────────────────────────────────────────────────────
// h* 归因报告（与 loom_contracts.HStarReport 镜像）
// ─────────────────────────────────────────────────────────────────────────────

export const HStarReport = z.object({
  idea_id: z.string(),
  r: z.number().default(4.0),
  G: z.number().int().nullable().default(null),
  disclosure_input: z.number().int().nullable().default(null),
  delta_repair_input: z.number().int().nullable().default(null),
  amortized: z.number().nullable().default(null),
  h_star: z.number().nullable().default(null),
  status: z.string().default("pending(需from_zero基准)"),
  equiv_cost_assembly: z.number().nullable().default(null),
  equiv_cost_from_zero: z.number().nullable().default(null),
  sources: z.record(z.string()).default({}),
});
export type HStarReport = z.infer<typeof HStarReport>;
