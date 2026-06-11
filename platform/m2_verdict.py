"""M2 GO/Kill 判定器。

读 .work/metrics-<arm>-<idea>.json（arm ∈ assembly/oracle/from_zero），对每想法算 5 个 GO
子条件 + 2×2 归因建议，输出"想法×臂×6指标"表 + 每想法 GO/NO-GO + 总结论。
复用 loom_contracts.compute_h_star，无新数学。

用法：cd platform && uv run python m2_verdict.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows 终端默认 GBK，强制 stdout UTF-8 避免中文/符号编码崩溃
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import loom_contracts as c

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / ".work"

IDEAS = [
    "saas-admin-with-google-auth",
    "task-tracker-with-github-auth",
    "contact-book-with-google-auth",
]
ARMS = ["assembly", "oracle", "from_zero"]


def load(arm: str, idea: str) -> c.AssemblyMetrics | None:
    p = WORK / f"metrics-{arm}-{idea}.json"
    if not p.exists():
        return None
    return c.AssemblyMetrics.model_validate_json(p.read_text(encoding="utf-8"))


def fmt(m: c.AssemblyMetrics | None) -> str:
    if m is None:
        return "（缺）"
    return (
        f"cost={m.equiv_cost:.0f} conv={'Y' if m.converged else 'N'} "
        f"err={m.final_error_count} wown={m.write_own_ratio:.2f} "
        f"fixdiff={m.fix_diff_lines} ΔR={m.delta_repair_input}"
    )


def attribute(asm, ora, fz) -> str:
    """2×2 归因建议（plan 原文铁律）。

    判断顺序：oracle 明确失败的信号最强（core-fit/物化），优先于 from_zero 缺失，
    避免"from_zero 没数据"盖过"oracle 人工最优 plan 都不收敛"这个更强的诊断。
    """
    # oracle 跑了但不收敛 → 最强信号：连人工最优 plan 都不通 = core-fit/物化问题
    if ora is not None and not ora.converged:
        return "core-fit/物化问题：连 oracle 人工最优 plan 都不收敛 → 物化层/生成接缝有结构问题（如 generate seam 的 import 约定/语法震荡），非选择层"
    # oracle 收敛、AI 组装不收敛 → 选择/披露层
    if ora is not None and ora.converged and (asm is None or not asm.converged):
        return "选择/披露层问题：oracle 组装能跑、AI 组装不能 → 选择引擎或披露层的问题，非组装机制"
    # from_zero 缺失或未跑通（且 oracle 没有明确失败）→ harness 嫌疑
    if fz is None or not fz.converged:
        return "harness/实现 bug 嫌疑：从零臂未跑通——先证 harness 能让从零臂收敛再谈赌注（注意从零臂收敛有 LLM 非确定性）"
    if asm is not None and asm.converged:
        return "组装机制健康：三臂都收敛，可比较成本/退化"
    return "数据不全，无法归因"


def go_subconditions(asm, fz):
    """5 个 GO 子条件。返回 (dict, all_pass)。h*<1 标注'非充分'。"""
    subs = {}
    if asm is None:
        return {"组装臂缺失": False}, False
    # 1 成本 < 从零
    subs["成本<从零"] = (fz is not None and asm.equiv_cost < fz.equiv_cost)
    # 2 fix-diff < 从零
    a_fd = asm.fix_diff_lines if asm.fix_diff_lines is not None else 0
    f_fd = fz.fix_diff_lines if (fz and fz.fix_diff_lines is not None) else None
    subs["fixdiff<从零"] = (f_fd is not None and a_fd < f_fd)
    # 3 h*<1（非充分，仅必要）
    rep = c.compute_h_star(asm, fz)
    subs["h*<1(非充分)"] = (rep.h_star is not None and rep.h_star < 1.0)
    # 4 WRITE_OWN < 40%
    subs["WRITE_OWN<40%"] = (asm.write_own_ratio < 0.40)
    # 5 3 轮收敛
    subs["3轮内收敛"] = (asm.converged and len(asm.rounds) <= 4)
    all_pass = all(subs.values())
    return subs, all_pass


def main() -> None:
    print("=" * 70)
    print("M2 判定：想法 × 臂 × 6指标")
    print("=" * 70)

    verdicts = {}
    for idea in IDEAS:
        asm, ora, fz = load("assembly", idea), load("oracle", idea), load("from_zero", idea)
        print(f"\n## {idea}")
        print(f"  assembly : {fmt(asm)}")
        print(f"  oracle   : {fmt(ora)}")
        print(f"  from_zero: {fmt(fz)}")
        subs, go = go_subconditions(asm, fz)
        print("  GO 子条件:")
        for k, v in subs.items():
            print(f"    [{'OK ' if v else 'XX '}] {k}")
        print(f"  → {'GO' if go else 'NO-GO'}（本想法）")
        print(f"  归因: {attribute(asm, ora, fz)}")
        verdicts[idea] = go

    print("\n" + "=" * 70)
    print("M2 总结论")
    print("=" * 70)
    n_go = sum(1 for v in verdicts.values() if v)
    print(f"  {n_go}/{len(IDEAS)} 想法满足全部 GO 子条件")
    print("\n  诚实边界（不可自欺）：")
    print("  - h*<1 是必要非充分：所有 mock（L0全量喂/手挑小池/无缓存/ΔRepair来自策展）单向压低 h*，")
    print("    只有 h*>1 是稳健 Kill；h*<1 不证真实省 token，待 M3 真检索证。")
    print("  - WRITE_OWN：故意造未覆盖想法暴露退化，但手工小池退化率本就偏高，真实决定因素推迟 M4。")
    print("  - 从零臂收敛有 LLM 非确定性（同 prompt 可能这次通下次不通）；3 想法小样本非统计显著。")
    print("  - '能跑'=能启动非功能可用（缺页面装配接缝 + 占位 OAuth）。")
    print("  - 故 M2 结论是'机制是否成立'的方向判断，非量化置信。命中任一 Kill 子条件应停工程回设计。")


if __name__ == "__main__":
    main()
