"""T9 双臂对照 + h* 计算。

读 .work/metrics-assembly.json 与 .work/metrics-from_zero.json，
用 loom_contracts.compute_h_star 算 h*（缺基准则 pending，不填 0），
写 .work/compare-<idea_id>.json + 打印一行双臂对照。

用法：cd platform && python run_compare.py
"""

from __future__ import annotations

import json
from pathlib import Path

import loom_contracts as c

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".work"


def _load(name: str) -> c.AssemblyMetrics | None:
    p = WORK / name
    if not p.exists():
        return None
    return c.AssemblyMetrics.model_validate_json(p.read_text(encoding="utf-8"))


def main() -> None:
    assembly = _load("metrics-assembly.json")
    from_zero = _load("metrics-from_zero.json")

    if assembly is None:
        print("缺 metrics-assembly.json —— 先跑 t9_runner --arm assembly")
        return

    report = c.compute_h_star(assembly, from_zero)

    out = WORK / f"compare-{assembly.idea_id}.json"
    out.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    print("=== T9 双臂对照 ===")
    print(f"idea={assembly.idea_id}")
    print(
        f"assembly : equiv_cost={assembly.equiv_cost:.1f} "
        f"(in={assembly.total_input_tok} out={assembly.total_output_tok} "
        f"disclosure={assembly.disclosure_input_tok} ΔRepair={assembly.delta_repair_input}) "
        f"converged={assembly.converged} write_own={assembly.write_own_ratio}"
    )
    if from_zero is not None:
        print(
            f"from_zero: equiv_cost={from_zero.equiv_cost:.1f} "
            f"(in={from_zero.total_input_tok} out={from_zero.total_output_tok}) "
            f"converged={from_zero.converged} G={from_zero.total_output_tok}"
        )
    else:
        print("from_zero: (缺) —— 跑 t9_runner --arm from_zero 以获得 h* 基准")

    print("-" * 60)
    if report.h_star is not None:
        verdict = "组装更省(注意 B1：mock 单向压低，非充分证据)" if report.h_star < 1 else "★ h*>1 稳健 Kill 信号"
        print(f"h* = {report.h_star:.4f}  [{report.status}]  → {verdict}")
    else:
        print(f"h* = pending  [{report.status}]  （决策2：缺基准不填0）")
    print(f"写入 {out}")
    print("\n诚实边界：h*<1 不证真实省 token（所有 mock 单向压低）；只有 h*>1 是稳健 Kill。")


if __name__ == "__main__":
    main()
