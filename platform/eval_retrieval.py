"""M3 检索召回率离线评测（不依赖 AI 调用，绕开网关）。

M3 完成判定 = "离线召回率达标"。这里对每个 (想法, capability_intent) 标注
"正确应召回的候选 ref"（ground truth），跑检索器看 top-k 是否命中，算 recall@k + MRR。

ground truth 标注原则：覆盖该 seam 的候选里，语义最贴合 intent 的那个为正例。
未覆盖能力（无候选的 seam）不计入召回（它本就该走 generate）。

用法：cd platform && uv run python eval_retrieval.py
真 embedding 渠道到位后（LOOM_EMBED_PROVIDER=api）重跑即得真值召回率。
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from load_candidates import load_candidates
from retrieve import Retriever
import json

ROOT = Path(__file__).resolve().parent.parent

# ground truth：(idea, seam, intent关键词, 期望召回的候选ref)
# 标注依据：该 seam 下语义最贴合 intent 的候选。
GOLD = [
    ("saas-admin", "auth.oauth_provider", "用户能用 Google 账号 OAuth 登录", "google-oauth"),
    ("saas-admin", "data.crud_resource", "对 Project 资源做增删改查", "project-crud-router"),
    ("saas-admin", "ui.data_table", "用数据表格展示 Project 列表", "simple-data-table"),
    ("task-tracker", "auth.oauth_provider", "用户能用 GitHub 账号 OAuth 登录", "github-oauth"),
    ("task-tracker", "data.crud_resource", "对 Task 资源做增删改查（标题=name，详情=description）", "project-crud-router"),
    ("task-tracker", "ui.data_table", "用数据表格展示 Task 列表", "simple-data-table"),
    ("contact-book", "auth.oauth_provider", "用户能用 Google 账号 OAuth 登录", "google-oauth"),
    ("contact-book", "data.crud_resource", "对 Contact 资源做增删改查", "project-crud-router"),
    ("contact-book", "ui.data_table", "用数据表格展示 Contact 列表", "simple-data-table"),
]


def main(top_k: int = 3) -> None:
    by_seam = load_candidates(ROOT / "candidates")
    core = json.loads((ROOT / "core" / "loom.core.json").read_text(encoding="utf-8"))
    seam_sig = {s["seam_id"]: s.get("signature", "") for s in core["seams"]}
    retriever = Retriever(by_seam)

    hit_at_1 = 0
    hit_at_k = 0
    mrr = 0.0
    n = len(GOLD)

    print(f"=== M3 检索召回率评测 (top_k={top_k}, provider={type(retriever.embedder).__name__}) ===\n")
    for idea, seam, intent, gold_ref in GOLD:
        q = f"{seam_sig.get(seam, '')} | {intent}"
        hits = retriever.retrieve(seam, q, top_k=top_k)
        ranked = [h.ref for h in hits]
        rank = ranked.index(gold_ref) + 1 if gold_ref in ranked else 0
        at1 = rank == 1
        atk = rank >= 1
        hit_at_1 += at1
        hit_at_k += atk
        mrr += (1.0 / rank) if rank else 0.0
        mark = "✓1" if at1 else ("✓k" if atk else "✗ ")
        print(f"  [{mark}] {idea:13} {seam:22} → gold={gold_ref:20} 召回={ranked} rank={rank or '未命中'}")

    print(f"\n  recall@1 = {hit_at_1}/{n} = {hit_at_1/n:.2%}")
    print(f"  recall@{top_k} = {hit_at_k}/{n} = {hit_at_k/n:.2%}")
    print(f"  MRR      = {mrr/n:.3f}")
    print(f"\n  注：当前 provider={type(retriever.embedder).__name__}。")
    if type(retriever.embedder).__name__ == "StubEmbedder":
        print("  StubEmbedder 是词袋伪向量（验证机制），真语义召回率待 LOOM_EMBED_PROVIDER=api 渠道到位。")
        print("  M3 完成判定（离线召回率达标）须用真 embedding 重跑本评测确认。")


if __name__ == "__main__":
    main()
