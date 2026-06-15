"""纯 Python 数据物化（loom_get_files）—— 不跑 Node，把 plan 物化成文件清单。

复刻 client/src/{materialize,injectEnv,repair}.ts 的确定性部分：
  拷 t3-base 内容 → 落候选 files → barrel append（注册进 root.ts/auth config 等）
  → 注入 prisma model（schema.prisma 锚点）→ 注入 env（env.js 两锚点 + .env 占位）

返回 {files:[{path,content}], deps:[{name,version}], env_vars:[...], notes:[...]}。
用户侧 agent 拿到后：写盘 → pnpm install（用 deps）→ 填 .env 真值 → tsc 自验。

不跑 Node、不跑 gate、不碰 node_modules（用户 pnpm install 时生成）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import loom_contracts as c
from load_candidates import load_candidates, find_candidate

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "core" / "t3-base"
CANDIDATES = ROOT / "candidates"

PRISMA_ANCHOR = "// <loom-anchor:prisma-models>"
ENV_SERVER_ANCHOR = "// <loom-anchor:env-server>"
ENV_RUNTIME_ANCHOR = "// <loom-anchor:env-runtime>"

# base 中不纳入返回的目录（用户 pnpm install 自己生成）
SKIP_DIRS = {"node_modules", ".next", ".git", "dist", "build"}


def _prisma_model_body(name: str) -> str:
    return "\n".join([
        f"model {name} {{",
        "    id          String   @id @default(cuid())",
        "    name        String",
        "    description String?",
        "    createdAt   DateTime @default(now())",
        "    updatedAt   DateTime @updatedAt",
        "",
        "    @@index([name])",
        "}",
    ])


def _insert_before_anchor(content: str, anchor: str, snippet: str) -> str:
    """在锚点行前插入 snippet（幂等：snippet 已存在则不动）。复刻 appendAtAnchor。"""
    if snippet.strip() in content:
        return content
    idx = content.find(anchor)
    if idx == -1:
        return content  # 无锚点，跳过
    line_start = content.rfind("\n", 0, idx) + 1
    indent = content[line_start:idx]
    insertion = f"{indent}{snippet.strip()}\n"
    return content[:line_start] + insertion + content[line_start:]


def _read_base_files() -> dict[str, str]:
    """读 t3-base 全部文本文件 → {相对路径: 内容}。跳过依赖/产物目录与二进制。"""
    files: dict[str, str] = {}
    for p in BASE.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(BASE).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        try:
            files["/".join(rel_parts)] = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # 二进制/不可读，跳过
    return files


def get_files(plan: c.AssemblyPlan) -> dict:
    """把 AssemblyPlan 物化成文件清单（纯数据，不跑 Node）。"""
    by_seam = load_candidates(CANDIDATES)
    core = json.loads((ROOT / "core" / "loom.core.json").read_text(encoding="utf-8"))
    seam_specs = {s["seam_id"]: s for s in core["seams"]}

    files = _read_base_files()
    deps: list[dict] = []
    env_vars: list[str] = []
    notes: list[str] = []
    prisma_models: list[str] = []

    for d in plan.seams:
        if d.action == c.SeamAction.SKIP:
            continue
        if d.action == c.SeamAction.GENERATE:
            notes.append(f"seam {d.seam_id}: generate（需宿主 agent 自写 {d.generated_file or '?'}）")
            continue
        if not d.ref:
            continue
        cand = find_candidate(by_seam, d.seam_id, d.ref)
        if cand is None:
            notes.append(f"seam {d.seam_id}: 候选 {d.ref} 未找到")
            continue

        # 1. 落候选文件（registry_item.files 的 src → target）
        for f in cand.registry_item.files:
            src = cand.dir / f.path
            if src.exists():
                files[f.target] = src.read_text(encoding="utf-8")

        # 2. 依赖（ext_pkgs + dependencies）
        for pkg in cand.registry_item.meta_loom.ext_pkgs:
            deps.append({"name": pkg.name, "version": pkg.version})
        for dep in cand.registry_item.dependencies:
            at = dep.rfind("@")
            if at > 0:
                deps.append({"name": dep[:at], "version": dep[at + 1:]})

        # 3. env_vars
        for ev in (cand.registry_item.env_vars or {}):
            if ev not in env_vars:
                env_vars.append(ev)

        # 4. prisma model（直读原始 meta，绕过 zod strip）
        raw = json.loads((cand.dir / "meta.json").read_text(encoding="utf-8"))
        pm = raw.get("registry_item", {}).get("meta_loom", {}).get("requires_prisma_model")
        if isinstance(pm, str) and pm.strip() and pm.strip() not in prisma_models:
            prisma_models.append(pm.strip())

        # 5. barrel append（注册进 root.ts/auth config 等）
        barrel = raw.get("barrel_snippet") or {}
        spec = seam_specs.get(d.seam_id, {})
        bfile = spec.get("barrel", {}).get("file")
        imp = barrel.get("import")
        reg = barrel.get("register")
        anchor_imp = spec.get("barrel", {}).get("anchor_import")
        anchor_reg = spec.get("barrel", {}).get("anchor_register")
        if bfile and bfile in files:
            if imp and anchor_imp:
                files[bfile] = _insert_before_anchor(files[bfile], anchor_imp, imp)
            if reg and anchor_reg:
                files[bfile] = _insert_before_anchor(files[bfile], anchor_reg, reg)

    # 6. prisma model 注入 schema.prisma
    schema_path = "prisma/schema.prisma"
    if prisma_models and schema_path in files:
        for m in prisma_models:
            if f"model {m} " not in files[schema_path]:
                files[schema_path] = _insert_before_anchor(
                    files[schema_path], PRISMA_ANCHOR, _prisma_model_body(m)
                )

    # 7. env 注入 env.js（两锚点）+ .env 占位
    env_js = "src/env.js"
    if env_vars and env_js in files:
        for name in env_vars:
            if re.search(rf"\b{re.escape(name)}\b", files[env_js]):
                continue
            files[env_js] = _insert_before_anchor(files[env_js], ENV_SERVER_ANCHOR, f"{name}: z.string(),")
            files[env_js] = _insert_before_anchor(files[env_js], ENV_RUNTIME_ANCHOR, f"{name}: process.env.{name},")
    if env_vars:
        env_content = files.get(".env", "")
        if "# injected by loom" not in env_content:
            env_content += "\n\n# injected by loom"
        for name in env_vars:
            if f"{name}=" not in env_content:
                env_content += f'\n{name}="loom-dev-placeholder"'
        files[".env"] = env_content

    # 依赖去重
    seen = set()
    uniq_deps = []
    for dep in deps:
        k = dep["name"]
        if k not in seen:
            seen.add(k)
            uniq_deps.append(dep)

    return {
        "idea_id": plan.idea_id,
        "core_ref": plan.core_ref,
        "files": [{"path": p, "content": files[p]} for p in sorted(files)],
        "deps": uniq_deps,
        "env_vars": env_vars,
        "prisma_models": prisma_models,
        "notes": notes,
    }
