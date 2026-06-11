"""候选加载器（Python 侧）：读 candidates/<seam>/<候选>/meta.json + files/。

与 client/src/loadCandidates.ts 同约定，供选择引擎使用。
"""

from __future__ import annotations

import json
from pathlib import Path

import loom_contracts as c


class Candidate:
    """一个候选的完整投影：L0/L1/RegistryItem + L2 文件全文（按需读）。"""

    def __init__(self, meta_path: Path):
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
        self.dir = meta_path.parent
        self.registry_item = c.RegistryItem.model_validate(raw["registry_item"])
        self.l0 = c.L0Candidate.model_validate(raw["l0"])
        self.l1 = c.L1Signature.model_validate(raw["l1"])
        self.barrel_snippet: dict = raw.get("barrel_snippet", {})

    @property
    def ref(self) -> str:
        return self.l0.ref

    @property
    def seam_id(self) -> str:
        return self.l0.seam_id

    def l2_files(self) -> list[c.L2File]:
        """读出候选所有源码文件全文（L2 层，最贵，按需调用）。"""
        out: list[c.L2File] = []
        for f in self.registry_item.files:
            src = self.dir / f.path
            out.append(c.L2File(path=f.target, content=src.read_text(encoding="utf-8")))
        return out


def load_candidates(candidates_root: Path) -> dict[str, list[Candidate]]:
    """加载所有候选，返回 seam_id -> [Candidate]。"""
    by_seam: dict[str, list[Candidate]] = {}
    if not candidates_root.exists():
        return by_seam
    for seam_dir in sorted(candidates_root.iterdir()):
        if not seam_dir.is_dir():
            continue
        for cand_dir in sorted(seam_dir.iterdir()):
            meta = cand_dir / "meta.json"
            if not meta.exists():
                continue
            cand = Candidate(meta)
            by_seam.setdefault(cand.seam_id, []).append(cand)
    return by_seam


def find_candidate(by_seam: dict[str, list[Candidate]], seam_id: str, ref: str) -> Candidate | None:
    for cand in by_seam.get(seam_id, []):
        if cand.ref == ref:
            return cand
    return None
