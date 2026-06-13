"""从用户选择组装 AssemblyPlan（第三步：对话式选择的落盘层）。

agent-native 流程：propose 给候选梯度 → 宿主 agent 摊给架构师挑 → 选择经此组装成
AssemblyPlan → materialize 物化。本模块是「选择 → plan」这一步，零 LLM、纯确定性。

choices 格式（每个 seam 一条）：
  {"seam_id": "ui.data_table", "action": "pick", "ref": "sortable-data-table"}
  {"seam_id": "report.custom_export", "action": "generate", "generated_file": "src/server/export/xlsx.ts"}
  action 省略时默认 pick（给了 ref）或 skip（没给 ref）。

用法（库）：plan = plan_from_choices(idea_path, choices); 写盘见 CLI。
CLI：uv run python plan_from_choices.py <idea.json> <choices.json> [-o out.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import loom_contracts as c
from load_candidates import load_candidates, find_candidate

ROOT = Path(__file__).resolve().parent.parent
CORE_REF = "create-t3-app@7.39.x"


def plan_from_choices(idea_path: Path, choices: list[dict]) -> c.AssemblyPlan:
    """把用户对每个 seam 的选择组装成 AssemblyPlan。零 LLM。

    校验：pick/adapt 的 ref 必须在候选池里真实存在（防选了不存在的候选）。
    """
    idea = json.loads(idea_path.read_text(encoding="utf-8"))
    idea_id = idea["idea_id"]
    by_seam = load_candidates(ROOT / "candidates")

    # idea 声明的 seam 集合，用于校验 choices 覆盖
    idea_seams = {ci["seam_id"] for ci in idea["capability_intents"]}
    chosen_seams = {ch["seam_id"] for ch in choices}
    missing = idea_seams - chosen_seams
    if missing:
        raise ValueError(f"choices 未覆盖想法的 seam: {sorted(missing)}")

    decisions: list[c.SelectionDecision] = []
    for ch in choices:
        seam_id = ch["seam_id"]
        ref = ch.get("ref")
        # action 推断：显式给 > 有 ref 默认 pick > 无 ref 默认 skip
        action_str = ch.get("action") or ("pick" if ref else "skip")
        action = c.SeamAction(action_str)

        if action in (c.SeamAction.PICK, c.SeamAction.ADAPT):
            if not ref:
                raise ValueError(f"seam {seam_id} 的 {action_str} 必须给 ref")
            # 校验候选真实存在
            cand = find_candidate(by_seam, seam_id, ref)
            if cand is None:
                avail = [c2.ref for c2 in by_seam.get(seam_id, [])]
                raise ValueError(f"seam {seam_id} 无候选 ref={ref}；可选：{avail}")

        decisions.append(
            c.SelectionDecision(
                seam_id=seam_id,
                action=action,
                ref=ref if action in (c.SeamAction.PICK, c.SeamAction.ADAPT) else None,
                adapter=ch.get("adapter"),
                generated_file=ch.get("generated_file") if action == c.SeamAction.GENERATE else None,
                confidence=float(ch.get("confidence", 1.0)),
                why=ch.get("why", "用户选择"),
            )
        )

    return c.AssemblyPlan(
        idea_id=idea_id,
        core_ref=idea.get("core_ref", CORE_REF),
        seams=decisions,
        synthesized=[],
        budget=c.TokenBudget(),  # 用户选择零 LLM，无 token 消耗
    )


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if len(args) < 2:
        print("用法: plan_from_choices.py <idea.json> <choices.json> [-o out.json]")
        sys.exit(1)
    idea_path = Path(args[0]).resolve()
    choices_path = Path(args[1]).resolve()
    choices = json.loads(choices_path.read_text(encoding="utf-8"))
    if isinstance(choices, dict) and "choices" in choices:
        choices = choices["choices"]

    plan = plan_from_choices(idea_path, choices)

    out = None
    if "-o" in sys.argv:
        out = Path(sys.argv[sys.argv.index("-o") + 1]).resolve()
    else:
        out = ROOT / ".work" / f"assembly-plan-{plan.idea_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    print(f"=== AssemblyPlan ({len(plan.seams)} decisions) ===")
    for d in plan.seams:
        print(f"  {d.seam_id}: {d.action.value}" + (f" -> {d.ref}" if d.ref else ""))
    print(f"plan 写入 {out}")


if __name__ == "__main__":
    main()
