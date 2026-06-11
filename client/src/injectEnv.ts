/**
 * envVars 注入：把候选需要的环境变量 append 进 t3 的 src/env.js。
 *
 * t3 的 env.js 用 @t3-oss/env-nextjs，启动期 zod 校验，缺变量会 throw。
 * 必须同时往两处 append（都是已注入的锚点）：
 *   1. server: {...}  的 zod schema —— 锚点 // <loom-anchor:env-server>
 *   2. runtimeEnv: {...} 的解构 —— 锚点 // <loom-anchor:env-runtime>
 * 并写 .env / .env.example 占位值，否则 dev 启动期校验仍 throw。
 *
 * 幂等：已存在同名变量则跳过。
 */
import { readFileSync, writeFileSync, existsSync, appendFileSync } from "node:fs";
import { join } from "node:path";

const ANCHOR_SERVER = "// <loom-anchor:env-server>";
const ANCHOR_RUNTIME = "// <loom-anchor:env-runtime>";

export interface InjectEnvResult {
  injected: string[];
  skipped: string[];
}

function insertBeforeAnchor(content: string, anchor: string, snippet: string): string {
  const idx = content.indexOf(anchor);
  if (idx === -1) return content;
  const lineStart = content.lastIndexOf("\n", idx) + 1;
  const indent = content.slice(lineStart, idx);
  return content.slice(0, lineStart) + `${indent}${snippet}\n` + content.slice(lineStart);
}

export function injectEnv(projectDir: string, envVars: string[]): InjectEnvResult {
  const envJsPath = join(projectDir, "src/env.js");
  const injected: string[] = [];
  const skipped: string[] = [];
  if (!existsSync(envJsPath) || envVars.length === 0) {
    return { injected, skipped: envVars };
  }

  let content = readFileSync(envJsPath, "utf-8");

  for (const name of envVars) {
    // 幂等：env.js 里已声明就跳过
    if (new RegExp(`\\b${name}\\b`).test(content)) {
      skipped.push(name);
      continue;
    }
    // 1. server schema：所有注入变量按 string 处理（OAuth secret 都是必填 string）
    content = insertBeforeAnchor(content, ANCHOR_SERVER, `${name}: z.string(),`);
    // 2. runtimeEnv 解构
    content = insertBeforeAnchor(content, ANCHOR_RUNTIME, `${name}: process.env.${name},`);
    injected.push(name);
  }

  writeFileSync(envJsPath, content, "utf-8");

  // 3. 写 .env / .env.example 占位（dev 启动期校验需要真值，给占位字符串）
  if (injected.length > 0) {
    const exampleLines = injected.map((n) => `${n}=""`).join("\n") + "\n";
    const envExamplePath = join(projectDir, ".env.example");
    const envPath = join(projectDir, ".env");
    appendFileSync(envExamplePath, `\n# injected by loom\n${exampleLines}`, "utf-8");
    // .env 给非空占位，否则 emptyStringAsUndefined + z.string() 仍 throw
    const devLines = injected.map((n) => `${n}="loom-dev-placeholder"`).join("\n") + "\n";
    if (existsSync(envPath)) {
      appendFileSync(envPath, `\n# injected by loom\n${devLines}`, "utf-8");
    } else {
      writeFileSync(envPath, devLines, "utf-8");
    }
  }

  return { injected, skipped };
}
