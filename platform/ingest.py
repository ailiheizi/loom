"""Ingestion 管线（loom.ingest）—— M4：把真实 TS 源自动切成候选入池。

核心命题（M4 完成判定）：候选池规模增长 → WRITE_OWN 退化率下降。
本管线用 tree-sitter 解析 TS 源、抽取 export 符号签名，自动生成候选 meta.json
（registry_item + l0 摘要 + l1 签名 + barrel_snippet + sha256 内容寻址），落进 candidates/。

当前最小真实版（一轮可做完可测）：
  - 单语言 TS/TSX（tree-sitter-typescript）
  - 抽 export function / export const（组件/工厂/纯函数）签名
  - 内容寻址用 sha256
诚实推迟到 M4+：多语言、Merkle 增量、Qdrant 规模化入库、SCIP 调用链。
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

ROOT = Path(__file__).resolve().parent.parent
_TSX = Language(tsts.language_tsx())


@dataclass
class ExportSig:
    name: str
    kind: str  # function | const | component
    signature: str


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def extract_exports(src: str) -> list[ExportSig]:
    """tree-sitter 抽 export 的 function/const 符号 + 一行签名。"""
    parser = Parser(_TSX)
    data = src.encode("utf-8")
    tree = parser.parse(data)
    out: list[ExportSig] = []

    def text(node) -> str:
        return data[node.start_byte : node.end_byte].decode("utf-8", "replace")

    def first_line(node) -> str:
        s = text(node).split("\n", 1)[0].strip().rstrip("{").strip()
        return s[:160]

    def visit(node):
        if node.type == "export_statement":
            for ch in node.children:
                if ch.type == "function_declaration":
                    name = next((text(c) for c in ch.children if c.type == "identifier"), "?")
                    # 大写开头视作 React 组件
                    kind = "component" if name[:1].isupper() else "function"
                    out.append(ExportSig(name, kind, first_line(ch)))
                elif ch.type == "lexical_declaration":
                    for vd in ch.children:
                        if vd.type == "variable_declarator":
                            name = next((text(c) for c in vd.children if c.type == "identifier"), "?")
                            kind = "component" if name[:1].isupper() else "const"
                            out.append(ExportSig(name, kind, first_line(ch)))
        for c in node.children:
            visit(c)

    visit(tree.root_node)
    return out


# seam → barrel 接入口配置（与 loom.core.json 对齐；file-add seam 无 barrel）
SEAM_BARREL = {
    "auth.oauth_provider": ("import", "register_array"),  # providers[] array-append
    "data.crud_resource": ("import", "register_obj"),  # appRouter{} object-key
}


def ingest_file(
    src_path: Path,
    seam_id: str,
    ref: str,
    summary: str,
    target: str,
    candidates_root: Path,
    deps: list[str] | None = None,
    env_vars: list[str] | None = None,
    requires_prisma_model: str | None = None,
) -> Path:
    """把一个 TS 源文件 ingest 成候选，写进 candidates/<seam>/<ref>/。返回 meta.json 路径。"""
    src = src_path.read_text(encoding="utf-8")
    exports = extract_exports(src)
    deps = deps or []
    env_vars = env_vars or []

    cand_dir = candidates_root / seam_id / ref
    (cand_dir / "files").mkdir(parents=True, exist_ok=True)
    file_name = Path(target).name
    (cand_dir / "files" / file_name).write_text(src, encoding="utf-8")

    meta_loom = {
        "seam_id": seam_id,
        "interface_sig": exports[0].signature if exports else "",
        "provenance": "platform",
        "health": 0.7,  # ingested 初始健康度低于手工策展(0.85)，被复用后升
        "content_hash": _sha256(src),
        "license": "MIT",
        "ext_pkgs": [],
    }
    if requires_prisma_model:
        meta_loom["requires_prisma_model"] = requires_prisma_model

    barrel_snippet: dict = {}
    if seam_id in SEAM_BARREL:
        mod = "~/" + target.replace("src/", "").replace(".tsx", "").replace(".ts", "")
        exp = exports[0].name if exports else ref
        barrel_snippet["import"] = f'import {{ {exp} }} from "{mod}";'
        _, reg_kind = SEAM_BARREL[seam_id]
        leaf = seam_id.split(".")[-1]
        barrel_snippet["register"] = f"{exp}," if reg_kind == "register_array" else f"{leaf}: {exp},"

    meta = {
        "registry_item": {
            "name": ref,
            "type": "registry:lib",
            "title": ref,
            "description": summary,
            "dependencies": [],
            "registry_dependencies": [],
            "files": [{"path": f"files/{file_name}", "type": "registry:lib", "target": target, "hash": None}],
            "css_vars": {},
            "env_vars": {e: "" for e in env_vars},
            "meta_loom": meta_loom,
        },
        "l0": {
            "ref": ref,
            "seam_id": seam_id,
            "summary": summary,
            "deps": deps,
            "loc": len(src.splitlines()),
            "health": 0.7,
            "provenance": "platform",
            "content_hash": _sha256(src),
        },
        "l1": {
            "ref": ref,
            "content_hash": _sha256(src),
            "exports": [{"name": e.name, "signature": e.signature, "kind": e.kind} for e in exports],
            "types": [],
            "imports": [],
        },
        "barrel_snippet": barrel_snippet,
    }
    meta_path = cand_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta_path


if __name__ == "__main__":
    # 自检：解析一个内联 TS 源
    sample = "export function MarkdownView({ source }: { source: string }) { return null; }\nexport const helper = (x: string) => x;"
    for e in extract_exports(sample):
        print(f"  {e.kind:10} {e.name:20} {e.signature}")
