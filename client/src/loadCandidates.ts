/**
 * 候选加载器：从 candidates/<seam>/<候选>/meta.json 读出候选，按 seam+ref 索引。
 */
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { RegistryItem, L0Candidate, L1Signature } from "./contracts.js";

export interface CandidateMeta {
  registry_item: RegistryItem;
  l0: L0Candidate;
  l1: L1Signature;
  /** file-add 候选可为空对象；有接入口的给 import/register 片段 */
  barrel_snippet: { import?: string; register?: string };
  /** 候选根目录绝对路径，用于解析 files[].path */
  dir: string;
}

/** 加载某 candidates 根目录下所有候选，返回 seamId -> ref -> meta。 */
export function loadCandidates(candidatesRoot: string): Map<string, Map<string, CandidateMeta>> {
  const bySeam = new Map<string, Map<string, CandidateMeta>>();
  if (!existsSync(candidatesRoot)) return bySeam;

  for (const seamDir of readdirSync(candidatesRoot, { withFileTypes: true })) {
    if (!seamDir.isDirectory()) continue;
    const seamPath = join(candidatesRoot, seamDir.name);
    for (const candDir of readdirSync(seamPath, { withFileTypes: true })) {
      if (!candDir.isDirectory()) continue;
      const metaPath = join(seamPath, candDir.name, "meta.json");
      if (!existsSync(metaPath)) continue;

      const raw = JSON.parse(readFileSync(metaPath, "utf-8"));
      const meta: CandidateMeta = {
        registry_item: RegistryItem.parse(raw.registry_item),
        l0: L0Candidate.parse(raw.l0),
        l1: L1Signature.parse(raw.l1),
        barrel_snippet: raw.barrel_snippet ?? {},
        dir: join(seamPath, candDir.name),
      };
      const ref = meta.l0.ref;
      if (!bySeam.has(seamDir.name)) bySeam.set(seamDir.name, new Map());
      bySeam.get(seamDir.name)!.set(ref, meta);
    }
  }
  return bySeam;
}

/** 把候选清单铺平成 L0 列表（喂给选择引擎用）。 */
export function allL0(bySeam: Map<string, Map<string, CandidateMeta>>): L0Candidate[] {
  const out: L0Candidate[] = [];
  for (const refs of bySeam.values()) {
    for (const meta of refs.values()) out.push(meta.l0);
  }
  return out;
}
