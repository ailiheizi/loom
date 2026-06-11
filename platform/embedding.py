"""可插拔 embedding provider（M3 真检索地基）。

设计：embedding 是 M3 的硬前置，但当前网关 code.ppchat.vip 无 embedding 通道
（voyage-code-3 / text-embedding-3-small 均 no available channels）。
故抽象成 provider 接口，先用 StubEmbedder 跑通检索链路与机制，待真渠道到位换 ApiEmbedder。

provider 由环境变量选择：
  LOOM_EMBED_PROVIDER = stub（默认）| api
  LOOM_EMBED_BASE_URL / LOOM_EMBED_API_KEY / LOOM_EMBED_MODEL（api 时用）
"""

from __future__ import annotations

import hashlib
import math
import os
from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """把文本编码成定长向量。"""

    dim: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量编码，返回每条文本的向量（已 L2 归一化）。"""
        ...

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class StubEmbedder(EmbeddingProvider):
    """确定性伪向量：用 token 的 hash 散布到固定维度的词袋。

    不是语义 embedding，但**确定可复现**、零依赖、零网络，足以跑通检索排序链路、
    验证"召回→喂子集→选择"机制是否成立。真语义质量待 ApiEmbedder。
    相同词汇重叠的文本会得到较高余弦相似——对"意图摘要 vs seam 签名"这种共享术语
    的匹配有基本判别力（如 'OAuth provider' 同时出现在候选 summary 和 auth seam）。
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _tokenize(self, text: str) -> list[str]:
        # 粗分词：小写 + 非字母数字切分，保留中英文 token
        out: list[str] = []
        cur = ""
        for ch in text.lower():
            if ch.isalnum():
                cur += ch
            else:
                if cur:
                    out.append(cur)
                cur = ""
        if cur:
            out.append(cur)
        return out

    def embed(self, texts: list[str]) -> list[list[float]]:
        vecs: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in self._tokenize(text):
                h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
                idx = h % self.dim
                sign = 1.0 if (h >> 8) & 1 else -1.0
                vec[idx] += sign
            vecs.append(_l2_normalize(vec))
        return vecs


class FastEmbedEmbedder(EmbeddingProvider):
    """本地离线语义 embedding（fastembed，ONNX/CPU，零网络零 key）。

    默认 BAAI/bge-small-en-v1.5（384 维，CPU 友好）。首次用会下载模型权重到本地缓存，
    之后完全离线、确定可复现。通用文本模型——意图摘要是自然语言，足够；
    代码语义专精待 ApiEmbedder(voyage-code-3)，换 provider 仅需环境变量。
    """

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5") -> None:
        from fastembed import TextEmbedding

        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)
        # 探测维度
        probe = next(iter(self._model.embed(["probe"])))
        self.dim = len(probe)

    def embed(self, texts: list[str]) -> list[list[float]]:
        # fastembed 返回 numpy 向量（已近似归一化），仍统一 L2 归一化保证点积=余弦
        return [_l2_normalize([float(x) for x in v]) for v in self._model.embed(texts)]


class ApiEmbedder(EmbeddingProvider):
    """走 OpenAI 兼容 /v1/embeddings 端点的真 embedding。

    待网关或外部渠道提供可用 embedding 模型后启用：
      LOOM_EMBED_PROVIDER=api
      LOOM_EMBED_BASE_URL=https://...  LOOM_EMBED_API_KEY=sk-...  LOOM_EMBED_MODEL=voyage-code-3
    """

    def __init__(self, base_url: str, api_key: str, model: str, dim: int = 1024) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        import urllib.request
        import json as _json

        req = urllib.request.Request(
            f"{self.base_url}/v1/embeddings",
            data=_json.dumps({"model": self.model, "input": texts}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = _json.loads(resp.read().decode("utf-8"))
        # OpenAI 兼容格式：data[].embedding，按 index 排序
        items = sorted(payload["data"], key=lambda d: d["index"])
        return [_l2_normalize(it["embedding"]) for it in items]


def get_embedder() -> EmbeddingProvider:
    """按环境变量选 provider。默认 fastembed（本地语义），stub（无依赖兜底），api（真渠道）。

    LOOM_EMBED_PROVIDER = fastembed（默认）| stub | api
    """
    provider = os.environ.get("LOOM_EMBED_PROVIDER", "fastembed").lower()
    if provider == "api":
        base = os.environ.get("LOOM_EMBED_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL", "")
        key = os.environ.get("LOOM_EMBED_API_KEY") or os.environ.get("ANTHROPIC_API_KEY", "")
        model = os.environ.get("LOOM_EMBED_MODEL", "voyage-code-3")
        if not base or not key:
            raise RuntimeError("LOOM_EMBED_PROVIDER=api 但缺 LOOM_EMBED_BASE_URL / LOOM_EMBED_API_KEY")
        return ApiEmbedder(base, key, model)
    if provider == "stub":
        return StubEmbedder()
    try:
        return FastEmbedEmbedder()
    except Exception as e:  # fastembed 不可用时兜底到 stub，不让检索链路崩
        print(f"[embedding] fastembed 不可用（{e}），回退 StubEmbedder")
        return StubEmbedder()
