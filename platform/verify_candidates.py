"""候选 gate 守门：逐个候选单独物化进 t3-base 跑 gate，报告哪些过不了 t3 严格模式。

教训（2026-06-11）：预制/ingest 的候选若没在 t3 的严格 tsconfig（noUncheckedIndexedAccess 等）
下验证，被 pick 后会触发修复轮、甚至被 AI override 改坏。本工具是预制候选的强制守门：
**候选必须单独过 gate 才算合格入池。**

用法：cd platform && uv run python verify_candidates.py
（gate 在 client 侧 TS，本脚本通过 node tsx 调用）
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "candidates"

# 内联 node 脚本：对每个候选构造单候选 pick plan，跑**完整确定性链**（materialize +
# derivePrismaModels/applyPrismaModels + injectEnv + prisma generate）再 gate。
# 与真实组装流程一致，避免"漏确定性步骤"的假阳性。不跑修复轮（只验候选自身物化后是否干净）。
NODE_SCRIPT = r"""
import {existsSync,rmSync} from 'node:fs';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const root=process.argv[2];
const specs=JSON.parse(process.argv[3]); // [{cand, seam_id, ref, files:[target]}]
const imp=async (p)=>import(pathToFileURL(resolve(root,p)).href);
const {gate}=await imp('client/src/gate.ts');
const {materialize}=await imp('client/src/materialize.ts');
const {injectEnv}=await imp('client/src/injectEnv.ts');
const {derivePrismaModels,applyPrismaModels,runWhitelisted}=await imp('client/src/repair.ts');
const {loadCandidates}=await imp('client/src/loadCandidates.ts');
const {CoreManifest}=await imp('client/src/contracts.ts');
const fs=await import('node:fs');
const core=CoreManifest.parse(JSON.parse(fs.readFileSync(resolve(root,'core/loom.core.json'),'utf-8')));
const candidates=loadCandidates(resolve(root,'candidates'));
const base=resolve(root,'core/t3-base');
const results=[];
for(const s of specs){
  const out=resolve(root,'.work/probe-verify');
  if(existsSync(out)) rmSync(out,{recursive:true,force:true});
  // 单候选 pick plan
  const plan={idea_id:'verify', core_ref:'verify', seams:[{seam_id:s.seam_id, action:'pick', ref:s.ref, content_hash:null, adapter:null, generated_file:null, confidence:1, why:'verify'}], synthesized:[], budget:{input_tok:0,output_tok:0}};
  try{
    const mat=materialize({plan,candidates,coreSeams:core.seams,baseDir:base,outDir:out});
    applyPrismaModels(out, derivePrismaModels(plan,candidates));
    injectEnv(out, mat.envVars);
    runWhitelisted(out,{kind:'prisma-generate'});
    const g=gate(out);
    const keys=s.files.map(t=>t.split('/').pop().replace(/\.tsx?$/,''));
    const errs=g.diagnostics.filter(d=>keys.some(k=>d.file.includes(k)));
    results.push({cand:s.cand, err:errs.length, detail:errs.slice(0,3).map(d=>'L'+d.line+' TS'+d.code)});
  }catch(e){
    results.push({cand:s.cand, err:-1, detail:[String(e).slice(0,60)]});
  }
}
console.log(JSON.stringify(results));
"""


def main() -> None:
    specs = []
    for seam_dir in sorted(CANDIDATES.iterdir()):
        if not seam_dir.is_dir():
            continue
        for cand_dir in sorted(seam_dir.iterdir()):
            meta_p = cand_dir / "meta.json"
            if not meta_p.exists():
                continue
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            files = [f["target"] for f in meta["registry_item"]["files"]]
            specs.append({
                "cand": f"{seam_dir.name}/{cand_dir.name}",
                "seam_id": seam_dir.name,
                "ref": meta["l0"]["ref"],
                "files": files,
            })

    script_path = ROOT / ".work" / "_verify_node.mjs"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(NODE_SCRIPT, encoding="utf-8")

    tsx = ROOT / "client" / "node_modules" / "tsx" / "dist" / "cli.mjs"
    proc = subprocess.run(
        ["node", str(tsx), str(script_path), str(ROOT), json.dumps(specs)],
        capture_output=True, text=True, cwd=str(ROOT / "client"),
    )
    out_lines = [l for l in proc.stdout.splitlines() if l.strip().startswith("[")]
    if not out_lines:
        print("✗ gate 验证未返回结果:", proc.stderr[-300:])
        return
    results = json.loads(out_lines[-1])

    print("=== 候选 gate 守门（单独物化进 t3 严格模式）===\n")
    ok = bad = 0
    for r in results:
        if r["err"] == 0:
            print(f"  [✓] {r['cand']}")
            ok += 1
        else:
            print(f"  [✗] {r['cand']}  err={r['err']}  {' '.join(r['detail'])}")
            bad += 1
    print(f"\n  {ok}/{ok+bad} 候选过 t3 gate。{'全部合格 ✓' if bad==0 else f'⚠ {bad} 个需修'}")


if __name__ == "__main__":
    main()
