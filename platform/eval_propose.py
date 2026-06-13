from __future__ import annotations

import sys
from pathlib import Path

from propose import propose

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
IDEA_PATH = ROOT / "ideas" / "saas-admin-with-google-auth.json"


def main() -> None:
    try:
        proposal = propose(IDEA_PATH)

        for seam in proposal.seams:
            if seam.candidates:
                assert len(seam.candidates) >= 2, f"{seam.seam_id} 候选不足 2 个"
                scores = [candidate.score for candidate in seam.candidates]
                assert scores == sorted(scores, reverse=True), f"{seam.seam_id} 候选未按 score 降序"
                recommended = [candidate for candidate in seam.candidates if candidate.recommended]
                assert len(recommended) == 1, f"{seam.seam_id} recommended 数量不是 1"
                assert recommended[0].score == max(scores), f"{seam.seam_id} recommended 不是最高分"
            else:
                assert seam.needs_generate, f"{seam.seam_id} 无候选时 needs_generate 应为 True"

        export_seam = next((seam for seam in proposal.seams if seam.seam_id == "report.custom_export"), None)
        assert export_seam is not None, "缺少 report.custom_export seam"
        assert len(export_seam.candidates) >= 2, "report.custom_export 应召回多个候选"

        print("=== eval_propose 通过 ===")
        for seam in proposal.seams:
            recommended_ref = next((candidate.ref for candidate in seam.candidates if candidate.recommended), "<none>")
            print(f"- {seam.seam_id}: 候选 {len(seam.candidates)} 个, recommended={recommended_ref}")
    except AssertionError as exc:
        print("=== eval_propose 失败 ===")
        print(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
