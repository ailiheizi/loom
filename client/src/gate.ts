/**
 * 闸门：用 ts-morph 对物化后的项目做全项目类型诊断（getPreEmitDiagnostics）。
 * 诊断源与 tsc --noEmit 等价，但同步、结构化、无 LSP 推送假绿 race。
 */
import { Project } from "ts-morph";
import { join } from "node:path";
import { existsSync } from "node:fs";
import type { Diagnostic } from "./contracts.js";

export interface GateResult {
  errorCount: number;
  diagnostics: Diagnostic[];
  /** 错误指纹集（file:code 去重排序），用于修复循环的震荡检测 */
  fingerprints: string[];
}

export function gate(projectDir: string): GateResult {
  const tsconfig = join(projectDir, "tsconfig.json");
  if (!existsSync(tsconfig)) {
    throw new Error(`tsconfig 不存在: ${tsconfig}`);
  }

  const project = new Project({
    tsConfigFilePath: tsconfig,
    skipAddingFilesFromTsConfig: false,
  });

  const diags = project.getPreEmitDiagnostics();
  const diagnostics: Diagnostic[] = [];

  for (const d of diags) {
    if (d.getCategory() !== 1 /* DiagnosticCategory.Error */) continue;
    const sourceFile = d.getSourceFile();
    const start = d.getStart();
    let line = 0;
    let column = 0;
    let file = "(global)";
    if (sourceFile && start !== undefined) {
      file = sourceFile.getFilePath().replace(projectDir.replace(/\\/g, "/"), "").replace(/^\//, "");
      const lc = sourceFile.getLineAndColumnAtPos(start);
      line = lc.line;
      column = lc.column;
    }
    const msgText = d.getMessageText();
    const message = typeof msgText === "string" ? msgText : msgText.getMessageText();
    diagnostics.push({
      file,
      line,
      column,
      code: d.getCode(),
      message,
      category: "error",
    });
  }

  const fingerprints = [...new Set(diagnostics.map((d) => `${d.file}:${d.code}`))].sort();
  return { errorCount: diagnostics.length, diagnostics, fingerprints };
}
