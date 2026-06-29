"""一次性：把 candidates/ 全部候选导出成 seed_data.json（打进包，首次运行迁移进 ~/.loom）。

用法：cd platform && uv run python gen_seed.py
产出：platform/loom_seed/seed_data.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from load_candidates import load_candidates

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES = ROOT / "candidates"
OUT_DIR = Path(__file__).resolve().parent / "loom_seed"
OUT = OUT_DIR / "seed_data.json"


def main() -> None:
    by_seam = load_candidates(CANDIDATES)
    seeds = []
    for seam_id, cands in by_seam.items():
        for cand in cands:
            # 读候选文件内容(可能多文件,取第一个主文件)
            files = cand.l2_files()
            if not files:
                continue
            main_file = files[0]
            ml = cand.registry_item.meta_loom
            raw = json.loads((cand.dir / "meta.json").read_text(encoding="utf-8"))
            ml_raw = raw.get("registry_item", {}).get("meta_loom", {})
            seeds.append({
                "ref": cand.ref,
                "seam_id": seam_id,
                "summary": cand.l0.summary,
                "target": main_file.path,
                "file_content": main_file.content,
                "deps": list(cand.l0.deps or []),
                "env_vars": list(cand.registry_item.env_vars.keys()) if cand.registry_item.env_vars else [],
                "tradeoffs": ml_raw.get("tradeoffs", ""),
                "barrel_snippet": cand.barrel_snippet,
                "requires_prisma_model": ml_raw.get("requires_prisma_model"),
            })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(seeds, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"导出 {len(seeds)} 个候选 → {OUT.relative_to(ROOT)}")
    # 按 seam 统计
    from collections import Counter
    c = Counter(s["seam_id"] for s in seeds)
    for sid, n in sorted(c.items()):
        print(f"  {sid}: {n}")


if __name__ == "__main__":
    main()
