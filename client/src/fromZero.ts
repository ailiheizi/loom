/**
 * T9 从零臂（from_zero）：不给任何候选，让 AI 为每个 seam 从零生成文件，
 * 然后**包装成与策展候选字节同构的 synthetic 候选库**，喂给与组装臂完全相同的
 * materialize→derivePrismaModels→applyPrismaModels→injectEnv→gate→repairLoop。
 *
 * 公平性核心（见 plan 支点1）：from_zero 不走独立代码路径。唯一变量 = 候选字节的作者
 * （手工策展 vs AI 临场写），其余逐行相同。因此：
 *  - prompt 只给 core 公开契约（intent + signature + target + barrel 锚点规格），绝不给候选代码。
 *  - infra 信号与组装臂同源：auth seam 的 synthetic meta 写 env_vars；data seam 写 requires_prisma_model。
 *  - report 接缝也对称化为 pick→synthetic 候选（组装臂那侧是 generate，这里统一成"从 synthetic 候选 pick"，
 *    区别只在候选谁写的），保持两臂结构对称。
 */
import { writeFileSync, mkdirSync, rmSync, existsSync } from "node:fs";
import { join, basename } from "node:path";
import { complete, extractCode } from "./llm.js";
import type { MaterializeInput } from "./materialize.js";
import { AssemblyPlan, type SelectionDecision } from "./contracts.js";

type CoreSeam = MaterializeInput["coreSeams"][number] & {
  signature?: string;
  target?: string;
  env_vars?: string[];
  kind?: string;
};

export interface FromZeroResult {
  plan: AssemblyPlan;
  candidatesDir: string;
  input_tok: number;
  output_tok: number;
  notes: string[];
}

const FROMZERO_SYS = [
  "你是资深 TypeScript/Next.js(App Router, React 19) + tRPC v11 + Prisma + NextAuth v5 工程师。",
  "从零为给定接缝实现一个完整、可直接编译的源文件（不参考任何现成候选）。",
  "硬约束：",
  "1. 只输出该文件完整内容，包在单个 ``` 代码块里，不要解释。",
  "2. 严格符合给定的接口签名(signature)与目标路径(target)。",
  "3. 禁止 `as any`、`@ts-ignore`、`@ts-expect-error`、空函数体占位。类型必须真实成立。",
  "4. 优先零运行时依赖；导出类功能用浏览器原生 API（Blob + URL.createObjectURL）实现，不引 npm 包。",
].join("\n");

function fenceComplete(text: string): boolean {
  return (text.match(/```/g) ?? []).length >= 2;
}
function rejectIfDegraded(code: string): boolean {
  return /\bas\s+any\b|@ts-ignore|@ts-expect-error/.test(code);
}
function looksLikeCode(code: string): boolean {
  const firstLine = code.split("\n").map((l) => l.trim()).find((l) => l.length > 0) ?? "";
  if (/^(read_file|write_file|I'?ll|let me|here'?s|我|让我|首先|step\b)/i.test(firstLine)) return false;
  return /^(import|export|"use client"|'use client'|\/\/|\/\*|\*|type|interface|const|function|class|async|@|\{|\})/.test(
    firstLine,
  );
}

/** 为某 seam 生成目标文件名（落在 seam.target 下）。 */
function targetFileFor(seam: CoreSeam): string {
  const t = seam.target ?? "src/";
  // target 是目录则补一个按 seam 命名的文件
  const leaf = seam.seam_id.split(".").pop() ?? "module";
  if (t.endsWith("/")) {
    const ext = seam.kind === "ui-component" || t.includes("_components") ? "tsx" : "ts";
    return `${t}fz-${leaf}.${ext}`;
  }
  return t;
}

/** 把 AI 产物写成一个与策展候选同构的 synthetic 候选（meta.json + files/）。 */
function writeSyntheticCandidate(
  candidatesDir: string,
  seam: CoreSeam,
  ref: string,
  target: string,
  content: string,
): { barrel_snippet: { import?: string; register?: string }; envVars: string[]; prismaModel: string | null } {
  const candRoot = join(candidatesDir, seam.seam_id, ref);
  const fileName = basename(target);
  mkdirSync(join(candRoot, "files"), { recursive: true });
  writeFileSync(join(candRoot, "files", fileName), content, "utf-8");

  // infra 信号与组装臂同源
  const isAuth = seam.seam_id === "auth.oauth_provider";
  const isData = seam.seam_id === "data.crud_resource";
  const envVars = isAuth ? ["AUTH_GOOGLE_ID", "AUTH_GOOGLE_SECRET"] : [];
  const prismaModel = isData ? "Project" : null;

  // barrel snippet：仅当 seam 有接入口锚点时给（与策展候选一致）
  const barrel_snippet: { import?: string; register?: string } = {};
  const hasAnchor = seam.barrel?.anchor_import || seam.barrel?.anchor_register;
  if (hasAnchor) {
    // 从 content 里抽第一个 export 名做 register（best-effort，与策展候选手写的等价）
    const expMatch = content.match(/export\s+(?:const|function)\s+(\w+)/);
    const expName = expMatch ? expMatch[1] : `fz_${seam.seam_id.replace(/\W/g, "_")}`;
    // 用相对 target 的模块路径（与候选 barrel_snippet.import 同形）
    const modPath = "~/" + target.replace(/^src\//, "").replace(/\.tsx?$/, "");
    if (seam.barrel.anchor_import) barrel_snippet.import = `import { ${expName} } from "${modPath}";`;
    if (seam.barrel.anchor_register) {
      // register 片段必须匹配 barrel.op：array-append（如 auth providers[]）用裸值，
      // object-key-append（如 trpc appRouter{}）用 key: value。用错会注入坏语法进黑名单文件。
      barrel_snippet.register =
        seam.barrel.op === "array-append"
          ? `${expName},`
          : `${seam.seam_id.split(".").pop()}: ${expName},`;
    }
  }

  const meta = {
    registry_item: {
      name: ref,
      type: "registry:lib",
      title: `from-zero ${seam.seam_id}`,
      description: `T9 从零臂为 ${seam.seam_id} 临场生成`,
      dependencies: [],
      registry_dependencies: [],
      files: [{ path: `files/${fileName}`, type: "registry:lib", target, hash: null }],
      css_vars: {},
      env_vars: Object.fromEntries(envVars.map((e) => [e, ""])),
      meta_loom: {
        seam_id: seam.seam_id,
        interface_sig: seam.signature ?? "",
        provenance: "synthesized",
        health: 1.0,
        content_hash: null,
        license: "MIT",
        ext_pkgs: [],
        ...(prismaModel ? { requires_prisma_model: prismaModel } : {}),
      },
    },
    l0: {
      ref,
      seam_id: seam.seam_id,
      summary: `from-zero ${seam.seam_id}`,
      deps: [],
      loc: content.split("\n").length,
      health: 1.0,
      provenance: "synthesized",
      content_hash: null,
    },
    l1: { ref, content_hash: null, exports: [], types: [], imports: [] },
    barrel_snippet,
  };
  writeFileSync(join(candRoot, "meta.json"), JSON.stringify(meta, null, 2), "utf-8");
  return { barrel_snippet, envVars, prismaModel };
}

/** 从零臂主函数：为每个 seam 生成 synthetic 候选 + 合成 pick plan。 */
export async function generateFromZero(
  idea: { idea_id: string; core_ref: string; capability_intents: Array<{ intent: string; seam_id: string; notes?: string }> },
  coreSeams: CoreSeam[],
  candidatesDir: string,
): Promise<FromZeroResult> {
  // 干净重建 synthetic 候选库
  if (existsSync(candidatesDir)) rmSync(candidatesDir, { recursive: true, force: true });
  mkdirSync(candidatesDir, { recursive: true });

  const seamById = new Map(coreSeams.map((s) => [s.seam_id, s]));
  const decisions: SelectionDecision[] = [];
  const notes: string[] = [];
  let input_tok = 0;
  let output_tok = 0;

  for (const intent of idea.capability_intents) {
    const seam = seamById.get(intent.seam_id);
    if (!seam) {
      notes.push(`想法 intent ${intent.seam_id} 无对应 core seam，跳过`);
      continue;
    }
    const target = targetFileFor(seam);
    // per-seam 约束：与组装臂候选所基于的契约对齐（组装臂候选是按已知 schema/无依赖写的，
    // 从零臂也必须知道同样的契约，否则幻觉字段/引新依赖，差异就不再是"代码来源"而是"信息不对等"）。
    const seamConstraint = (() => {
      if (seam.seam_id === "data.crud_resource") {
        return [
          "数据约束：Project model 字段**只有** id(String) / name(String) / description(String?) / createdAt(DateTime) / updatedAt(DateTime)。",
          "不要假设 createdById、status、ownerId 等任何其他字段；CRUD 只针对上述字段。",
          "用 t3 的 ctx.db.project（Prisma delegate）与 protectedProcedure。",
        ].join("\n");
      }
      if (seam.seam_id === "report.custom_export") {
        return [
          "依赖约束（硬性）：环境**无法安装任何 npm 包**。禁止 import 任何第三方库——",
          "不要 xlsx / exceljs / papaparse / date-fns / lodash 等任何包。只能用项目已有依赖或浏览器原生 API。",
          "也不要 import 任何 Prisma 类型（不要 `import { Prisma } from '@prisma/client'`）——本项目的 prisma client 生成在 ~/generated/prisma，且导出组件用不到 Prisma 命名空间。",
          "用 TS 原生类型自定义行/列形状（如 columns: {key,header}[]、rows: Record<string,unknown>[]）。",
          "日期格式化用 `Intl.DateTimeFormat` 或 `toISOString()`；导出用 Blob + URL.createObjectURL 触发 CSV 下载。文件首行 \"use client\"。",
        ].join("\n");
      }
      if (seam.seam_id === "auth.oauth_provider") {
        return "用 next-auth v5 provider，从 ~/env 读 AUTH_GOOGLE_ID / AUTH_GOOGLE_SECRET；导出一个可加入 providers[] 的 provider 实例。";
      }
      return "";
    })();
    const userMsg = [
      `接缝 ID: ${seam.seam_id}`,
      `能力意图: ${intent.intent}`,
      intent.notes ? `备注: ${intent.notes}` : "",
      `接口签名(必须满足): ${seam.signature ?? "(未指定)"}`,
      `目标文件路径: ${target}`,
      seamConstraint,
      seam.barrel?.anchor_register ? `该文件的导出会被注册进 barrel，请用清晰的具名 export。` : "",
      `请输出该文件的完整内容。`,
    ].filter(Boolean).join("\n");

    const { text, usage } = await complete(FROMZERO_SYS, userMsg, 8192);
    input_tok += usage.input_tok;
    output_tok += usage.output_tok;
    const code = extractCode(text);
    if (!fenceComplete(text) || rejectIfDegraded(code) || !looksLikeCode(code)) {
      notes.push(`接缝 ${seam.seam_id}: 从零生成被拒（截断/退化/非源码），该 seam 留空`);
      continue;
    }
    const ref = "fz";
    writeSyntheticCandidate(candidatesDir, seam, ref, target, code);
    decisions.push({
      seam_id: seam.seam_id,
      action: "pick",
      ref,
      content_hash: null,
      adapter: null,
      generated_file: null,
      confidence: 1.0,
      why: `from_zero 臂：AI 临场生成 ${seam.seam_id}`,
    });
  }

  const plan = AssemblyPlan.parse({
    idea_id: idea.idea_id,
    core_ref: idea.core_ref,
    seams: decisions,
    synthesized: [],
    budget: { input_tok, output_tok },
  });

  return { plan, candidatesDir, input_tok, output_tok, notes };
}
