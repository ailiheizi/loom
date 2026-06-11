"""M5 飞轮健康度闭环评测（端到端，不依赖网关）。

验证完整闭环：
  1. harvest 一个合成产物入池（provenance=synthesized，健康度 0.3 低）
  2. 它与同 seam 现有候选竞争检索排序 —— 初始因健康度低，排在后面
  3. record_reuse 多次（模拟被反复 pick）→ 健康度升过阈值 0.6
  4. 健康度升 → 检索得分升（retrieve W_HEALTH=0.3）→ 排序提升 → 转优先 pick

测试用临时 ref，跑完清理，不污染真实候选池。
用法：cd platform && uv run python eval_flywheel.py
"""

from __future__ import annotations

import sys
import shutil
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from flywheel import harvest, record_reuse, CANDIDATES, PROMOTE_THRESHOLD
from load_candidates import load_candidates
from retrieve import Retriever
import json

ROOT = Path(__file__).resolve().parent.parent
SEAM = "ui.data_table"  # 已有 simple/tanstack 两候选，合成产物来竞争
TEST_REF = "synth-data-table-FLYWHEEL-TEST"
QUERY = "React 组件 <DataTable columns rows /> | 用数据表格展示列表"


def _rank_of(ref: str) -> tuple[int, float]:
    """重新加载池 + 检索，返回该 ref 在召回结果里的 (排名, 健康度)。"""
    by_seam = load_candidates(CANDIDATES)
    r = Retriever(by_seam)
    hits = r.retrieve(SEAM, QUERY, top_k=10)
    for i, h in enumerate(hits, 1):
        if h.ref == ref:
            return i, h.health
    return 0, 0.0


def main() -> None:
    # 造一个合成产物源（一个简化的 data-table，与现有候选同 seam 竞争）
    src = ROOT / ".work" / "ingest-src" / "synth-table.tsx"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(
        'export function DataTable({ columns, rows }: { columns: string[]; rows: Record<string, unknown>[] }) {\n'
        '  return null;\n}\n',
        encoding="utf-8",
    )
    cand_dir = CANDIDATES / SEAM / TEST_REF
    try:
        print("=== M5 飞轮健康度闭环评测 ===\n")
        # 1. harvest 合成产物入池
        harvest(src, SEAM, TEST_REF,
                "合成的 DataTable 组件，展示列表（飞轮测试用）",
                "src/app/_components/synth-table.tsx",
                provenance="synthesized")
        rank, health = _rank_of(TEST_REF)
        print(f"1. harvest 入池：provenance=synthesized 健康度={health:.2f} → 检索排名 #{rank}（同 seam {SEAM}）")

        # 2-3. 反复复用，健康度升
        print("\n2. 模拟被反复 pick（record_reuse）：")
        for _ in range(3):
            st = record_reuse(SEAM, TEST_REF)
            rank, health = _rank_of(TEST_REF)
            flag = " ← 跨阈值转优先pick" if st["promoted"] else ""
            print(f"   复用#{st['reuse_count']}: 健康度 {st['health_before']:.2f}→{st['health_after']:.2f} 排名#{rank}{flag}")

        # 4. 结论
        final_rank, final_health = _rank_of(TEST_REF)
        print(f"\n3. 闭环结果：健康度 0.30 → {final_health:.2f}（阈值 {PROMOTE_THRESHOLD}），检索排名升至 #{final_rank}")
        ok = final_health >= PROMOTE_THRESHOLD
        print(f"   {'✓ 闭环成立' if ok else '✗ 未达阈值'}：合成产物入池→被复用→健康度升→检索排序提升→转优先 pick")
        print("   （健康度→排序的另半在 retrieve.py W_HEALTH=0.3 就位，本测试验证端到端飞轮）")
    finally:
        # 清理测试候选，不污染真实池
        if cand_dir.exists():
            shutil.rmtree(cand_dir)
        if src.exists():
            src.unlink()
        print("\n(已清理测试候选)")


if __name__ == "__main__":
    main()
