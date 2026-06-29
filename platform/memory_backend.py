"""Loom ↔ memory-engine 集成层（B路线：memory-engine 为唯一真相）。

把 memory-engine 的 FactStore 适配成 Loom 的候选检索/入库/信任后端。
候选 = fact，text 用于检索，metadata 存完整候选数据（文件内容/seam/target/deps 等）。

对外暴露：
  MemoryBackend.retrieve(seam_id, query, top_k) → 候选列表
  MemoryBackend.ingest(src_content, seam_id, ref, summary, target, ...) → fact_id
  MemoryBackend.reinforce(ref) → 信任升
  MemoryBackend.get_candidate(ref) → 候选完整数据(含文件内容)

依赖 memory-engine 作为 Python 包（sys.path 注入或 pip install -e）。
"""

from __future__ import annotations

import sys
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# memory-engine 的路径（相对于 Loom 项目根）
MEMORY_ENGINE_PATH = Path(__file__).resolve().parent.parent.parent / "research" / "memory" / "memory-engine"

# 确保 memory-engine 可 import
if str(MEMORY_ENGINE_PATH) not in sys.path:
    sys.path.insert(0, str(MEMORY_ENGINE_PATH))

from memory_engine.fact_store import FactStore

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORE_DIR = str(ROOT / ".work" / "loom-memory")


def _patch_factstore_with_fastembed(store: FactStore) -> None:
    """用 Loom 已有的 fastembed(本地 ONNX,零网络下载)替换 FactStore 的 sentence-transformers。

    这样 memory-engine 的信任+矛盾检测+持久化逻辑全复用,只把 embedding 换成本地的。
    """
    import numpy as np
    try:
        from fastembed import TextEmbedding
        model = TextEmbedding("BAAI/bge-small-en-v1.5")
    except Exception:
        # fastembed 不可用(网络问题等)→ 用 StubEmbedder 兜底
        from embedding import get_embedder
        embedder = get_embedder()
        # 模拟 fastembed 的 encode 接口
        class _Stub:
            def encode(self, texts, normalize_embeddings=True):
                return [embedder.embed_one(t) for t in texts]
            @property
            def dim(self):
                return embedder.dim
        model = _Stub()

    def _ensure_model(self):
        if self._model is None:
            self._model = model
            # fastembed 的 bge-small 维度 384；stub 是 256
            self._dim = 384 if hasattr(model, 'encode') and not hasattr(model, 'dim') else getattr(model, 'dim', 384)
    store._ensure_model = lambda: _ensure_model(store)

    def _rebuild_index(self):
        import faiss
        self._ensure_model()
        if not self.facts:
            self._index = None
            return
        texts = [f["text"] for f in self.facts]
        if hasattr(self._model, 'encode'):
            vecs = self._model.encode(texts, normalize_embeddings=True)
            if isinstance(vecs, list):
                vecs = np.array(vecs, dtype=np.float32)
            elif not isinstance(vecs, np.ndarray):
                vecs = np.array(list(vecs), dtype=np.float32)
        else:
            vecs = np.array(self._model.encode(texts), dtype=np.float32)
        if vecs.ndim == 1:
            vecs = vecs.reshape(1, -1)
        self._dim = vecs.shape[1]
        self._index = faiss.IndexFlatIP(self._dim)
        # L2 归一化(fastembed 已归一化,但 stub 可能没有)
        faiss.normalize_L2(vecs)
        self._index.add(vecs)
    store._rebuild_index = lambda: _rebuild_index(store)


class MemoryBackend:
    """Loom 的 memory-engine 后端。所有候选存在 FactStore 里。"""

    def __init__(self, store_dir: str = DEFAULT_STORE_DIR, embed_model: str = "BAAI/bge-small-en-v1.5"):
        self.store = FactStore(store_dir, embed_model=embed_model)
        # 用本地 fastembed/stub 替换 sentence-transformers(避免 HuggingFace 下载)
        _patch_factstore_with_fastembed(self.store)

    def _make_text(self, summary: str, seam_id: str, ref: str, exports: list[str] | None = None) -> str:
        """构造可检索的 fact text（summary + seam + ref + 导出签名）。"""
        parts = [summary, f"seam:{seam_id}", f"ref:{ref}"]
        if exports:
            parts.append("exports:" + " ".join(exports[:3]))
        return " | ".join(parts)

    def ingest(
        self,
        src_content: str,
        seam_id: str,
        ref: str,
        summary: str,
        target: str,
        deps: list[str] | None = None,
        env_vars: list[str] | None = None,
        tradeoffs: str = "",
        barrel_snippet: dict | None = None,
        requires_prisma_model: str | None = None,
    ) -> dict:
        """入库一个候选到 memory-engine。返回 {fact_id, ref, seam_id, status}。"""
        text = self._make_text(summary, seam_id, ref)
        metadata = {
            "ref": ref,
            "seam_id": seam_id,
            "target": target,
            "file_content": src_content,
            "summary": summary,
            "deps": deps or [],
            "env_vars": env_vars or [],
            "tradeoffs": tradeoffs,
            "barrel_snippet": barrel_snippet or {},
            "requires_prisma_model": requires_prisma_model,
        }
        fact_id = self.store.add(text, metadata=metadata)
        return {"fact_id": fact_id, "ref": ref, "seam_id": seam_id, "status": "ingested"}

    def retrieve(self, seam_id: str, query: str, top_k: int = 3) -> list[dict]:
        """检索某 seam 下最匹配的候选。返回 [{ref, summary, score, trust, metadata...}]。

        用 memory-engine 的语义检索 + 信任加权，然后按 seam_id 过滤（硬过滤）。
        """
        # 多取一些再按 seam 过滤（memory-engine 没有 seam 概念）
        results = self.store.retrieve(f"seam:{seam_id} | {query}", top_k=top_k * 5)
        hits = []
        for r in results:
            meta = r.get("metadata", {})
            if meta.get("seam_id") != seam_id:
                continue
            hits.append({
                "ref": meta.get("ref", "?"),
                "summary": meta.get("summary", ""),
                "score": r.get("final", r.get("score", 0)),
                "trust": r.get("eff_trust", r.get("trust", 0.5)),
                "health": r.get("trust", 0.5),  # 映射 trust → health
                "deps": meta.get("deps", []),
                "tradeoffs": meta.get("tradeoffs", ""),
                "target": meta.get("target", ""),
                "file_content": meta.get("file_content", ""),
                "barrel_snippet": meta.get("barrel_snippet", {}),
                "env_vars": meta.get("env_vars", []),
                "requires_prisma_model": meta.get("requires_prisma_model"),
                "fact_id": r.get("id"),
            })
            if len(hits) >= top_k:
                break
        return hits

    def get_candidate(self, ref: str) -> Optional[dict]:
        """按 ref 查找候选完整数据。遍历 facts（小规模可接受）。"""
        for f in self.store.facts:
            meta = f.get("metadata", {})
            if meta.get("ref") == ref:
                return meta
        return None

    def reinforce(self, ref: str) -> bool:
        """候选被复用 → 信任升。按 ref 找到 fact_id 后调 reinforce。"""
        for f in self.store.facts:
            if f.get("metadata", {}).get("ref") == ref:
                return self.store.reinforce(f["id"])
        return False

    def list_candidates(self, seam_id: str | None = None) -> list[dict]:
        """列出所有候选（或某 seam 的）。"""
        results = []
        for f in self.store.facts:
            meta = f.get("metadata", {})
            if seam_id and meta.get("seam_id") != seam_id:
                continue
            results.append({
                "ref": meta.get("ref", "?"),
                "seam_id": meta.get("seam_id", "?"),
                "summary": meta.get("summary", ""),
                "trust": f.get("trust", 0.5),
                "uses": f.get("uses", 0),
            })
        return results

    @property
    def count(self) -> int:
        return len(self.store.facts)

    def bootstrap_from_seed(self, seed_path: Optional[Path] = None) -> int:
        """首次运行：若库为空，从 seed_data.json 导入内置候选。返回导入数。

        seed_data.json 打进包（platform/loom_seed/），首次跑 loom-mcp 时把 39 个
        基础候选迁进用户的 ~/.loom FactStore。之后用户 ingest 的新组件也存这。
        """
        if self.count > 0:
            return 0  # 已有数据，不重复 bootstrap
        if seed_path is None:
            seed_path = Path(__file__).resolve().parent / "loom_seed" / "seed_data.json"
        if not seed_path.exists():
            logger.warning(f"seed 数据不存在: {seed_path}")
            return 0
        seeds = json.loads(seed_path.read_text(encoding="utf-8"))
        n = 0
        for s in seeds:
            self.ingest(
                src_content=s["file_content"],
                seam_id=s["seam_id"],
                ref=s["ref"],
                summary=s["summary"],
                target=s["target"],
                deps=s.get("deps"),
                env_vars=s.get("env_vars"),
                tradeoffs=s.get("tradeoffs", ""),
                barrel_snippet=s.get("barrel_snippet"),
                requires_prisma_model=s.get("requires_prisma_model"),
            )
            n += 1
        logger.info(f"bootstrap: 从 seed 导入 {n} 个候选到 {self.store.store_dir}")
        return n


# 单例（MCP server 复用同一个 backend，避免重复加载模型）
_BACKEND: Optional[MemoryBackend] = None


def get_backend() -> MemoryBackend:
    """获取全局 MemoryBackend 单例。store_dir 由 LOOM_STORE_DIR 决定（默认 ~/.loom）。"""
    global _BACKEND
    if _BACKEND is None:
        import os
        store_dir = os.environ.get("LOOM_STORE_DIR", str(Path.home() / ".loom"))
        _BACKEND = MemoryBackend(store_dir=str(Path(store_dir) / "facts"))
        _BACKEND.bootstrap_from_seed()  # 首次自动导入 seed
    return _BACKEND
