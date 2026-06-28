"""检索排序（loom.retrieve）—— M3 真检索，替换 run_select 的"L0 全量喂"mock。

按 architecture-v2 步骤 2 的混合排序，对每个 (seam, capability) 排候选：
  ① 接口契合度（最强）：seam_id 必须匹配——硬过滤，非该 seam 的候选直接排除。
  ② 向量相似（显式降权）：候选意图摘要 vs (seam签名 + capability意图) 的余弦。
     docs 实证：相似度会引噪声，故只作 seam 内的次级排序信号，不跨 seam。
  ③ 依赖可满足性：候选 deps 越少越优（M1 简化：deps 空=满分）。
  ④ 健康度：l0.health。

输出每个 seam 的 top-k 候选。无候选的 seam → 空（selection 对它走 generate）。
"""

from __future__ import annotations

from dataclasses import dataclass

from embedding import EmbeddingProvider, get_embedder
from load_candidates import Candidate


def _cosine(a: list[float], b: list[float]) -> float:
    # 两侧已 L2 归一化，点积即余弦
    return sum(x * y for x, y in zip(a, b))


def _candidate_doc(cand: Candidate) -> str:
    """候选的可向量化文本：意图摘要 + 导出签名（语义检索的输入）。"""
    exports = " ".join(e.name for e in cand.l1.exports)
    return f"{cand.l0.summary} | exports: {exports} | seam: {cand.seam_id}"


@dataclass
class RetrievalHit:
    ref: str
    seam_id: str
    score: float
    vector_sim: float
    dep_penalty: float
    health: float
    summary: str


# 混合排序权重：接口契合度已是硬过滤，剩余信号里向量相似显式降权（docs：相似引噪声）
W_VECTOR = 0.4
W_DEP = 0.15
W_HEALTH = 0.25
W_TRUST = 0.2  # 信任加权：越用越靠前（flywheel.trust_score）


class Retriever:
    def __init__(self, by_seam: dict[str, list[Candidate]], embedder: EmbeddingProvider | None = None):
        self.by_seam = by_seam
        self.embedder = embedder or get_embedder()
        # 预先编码所有候选 doc（建索引）
        self._index: dict[str, list[tuple[Candidate, list[float]]]] = {}
        for seam_id, cands in by_seam.items():
            if not cands:
                continue
            vecs = self.embedder.embed([_candidate_doc(c) for c in cands])
            self._index[seam_id] = list(zip(cands, vecs))

    def retrieve(self, seam_id: str, query_text: str, top_k: int = 3) -> list[RetrievalHit]:
        """对某 seam + 查询文本（seam 签名 + capability 意图）召回 top-k 候选。"""
        entries = self._index.get(seam_id, [])
        if not entries:
            return []  # 无候选 → selection 对该 seam 走 generate
        qvec = self.embedder.embed_one(query_text)
        hits: list[RetrievalHit] = []
        for cand, cvec in entries:
            vsim = _cosine(qvec, cvec)
            n_deps = len(cand.l0.deps or [])
            dep_penalty = 1.0 / (1.0 + n_deps)  # deps 越少越接近 1
            health = cand.l0.health or 0.0
            # 信任分：从 meta_loom 取（飞轮 record_reuse 写入），兜底 0.5
            trust = getattr(cand.registry_item.meta_loom, "trust_score", None)
            if trust is None:
                # pydantic 可能 strip 了未定义字段，回退读原始 JSON
                try:
                    import json
                    raw = json.loads((cand.dir / "meta.json").read_text(encoding="utf-8"))
                    trust = float(raw.get("registry_item", {}).get("meta_loom", {}).get("trust_score", 0.5))
                except Exception:
                    trust = 0.5
            score = W_VECTOR * vsim + W_DEP * dep_penalty + W_HEALTH * health + W_TRUST * float(trust)
            hits.append(
                RetrievalHit(
                    ref=cand.ref, seam_id=seam_id, score=score, vector_sim=vsim,
                    dep_penalty=dep_penalty, health=health, summary=cand.l0.summary,
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]
