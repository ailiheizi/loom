"""seam 自动推断（evolution-design P2）：用 embedding 相似度自动匹配最近的 seam。

用户不再需要手写 seam_id——传入代码或描述文本,返回最匹配的 seam_id。
用 retrieve.py 同一个 EmbeddingProvider（StubEmbedder 或 fastembed）保持一致性。

用法：
  from infer_seam import infer_seam
  seam_id, confidence = infer_seam("Google OAuth 登录 provider")
  # → ("auth.oauth_provider", 0.82)
"""

from __future__ import annotations

import json
from pathlib import Path

from embedding import EmbeddingProvider, get_embedder

ROOT = Path(__file__).resolve().parent.parent
CORE_PATH = ROOT / "core" / "loom.core.json"

# 缓存 seam 向量（进程级，只算一次）
_SEAM_INDEX: list[tuple[str, str, list[float]]] | None = None
_EMBEDDER: EmbeddingProvider | None = None

MIN_CONFIDENCE = 0.35  # 低于此阈值认为 embedding 没匹配上,退化到关键词

# 关键词→seam 映射(中英文,embedding 对中文无力时兜底)
_KEYWORD_MAP: list[tuple[list[str], str]] = [
    (["oauth", "登录", "login", "auth", "provider", "nextauth", "credential", "magic-link"], "auth.oauth_provider"),
    (["crud", "router", "增删改查", "资源", "create", "update", "delete", "trpc"], "data.crud_resource"),
    (["table", "表格", "列表", "data-table", "datagrid"], "ui.data_table"),
    (["form", "表单", "输入", "编辑", "创建", "录入"], "ui.form"),
    (["layout", "布局", "导航", "sidebar", "topbar", "nav"], "ui.layout"),
    (["detail", "详情", "卡片", "card"], "ui.detail"),
    (["export", "导出", "csv", "xlsx", "blob", "download", "报表"], "report.custom_export"),
    (["import", "导入", "批量", "upload csv", "parse", "批量导入"], "data.bulk_import"),
    (["upload", "上传", "文件", "presigned", "s3", "oss"], "file.upload"),
    (["markdown", "渲染", "render", "md"], "content.markdown_render"),
]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _get_index() -> tuple[list[tuple[str, str, list[float]]], EmbeddingProvider]:
    """延迟构建 seam 签名向量索引。"""
    global _SEAM_INDEX, _EMBEDDER
    if _SEAM_INDEX is not None and _EMBEDDER is not None:
        return _SEAM_INDEX, _EMBEDDER

    core = json.loads(CORE_PATH.read_text(encoding="utf-8"))
    embedder = get_embedder()

    # 每个 seam 用 "seam_id | kind | signature" 作为可搜索文本
    texts: list[str] = []
    entries: list[tuple[str, str]] = []
    for s in core["seams"]:
        doc = f"{s['seam_id']} | {s.get('kind','')} | {s.get('signature','')}"
        texts.append(doc)
        entries.append((s["seam_id"], doc))

    vecs = embedder.embed(texts)
    _SEAM_INDEX = [(sid, doc, vec) for (sid, doc), vec in zip(entries, vecs)]
    _EMBEDDER = embedder
    return _SEAM_INDEX, _EMBEDDER


def _keyword_match(text: str) -> tuple[str, float]:
    """关键词兜底：对中文/短文本 embedding 无力时用。返回 (seam_id, 匹配度 0~1)。"""
    t = text.lower()
    best_id = ""
    best_count = 0
    for keywords, sid in _KEYWORD_MAP:
        count = sum(1 for kw in keywords if kw in t)
        if count > best_count:
            best_count = count
            best_id = sid
    # 匹配度 = 命中关键词数 / 该 seam 关键词总数(归一化)
    if best_id:
        total = next(len(kws) for kws, sid in _KEYWORD_MAP if sid == best_id)
        return (best_id, min(1.0, best_count / max(total * 0.4, 1)))
    return ("", 0.0)


def infer_seam(text: str) -> tuple[str, float]:
    """推断文本（代码片段/描述/文件内容前 500 字符）最匹配的 seam。

    策略：先试 embedding 相似度；confidence < MIN_CONFIDENCE 时退化到关键词匹配。
    返回 (seam_id, confidence)。confidence 0 表示完全没匹配上。
    """
    index, embedder = _get_index()
    qvec = embedder.embed_one(text[:800])

    best_id = ""
    best_sim = -1.0
    for sid, _, svec in index:
        sim = _cosine(qvec, svec)
        if sim > best_sim:
            best_sim = sim
            best_id = sid

    if best_sim >= MIN_CONFIDENCE:
        return (best_id, best_sim)

    # embedding 没匹配上 → 退化到关键词
    return _keyword_match(text)


def infer_seam_top_k(text: str, k: int = 3) -> list[tuple[str, float]]:
    """返回 top-k 最匹配的 seam（给用户看选项）。"""
    index, embedder = _get_index()
    qvec = embedder.embed_one(text[:800])
    scored = [(sid, _cosine(qvec, svec)) for sid, _, svec in index]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]
