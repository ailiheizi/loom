from __future__ import annotations

import json
import sys
from pathlib import Path

from load_candidates import load_candidates
import loom_contracts as c
from retrieve import Retriever

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CANDIDATES_ROOT = ROOT / "candidates"
CORE_PATH = ROOT / "core" / "loom.core.json"
WORK_DIR = ROOT / ".work"


def _load_idea(idea_path: Path) -> dict:
    return json.loads(idea_path.read_text(encoding="utf-8"))


def _load_seam_signatures() -> dict[str, str]:
    core = json.loads(CORE_PATH.read_text(encoding="utf-8"))
    return {seam["seam_id"]: seam.get("signature", "") for seam in core.get("seams", [])}


def _tradeoffs_for(candidate) -> str:
    raw = json.loads((candidate.dir / "meta.json").read_text(encoding="utf-8"))
    return raw.get("registry_item", {}).get("meta_loom", {}).get("tradeoffs", "") or ""


def _build_candidate_lookup(by_seam: dict[str, list]) -> dict[tuple[str, str], object]:
    lookup: dict[tuple[str, str], object] = {}
    for seam_id, candidates in by_seam.items():
        for candidate in candidates:
            lookup[(seam_id, candidate.ref)] = candidate
    return lookup


# 长驻进程（MCP server）缓存：候选池 + Retriever（含 fastembed 模型）只建一次。
# 首次构建会加载 ONNX 模型（慢），缓存后后续调用快——避免 MCP 工具首调超时。
_RETRIEVER_CACHE: dict | None = None


def _get_retriever_bundle() -> tuple[dict, dict, Retriever]:
    global _RETRIEVER_CACHE
    if _RETRIEVER_CACHE is None:
        by_seam = load_candidates(CANDIDATES_ROOT)
        _RETRIEVER_CACHE = {
            "by_seam": by_seam,
            "lookup": _build_candidate_lookup(by_seam),
            "retriever": Retriever(by_seam),
        }
    c2 = _RETRIEVER_CACHE
    return c2["by_seam"], c2["lookup"], c2["retriever"]


def warmup() -> None:
    """预热：在 MCP server 启动时调用，把 fastembed 模型加载移到启动期。"""
    _get_retriever_bundle()


def propose(idea_path: Path) -> c.GradientProposal:
    idea = _load_idea(idea_path)
    seam_signatures = _load_seam_signatures()
    by_seam, candidate_lookup, retriever = _get_retriever_bundle()

    seams: list[c.SeamProposal] = []
    for capability in idea.get("capability_intents", []):
        seam_id = capability["seam_id"]
        intent = capability["intent"]
        query_text = f"{seam_signatures.get(seam_id, '')} | {intent}"
        hits = sorted(retriever.retrieve(seam_id, query_text, top_k=3), key=lambda hit: hit.score, reverse=True)

        candidates: list[c.CandidateProposal] = []
        for index, hit in enumerate(hits):
            candidate = candidate_lookup.get((seam_id, hit.ref))
            deps = list(candidate.l0.deps) if candidate is not None else []
            provenance = candidate.l0.provenance if candidate is not None else c.Provenance.PLATFORM
            tradeoffs = _tradeoffs_for(candidate) if candidate is not None else ""
            candidates.append(
                c.CandidateProposal(
                    ref=hit.ref,
                    summary=hit.summary,
                    deps=deps,
                    health=hit.health,
                    provenance=provenance,
                    score=hit.score,
                    tradeoffs=tradeoffs,
                    recommended=index == 0,
                )
            )

        seams.append(
            c.SeamProposal(
                seam_id=seam_id,
                intent=intent,
                candidates=candidates,
                needs_generate=not candidates,
            )
        )

    proposal = c.GradientProposal(
        idea_id=idea["idea_id"],
        core_ref=idea["core_ref"],
        seams=seams,
    )

    WORK_DIR.mkdir(exist_ok=True)
    output_path = WORK_DIR / f"proposal-{proposal.idea_id}.json"
    output_path.write_text(
        json.dumps(proposal.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"=== 候选梯度提案：{proposal.idea_id} ===")
    print(f"core_ref: {proposal.core_ref}")
    print(f"输出文件: {output_path}")
    print()
    for seam in proposal.seams:
        print(f"- seam: {seam.seam_id}")
        print(f"  intent: {seam.intent}")
        if seam.needs_generate:
            print("  candidates: 0")
            print("  needs_generate: True")
            print()
            continue
        print(f"  candidates: {len(seam.candidates)}")
        for candidate in seam.candidates:
            mark = "[recommended]" if candidate.recommended else "            "
            print(
                f"  {mark} {candidate.ref} | score={candidate.score:.4f} | "
                f"health={candidate.health:.2f} | deps={len(candidate.deps)}"
            )
            print(f"             {candidate.summary}")
            if candidate.tradeoffs:
                print(f"             tradeoffs: {candidate.tradeoffs}")
        print()

    return proposal


def main() -> None:
    if len(sys.argv) != 2:
        print("用法: uv run python propose.py <idea.json>")
        raise SystemExit(1)
    propose(Path(sys.argv[1]).resolve())


if __name__ == "__main__":
    main()
