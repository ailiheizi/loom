"""验池实验离线指标：pick 可选度（pickable diversity）。

现有 eval_retrieval（recall@k/MRR）和 eval_writeown（退化率）在当前 3 想法上已饱和
（recall@1=100%、WRITE_OWN=0%），测不出"池灌密"的增量——它们只问"能不能召回到 gold"，
不问"召回到几个可选"。本脚本补这个缺口：

  pick 可选度 = 对每个 seam，检索 top_k 实际能召回到的【真实候选数】。
  密前多为 1（只有一个候选，架构师无可挑）；密后应达 top_k（有真实梯度可挑）。

这是 agent-native 愿景"每功能给 2-3 个真实候选让架构师挑"成立与否的直接度量。
零 LLM，离线可复现。

用法：cd platform && uv run python eval_pool_density.py
对照：灌密前后各跑一次，对比每个 seam 的可选度。
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from load_candidates import load_candidates
from retrieve import Retriever

ROOT = Path(__file__).resolve().parent.parent

# 每个 seam 一个代表性查询（取自 saas-admin 想法的 intent），测该 seam 的可选度。
SEAM_QUERIES = [
    ("auth.oauth_provider", "用户能用 Google 账号 OAuth 登录"),
    ("data.crud_resource", "对 Project 资源做增删改查"),
    ("ui.data_table", "用数据表格展示 Project 列表"),
    ("report.custom_export", "把 Project 列表导出"),
    ("content.markdown_render", "渲染 markdown 内容"),
    ("data.bulk_import", "批量导入 CSV 数据"),
]


def main(top_k: int = 5) -> None:
    by_seam = load_candidates(ROOT / "candidates")
    core = json.loads((ROOT / "core" / "loom.core.json").read_text(encoding="utf-8"))
    seam_sig = {s["seam_id"]: s.get("signature", "") for s in core["seams"]}
    retriever = Retriever(by_seam)

    print(f"=== pick 可选度（top_k={top_k}）===")
    print(f"{'seam':<26} {'池内候选':>6} {'召回可选':>6}  候选 refs")
    print("-" * 78)

    total_pool = 0
    total_pickable = 0
    for seam_id, query in SEAM_QUERIES:
        pool_n = len(by_seam.get(seam_id, []))
        q = f"{seam_sig.get(seam_id, '')} | {query}"
        hits = retriever.retrieve(seam_id, q, top_k=top_k)
        refs = [h.ref for h in hits]
        total_pool += pool_n
        total_pickable += len(refs)
        # 可选度 >=2 才算"架构师有得挑"
        flag = "✓挑" if len(refs) >= 2 else "·单"
        print(f"{seam_id:<26} {pool_n:>6} {len(refs):>6}  {flag} {refs}")

    print("-" * 78)
    n_seams = len(SEAM_QUERIES)
    multi = sum(
        1 for sid, q in SEAM_QUERIES
        if len(retriever.retrieve(sid, f"{seam_sig.get(sid,'')} | {q}", top_k=top_k)) >= 2
    )
    print(f"池内候选合计 = {total_pool}")
    print(f"可挑 seam（可选度≥2）= {multi}/{n_seams}")
    print(f"平均可选度 = {total_pickable / n_seams:.2f} 候选/seam")


if __name__ == "__main__":
    main()
