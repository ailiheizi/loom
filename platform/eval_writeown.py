"""M4 完成判定评测：候选池规模增长 → WRITE_OWN 退化率下降。

WRITE_OWN 退化率 = 想法的 capability_intent 里，检索召回不到任何候选（只能 generate）的比例。
池小（M1：6候选/3seam）时，markdown/csv/export 等 seam 无候选 → 必须 generate → WRITE_OWN 高。
池增长（M4 ingest 后：9候选/6seam）后，这些 seam 有了候选 → 可 pick → WRITE_OWN 降。

不依赖 AI / 网关：直接用检索器判定每个 intent 能否召回到候选。
用法：cd platform && uv run python eval_writeown.py
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
IDEAS = [
    "saas-admin-with-google-auth",
    "task-tracker-with-github-auth",
    "contact-book-with-google-auth",
]
# M1 原始池只有这 3 个 seam 有候选；其余 seam 在 M4 ingest 后才有
M1_COVERED_SEAMS = {"auth.oauth_provider", "data.crud_resource", "ui.data_table"}


def write_own_for_idea(idea_id: str, retriever: Retriever, seam_sig: dict, simulate_m1: bool) -> tuple[int, int]:
    """返回 (generate 数, 总 intent 数)。simulate_m1=True 时把 M4 新增 seam 当作无候选。"""
    idea = json.loads((ROOT / "ideas" / f"{idea_id}.json").read_text(encoding="utf-8"))
    gen = 0
    total = 0
    for ci in idea["capability_intents"]:
        sid = ci["seam_id"]
        total += 1
        if simulate_m1 and sid not in M1_COVERED_SEAMS:
            gen += 1  # M1 池：该 seam 无候选 → generate
            continue
        q = f"{seam_sig.get(sid, '')} | {ci['intent']}"
        hits = retriever.retrieve(sid, q, top_k=3)
        if not hits:
            gen += 1  # 召回不到 → generate
    return gen, total


def main() -> None:
    by_seam = load_candidates(ROOT / "candidates")
    core = json.loads((ROOT / "core" / "loom.core.json").read_text(encoding="utf-8"))
    seam_sig = {s["seam_id"]: s.get("signature", "") for s in core["seams"]}
    retriever = Retriever(by_seam)

    pool_size = sum(len(v) for v in by_seam.values())
    print(f"=== M4 WRITE_OWN 退化率评测 ===")
    print(f"当前候选池: {pool_size} 候选 / {len(by_seam)} seam (provider={type(retriever.embedder).__name__})\n")

    for label, sim_m1 in [("M1 原始池 (6候选/3seam)", True), ("M4 扩池后 (9候选/6seam)", False)]:
        tot_gen, tot_all = 0, 0
        print(f"## {label}")
        for idea_id in IDEAS:
            gen, total = write_own_for_idea(idea_id, retriever, seam_sig, sim_m1)
            tot_gen += gen
            tot_all += total
            print(f"  {idea_id:32} WRITE_OWN = {gen}/{total} = {gen/total:.0%}")
        print(f"  → 总 WRITE_OWN 退化率 = {tot_gen}/{tot_all} = {tot_gen/tot_all:.1%}\n")

    print("M4 完成判定：池从 6→9 候选（3→6 seam 覆盖）后，WRITE_OWN 退化率应显著下降。")
    print("（不依赖 AI/网关；ingest 来的候选 provenance=ingested 健康度 0.7，被复用后可升级。）")


if __name__ == "__main__":
    main()
