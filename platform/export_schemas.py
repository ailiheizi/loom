"""导出所有契约模型的 JSON Schema 到 ../schema/，供 TS 侧 zod 对拍。

用法：python export_schemas.py
"""

from __future__ import annotations

import json
from pathlib import Path

import loom_contracts as c

# 顶层模型 → 输出文件名
MODELS = {
    "core-manifest": c.CoreManifest,
    "registry-item": c.RegistryItem,
    "l0-candidate": c.L0Candidate,
    "l1-signature": c.L1Signature,
    "l2-fulltext": c.L2FullText,
    "assembly-plan": c.AssemblyPlan,
    "manifest": c.Manifest,
    "lockfile": c.Lockfile,
    "diagnostic": c.Diagnostic,
    "assembly-metrics": c.AssemblyMetrics,
}


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "schema"
    out_dir.mkdir(exist_ok=True)
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        (out_dir / f"{name}.schema.json").write_text(
            json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  wrote schema/{name}.schema.json")
    print(f"导出 {len(MODELS)} 个 schema 到 {out_dir}")


if __name__ == "__main__":
    main()
