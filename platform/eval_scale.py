"""规模化测试：候选池放大到 N∈{50,100,200,500} 时，检索/飞轮还灵吗？

回答 workflow 警告的两个规模问题：
1. 召回截断 bug：retrieve 用 top_k*5 全局召回再按 seam 过滤。大池下全局 top(k*5)
   可能不含目标 seam 的候选 → 召回率塌。
2. 飞轮在大池下还能翻盘吗？(小池易翻盘可能只是池浅的假象)

实测结论(2026-06-30, stub)：
- 召回截断 bug 实际不发作：retrieve 查询带 "seam:xxx |" 前缀，候选 text 也存
  "seam:xxx"，seam 名成强匹配信号 → 同 seam 候选天然聚在召回窗口顶部。
  1040 候选下精确查询仍命中 #1，过滤后稳定返回满 top_k。
- 飞轮大池下照样翻盘：40~200/seam(总库240~1040) reinforce 8 次 #30→#1。
- ⚠️ 真实规模化瓶颈在写入侧：fact_store.add 每次都 _rebuild_index()，fastembed 下
  批量 ingest N 条 = O(n²) 次 encode，500 条会卡死(stub 快无此问题)。真实用户
  "写完一个 ingest 一个"不触发；批量导入场景需批量建索引(bootstrap 已这么做)。

跑：cd platform && PYTHONIOENCODING=utf-8 LOOM_EMBED_PROVIDER=stub uv run python eval_scale.py
"""
from __future__ import annotations
import os, sys, shutil, tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("LOOM_EMBED_PROVIDER", "stub")

from memory_backend import MemoryBackend

SEAM = "ui.data_table"
# 一批同 seam 的合成候选描述(语义都相关，但各有侧重——模拟真实大库里同类组件多)
VARIANTS = [
    "data table with {f}",
]
FEATURES = ["sorting", "pagination", "filtering", "row selection", "column resize",
            "sticky header", "csv export", "inline edit", "virtual scroll", "grouping",
            "expandable rows", "fixed columns", "cell merge", "drag reorder", "tree view",
            "search box", "bulk actions", "context menu", "keyboard nav", "dark mode"]


def build_pool(n_per_seam: int):
    """造一个有 n_per_seam 个 ui.data_table 候选的库，返回 backend + 注入的目标 ref。"""
    tmp = tempfile.mkdtemp(prefix=f"loom_scale_{n_per_seam}_")
    os.environ["LOOM_STORE_DIR"] = tmp
    mb = MemoryBackend(store_dir=tmp + "/facts")
    mb.bootstrap_from_seed()  # 先有 39 真种子
    # 批量造合成候选(多个 seam 都造，让全局池真的大)
    seams = ["ui.data_table", "ui.form", "data.crud_resource", "auth.oauth_provider", "ui.layout"]
    for s in seams:
        for i in range(n_per_seam):
            feat = FEATURES[i % len(FEATURES)]
            mb.ingest(src_content=f"export function Gen{s}{i}(){{}}",
                      seam_id=s, ref=f"gen-{s}-{i}",
                      summary=f"{s} component variant {i} with {feat}",
                      target=f"src/gen/{s}/{i}.tsx")
    # 注入一个独特目标候选(用罕见词，便于精确查询)
    mb.ingest(src_content="export function ZebraQuux(){}", seam_id=SEAM,
              ref="zebra-quux-target", summary="zebra quux flux capacitor data table",
              target="src/gen/target.tsx")
    return mb, tmp


def main():
    print("规模化：候选池放大后，目标候选还能被召回吗？飞轮还能翻盘吗？")
    print(f"{'每seam候选':>10} | {'总库':>6} | {'精确查询召回':>14} | {'reinforce8次翻盘':>16}")
    print("-" * 64)
    for n in [10, 40, 100, 200]:
        mb, tmp = build_pool(n)
        total = mb.count
        # 1. 精确查询：用目标的罕见词，看大池下还能否召回
        hits = mb.retrieve(SEAM, "zebra quux flux capacitor", top_k=5)
        refs = [h["ref"] for h in hits]
        recalled = "zebra-quux-target" in refs
        rank = refs.index("zebra-quux-target") + 1 if recalled else -1
        # 2. 飞轮：取一个靠后的合成候选 reinforce 8 次看翻盘
        base = mb.retrieve(SEAM, "data table sorting", top_k=30)
        brefs = [h["ref"] for h in base]
        target = brefs[-1] if brefs else None
        flip = "N/A"
        if target:
            r0 = len(brefs)
            for _ in range(8):
                mb.reinforce(target, success=True)
            after = [h["ref"] for h in mb.retrieve(SEAM, "data table sorting", top_k=30)]
            r1 = after.index(target) + 1 if target in after else -1
            flip = f"#{r0}→#{r1}" if r1 > 0 else f"#{r0}→掉出top30"
        rec_str = f"{'命中#'+str(rank) if recalled else '✗未召回'}"
        print(f"{n:>10} | {total:>6} | {rec_str:>14} | {flip:>16}")
        shutil.rmtree(tmp, ignore_errors=True)
    os.environ.pop("LOOM_STORE_DIR", None)
    print("\n关注：'未召回'出现=召回截断 bug 发作(top_k*5 全局召回不含目标 seam)。")


if __name__ == "__main__":
    main()
