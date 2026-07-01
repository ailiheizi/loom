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
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# memory-engine 的路径（相对于 Loom 项目根）
# FactStore: 优先用 vendored 副本(打包进 loom-mcp),回退 research 仓库(开发时)
try:
    from loom_vendor.fact_store import FactStore
except ImportError:
    MEMORY_ENGINE_PATH = Path(__file__).resolve().parent.parent.parent / "research" / "memory" / "memory-engine"
    if str(MEMORY_ENGINE_PATH) not in sys.path:
        sys.path.insert(0, str(MEMORY_ENGINE_PATH))
    from memory_engine.fact_store import FactStore

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORE_DIR = str(ROOT / ".work" / "loom-memory")

# 检索排序里信任(worth)的权重。越大→飞轮越能让常用候选翻盘，但也越可能压过语义。
# 可用 LOOM_W_TRUST 显式覆盖。未设时按【实际生效的】embedder 自适应(见 __init__)：
#   stub(词袋)：同 seam 候选分差大(~0.22)，需 0.4 才翻盘(#8→#3)
#   fastembed：同 seam 候选分差小(~0.07)，0.2 即翻盘，0.4 过度(一次成功可能霸榜)
_W_TRUST_EXPLICIT = os.environ.get("LOOM_W_TRUST")


def _patch_factstore_with_fastembed(store: FactStore) -> None:
    """用 Loom 已有的 fastembed(本地 ONNX,零网络下载)替换 FactStore 的 sentence-transformers。

    这样 memory-engine 的信任+矛盾检测+持久化逻辑全复用,只把 embedding 换成本地的。
    """
    import numpy as np
    import os
    # 尊重 LOOM_EMBED_PROVIDER：stub 模式直接用词袋(零加载),不碰 fastembed(它要加载 ONNX 模型,慢)
    use_stub = os.environ.get("LOOM_EMBED_PROVIDER", "").lower() == "stub"
    model = None
    kind = "stub"
    model_name = "stub-bow"  # 词袋兜底的标识
    if not use_stub:
        try:
            from fastembed import TextEmbedding
            # 模型选择：LOOM_EMBED_MODEL 可覆盖。默认 multilingual-MiniLM(中英混用最佳)。
            # bge-small-en 只适合纯英文；multilingual 跨语言判别力 0.6+(bge-en 只 0.06)。
            model_name = os.environ.get(
                "LOOM_EMBED_MODEL",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            )
            _fe = TextEmbedding(model_name)
            # fastembed API: .embed() 返回 numpy ndarray 生成器，包装成统一 .encode()
            _dim = len(list(_fe.embed(["dim_probe"]))[0])
            class _FastEmbed:
                def encode(self, texts, normalize_embeddings=True):
                    return list(_fe.embed(list(texts)))
                @property
                def dim(self):
                    return _dim
            model = _FastEmbed()
            kind = "fastembed"
        except Exception:
            model = None
    if model is None:
        # StubEmbedder 兜底(stub 模式 或 fastembed 不可用)
        from embedding import get_embedder
        embedder = get_embedder()
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
            self._dim = model.dim
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
    # 返回实际生效的 embedder 类型 + 模型名(fastembed 加载失败会回退 stub)——
    # 供调用方设 W_TRUST + 检测"库换了模型"(排序会变)，避免按环境变量猜错。
    return kind, model_name


class MemoryBackend:
    """Loom 的 memory-engine 后端。所有候选存在 FactStore 里。"""

    def __init__(self, store_dir: str = DEFAULT_STORE_DIR, embed_model: str = "BAAI/bge-small-en-v1.5"):
        self.store = FactStore(store_dir, embed_model=embed_model)
        # 用本地 fastembed/stub 替换 sentence-transformers(避免 HuggingFace 下载)
        kind, model_name = _patch_factstore_with_fastembed(self.store)
        # 模型指纹检查：库若用别的模型建过，换模型会改变检索排序(向量空间不同)。
        # 不阻断(向量不持久化，会用新模型重建，结果自洽)，但 warn 提示用户结果会变。
        self._check_model_fingerprint(store_dir, model_name)
        # W_TRUST 按【实际生效的】embedder 定(不是按环境变量猜)：显式 LOOM_W_TRUST 优先，
        # 否则 fastembed=0.2 / stub=0.4。fastembed 回退 stub 时 kind 已是 stub，不会配错。
        self._w_trust = float(_W_TRUST_EXPLICIT) if _W_TRUST_EXPLICIT else (
            0.2 if kind == "fastembed" else 0.4
        )
        # 信任评分：用 memory-engine 的 Beta-Bernoulli MemoryWorth(上游官方实现)
        try:
            from loom_vendor.memory_worth import MemoryWorth
        except ImportError:
            from memory_engine.memory_worth import MemoryWorth
        self.worth = MemoryWorth(self.store)

    def _check_model_fingerprint(self, store_dir: str, model_name: str) -> None:
        """记录/校验库是用哪个 embedding 模型建的。换模型会改变检索排序——
        向量不持久化(每次用当前模型重建索引，无旧向量污染)，所以不阻断，但 warn 提示。
        """
        try:
            from pathlib import Path
            fp = Path(store_dir).parent / ".loom_embed_model"
            prev = fp.read_text(encoding="utf-8").strip() if fp.exists() else None
            if prev and prev != model_name:
                logger.warning(
                    f"embedding 模型已从 '{prev}' 换成 '{model_name}'——"
                    f"同一个库的检索排序会变化(语义空间不同)。"
                    f"如需保持旧行为，设 LOOM_EMBED_MODEL={prev}。"
                )
            if prev != model_name:
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(model_name, encoding="utf-8")
        except Exception:
            pass  # 指纹检查是尽力而为，失败不影响主流程

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

    def ingest_batch(self, items: list[dict]) -> int:
        """批量收录候选，只在最后建一次索引（避免逐条 _rebuild_index 的 O(n²)）。

        用于"第一次把现有项目的一批组件导入"场景。fastembed 下尤其关键：逐条
        ingest N 条 = O(n²) 次 encode，批量则 O(n)。每个 item 同 ingest 的参数。
        """
        real_rebuild = self.store._rebuild_index
        self.store._rebuild_index = lambda: None
        n = 0
        try:
            for it in items:
                self.ingest(**it)
                n += 1
        finally:
            self.store._rebuild_index = real_rebuild
        self.store._rebuild_index()  # 一次性建索引
        return n

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
            # 信任分用 Beta-Bernoulli worth(s/f 计数)，融入排序
            worth = self.worth.get_worth(r["id"])
            sim = r.get("score", 0)  # fact_store 的语义相似度
            final = sim + self._w_trust * worth  # 信任加权(按实际 embedder 自适应)
            hits.append({
                "ref": meta.get("ref", "?"),
                "summary": meta.get("summary", ""),
                "score": final,
                "trust": round(worth, 4),
                "health": round(worth, 4),
                "deps": meta.get("deps", []),
                "tradeoffs": meta.get("tradeoffs", ""),
                "target": meta.get("target", ""),
                "file_content": meta.get("file_content", ""),
                "barrel_snippet": meta.get("barrel_snippet", {}),
                "env_vars": meta.get("env_vars", []),
                "requires_prisma_model": meta.get("requires_prisma_model"),
                "fact_id": r.get("id"),
            })
        # 用融合了 worth 的 final 重排
        hits.sort(key=lambda h: h["score"], reverse=True)
        hits = hits[:top_k]
        return hits

    def get_candidate(self, ref: str) -> Optional[dict]:
        """按 ref 查找候选完整数据。遍历 facts（小规模可接受）。"""
        for f in self.store.facts:
            meta = f.get("metadata", {})
            if meta.get("ref") == ref:
                return meta
        return None

    def reinforce(self, ref: str, success: bool = True) -> bool:
        """候选被复用后记录结果 → Beta-Bernoulli 更新信任(MemoryWorth)。

        success=True: 被 pick 且物化收敛(正反馈) → worth 升
        success=False: 被 pick 但物化失败(负反馈) → worth 降
        """
        for f in self.store.facts:
            if f.get("metadata", {}).get("ref") == ref:
                if success:
                    self.worth.record_success(f["id"])
                else:
                    self.worth.record_failure(f["id"])
                return True
        return False

    def get_worth(self, ref: str) -> float:
        """某候选的 Beta-Bernoulli 信任分(worth)。"""
        for f in self.store.facts:
            if f.get("metadata", {}).get("ref") == ref:
                return self.worth.get_worth(f["id"])
        return 0.5

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
            try:
                from _paths import seed_data_path
                seed_path = seed_data_path()
            except ImportError:
                seed_path = Path(__file__).resolve().parent / "loom_seed" / "seed_data.json"
        if not seed_path.exists():
            logger.warning(f"seed 数据不存在: {seed_path}")
            return 0
        seeds = json.loads(seed_path.read_text(encoding="utf-8"))

        # 批量导入(只建一次索引，避免 39 次全量重建的 O(n²))
        items = [{
            "src_content": s["file_content"],
            "seam_id": s["seam_id"],
            "ref": s["ref"],
            "summary": s["summary"],
            "target": s["target"],
            "deps": s.get("deps"),
            "env_vars": s.get("env_vars"),
            "tradeoffs": s.get("tradeoffs", ""),
            "barrel_snippet": s.get("barrel_snippet"),
            "requires_prisma_model": s.get("requires_prisma_model"),
        } for s in seeds]
        n = self.ingest_batch(items)
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
